import aiohttp
import asyncio
import gitlab
import logging
from datetime import datetime

from markdown import markdown
from mmodabot.builder import ImageBuilder
from mmodabot.config import Config
from mmodabot.deployer import HelmDeployer
from mmodabot.git_interface import CommitType, GitServerInterface
from mmodabot.k8s_interface import K8SInterface
from mmodabot.mmoda_requirements import RequirementsAnalyser
from mmodabot.notifier import CompositeNotificationHandler, NotificationHandler
from mmodabot.status import BuildStatus, DeploymentStatus, RepoChangeStatus
from mmodabot.utils import convert_help, gitlab_instance_url_from_full_url, repo_id

logger = logging.getLogger()

class NBRepoAdapter:
    def __init__(self,
                 repo_url: str,
                 target_image_base_tmpl: str, # either template with {slug} or just a full string
                 config: Config,
                 k8interface: K8SInterface,
                 gitlab_base: str | None = None,
                 registry_secret_name: str|None = None,
                 git_token_secret_name: str|None = None,
                 git_token_secret_key: str|None = None,
                 notifier: NotificationHandler | None = None
                 ):
        self.repo_url = repo_url # NOTE: with .git suffix (important, used for hash generation)
        if gitlab_base is None:
            gitlab_base = gitlab_instance_url_from_full_url(self.repo_url)
        self.registry_secret_name = registry_secret_name
        self.git_token_secret_name = git_token_secret_name
        self.git_token_secret_key = git_token_secret_key
        self.config = config
        self.repo_id = repo_id(self.repo_url)

        if notifier is None:
            notifier = CompositeNotificationHandler([]) # does nothing, to avoid checking if None
        self.notifier = notifier

        self.k8interface = k8interface

        self.repo_credentials = None
        if self.git_token_secret_name and self.git_token_secret_key:
            self.repo_credentials = self.k8interface.read_secret(
                self.git_token_secret_name)[self.git_token_secret_key]

        self.git_interface = GitServerInterface(
            instance = gitlab_base, 
            token = self.repo_credentials,
            )
        try:
            self.git_interface.preset_project_by_repo_url(self.repo_url)
        except gitlab.GitlabGetError:
            # in a special case of old deployments deletion, we can allow this
            if target_image_base_tmpl == '_FLAG_OLD_DEPLOYMENT_':
                self.project_slug = self.repo_url.replace('.git', '').split('/')[-1]
                self.deployer = HelmDeployer(
                    project_slug=self.project_slug,
                    repo_id=self.repo_id,
                    repo_url=self.repo_url,
                    target_image_base=target_image_base_tmpl,
                    config=self.config,
                    k8interface=self.k8interface
                )
                return
            else:
                raise

        # NOTE: this becomes inconsistent use of the term, but it only controls instrument visibility anyway
        self.creative_work_status = "production" if self.git_interface.visibility_setting() == "public" else "development"
        
        # NOTE: we change behaviour to allow several "messenger" topics
        messengers = []
        for topic in self.git_interface.get_topics():
            if topic.startswith('MM '):
                messengers.append(topic[3:])
        self.messenger = '/'.join(messengers)

        self.project_slug = self.git_interface.get_project_slug()
        self.project_title = self.git_interface.get_project_title()

        self.target_image_base = target_image_base_tmpl.format(slug=self.project_slug)



        self.builder = ImageBuilder(
            repo_url=self.repo_url,
            target_image_base=self.target_image_base,
            config=self.config,
            k8interface=self.k8interface,
            registry_secret_name=self.registry_secret_name,
            git_token_secret_name=self.git_token_secret_name,
            git_token_secret_key=self.git_token_secret_key,
            notifier=self.notifier
        )

        self.deployer = HelmDeployer(
            project_slug=self.project_slug,
            repo_id=self.repo_id,
            repo_url=self.repo_url,
            target_image_base=self.target_image_base,
            config=self.config,
            image_pull_secret=self.registry_secret_name,
            k8interface=self.k8interface,
            notifier=self.notifier
        )

        self.state_store = {}
        # TODO: the store may persist, however, it should be invalidated if bot configuration specific to the repo changes.
        # If not persistent, may send unnecessary notifications on restart (to check which exactly). 



    async def build_mmoda_backend(self, git_ref: str, target_image_tag: str, commit: CommitType):
        try:
            # this function run in a loop to check status. Notification of build start is in builder
            status = await self.builder.build(git_ref=git_ref, commit=commit)
            if status == BuildStatus.FAILED:
                logger.error(f"Build failed for {self.repo_url}@{commit.id}")
                logs = self.k8interface.extract_pod_logs(f"bld-{self.repo_id}-{target_image_tag[:8]}")
                self.notifier.on_build_failed(
                    repo_url=self.repo_url,
                    commit=commit,
                    image_tag=target_image_tag,
                    data={'logs': logs, 'dockerfile': self.config.builder.dockerfile_content})
                return status
            if status == BuildStatus.CANCELLED:
                self.notifier.on_build_cancelled(repo_url=self.repo_url, commit=commit, image_tag=target_image_tag)
            if status == BuildStatus.SUCCEEDED:
                self.notifier.on_build_completed(
                    repo_url=self.repo_url,
                    commit=commit,
                    image_repo=self.target_image_base,
                    image_tag=target_image_tag)
            return status
        except Exception:
            logger.exception(f"Exception occurred while building backend for {self.repo_url}@{commit.id}")
            return BuildStatus.FAILED


    async def ensure_container_image(self, git_ref: str, commit: CommitType):
        target_tag = await self.builder.get_target_image_tag(commit.id)
        logger.debug(f"Ensure_container_image target {self.target_image_base}:{target_tag} for commit {commit}")

        if await self.builder.image_exists(target_tag):
            logger.info(f"Image {self.target_image_base}:{target_tag} exists in registry.")
            return target_tag

        if self.config.builder.enabled:

            status = await self.build_mmoda_backend(
                git_ref=git_ref,
                commit=commit,
                target_image_tag=target_tag)

            if status == BuildStatus.FAILED:
                return RepoChangeStatus.BUILD_FAILED

            if status == BuildStatus.SUCCEEDED:
                return target_tag

            if status == BuildStatus.CANCELLED:
                return RepoChangeStatus.CANCELLED

            return None # queued or running

        logger.warning(
            f"Image {self.target_image_base}:{target_tag} does not exist in registry "
            "and builder is disabled. Waiting for external update.")
        return None


    def deploy_mmoda_backend(self, commit: CommitType, image_tag: str):
        try:
            # NOTE: deployment started notification is in deployer (only trigerred if changes are there)
            mmoda_external_resources = RequirementsAnalyser(self.git_interface).external_resources(commit.id)
            status = self.deployer.deploy(image_tag, commit=commit, mmoda_external_resources=mmoda_external_resources)

            if status == DeploymentStatus.FAILED:
                self.notifier.on_deployment_failed(repo_url=self.repo_url, commit=commit, image_tag=image_tag)
                return RepoChangeStatus.DEPLOY_FAILED

            if status == DeploymentStatus.NOT_CHANGED:
                return RepoChangeStatus.NO_ACTION

            self.notifier.on_deployment_completed(repo_url=self.repo_url, commit=commit, image_tag=image_tag)
            return RepoChangeStatus.DEPLOYED

        except Exception:
            logger.exception(f"Exception occured while deploying backend for {self.repo_url}")
            self.notifier.on_deployment_failed(repo_url=self.repo_url, commit=commit, image_tag=image_tag)
            return RepoChangeStatus.DEPLOY_FAILED

    async def register_mmoda_backend(self, commit: CommitType): # commit is for info here, it registers current state anyway
        try:
            deployment_info = await asyncio.to_thread(
                self.deployer.get_deployment_details)
            deployment_info = deployment_info["manifests"]
            deployment_name = service_name = None
            for resource in deployment_info:
                if resource.get("kind") == "Deployment":
                    deployment_name = resource["metadata"]["name"]
                if resource.get("kind") == "Service":
                    service_name = resource["metadata"]["name"]

            async with aiohttp.ClientSession() as session:
                payload = {
                    "project_repo": self.repo_url,
                    "project_title": self.project_slug,
                    "last_activity_timestamp": commit.committed_date,
                    "last_deployed_timestamp": f"{datetime.now().timestamp()}",
                    "service_name": f"{service_name}",
                    "deployment_name": f"{deployment_name}",
                    "deployment_namespace": self.config.namespace,
                    "creative_work_status": self.creative_work_status
                }

                async with session.post(str(self.config.registrar.url), json=payload) as resp:
                    if resp.status == 201:
                        self.notifier.on_backend_registered(repo_url=self.repo_url, commit=commit)
                        return RepoChangeStatus.REGISTERED
                    else:
                        self.notifier.on_backend_registration_failed(repo_url=self.repo_url, commit=commit)
                        return RepoChangeStatus.REGISTER_FAILED
        except Exception:
            logger.exception(f"Exception registering backend for {self.repo_url}@{commit.id}")
            self.notifier.on_backend_registration_failed(repo_url=self.repo_url, commit=commit)

    async def unregister_mmoda_backend(self):
        async with aiohttp.ClientSession() as session:
            async with session.delete(str(self.config.registrar.url), params={"repo": self.repo_url}) as resp:
                if resp.status == 200:
                    logger.info(f"Successfully unregistered {self.repo_url} from KG.")
                    return True
                else:
                    logger.error(f"Failed to unregister {self.repo_url} from KG. Status code: {resp.status}")
                    return False

    async def generate_help_html(self, commit: CommitType) -> str | None:
        try:
            help_md = await asyncio.to_thread(self.git_interface.get_repo_file_content, 
                                        path='mmoda_help_page.md', git_ref=commit.id)
            help_md = help_md.decode()
            img_base_url = f"{commit.web_url.replace('commit', 'raw')}/"
            return await asyncio.to_thread(convert_help, help_md, img_base_url)
        except gitlab.GitlabGetError:
            return None
        except Exception:
            logger.exception("Unexpected exception in generate_help_html:")
            return None

    async def generate_acknowledgement(self, commit_id: str) -> str:
        try:
            acknowl = await asyncio.to_thread(self.git_interface.get_repo_file_content, 
                                        path='acknowledgements.md', git_ref=commit_id)
            logger.info('Acknowledgements found in repo. Converting')
            acknowl = acknowl.decode()           
            return await asyncio.to_thread(markdown, acknowl)
        except gitlab.GitlabGetError:
            pass     
        except Exception:
            logger.exception("Unexpected exception in generate_acknowledgements:")

        return f'Service generated from <a href="{self.repo_url}" target="_blank">the repository</a>'

            


    async def update_frontend_module(self, commit: CommitType): # commit is for info here, it registers current state anyway
        help_html = await self.generate_help_html(commit)
        acknowledgement = await self.generate_acknowledgement(commit.id)

        self.notifier.on_frontend_update_started(repo_url=self.repo_url, commit=commit)
        async with aiohttp.ClientSession() as session:
            payload = {
                "instr_name": self.project_slug,
                "title": self.project_title,
                "messenger": self.messenger,
                "creative_work_status": self.creative_work_status,
                "instrument_version": commit.id,
                "instrument_version_link": self.git_interface.get_commit_link(commit),
                "help_html": help_html,
                "acknowledgement": acknowledgement
            }
            try:
                async with session.post(str(self.config.frontend_controller.url), json=payload) as resp:
                    if resp.status == 202:
                        job_id = (await resp.json())["job_id"]
                        while True:
                            await asyncio.sleep(5)
                            async with session.get(f"{self.config.frontend_controller.url}/jobs/{job_id}") as status_resp:
                                if status_resp.status == 200:
                                    status_data = await status_resp.json()
                                    if status_data["status"] == "done":
                                        break
                                    elif status_data["status"] == "failed":
                                        self.notifier.on_frontend_update_failed(self.repo_url, commit, response=status_resp)
                                        return RepoChangeStatus.FRONTEND_UPDATE_FAILED
                                else:
                                    raise RuntimeError(f"Unexpected status code while checking frontend update job status: {status_resp.status}")

                        self.notifier.on_frontend_updated(self.repo_url, commit)
                        return RepoChangeStatus.FRONTEND_UPDATED
                    else:
                        self.notifier.on_frontend_update_failed(self.repo_url, commit, response=resp)
                        return RepoChangeStatus.FRONTEND_UPDATE_FAILED

            except Exception as e:
                logger.exception("Exception in update_frontend_module")
                self.notifier.on_frontend_update_failed(self.repo_url, commit, ex=e)
                return RepoChangeStatus.FRONTEND_UPDATE_FAILED

    async def remove_frontend_module(self):
        # TODO: monitor the deletion job
        async with aiohttp.ClientSession() as session:
            try:
                async with session.delete(f"{self.config.frontend_controller.url}/{self.project_slug}") as resp:
                    if resp.status == 200:
                        logger.info(f"Successfully requested frontend to remove module for {self.repo_url}.")
                        return True
                    else:
                        logger.error(f"Failed to request frontend to remove module for {self.repo_url}. Status code: {resp.status}")
                        return False
            except Exception:
                logger.exception(f"Error while requesting frontend to remove module for {self.repo_url}:")
                return False

    async def remove(self):
        if self.config.frontend_controller.enabled:
            await self.remove_frontend_module()
        if self.config.registrar.enabled:
            await self.unregister_mmoda_backend()
        if self.config.backend_deployer.enabled:
            await asyncio.to_thread(self.deployer.remove)

    async def react_repo_change(self, git_ref: str, commit: CommitType):
        commit_id = commit.id
        logger.info(f"Detected change in {self.repo_url}@{git_ref}, commit id: {commit_id}.")

        result = await self.ensure_container_image(git_ref, commit)

        if result == RepoChangeStatus.BUILD_FAILED:
            return result

        if result == RepoChangeStatus.CANCELLED:
            return result

        if not result:
            return RepoChangeStatus.WAITING_IMAGE

        if self.config.backend_deployer.enabled:
            target_tag = result
            result = await asyncio.to_thread(self.deploy_mmoda_backend, commit, target_tag)
            if result in [RepoChangeStatus.DEPLOY_FAILED, RepoChangeStatus.NO_ACTION]:
                return result

        if self.config.registrar.enabled:
            result = await self.register_mmoda_backend(commit)
            if result == RepoChangeStatus.REGISTER_FAILED:
                return RepoChangeStatus.REGISTER_FAILED

        if self.config.frontend_controller.enabled:
            result = await self.update_frontend_module(commit)

            if result == RepoChangeStatus.FRONTEND_UPDATE_FAILED:
                return RepoChangeStatus.FRONTEND_UPDATE_FAILED

        return result

    async def monitor_repo(self, type='branch', ref='HEAD'):
        try:
            while True:
                if type == 'branch':
                    latest_commit = self.git_interface.get_latest_commit(git_ref=ref)
                else:
                    # TODO: tag/PR etc.
                    raise NotImplementedError(f"Monitoring {type} is not implemented.")

                if self.state_store.get(latest_commit.id):
                    await asyncio.sleep(self.config.monitor.repo_poll_timeout)
                    continue

                repo_change_result = await self.react_repo_change(ref, latest_commit)
                if repo_change_result != RepoChangeStatus.WAITING_IMAGE:
                    self.state_store[latest_commit.id] = repo_change_result

                await asyncio.sleep(self.config.monitor.repo_poll_timeout)
        except asyncio.CancelledError:
            logger.info(f'Repo {self.repo_url} monitoring stopped.')
            # TODO: Gaceful shutdown: Cancel build jobs? Any additional cleanups, waitings?
            raise