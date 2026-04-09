import pytest
import json
from unittest.mock import MagicMock, patch, call
from mmodabot.deployer import HelmDeployer
from mmodabot.status import DeploymentStatus
from mmodabot.notifier import LoggingNotificationHandler


class TestHelmDeployer:
    @pytest.fixture
    def deployer_with_pull_secret(self, deployer):
        deployer.image_pull_secret = "secret"
        return deployer

    def test_release_name_generation(self, deployer):
        """Test Helm release name format"""
        result = deployer._release_name()
        assert result == "test-project-test123"

    def test_build_deployment_values_basic(self, deployer, mock_commit):
        """Test basic deployment values generation"""
        values = deployer._build_deployment_values("test-tag", mock_commit.id)
        expected = {
            "image": {"repository": "test/repo", "tag": "test-tag"},
            "appVersion": "abc123"
        }
        assert values == expected

    def test_build_deployment_values_with_pull_secrets(self, deployer_with_pull_secret, mock_commit):
        """Test deployment values with image pull secrets"""
        values = deployer_with_pull_secret._build_deployment_values("test-tag", mock_commit.id)
        assert "imagePullSecrets" in values
        assert values["imagePullSecrets"] == [{"name": "secret"}]

    @patch('subprocess.check_output')
    @patch('subprocess.run')
    def test_deploy_no_diff(self, mock_run, mock_check_output, deployer, mock_commit):
        """Test successful deployment when no diff"""
        mock_check_output.return_value = b""  # No diff

        result = deployer.deploy("test-tag", mock_commit)

        assert result == DeploymentStatus.NOT_CHANGED
        assert mock_run.call_count == 0  # No upgrade needed when no diff

    @patch('subprocess.check_output')
    @patch('subprocess.run')
    def test_deploy_with_diff(self, mock_run, mock_check_output, deployer, mock_commit):
        """Test deployment when diff exists"""
        mock_check_output.return_value = b"diff output"  # Has diff
        mock_run.return_value = MagicMock(returncode=0)

        result = deployer.deploy("test-tag", mock_commit)

        assert result == DeploymentStatus.SUCCEEDED
        assert mock_run.call_count == 1  # Upgrade command

    @patch('subprocess.check_output')
    @patch('subprocess.run')
    def test_deploy_failure(self, mock_run, mock_check_output, deployer, mock_commit):
        """Test deployment failure triggers rollback"""
        from subprocess import CalledProcessError
        mock_check_output.return_value = b"diff output"  # Has diff, will try to deploy
        
        # Mock run to raise CalledProcessError
        error = CalledProcessError(1, ["helm", "upgrade"])
        mock_run.return_value = MagicMock(returncode=1)
        mock_run.return_value.check_returncode.side_effect = error

        with patch.object(deployer, 'rollback', return_value=DeploymentStatus.ROLLED_BACK):
            result = deployer.deploy("test-tag", mock_commit)

            assert result == DeploymentStatus.FAILED

    @patch('subprocess.check_output')
    @patch('subprocess.run')
    def test_rollback_success(self, mock_run, mock_check_output, deployer):
        """Test rollback command execution"""
        # Mock history response (list with 2 items means we can rollback)
        history = [{"revision": 1}, {"revision": 2}]
        mock_check_output.return_value = json.dumps(history).encode()
        mock_run.return_value = MagicMock(returncode=0)

        result = deployer.rollback()

        assert result == DeploymentStatus.ROLLED_BACK
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0]
        assert call_args[0] == ["helm", "-n", "default", "rollback", "test-project-test123"]

    @patch('subprocess.check_output')
    @patch('subprocess.run')
    def test_rollback_failure(self, mock_run, mock_check_output, deployer):
        """Test rollback failure"""
        history = [{"revision": 1}, {"revision": 2}]
        mock_check_output.return_value = json.dumps(history).encode()
        mock_run.return_value = MagicMock(returncode=1)

        result = deployer.rollback()

        assert result == DeploymentStatus.ROLLBACK_FAILED

    @patch('subprocess.run')
    def test_remove_success(self, mock_run, deployer):
        """Test remove command execution"""
        mock_run.return_value = MagicMock(returncode=0)

        deployer.remove()

        mock_run.assert_called_once()
        call_args = mock_run.call_args[0]
        assert call_args[0] == ["helm", "-n", "default", "uninstall", "test-project-test123"]

    @patch('subprocess.run')
    def test_get_deployment_details(self, mock_run, deployer):
        """Test getting deployment details"""
        deployment_yaml = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: test-deployment
---
apiVersion: v1
kind: Service
metadata:
  name: test-service
"""
        mock_run.return_value = MagicMock(stdout=deployment_yaml.encode(), returncode=0)
        mock_run.return_value.check_returncode = MagicMock()

        result = deployer.get_deployment_details()

        assert "manifests" in result
        assert len(result["manifests"]) == 2
        assert result["manifests"][0]["kind"] == "Deployment"
        assert result["manifests"][1]["kind"] == "Service"