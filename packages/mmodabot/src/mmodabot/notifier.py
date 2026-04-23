import aiohttp
from mmodabot.utils import split_registry_image_ref
import requests
from typing import Callable, Any, Sequence
from mmodabot.git_interface import GitServerInterface, CommitType
import logging

type ApiResponse = requests.Response | aiohttp.ClientResponse


class NotificationHandler:
    """
    Base class for notification handlers. Subclasses can override any of the methods to handle specific events.
    Not ABC to allow for flexible implementations without requiring all methods to be defined.
    """
    def on_build_started(self, repo_url: str, commit: CommitType, image_tag: str): ...
    def on_build_completed(self, repo_url: str, commit: CommitType, image_repo: str, image_tag: str): ...
    def on_build_failed(self, repo_url: str, commit: CommitType, image_tag: str, data: dict = {}): ...
    def on_build_cancelled(self, repo_url: str, commit: CommitType, image_tag: str): ...
    def on_deployment_started(self, repo_url: str, commit: CommitType, image_tag: str): ...
    def on_deployment_completed(self, repo_url: str, commit: CommitType, image_tag: str): ...
    def on_deployment_failed(self, repo_url: str, commit: CommitType, image_tag: str, error: str | None = None): ...
    def on_backend_registered(self, repo_url: str, commit: CommitType): ...
    def on_backend_registration_failed(
        self,
        repo_url: str,
        commit: CommitType,
        status_code: str | int | None = None,
        response_content: str | dict | None = None,
        ex: Exception | None = None,
    ): ...
    def on_frontend_update_started(self, repo_url: str, commit: CommitType): ...
    def on_frontend_updated(self, repo_url: str, commit: CommitType): ...
    def on_frontend_update_failed(
        self,
        repo_url: str,
        commit: CommitType,
        status_code: str | int | None = None,
        response_content: str | dict | None = None,
        ex: Exception | None = None,
    ): ...


class CompositeNotificationHandler(NotificationHandler):
    def __init__(self, handlers: Sequence[NotificationHandler]):
        self.handlers = handlers
        self.logger = logging.getLogger(__name__)

    @staticmethod
    def delegated(method_name: str) -> Callable[..., Any]:
        def method(self, *args, **kwargs):
            if not self.handlers:
                # check method signature against superclass method to ensure correct usage
                super_method = getattr(super(), method_name)
                try:
                    super_method(*args, **kwargs)
                except TypeError as e:
                    raise TypeError(f"Incorrect arguments for method {method_name}: {e}")
            for handler in self.handlers:
                try:
                    getattr(handler, method_name)(*args, **kwargs)
                except Exception as e:
                    self.logger.error(f'Unexpected exception in notifier {handler.__class__.__name__}: {e}')
        return method

    on_build_started = delegated('on_build_started')
    on_build_completed = delegated('on_build_completed')
    on_build_failed = delegated('on_build_failed')
    on_build_cancelled = delegated('on_build_cancelled')
    on_deployment_started = delegated('on_deployment_started')
    on_deployment_completed = delegated('on_deployment_completed')
    on_deployment_failed = delegated('on_deployment_failed')
    on_backend_registered = delegated('on_backend_registered')
    on_backend_registration_failed = delegated('on_backend_registration_failed')
    on_frontend_update_started = delegated('on_frontend_update_started')
    on_frontend_updated = delegated('on_frontend_updated')
    on_frontend_update_failed = delegated('on_frontend_update_failed')

class LoggingNotificationHandler(NotificationHandler):
    # this is used for manual testing
    def __init__(self, logger=None):
        self.logger = logger or logging.getLogger(__name__)

    def on_build_started(self, repo_url: str, commit: CommitType, image_tag: str):
        self.logger.info(f"[NOTIFIER] Build started: {repo_url} {commit.id} => {image_tag}")

    def on_build_completed(self, repo_url: str, commit: CommitType, image_repo: str, image_tag: str):
        self.logger.info(f"[NOTIFIER] Build succeeded: {repo_url} {commit.id} => {image_tag}")

    def on_build_failed(self, repo_url: str, commit: CommitType, image_tag: str, data: dict = {}):
        self.logger.error(f"[NOTIFIER] Build failed: {repo_url} {commit.id} => {image_tag}")
        if data.get('logs'):
            self.logger.error(f"[NOTIFIER] Build logs:\n{data['logs']}")

    def on_build_cancelled(self, repo_url: str, commit: CommitType, image_tag: str):
        self.logger.warning(f"[NOTIFIER] Build cancelled for {repo_url} {commit.id} => {image_tag}")

    def on_deployment_started(self, repo_url: str, commit: CommitType, image_tag: str):
        self.logger.info(f"[NOTIFIER] Deployment started: {repo_url} {commit.id} => {image_tag}")

    def on_deployment_completed(self, repo_url: str, commit: CommitType, image_tag: str):
        self.logger.info(f"[NOTIFIER] Deployment succeeded: {repo_url} {commit.id} => {image_tag}")

    def on_deployment_failed(self, repo_url: str, commit: CommitType, image_tag: str, error: str | None = None):
        self.logger.error(f"[NOTIFIER] Deployment failed: {repo_url} {commit.id} => {image_tag}")
        if error:
            self.logger.error(f"[NOTIFIER] Deployment error: {error}")

    def on_backend_registered(self, repo_url: str, commit: CommitType):
        self.logger.info(f"[NOTIFIER] Backend {repo_url} registered in KG following commit: {commit.id}")

    def on_backend_registration_failed(
        self,
        repo_url: str,
        commit: CommitType,
        status_code: str | int | None = None,
        response_content: str | dict | None = None,
        ex: Exception | None = None,
    ):
        extra_info = ''
        if status_code:
            extra_info += f"Status code: {status_code}\n"
        if response_content:
            f"Response content: {response_content}\n"
        if ex:
            extra_info += (f"Exception occurred: {ex}")
        self.logger.error(f"[NOTIFIER] Backend registration in KG failed: {repo_url} {commit.id}\n{extra_info}")


    def on_frontend_updated(self, repo_url: str, commit: CommitType):
        self.logger.info(f"[NOTIFIER] Updated frontend instrument module: {repo_url} {commit.id}")

    def on_frontend_update_failed(
        self,
        repo_url: str,
        commit: CommitType,
        status_code: str | int | None = None,
        response_content: str | dict | None = None,
        ex: Exception | None = None,
    ):
        extra_info = ''
        if status_code:
            extra_info += f"Status code: {status_code}\n"
        if response_content:
            f"Response content: {response_content}\n"
        if ex:
            extra_info += (f"Exception occurred: {ex}")
        self.logger.error(f"[NOTIFIER] Failed to update frontend instrument module: {repo_url} {commit.id}\n{extra_info}")

class GitlabNotificationHandler(NotificationHandler):
    def __init__(self, nickname: str = 'MMODA', frontend_url: str | None = None):
        self.nickname = nickname
        self.frontend_url = frontend_url

    def on_build_started(self, repo_url: str, commit: CommitType, image_tag: str):
        GitServerInterface.set_commit_status(
            commit=commit,
            name=f'{self.nickname}: Build',
            status='running',
            description=f'Building image {image_tag}...'
        )

    def on_build_completed(self, repo_url: str, commit: CommitType, image_repo: str, image_tag: str):
        registry = split_registry_image_ref(image_repo)
        if registry == 'docker.io':
            target_url = f"https://hub.docker.com/r/{image_repo}"
        elif 'gitlab' in registry:
            # Assume we are using gitlab registry linked to the project
            target_url = f"{repo_url.replace('.git', '').strip('/')}/container_registry"
        else:
            target_url = None

        GitServerInterface.set_commit_status(
            commit=commit,
            name='f{self.nickname}: Build',
            status='success',
            description=f'Image {image_repo}:{image_tag} built successfully',
            target_url=target_url
        )

    def on_build_failed(self, repo_url: str, commit: CommitType, image_tag: str, data: dict = {}):
        GitServerInterface.set_commit_status(
            commit=commit,
            name=f'{self.nickname}: Build',
            status='failed',
            description=f'Build failed, image tag: {image_tag}'
        )
        
    def on_build_cancelled(self, repo_url: str, commit: CommitType, image_tag: str): ...
    def on_deployment_started(self, repo_url: str, commit: CommitType, image_tag: str):
        GitServerInterface.set_commit_status(
            commit=commit,
            name=f'{self.nickname}: Deployment',
            status='running',
            description=f'Deploying MMODA backend, image tag: {image_tag}...'
        )

    def on_deployment_completed(self, repo_url: str, commit: CommitType, image_tag: str):
        GitServerInterface.set_commit_status(
            commit=commit,
            name=f'{self.nickname}: Deployment',
            status='success',
            description=f'Deployed MMODA backend, image tag: {image_tag}'
        )

    def on_deployment_failed(self, repo_url: str, commit: CommitType, image_tag: str, error: str | None = None):
        GitServerInterface.set_commit_status(
            commit=commit,
            name=f'{self.nickname}: Deployment',
            status='failed',
            description=f'Failed to deploy MMODA backend, image tag: {image_tag}' + (f': {error}' if error else '')
        )

    def on_backend_registered(self, repo_url: str, commit: CommitType):
        GitServerInterface.set_commit_status(
            commit=commit,
            name=f'{self.nickname}: Registration',
            status='success',
            description='Backend registered in KG'
        )

    def on_backend_registration_failed(
        self,
        repo_url: str,
        commit: CommitType,
        status_code: str | int | None = None,
        response_content: str | dict | None = None,
        ex: Exception | None = None,
    ):
        GitServerInterface.set_commit_status(
            commit=commit,
            name=f'{self.nickname}: Registration',
            status='failed',
            description=f"Failed to register backend in KG. {'Status code: '+str(status_code) if status_code else ''} {'Exception: '+str(ex) if ex else ''}"
        )

    def on_frontend_update_started(self, repo_url: str, commit: CommitType):
        GitServerInterface.set_commit_status(
            commit=commit,
            name=f'{self.nickname}: Update Frontend',
            status='running',
            description='Updating frontend instrument module...'
        )

    def on_frontend_updated(self, repo_url: str, commit: CommitType):
        GitServerInterface.set_commit_status(
            commit=commit,
            name=f'{self.nickname}: Update Frontend',
            status='success',
            description='Frontend instrument module updated successfully',
            target_url=self.frontend_url
        )

    def on_frontend_update_failed(
        self,
        repo_url: str,
        commit: CommitType,
        status_code: str | int | None = None,
        response_content: str | dict | None = None,
        ex: Exception | None = None,
    ):
        GitServerInterface.set_commit_status(
            commit=commit,
            name=f'{self.nickname}: Update Frontend',
            status='failed',
            description=f"Failed to update frontend instrument module: {'Status code: '+str(status_code) if status_code else ''} {'Exception: '+str(ex) if ex else ''}"
        )
