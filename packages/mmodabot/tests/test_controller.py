import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from mmodabot.main import Controller


class TestController:
    @patch('mmodabot.main.GitServerInterface')
    @patch('mmodabot.main.NBRepoAdapter')
    def test_controller_initialization(self, mock_adapter_class, mock_git_class, mock_config_controller, mock_k8interface):
        """Test Controller initialization"""
        mock_git_instance = MagicMock()
        mock_git_class.return_value = mock_git_instance

        controller = Controller(mock_config_controller, mock_k8interface)

        # Check that components are initialized
        assert controller.config == mock_config_controller
        assert controller.namespace == "test-namespace"
        assert controller.k8interface == mock_k8interface
        assert controller.notifier is not None
        assert isinstance(controller.repo_registry, dict)
        assert isinstance(controller.group_interfaces, dict)

        # Check that group interfaces are initialized
        mock_git_class.assert_called_once()
        assert len(controller.group_interfaces) == 1

    @patch('mmodabot.main.GitServerInterface')
    @patch('mmodabot.main.NBRepoAdapter')
    def test_controller_initialization_with_repo_credentials(self, mock_adapter_class, mock_git_class, mock_config_controller, mock_k8interface):
        """Test Controller initialization reads repo credentials"""
        mock_git_instance = MagicMock()
        mock_git_class.return_value = mock_git_instance

        controller = Controller(mock_config_controller, mock_k8interface)

        # Check that secret was read for group token
        mock_k8interface.read_secret.assert_called_once_with('mmoda-dev-group-token')

    @patch('mmodabot.main.GitServerInterface')
    @patch('mmodabot.main.NBRepoAdapter')
    def test_controller_initialization_group_interface_creation(self, mock_adapter_class, mock_git_class, mock_config_controller, mock_k8interface):
        """Test group interface creation during initialization"""
        mock_git_instance = MagicMock()
        mock_git_class.return_value = mock_git_instance

        controller = Controller(mock_config_controller, mock_k8interface)

        # Check GitServerInterface was created with correct parameters
        mock_git_class.assert_called_once_with(
            'https://gitlab.in2p3.fr/',
            token=None
        )

    @patch('mmodabot.main.GitServerInterface')
    @patch('mmodabot.main.NBRepoAdapter')
    def test_controller_cleanup_on_init_failure(self, mock_adapter_class, mock_git_class, mock_config_controller, mock_k8interface):
        """Test cleanup is called when initialization fails"""
        mock_git_class.side_effect = Exception("Init failed")

        with patch.object(Controller, '_cleanup') as mock_cleanup:
            with pytest.raises(Exception, match="Init failed"):
                Controller(mock_config_controller, mock_k8interface)

            mock_cleanup.assert_called_once()

    @patch('mmodabot.main.GitServerInterface')
    @patch('mmodabot.main.NBRepoAdapter')
    def test_controller_cleanup_method(self, mock_adapter_class, mock_git_class, mock_config_controller, mock_k8interface):
        """Test cleanup method"""
        mock_git_instance = MagicMock()
        mock_git_class.return_value = mock_git_instance

        controller = Controller(mock_config_controller, mock_k8interface)

        # Add some mock tasks to repo registry
        mock_task = AsyncMock()
        controller.repo_registry['repo1'] = (MagicMock(), mock_task)

        controller._cleanup()

        # _cleanup currently removes builder configmap only
        mock_k8interface.delete_cm.assert_called_once_with("backend-builder-dockerfile")
        mock_task.cancel.assert_not_called()

    @patch('mmodabot.main.gitlab_instance_url_from_full_url')
    @patch('mmodabot.main.GitServerInterface')
    @patch('mmodabot.main.NBRepoAdapter')
    def test_initialize_group_interfaces(self, mock_adapter_class, mock_git_class, mock_gitlab_url_func, mock_config_controller, mock_k8interface):
        """Test group interfaces initialization"""
        mock_gitlab_url_func.return_value = "https://gitlab.in2p3.fr/"
        mock_git_instance = MagicMock()
        mock_git_class.return_value = mock_git_instance

        # Remove explicit gitlab_base from fixture so fallback is exercised
        mock_config_controller.monitor['groups']['https://gitlab.in2p3.fr/mmoda/dev'].pop('gitlab_base', None)

        controller = Controller(mock_config_controller, mock_k8interface)

        # Check that gitlab_instance_url_from_full_url was called
        mock_gitlab_url_func.assert_called_once_with('https://gitlab.in2p3.fr/mmoda/dev')

        # Check group interface was stored
        assert 'https://gitlab.in2p3.fr/mmoda/dev' in controller.group_interfaces
        assert controller.group_interfaces['https://gitlab.in2p3.fr/mmoda/dev'] == mock_git_instance