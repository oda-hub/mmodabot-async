import json
import logging
from mmodabot.git_interface import CommitType
from mmodabot.notifier import NotificationHandler
import yaml
from mmodabot.config import Config
from mmodabot.k8s_interface import K8SInterface
from mmodabot.registry_interface import tag_exists
from mmodabot.utils import get_registry_api_base, get_registry_auth_key, repo_id, split_registry_image_ref
from mmodabot.status import BuildStatus

logger = logging.getLogger(__name__)


class ImageBuilder:
    def __init__(self,
                 repo_url: str,
                 target_image_base: str,
                 config: Config,
                 k8interface: K8SInterface,
                 registry_secret_name: str | None = None,
                 git_token_secret_name: str | None = None,
                 git_token_secret_key: str | None = None,
                 notifier: NotificationHandler | None = None):
        self.repo_url = repo_url
        self.target_image_base = target_image_base
        self.registry_secret_name = registry_secret_name
        self.git_token_secret_name = git_token_secret_name
        self.git_token_secret_key = git_token_secret_key
        self.config = config
        self.k8interface = k8interface
        self.notifier = notifier
        self.repo_id = repo_id(self.repo_url)

        self.repo_credentials = None
        if self.git_token_secret_name and self.git_token_secret_key:
            self.repo_credentials = self.k8interface.read_secret(
                self.git_token_secret_name)[self.git_token_secret_key]

        if self.config.builder.enabled and self.registry_secret_name is None:
            raise RuntimeError(
                f"Registry secret is not defined for {self.target_image_base} but is required by builder.")

        if self.registry_secret_name is not None:
            registry_auth = k8interface.read_secret(self.registry_secret_name)[".dockerconfigjson"]
            registry_auth = json.loads(registry_auth)
            self.registry_auth = registry_auth["auths"][get_registry_auth_key(self.target_image_base)]
        else:
            self.registry_auth = None

    async def get_target_image_tag(self, commit_id: str):
        hash_base = self.config.hash_base
        hash_base.update(commit_id.encode("utf-8"))
        tag = hash_base.hexdigest()
        return tag

    def _get_job_id(self, image_tag: str):
        return f"{self.repo_id}-{image_tag[:8]}"

    async def prepare_job_spec(self, git_ref: str, target_image_tag: str, commit_id: str | None = None):
        job_yaml = yaml.safe_load(self.config.builder.job_tmpl)
        job_yaml.update({"metadata": {"name": f"bld-{self.repo_id}-{target_image_tag[:8]}"}})
        container = job_yaml["spec"]["template"]["spec"]["containers"][0]

        container["args"] += [
            f"--destination={self.target_image_base}:{target_image_tag}",
            f"--build-arg=REPO_URL={self.repo_url}",
            f"--build-arg=NB2W_VER={self.config.builder.nb2w_version_spec}"
        ]

        if git_ref != "HEAD":
            container["args"].append(f"--build-arg=GIT_REF={git_ref}")

        if commit_id is not None:
            container["args"].append(f"--build-arg=COMMIT_ID={commit_id}")

        if self.repo_credentials:
            container["env"] = [{
                "name": "GIT_TOKEN",
                "valueFrom": {
                    "secretKeyRef": {
                        "name": self.git_token_secret_name,
                        "key": self.git_token_secret_key
                    }
                }
            }]
        else:
            container["env"] = [{"name": "GIT_TOKEN", "value": ""}]

        for vol in job_yaml["spec"]["template"]["spec"]["volumes"]:
            if vol.get("name") == "kaniko-docker-config":
                vol["secret"]["secretName"] = self.registry_secret_name

        return job_yaml

    async def _cancel_conflicting_builds(self, current_job_id: str):
        for existing_id, metadata in self.k8interface.jobs.items():
            if existing_id.startswith(self.repo_id) and metadata["status"] in ["queued", "running"] and existing_id != current_job_id:
                await self.k8interface.cancel(existing_id)
                logger.info(f"Cancelled conflicting job {existing_id} for repo {self.repo_url}")

    async def build(self, git_ref: str, commit: CommitType) -> BuildStatus:
        image_tag = await self.get_target_image_tag(commit.id)
        job_id = self._get_job_id(image_tag)

        existing = self.k8interface.jobs.get(job_id)
        if existing:
            if existing["status"] == "failed":
                logger.error(f"Build failed for {git_ref}@{commit.id}")
                return BuildStatus.FAILED
            if existing["status"] == "running":
                return BuildStatus.RUNNING
            return BuildStatus.QUEUED

        await self._cancel_conflicting_builds(job_id)

        job_yaml = await self.prepare_job_spec(git_ref, image_tag, commit.id)

        logger.info(f"Build queued for {self.repo_url}@{commit.id}, image {self.target_image_base}:{image_tag}")
        if self.notifier is not None:
            self.notifier.on_build_started(repo_url=self.repo_url, commit=commit, image_tag=image_tag)

        # self.k8interface.jobs[job_id] = {"status": "queued", "manifest": job_yaml}
        await self.k8interface.submit_job(job_id, job_yaml)

        return BuildStatus.QUEUED

    async def check_build_job_succeeded(self, git_ref: str, commit: CommitType) -> bool:
        image_tag = await self.get_target_image_tag(commit.id)
        job_id = self._get_job_id(image_tag)

        existing = self.k8interface.jobs.get(job_id)
        if existing and existing.get("status") == "succeeded":
            return True
        return False


    async def image_exists(self, image_tag: str) -> bool:
        if self.registry_auth:
            authkw = dict(username=self.registry_auth["username"], password=self.registry_auth["password"])
        else:
            authkw = {}

        try:
            exists = await tag_exists(
                registry=get_registry_api_base(self.target_image_base),
                repository=split_registry_image_ref(self.target_image_base)[1],
                tag=image_tag,
                **authkw
            )
            logger.info(f"image_exists check for {self.target_image_base}:{image_tag} => {bool(exists)}")
            return bool(exists)
        except Exception:
            logger.exception(f"image_exists failed for {self.target_image_base}:{image_tag}")
            return False
