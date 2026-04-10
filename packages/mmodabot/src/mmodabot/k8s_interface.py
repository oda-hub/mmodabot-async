import logging
import typing
from kubernetes import client
import base64
import asyncio

logger = logging.getLogger(__name__)

core_v1 = client.CoreV1Api()
batch_v1 = client.BatchV1Api()
app_v1 = client.AppsV1Api()

# NOTE: create it globally as concurrency is set per-instance
class K8SInterface:
    def __init__(self, namespace="default", job_concurrency=3, job_queue_size=100):
        self.job_concurrency = job_concurrency
        self.namespace = namespace

        self.job_queue = asyncio.Queue(maxsize=job_queue_size) # (job_id, manifest)
        self.jobs = {} # job_id: {status, manifest}
        self.cancelled_jobs = set() # job_ids
        self.running_tasks = {} # job_id -> asyncio.Task

    def get_cm(self, name: str, quiet: bool = False) -> client.V1ConfigMap | None:
        try:
            cm = typing.cast(client.V1ConfigMap, core_v1.read_namespaced_config_map(name=name, namespace=self.namespace))
            return cm
        except client.ApiException as e:
            if not quiet:
                logger.error(f"Failed to get ConfigMap '{name}': {e}")
            return None
    
    def read_cm_data(self, name: str):
        cm = core_v1.read_namespaced_config_map(name=name, namespace=self.namespace)
        enc_data = getattr(cm, 'data')

        if enc_data is None:
            enc_data = {}
        # Decode the base64 encoded data
        decoded_data = {}
        for key, value in enc_data.items():
            decoded_data[key] = value

        return decoded_data

    def create_cm(self, name: str, data: dict, raise_if_exists=False):
        try:
            cm = client.V1ConfigMap(
                metadata=client.V1ObjectMeta(name=name),
                data=data
            )
            cm = core_v1.create_namespaced_config_map(namespace=self.namespace, body=cm)
            logger.info(f"ConfigMap '{name}' created successfully.")
            return typing.cast(client.V1ConfigMap, cm)
        except client.ApiException as e:
            logger.error(f"Failed to create ConfigMap '{name}': {e}")
            if e.status == 409 and raise_if_exists:
                raise Exception(f"ConfigMap '{name}' already exists.")

    def update_cm(self, name: str, data: dict):
        try:
            cm = client.V1ConfigMap(
                metadata=client.V1ObjectMeta(name=name),
                data=data
            )
            cm = core_v1.patch_namespaced_config_map(name=name, namespace=self.namespace, body=cm)
            logger.info(f"ConfigMap '{name}' updated successfully.")
            return cm
        except client.ApiException as e:
            logger.error(f"Failed to update ConfigMap '{name}': {e}")

    def delete_cm(self, name: str):
        try:
            core_v1.delete_namespaced_config_map(name=name, namespace=self.namespace)
            logger.info(f"ConfigMap '{name}' deleted successfully.")
        except client.ApiException as e:
            logger.error(f"Failed to delete ConfigMap '{name}': {e}")
    
    def verify_secret(self, secret_name: str):
        try:
            core_v1.read_namespaced_secret(name=secret_name, namespace=self.namespace)
            return True
        except client.ApiException as e:
            if e.status == 404:
                logger.warning(f"Secret '{secret_name}' not found in namespace '{self.namespace}'.")
                return False
            else:
                logger.error(f"Error while verifying secret '{secret_name}': {e}")
                return False

    def read_secret(self, secret_name: str):
        secret = core_v1.read_namespaced_secret(name=secret_name, namespace=self.namespace)
        enc_data = getattr(secret, 'data', {})

        # Decode the base64 encoded data
        decoded_data = {}
        for key, value in enc_data.items():
            decoded_data[key] = base64.b64decode(value).decode('utf-8')

        return decoded_data

    async def run_job(self, job_id: str, job_spec: dict):
        try:
            job = await asyncio.to_thread(
                batch_v1.create_namespaced_job,
                namespace=self.namespace, body=job_spec)
            logger.info(f"Job {job_spec['metadata']['name']} created successfully.")
        except client.ApiException as e:
            if e.status == 409:  # already exists
                logger.warning(f'Old job {job_spec['metadata']['name']} exists. Will recreate.')
                await asyncio.to_thread(
                    batch_v1.delete_namespaced_job,
                    name = job_spec['metadata']['name'],
                    namespace=self.namespace
                )
                await asyncio.sleep(5)
                return await self.run_job(job_id, job_spec)
            
            raise
                
        try:
            while True:
                if job_id in self.cancelled_jobs:
                    raise asyncio.CancelledError()
                
                job = await asyncio.to_thread(
                    batch_v1.read_namespaced_job,
                    job_spec['metadata']['name'],
                    self.namespace
                )

                status = job.status # type: ignore

                if status.succeeded:
                    logger.debug(f"Job {job_spec['metadata']['name']} suceeded")
                    return "succeeded"

                if status.failed:
                    logger.error(f"Job {job_spec['metadata']['name']} failed")
                    return "failed"

                await asyncio.sleep(10)
        
        except asyncio.CancelledError:
            logger.warning(f"run_job received cancel for {job_id}")
            try:
                # it's duplicate call, but 
                await asyncio.to_thread(
                    batch_v1.delete_namespaced_job,
                    name=job_spec['metadata']['name'],
                    namespace=self.namespace,
                    propagation_policy="Foreground"
                )
                logger.info(f"Deleted K8s job {job_spec['metadata']['name']}")
            except Exception as e:
                logger.info(f"(ignore) delete failed: {e}")
            raise

    async def job_worker(self, worker_id: int):
        while True:
            job_id, job_manifest = await self.job_queue.get()
            
            if job_id in self.cancelled_jobs:
                logger.debug(f"[Worker{worker_id}] skipping cancelled job {job_id}")
                self.job_queue.task_done()
                continue

            self.jobs[job_id]["status"] = "running"

            task = asyncio.create_task(self.run_job(job_id, job_manifest))
            self.running_tasks[job_id] = task

            try:
                result = await task
                self.jobs[job_id]["status"] = result

            except asyncio.CancelledError:
                logger.debug(f"[Worker{worker_id}] Job {job_id} cancelled during execution")
                self.jobs[job_id]["status"] = "cancelled"

            except Exception:
                self.jobs[job_id]["status"] = "failed"
                logger.exception(f"[Worker{worker_id}] Error")

            finally:
                self.running_tasks.pop(job_id, None)
                self.job_queue.task_done()

    async def cancel(self, job_id):
        logger.info(f"Cancelling job {job_id}")

        # 1. mark as cancelled for queued jobs
        self.cancelled_jobs.add(job_id)

        job = self.jobs.get(job_id)
        if not job:
            return

        job["status"] = "cancelled"

        # 2. if running then cancel asyncio task
        task = self.running_tasks.get(job_id)
        if task:
            logger.debug(f"Cancelling running task {job_id}")
            task.cancel()

        # we cancel in task, this is duplicate
        # # 3. delete K8s job
        # job_name = job["manifest"]["metadata"]["name"]

        # try:
        #     await asyncio.to_thread(
        #         batch_v1.delete_namespaced_job,
        #         name=job_name,
        #         namespace=self.namespace,
        #         propagation_policy="Foreground"
        #     )
        #     logger.info(f"Deleted K8s job {job_name}")
        # except Exception as e:
        #     logger.info(f"(ignore) delete failed: {e}")

    async def run_job_workers(self):
        self.job_workers = [
            asyncio.create_task(self.job_worker(i))
            for i in range(self.job_concurrency)]

    async def stop_job_workers(self):
        if getattr(self, 'job_workers', None):
            for worker in self.job_workers:
                worker.cancel()
            await asyncio.gather(*self.job_workers, return_exceptions=True)
            self.job_workers = []

        for task in list(self.running_tasks.values()):
            task.cancel()

    def extract_pod_logs(self, job_name: str, tail_lines: int = 500) -> str:
        try:
            label_selector = f"job-name={job_name}"
            pods = core_v1.list_namespaced_pod(namespace=self.namespace, label_selector=label_selector)
            if not pods.items:
                return ""

            pod_name = pods.items[0].metadata.name
            logs = core_v1.read_namespaced_pod_log(
                name=pod_name,
                namespace=self.namespace,
                tail_lines=tail_lines,
                pretty='false'
            )
            return logs
        except Exception:
            logger.exception(f"Failed to extract logs for job {job_name}")
            return ""
        for w in self.job_workers:
            w.cancel()

    async def submit_job(self, job_id, job_manifest):
        self.jobs[job_id] = {
            "status": "queued",
            "manifest": job_manifest,
        }

        await self.job_queue.put((job_id, job_manifest))
        

        