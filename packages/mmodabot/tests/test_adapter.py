from mmodabot.git_interface import CommitType
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from mmodabot.repo_adapter import NBRepoAdapter
from mmodabot.status import BuildStatus, DeploymentStatus, RepoChangeStatus
from mmodabot.notifier import LoggingNotificationHandler



class TestNBRepoAdapter:
    @pytest.fixture
    def adapter(self, mock_config, mock_k8interface, mock_git_interface):
        with patch('mmodabot.repo_adapter.GitServerInterface', return_value=mock_git_interface):
            return NBRepoAdapter(
                repo_url="https://github.com/test/repo.git",
                target_image_base_tmpl="test/repo",
                config=mock_config,
                k8interface=mock_k8interface,
                registry_secret_name="test-secret",
                notifier=LoggingNotificationHandler()
            )

    @pytest.mark.asyncio
    async def test_react_repo_change_all_success(self, adapter, mock_commit):
        """Test full flow: build succeeds, deploy succeeds"""
        # Enable all components
        adapter.config.registrar['enabled'] = True
        adapter.config.frontend_controller = {'enabled': True, 'url': 'http://frontend:8181'}
        
        with patch.object(adapter.builder, 'image_exists', new_callable=AsyncMock, return_value=False), \
             patch.object(adapter.builder, 'build', new_callable=AsyncMock, return_value=BuildStatus.SUCCEEDED), \
             patch.object(adapter.deployer, 'deploy', return_value=DeploymentStatus.SUCCEEDED), \
             patch.object(adapter, 'register_mmoda_backend', new_callable=AsyncMock, return_value=RepoChangeStatus.REGISTERED), \
             patch.object(adapter, 'update_frontend_module', new_callable=AsyncMock, return_value=RepoChangeStatus.FRONTEND_UPDATED):

            result = await adapter.react_repo_change("main", mock_commit)

            assert result == RepoChangeStatus.FRONTEND_UPDATED

    @pytest.mark.asyncio
    async def test_react_repo_change_image_exists_skip_build(self, adapter, mock_commit):
        """Test when image already exists, skip build and deploy"""
        # Enable frontend controller and registrar
        adapter.config.registrar['enabled'] = True
        adapter.config.frontend_controller = {'enabled': True, 'url': 'http://frontend:8181'}
        
        with patch.object(adapter.builder, 'image_exists', new_callable=AsyncMock, return_value=True), \
             patch.object(adapter, 'register_mmoda_backend', new_callable=AsyncMock, return_value=RepoChangeStatus.REGISTERED) as mock_reg, \
             patch.object(adapter, 'update_frontend_module', new_callable=AsyncMock, return_value=RepoChangeStatus.FRONTEND_UPDATED) as mock_update, \
             patch.object(adapter.deployer, 'deploy', return_value=DeploymentStatus.SUCCEEDED) as mock_deploy:

            result = await adapter.react_repo_change("main", mock_commit)

            assert result == RepoChangeStatus.FRONTEND_UPDATED
            mock_deploy.assert_called_once_with("test-tag", commit=mock_commit, mmoda_external_resources={})
            mock_reg.assert_called_once_with(mock_commit)
            mock_update.assert_called_once_with(mock_commit)

    @pytest.mark.asyncio
    async def test_react_repo_change_build_failed(self, adapter, mock_commit):
        """Test build failure handling"""
        with patch.object(adapter.builder, 'image_exists', new_callable=AsyncMock, return_value=False), \
             patch.object(adapter.builder, 'build', new_callable=AsyncMock, return_value=BuildStatus.FAILED):

            result = await adapter.react_repo_change("main", mock_commit)

            assert result == RepoChangeStatus.BUILD_FAILED

    @pytest.mark.asyncio
    async def test_react_repo_change_deploy_failed(self, adapter, mock_commit):
        """Test deploy failure triggers rollback"""
        with patch.object(adapter.builder, 'image_exists', new_callable=AsyncMock, return_value=True), \
             patch.object(adapter.deployer, 'deploy', return_value=DeploymentStatus.FAILED):

            result = await adapter.react_repo_change("main", mock_commit)

            assert result == RepoChangeStatus.DEPLOY_FAILED

    @pytest.mark.asyncio
    async def test_react_repo_change_deploy_exception_handling(self, adapter, mock_commit):
        """Test deploy exception handling"""
        with patch.object(adapter.builder, 'image_exists', new_callable=AsyncMock, return_value=True), \
             patch.object(adapter.deployer, 'deploy', side_effect=Exception("Helm error")):

            result = await adapter.react_repo_change("main", mock_commit)

            assert result == RepoChangeStatus.DEPLOY_FAILED

    @pytest.mark.asyncio
    async def test_react_repo_change_builder_disabled_no_action(self, adapter, mock_commit):
        """Test when builder disabled and image doesn't exist"""
        adapter.config.builder["enabled"] = False

        with patch.object(adapter.builder, 'image_exists', new_callable=AsyncMock, return_value=False):
            result = await adapter.react_repo_change("main", mock_commit)

            assert result == RepoChangeStatus.WAITING_IMAGE

    def test_adapter_initialization(self, adapter):
        """Test adapter initializes components correctly"""
        assert adapter.notifier is not None
        assert adapter.builder is not None
        assert adapter.deployer is not None
        assert adapter.repo_url == "https://github.com/test/repo.git"
        assert adapter.target_image_base == "test/repo"

    @pytest.mark.asyncio
    async def test_register_mmoda_backend_success(self, adapter, mock_commit):
        """Test successful backend registration"""
        adapter.config.registrar = {"url": "http://registrar.example.com"}
        adapter.config.namespace = "test-namespace"
        mock_commit.committed_date = "2023-01-01T00:00:00Z"

        # Mock deployer.get_deployment_details
        mock_deployment_details = {
            "manifests": [
                {"kind": "Deployment", "metadata": {"name": "test-deployment"}},
                {"kind": "Service", "metadata": {"name": "test-service"}}
            ]
        }

        with patch.object(adapter.deployer, 'get_deployment_details', return_value=mock_deployment_details), \
             patch('aiohttp.ClientSession') as mock_session_class:

            mock_session = MagicMock()
            mock_session_class.return_value.__aenter__.return_value = mock_session

            mock_response = MagicMock()
            mock_response.status = 201
            mock_response.__aenter__ = AsyncMock(return_value=mock_response)
            mock_response.__aexit__ = AsyncMock(return_value=None)
            mock_session.post.return_value = mock_response

            result = await adapter.register_mmoda_backend(mock_commit)

            assert result == RepoChangeStatus.REGISTERED
            mock_session.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_register_mmoda_backend_failure(self, adapter, mock_commit):
        """Test backend registration failure"""
        adapter.config.registrar = {"url": "http://registrar.example.com"}

        with patch.object(adapter.deployer, 'get_deployment_details', return_value={"manifests": []}), \
             patch('aiohttp.ClientSession') as mock_session_class:

            mock_session = MagicMock()
            mock_session_class.return_value.__aenter__.return_value = mock_session

            mock_response = MagicMock()
            mock_response.status = 400
            mock_response.__aenter__ = AsyncMock(return_value=mock_response)
            mock_response.__aexit__ = AsyncMock(return_value=None)
            mock_session.post.return_value = mock_response

            result = await adapter.register_mmoda_backend(mock_commit)

            assert result == RepoChangeStatus.REGISTER_FAILED

    @pytest.mark.asyncio
    async def test_register_mmoda_backend_exception(self, adapter, mock_commit):
        """Test backend registration exception handling"""
        adapter.config.registrar = {"url": "http://registrar.example.com"}

        with patch.object(adapter.deployer, 'get_deployment_details', side_effect=Exception("Deployer error")):
            result = await adapter.register_mmoda_backend(mock_commit)

            assert result is None

    @pytest.mark.asyncio
    async def test_update_frontend_module_success(self, adapter, mock_commit):
        """Test successful frontend module update"""
        adapter.config.frontend_controller = {"url": "http://frontend.example.com"}

        with patch.object(adapter, 'generate_help_html', new_callable=AsyncMock, return_value="<html>help</html>"), \
             patch.object(adapter, 'generate_acknowledgement', new_callable=AsyncMock, return_value="acknowledgement text"), \
             patch('aiohttp.ClientSession') as mock_session_class:

            mock_session = MagicMock()
            mock_session_class.return_value.__aenter__.return_value = mock_session

            # Initial POST response
            mock_post_response = MagicMock()
            mock_post_response.status = 202
            mock_post_response.json = AsyncMock(return_value={"job_id": "job123"})
            mock_post_response.__aenter__ = AsyncMock(return_value=mock_post_response)
            mock_post_response.__aexit__ = AsyncMock(return_value=None)
            mock_session.post.return_value = mock_post_response

            # Status check responses
            mock_status_response = MagicMock()
            mock_status_response.status = 200
            mock_status_response.json = AsyncMock(return_value={"status": "done"})
            mock_status_response.__aenter__ = AsyncMock(return_value=mock_status_response)
            mock_status_response.__aexit__ = AsyncMock(return_value=None)
            mock_session.get.return_value = mock_status_response

            result = await adapter.update_frontend_module(mock_commit)

            assert result == RepoChangeStatus.FRONTEND_UPDATED

    @pytest.mark.asyncio
    async def test_update_frontend_module_job_failed(self, adapter, mock_commit):
        """Test frontend module update when job fails"""
        adapter.config.frontend_controller = {"url": "http://frontend.example.com"}

        with patch.object(adapter, 'generate_help_html', new_callable=AsyncMock, return_value="<html>help</html>"), \
             patch.object(adapter, 'generate_acknowledgement', new_callable=AsyncMock, return_value="acknowledgement text"), \
             patch('aiohttp.ClientSession') as mock_session_class:

            mock_session = MagicMock()
            mock_session_class.return_value.__aenter__.return_value = mock_session

            # Initial POST response
            mock_post_response = MagicMock()
            mock_post_response.status = 202
            mock_post_response.json = AsyncMock(return_value={"job_id": "job123"})
            mock_post_response.__aenter__ = AsyncMock(return_value=mock_post_response)
            mock_post_response.__aexit__ = AsyncMock(return_value=None)
            mock_session.post.return_value = mock_post_response

            # Status check response - job failed
            mock_status_response = MagicMock()
            mock_status_response.status = 200
            mock_status_response.json = AsyncMock(return_value={"status": "failed"})
            mock_status_response.__aenter__ = AsyncMock(return_value=mock_status_response)
            mock_status_response.__aexit__ = AsyncMock(return_value=None)
            mock_session.get.return_value = mock_status_response

            result = await adapter.update_frontend_module(mock_commit)

            assert result == RepoChangeStatus.FRONTEND_UPDATE_FAILED

    @pytest.mark.asyncio
    async def test_update_frontend_module_post_failure(self, adapter, mock_commit):
        """Test frontend module update when initial POST fails"""
        adapter.config.frontend_controller = {"url": "http://frontend.example.com"}

        with patch.object(adapter, 'generate_help_html', new_callable=AsyncMock, return_value="<html>help</html>"), \
             patch.object(adapter, 'generate_acknowledgement', new_callable=AsyncMock, return_value="acknowledgement text"), \
             patch('aiohttp.ClientSession') as mock_session_class:

            mock_session = MagicMock()
            mock_session_class.return_value.__aenter__.return_value = mock_session

            # POST response with failure status
            mock_response = MagicMock()
            mock_response.status = 400
            mock_response.__aenter__ = AsyncMock(return_value=mock_response)
            mock_response.__aexit__ = AsyncMock(return_value=None)
            mock_session.post.return_value = mock_response

            result = await adapter.update_frontend_module(mock_commit)

            assert result == RepoChangeStatus.FRONTEND_UPDATE_FAILED

    @pytest.mark.asyncio
    async def test_update_frontend_module_exception(self, adapter, mock_commit):
        """Test frontend module update exception handling"""
        adapter.config.frontend_controller = {"url": "http://frontend.example.com"}

        with patch.object(adapter, 'generate_help_html', new_callable=AsyncMock, side_effect=Exception("Generation error")):
            with pytest.raises(Exception, match="Generation error"):
                await adapter.update_frontend_module(mock_commit)
