from importlib.resources import files
import hashlib

from mmodabot.notifier import LoggingNotificationHandler
from mmodabot.utils import get_pypi_package_info, get_unique_spec


class Config:
    def __init__(self, config_file=None):
        self.namespace = "default"

        self.monitor = {}
        self.monitor['triggering_topics'] = ['mmoda-live-service']
        self.monitor['groups_poll_timeout'] = 300 #sec
        self.monitor['repo_poll_timeout'] = 60 #sec

        self.monitor['groups'] = {}
        self.monitor['repos'] = {}

        self.monitor['groups']['https://gitlab.in2p3.fr/mmoda/dev'] = {
            'gitlab_base': 'https://gitlab.in2p3.fr/',
            'git_token_secret_name': 'mmoda-dev-group-token',
            'git_token_secret_key': 'token',
            'registry_secret_name': 'mmoda-group-registry-token',
            'target_image_base_tmpl': 'gitlab-registry.in2p3.fr/mmoda/dev/{slug}'
        }

        self.monitor['repos']['https://gitlab.in2p3.fr/savchenko/icecube-priv'] = {
            'git_token_secret_name': 'private-repo-token',
            'git_token_secret_key': 'token',
            'registry_secret_name': 'private-repo-registry-token',
            'target_image_base': 'gitlab-registry.in2p3.fr/savchenko/icecube-priv'
        }

        self.builder = {}
        self.builder['enabled'] = True
        self.builder['nb2w_version_spec'] = "" # empty string == latest pypi
        self.builder['dockerfile_path'] = files("mmodabot").joinpath("templates/Dockerfile.builder")
        self.builder['job_tmpl_path'] = files("mmodabot").joinpath("templates/builder-job.yaml")
        self.builder['job_concurrency'] = 3
        self.builder['job_queue_size'] = 100

        self.backend_deployer = {}
        self.backend_deployer['enabled'] = True
        self.backend_deployer['mechanism'] = 'helm-cli'
        self.backend_deployer['helm_chart'] = files("mmodabot").joinpath("templates/mmoda-backend-chart")
        self.backend_deployer['values'] = {}
        self.backend_deployer['timeout'] = "5m"
        
        self.registrar = {}
        self.registrar['enabled'] = False
        self.registrar['url'] = "http://oda-dispatcher:8181"

        self.frontend_controller = {}
        self.frontend_controller['enabled'] = False
        self.frontend_controller['url'] = "http://frontend:8181"


        # derived
        self.notifiers = [LoggingNotificationHandler()] # TODO:
        self.builder['dockerfile_content'] = self.builder['dockerfile_path'].read_text()
        self.builder['job_tmpl'] = self.builder['job_tmpl_path'].read_text()
        self._make_hash_base()


    def _make_hash_base(self):
        if self.builder['nb2w_version_spec']:
            self.nb2w_version_hashable_bytes = self.builder['nb2w_version_spec'].encode("utf-8")
        else:
            pkgdata = get_pypi_package_info('nb2workflow')
            self.nb2w_version_hashable_bytes = get_unique_spec(pkgdata['info']['version']).encode("utf-8")
        
        self.builder_dockerfile_bytes = self.builder['dockerfile_path'].read_bytes()

        self._hash_base = hashlib.sha256()
        self._hash_base.update(self.builder_dockerfile_bytes)
        self._hash_base.update(self.nb2w_version_hashable_bytes)
    
    @property
    def hash_base(self):
        return self._hash_base.copy()