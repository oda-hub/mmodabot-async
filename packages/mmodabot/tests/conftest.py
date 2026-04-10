import os
import tempfile
import pytest
import yaml

from unittest.mock import MagicMock, AsyncMock
from kubernetes import config as kube_config


@pytest.fixture(scope="session")
def mock_kubeconfig():
    kubeconfig = {
        "apiVersion": "v1",
        "clusters": [{"cluster": {"server": "https://mock-server:6443"}, "name": "mock-cluster"}],
        "users": [{"name": "mock-user", "user": {"token": "mock-token"}}],
        "contexts": [{"context": {"cluster": "mock-cluster", "user": "mock-user"}, "name": "mock-context"}],
        "current-context": "mock-context",
    }

    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".yaml") as f:
        yaml.dump(kubeconfig, f)
        os.environ["KUBECONFIG"] = f.name
        kube_config.load_kube_config()
        yield
        os.unsetenv("KUBECONFIG")

@pytest.fixture
def mock_commit():
    """Create mock commit object"""
    commit = MagicMock()
    commit.id = "abc123"
    commit.committed_date = "2023-01-01T00:00:00Z"
    commit.web_url = "https://gitlab.example.com/commit/abc123"
    return commit


@pytest.fixture
def mock_config():
    """Create complete mock config for NBRepoAdapter and other components"""
    config = MagicMock()
    config.namespace = "default"
    
    # Builder config
    config.builder = MagicMock()
    config.builder.enabled = True
    config.builder.nb2w_version_spec = "1.0.0"
    config.builder.job_tmpl = """
apiVersion: batch/v1
kind: Job
metadata:
  name: test-job
spec:
  template:
    spec:
      containers:
      - name: kaniko
        image: gcr.io/kaniko-project/executor:latest
        args: []
        env: []
      volumes:
      - name: kaniko-docker-config
        secret:
          secretName: test-secret
"""
    
    # Backend deployer config
    config.backend_deployer = MagicMock()
    config.backend_deployer.mechanism = "helm-cli"
    config.backend_deployer.values = {}
    config.backend_deployer.timeout = "5m"
    config.backend_deployer.helm_chart = "/chart"
    config.backend_deployer.enabled = True
    
    # Registrar config
    config.registrar = MagicMock()
    config.registrar.enabled = False
    config.registrar.url = "http://example:8888"
    
    # Frontend controller config
    config.frontend_controller = MagicMock()
    config.frontend_controller.enabled = False
    config.frontend_controller.url = "http://example:8888"
    
    # Hash base mock
    hash_base = MagicMock()
    hash_base.hexdigest.return_value = "test-tag"
    hash_base.copy.return_value = hash_base
    config.hash_base = hash_base
    
    return config


@pytest.fixture
def mock_config_builder_only():
    """Mock config for testing builder component only"""
    config = MagicMock()
    
    # Builder config
    config.builder = MagicMock()
    config.builder.enabled = True
    config.builder.nb2w_version_spec = "1.0.0"
    config.builder.job_tmpl = """
apiVersion: batch/v1
kind: Job
metadata:
  name: test-job
spec:
  template:
    spec:
      containers:
      - name: kaniko
        image: gcr.io/kaniko-project/executor:latest
        args: []
        env: []
      volumes:
      - name: kaniko-docker-config
        secret:
          secretName: test-secret
"""
    
    # Hash base mock
    hash_base_mock = MagicMock()
    hash_base_mock.hexdigest.return_value = "test-tag"
    config.hash_base = hash_base_mock
    config.hash_base.copy.return_value = hash_base_mock
    return config


@pytest.fixture
def mock_config_deployer_only():
    """Mock config for testing deployer component only"""
    config = MagicMock()
    config.namespace = "default"
    
    # Backend deployer config
    config.backend_deployer = MagicMock()
    config.backend_deployer.mechanism = "helm-cli"
    config.backend_deployer.values = {"test": "value"}
    config.backend_deployer.timeout = "5m"
    config.backend_deployer.helm_chart = "/chart"
    config.backend_deployer.enabled = True
    
    return config


@pytest.fixture
def mock_config_controller():
    """Mock config for testing controller"""
    config = MagicMock()
    config.namespace = "test-namespace"
    
    # Monitor config
    config.monitor = MagicMock()
    mock_group_conf = MagicMock()
    mock_group_conf.url = 'https://gitlab.example.fr/mmoda/dev'
    mock_group_conf.gitlab_base = 'https://gitlab.example.fr/'
    mock_group_conf.git_token_secret_name = 'mmoda-dev-group-token'
    mock_group_conf.git_token_secret_key = 'token'
    mock_group_conf.registry_secret_name = 'mmoda-group-registry-token'
    mock_group_conf.target_image_base_tmpl = 'gitlab-registry.example.fr/mmoda/dev/{slug}'
    config.monitor.groups = [mock_group_conf]
    config.monitor.repos = {}
    
    config.builder = MagicMock()
    config.backend_deployer = MagicMock()
    return config


@pytest.fixture
def mock_k8interface():
    """Create mock K8S interface"""
    k8 = MagicMock()
    k8.jobs = {}
    k8.submit_job = AsyncMock()
    
    # Handle different secret types
    def read_secret_side_effect(secret_name):
        if secret_name == 'mmoda-dev-group-token':
            return {'token': 'test-token'}
        else:
            # Default for other secrets (like registry configs)
            return {
                ".dockerconfigjson": '{"auths":{"https://index.docker.io/v1/":{"username":"test","password":"secret"}}}'
            }
    
    k8.read_secret = MagicMock(side_effect=read_secret_side_effect)
    k8.extract_pod_logs = MagicMock(return_value="build logs here")
    return k8


@pytest.fixture
def mock_git_interface():
    """Create mock Git interface"""
    git = MagicMock()
    return git


@pytest.fixture
def builder(mock_config_builder_only, mock_k8interface):
    """Create ImageBuilder instance for testing"""
    from mmodabot.builder import ImageBuilder
    return ImageBuilder(
        repo_url="https://github.com/test/repo.git",
        target_image_base="test/repo",
        config=mock_config_builder_only,
        k8interface=mock_k8interface,
        registry_secret_name="test-secret",
    )


@pytest.fixture
def deployer(mock_config_deployer_only, mock_k8interface):
    """Create HelmDeployer instance for testing"""
    from mmodabot.deployer import HelmDeployer
    return HelmDeployer(
        project_slug="test-project",
        repo_id="test123",
        repo_url="https://github.com/test/repo.git",
        target_image_base="test/repo",
        config=mock_config_deployer_only,
        k8interface=mock_k8interface,
    )
