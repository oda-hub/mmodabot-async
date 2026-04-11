import asyncio
import argparse
import logging
from typing import TypedDict

from mmodabot.git_interface import GitServerInterface
from mmodabot.notifier import NotificationHandler
from mmodabot.repo_adapter import NBRepoAdapter
from mmodabot.k8s_interface import K8SInterface
from mmodabot.config import Config
from mmodabot.utils import gitlab_instance_url_from_full_url, list_bot_helm_deployments, repo_id


logger = logging.getLogger(__name__)

class RepoAdapterKwargs(TypedDict):
    repo_url: str
    target_image_base_tmpl: str
    config: Config
    k8interface: K8SInterface
    gitlab_base: str | None
    registry_secret_name: str | None
    git_token_secret_name: str | None
    git_token_secret_key: str | None
    notifier: NotificationHandler | None


class Controller:
    def __init__(self, config: Config, k8interface: K8SInterface):
        try:
            self.config = config
            self.namespace = self.config.namespace
            self.k8interface = k8interface

            self._prepare_builder()

            self.notifier=self.config.composite_notifier
            
            self.repo_registry: dict[str, tuple[NBRepoAdapter, asyncio.Task] | None] = {} # repo_url -> (NBRepoAdapter, task) | None
            self._inititalize_repo_registry()

            self.group_interfaces: dict[str, GitServerInterface] = {} # group_url -> GitServerInterface
            self._initialize_group_interfaces()
        except Exception:
            self._cleanup()
            raise

    def _initialize_group_interfaces(self):
        for group_conf in self.config.monitor.groups:
            group_url = str(group_conf.url)
            git_token_secret_name = group_conf.git_token_secret_name
            git_token_secret_key = group_conf.git_token_secret_key
            gitlab_base = group_conf.gitlab_base

            repo_credentials = None
            if git_token_secret_name and git_token_secret_key:
                self.repo_credentials = self.k8interface.read_secret(
                    git_token_secret_name)[git_token_secret_key]

            if gitlab_base is None:
                gitlab_base = gitlab_instance_url_from_full_url(group_url)
            git = GitServerInterface(
                str(gitlab_base),
                token = repo_credentials,
                )
            self.group_interfaces[group_url] = git

    def _inititalize_repo_registry(self):
        repoid_cm = self._ensure_repoid_mapping_cm()
        if repoid_cm is None:
            raise RuntimeError("Failed to ensure repo_id mapping ConfigMap, cannot proceed.")
        deployments = list_bot_helm_deployments(self.namespace)
        for deployment in deployments:
            repo_id = deployment.split("-")[-1]
            repo_url: str | None = repoid_cm.data.get(repo_id) # pyright: ignore[reportOptionalMemberAccess]
            if repo_url:
                self.repo_registry[repo_url] = None
                logger.info(f"Added {repo_url} to repo registry from existing deployment.")
            else:
                logger.warning(f"No repo URL found for repo ID {repo_id} in ConfigMap, skipping adding to registry.")

    def _ensure_repoid_mapping_cm(self):
        # the repoid mapping cm: repo_id -> repo_url. Used upon initialisation of the repo registry.
        cm = self.k8interface.get_cm("mmodabot-repoid-mapping", quiet=True)
        if cm:
            logger.info("Found existing repo_id mapping ConfigMap.")
            return cm
        cm = self.k8interface.create_cm("mmodabot-repoid-mapping", {})
        if cm is not None:
            logger.info("Created new repo_id mapping ConfigMap.")
            return cm
        
    async def _update_repoid_mapping(self, mapping: dict[str, str]):
        current = await asyncio.to_thread(self.k8interface.read_cm_data, "mmodabot-repoid-mapping")
        for k, v in mapping.items():
            current[k] = v
        await asyncio.to_thread(self.k8interface.update_cm, "mmodabot-repoid-mapping", data=current)


    def _prepare_builder(self):
        dockerfile = self.config.builder.dockerfile_content
        try:
            self.k8interface.create_cm("backend-builder-dockerfile", {"Dockerfile": dockerfile}, raise_if_exists=True)
        except RuntimeError:
            logger.warning("Old Dockerfile configmap exists, overwriting")
            self.k8interface.update_cm("backend-builder-dockerfile", {"Dockerfile": dockerfile})

    async def _projects_to_deploy_in_gitlab_group(
            self,
            group_url: str, 
            ) -> set[str]:

        git_interface = self.group_interfaces[group_url]
        project_iterator = await asyncio.to_thread(
            git_interface.list_group, group_link=group_url, iterator=True)
        
        projects_set = set()
        for project in project_iterator:
            logger.debug(f"Project in group {group_url}: {project.http_url_to_repo}")
            if project.marked_for_deletion_on or project.archived:
                logger.debug(f"Project {project.http_url_to_repo} is archived or marked for deletion.")
                continue
            
            logger.debug("Topics: project.topics")
            if set(project.topics) & set(self.config.monitor.triggering_topics):
                logger.debug("Added to monitoring")
                projects_set.add(project.http_url_to_repo)

        return projects_set
        
    async def _update_round(self):
        try:
            projects_to_deploy: dict[str, RepoAdapterKwargs] = {}
            mapping: dict[str, str] = {}
            for group_url in self.group_interfaces:
                group_conf = [x for x in self.config.monitor.groups if str(x.url) == group_url][0]
                git_token_secret_name = group_conf.git_token_secret_name
                git_token_secret_key = group_conf.git_token_secret_key
                target_image_base_tmpl = group_conf.target_image_base_tmpl
                registry_secret_name = group_conf.registry_secret_name
                gitlab_base = group_conf.gitlab_base
                if gitlab_base is not None:
                    gitlab_base = str(gitlab_base)

                ptd_in_group = await self._projects_to_deploy_in_gitlab_group(group_url=group_url)
                for prj in ptd_in_group:
                    projects_to_deploy[prj] = RepoAdapterKwargs(
                        repo_url=prj,
                        target_image_base_tmpl=target_image_base_tmpl,
                        config=self.config,
                        k8interface=self.k8interface,
                        gitlab_base=gitlab_base,
                        registry_secret_name=registry_secret_name,
                        git_token_secret_name=git_token_secret_name,
                        git_token_secret_key=git_token_secret_key,
                        notifier=self.notifier)

                    mapping[repo_id(prj)] = prj

            for prj_conf in self.config.monitor.repos:
                proj_url = str(prj_conf.url)
                git_token_secret_name = prj_conf.git_token_secret_name
                git_token_secret_key = prj_conf.git_token_secret_key
                target_image_base_tmpl = prj_conf.target_image_base
                registry_secret_name = prj_conf.registry_secret_name
                gitlab_base = prj_conf.gitlab_base
                if gitlab_base is not None:
                    gitlab_base = str(gitlab_base)

                projects_to_deploy[proj_url] = RepoAdapterKwargs(
                    repo_url=proj_url,
                    target_image_base_tmpl=target_image_base_tmpl,
                    config=self.config,
                    k8interface=self.k8interface,
                    gitlab_base=gitlab_base,
                    registry_secret_name=registry_secret_name,
                    git_token_secret_name=git_token_secret_name,
                    git_token_secret_key=git_token_secret_key,
                    notifier=self.notifier)
                
                mapping[repo_id(proj_url)] = proj_url

            await self._update_repoid_mapping(mapping=mapping)

            projects_to_remove = set(self.repo_registry.keys()) - set(projects_to_deploy.keys())

            logger.info(f'Projects to remove: {','.join(projects_to_remove)}')
            for proj_url in projects_to_remove:
                repo_in_registry = self.repo_registry[proj_url]
                if repo_in_registry is None:
                    # special case upon startup
                    adapter = NBRepoAdapter(
                        repo_url=proj_url,
                        target_image_base_tmpl='_FLAG_OLD_DEPLOYMENT_',
                        config = self.config,
                        k8interface=self.k8interface
                    )
                else:
                    adapter, task = repo_in_registry
                    task.cancel()

                await adapter.remove()
                self.repo_registry.pop(proj_url)

            logger.info(f'Projects to monitor: {",".join(projects_to_deploy.keys())}')
            for proj_url, proj_kwargs in projects_to_deploy.items():
                if self.repo_registry.get(proj_url):
                    logger.debug(f"Repo {proj_url} is already processing.")
                    continue
                    # NOTE: assume kwargs unchanged. So no on-the-fly configuration change possible.
                else:
                    # either not in registry or None (first round after startup)
                    logger.info(f"Starting {proj_url} monitoring task.")
                    adapter = NBRepoAdapter(**proj_kwargs)
                    self.repo_registry[proj_url] = (
                        adapter,
                        asyncio.create_task(
                            adapter.monitor_repo(), # TODO: other repo monitoring options 
                            name=f'adapter-{proj_url}')
                    )
        except Exception:
            logger.exception("Exception in _update_round")
        
        
    async def monitor_projects(self):
        while True:
            await self._update_round()
            await asyncio.sleep(self.config.monitor.groups_poll_timeout)

    
    def _cleanup(self):
        self.k8interface.delete_cm("backend-builder-dockerfile")
        # TODO: do we need to stop repo adapters, job workers, probably cleanup unfinished jobs (the logic to be in proper interfaces)



async def main():
    argparser = argparse.ArgumentParser(description="MMODA Bot")
    argparser.add_argument("--config", type=str, default="", help="Path to configuration TOML file")
    args = argparser.parse_args()

    if args.config:
        config = Config().from_toml_file(args.config)
    else:
        config = Config()

    k8interface = K8SInterface(
        namespace=config.namespace, 
        job_concurrency=config.builder.job_concurrency,
        job_queue_size=config.builder.job_queue_size)
    
    ctrlr = Controller(config, k8interface=k8interface)

    try:
        await asyncio.gather(
            k8interface.run_job_workers(),
            ctrlr.monitor_projects()
            )
    finally:
        ctrlr._cleanup()

def run():
    asyncio.run(main())

if __name__ == "__main__":    
    asyncio.run(main())