import pytest
from unittest.mock import MagicMock, AsyncMock, patch


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
    config.builder = {
        "enabled": True,
        "nb2w_version_spec": "1.0.0",
        "job_tmpl": """
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
    }
    config.backend_deployer = {
        "mechanism": "helm-cli",
        "values": {},
        "timeout": "5m",
        "helm_chart": "/chart",
        "enabled": True
    }
    config.registrar = {"enabled": False}
    config.frontend_controller = {"enabled": False}
    
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
    config.builder = {
        "enabled": True,
        "nb2w_version_spec": "1.0.0",
        "job_tmpl": """
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
    }
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
    config.backend_deployer = {
        "mechanism": "helm-cli",
        "values": {"test": "value"},
        "timeout": "5m",
        "helm_chart": "/chart",
        "enabled": True
    }
    return config


@pytest.fixture
def mock_config_controller():
    """Mock config for testing controller"""
    config = MagicMock()
    config.namespace = "test-namespace"
    config.monitor = {
        'groups': {
            'https://gitlab.in2p3.fr/mmoda/dev': {
                'gitlab_base': 'https://gitlab.in2p3.fr/',
                'git_token_secret_name': 'mmoda-dev-group-token',
                'git_token_secret_key': 'token',
                'registry_secret_name': 'mmoda-group-registry-token',
                'target_image_base_tmpl': 'gitlab-registry.in2p3.fr/mmoda/dev/{slug}'
            }
        },
        'repos': {}
    }
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
