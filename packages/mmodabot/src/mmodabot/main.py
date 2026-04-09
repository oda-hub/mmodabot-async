import asyncio
import logging

from mmodabot.git_interface import GitServerInterface
from mmodabot.repo_adapter import NBRepoAdapter
from mmodabot.k8s_interface import K8SInterface
from mmodabot.config import Config
from mmodabot.notifier import LoggingNotificationHandler
from mmodabot.utils import gitlab_instance_url_from_full_url, list_bot_helm_deployments, repo_id


logger = logging.getLogger(__name__)


class Controller:
    # TODO: more typing, e.g. dictionaries; also Config 
    def __init__(self, config, k8interface: K8SInterface):
        try:
            self.config = config
            self.namespace = self.config.namespace
            self.k8interface = k8interface

            self._prepare_builder()

            self.notifier=LoggingNotificationHandler() # TODO: config
            
            self.repo_registry = {} # repo_url -> (NBRepoAdapter, task) | None
            self._inititalize_repo_registry()

            self.group_interfaces = {} # group_url -> GitServerInterface
            self._initialize_group_interfaces()
        except Exception:
            self._cleanup()
            raise

    def _initialize_group_interfaces(self):
        for group_url, group_conf in self.config.monitor['groups'].items():
            repo_credentials = None
            git_token_secret_name = group_conf.get('git_token_secret_name')
            git_token_secret_key = group_conf.get('git_token_secret_key')
            gitlab_base = group_conf.get('gitlab_base')

            if git_token_secret_name and git_token_secret_key:
                self.repo_credentials = self.k8interface.read_secret(
                    git_token_secret_name)[git_token_secret_key]

            if gitlab_base is None:
                gitlab_base = gitlab_instance_url_from_full_url(group_url)
            git = GitServerInterface(
                gitlab_base,
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
            repo_url = repoid_cm.data.get(repo_id) # pyright: ignore[reportOptionalMemberAccess]
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
        dockerfile = self.config.builder['dockerfile_content']
        self.k8interface.create_cm("backend-builder-dockerfile", {"Dockerfile": dockerfile})

    async def _projects_to_deploy_in_gitlab_group(
            self,
            group_url: str, 
            ):

        git_interface = self.group_interfaces[group_url]
        project_iterator = await asyncio.to_thread(
            git_interface.list_group, group_link=group_url, iterator=True)
        
        projects_set = set()
        for project in project_iterator:
            if project.marked_for_deletion_on or project.archived:
                continue
            
            if set(project.topics) & set(self.config.monitor['triggering_topics']):
                projects_set.add(project.http_url_to_repo)

        return projects_set
        
    async def _update_round(self):
        try:
            projects_to_deploy = {}
            mapping= {}
            for group_url in self.group_interfaces:
                group_conf = self.config.monitor['groups'][group_url]
                git_token_secret_name = group_conf.get('git_token_secret_name')
                git_token_secret_key = group_conf.get('git_token_secret_key')
                target_image_base_tmpl = group_conf.get('target_image_base_tmpl')
                registry_secret_name = group_conf.get('registry_secret_name')
                gitlab_base = group_conf.get('gitlab_base')

                ptd_in_group = await self._projects_to_deploy_in_gitlab_group(group_url=group_url)
                for prj in ptd_in_group:
                    projects_to_deploy[prj] = {
                        'repo_url': prj,
                        'target_image_base_tmpl': target_image_base_tmpl,
                        'config': self.config,
                        'k8interface': self.k8interface,
                        'gitlab_base': gitlab_base,
                        'registry_secret_name': registry_secret_name,
                        'git_token_secret_name': git_token_secret_name,
                        'git_token_secret_key': git_token_secret_key,
                        'notifier': self.notifier
                    }
                    mapping[repo_id(prj)] = prj

            for prj, prj_conf in self.config.monitor['repos'].items():
                git_token_secret_name = prj_conf.get('git_token_secret_name')
                git_token_secret_key = prj_conf.get('git_token_secret_key')
                target_image_base_tmpl = prj_conf.get('target_image_base')
                registry_secret_name = prj_conf.get('registry_secret_name')
                gitlab_base = prj_conf.get('gitlab_base')

                projects_to_deploy[prj] = {
                    'repo_url': prj,
                    'target_image_base_tmpl': target_image_base_tmpl,
                    'config': self.config,
                    'k8interface': self.k8interface,
                    'gitlab_base': gitlab_base,
                    'registry_secret_name': registry_secret_name,
                    'git_token_secret_name': git_token_secret_name,
                    'git_token_secret_key': git_token_secret_key,
                    'notifier': self.notifier
                }
                mapping[repo_id(prj)] = prj

            await self._update_repoid_mapping(mapping=mapping)

            projects_to_remove = set(self.repo_registry.keys()) - set(projects_to_deploy.keys())

            logger.info(f'Projects to remove: {projects_to_remove}')
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

            logger.info(f'Projects to monitor: {projects_to_deploy.keys()}')
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
            await asyncio.sleep(self.config.monitor['groups_poll_timeout'])

    
    def _cleanup(self):
        self.k8interface.delete_cm("backend-builder-dockerfile")
        # TODO: will need to stop repo adapters, job workers, probably cleanup unfinished jobs (the logic to be in proper interfaces)


async def main():
    config = Config()

    k8interface = K8SInterface(namespace=config.namespace) # TODO: configure concurrency 
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