import aiohttp
import requests
from typing import Callable, Any, Sequence
from mmodabot.git_interface import CommitType

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
    def on_backend_registration_failed(self, repo_url: str, commit: CommitType, response: ApiResponse | None = None, ex: Exception | None = None): ...
    def on_frontend_update_started(self, repo_url: str, commit: CommitType): ...
    def on_frontend_updated(self, repo_url: str, commit: CommitType): ...
    def on_frontend_update_failed(self, repo_url: str, commit: CommitType, response: ApiResponse | None = None, ex: Exception | None = None): ...


class CompositeNotificationHandler(NotificationHandler):
    def __init__(self, handlers: Sequence[NotificationHandler]):
        self.handlers = handlers

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
                getattr(handler, method_name)(*args, **kwargs)
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
        import logging
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

    def on_backend_registration_failed(self, repo_url: str, commit: CommitType, response: ApiResponse | None = None, ex: Exception | None = None):
        self.logger.error(f"[NOTIFIER] Backend registration in KG failed: {repo_url} {commit.id}")
        if response:
            status = getattr(response, 'status_code', getattr(response, 'status', 'unknown'))
            self.logger.error(
                f"[NOTIFIER] Status code: {getattr(response, 'status_code', status)}\n"
                f"[NOTIFIER] Response content: {getattr(response, 'text', getattr(response, 'content', ''))}")
        if ex:
            self.logger.error(f"[NOTIFIER]Exception occurred: {ex}")

    def on_frontend_updated(self, repo_url: str, commit: CommitType):
        self.logger.info(f"[NOTIFIER] Updated frontend instrument module: {repo_url} {commit.id}")

    def on_frontend_update_failed(self, repo_url: str, commit: CommitType, response: ApiResponse | None = None, ex: Exception | None = None):
        self.logger.error(f"[NOTIFIER] Failed to update frontend instrument module: {repo_url} {commit.id}")
        if response:
            self.logger.error(
                f"[NOTIFIER] Status code: {getattr(response, 'status_code', getattr(response, 'status', 'unknown'))}\n"
                f"[NOTIFIER] Response content: {getattr(response, 'text', getattr(response, 'content', ''))}")
        if ex:
            self.logger.error(f"[NOTIFIER] Exception occurred: {ex}")