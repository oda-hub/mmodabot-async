import pytest
from unittest.mock import MagicMock, patch
from mmodabot.git_interface import GitServerInterface, CommitType


class TestGitServerInterface:
    @patch('mmodabot.git_interface.gitlab.Gitlab', new=MagicMock())
    def test_init_with_gitlab_instance(self):
        """Test initialization with existing gitlab instance"""
        from mmodabot.git_interface import gitlab
        
        mock_gl_instance = MagicMock()
        mock_gl_instance.url = "https://gitlab.example.com"

        git_interface = GitServerInterface(mock_gl_instance)

        assert git_interface.git == mock_gl_instance
        assert git_interface.project is None

    @patch('mmodabot.git_interface.gitlab.Gitlab', new=MagicMock())
    def test_init_with_url(self):
        """Test initialization with URL"""
        from mmodabot.git_interface import gitlab

        mock_gl_instance = MagicMock()
        mock_gl_instance.url = "https://gitlab.example.com"
        gitlab.Gitlab.return_value = mock_gl_instance

        git_interface = GitServerInterface("https://gitlab.example.com", token="test-token")

        gitlab.Gitlab.assert_called_once_with("https://gitlab.example.com", private_token="test-token")
        assert git_interface.git == mock_gl_instance

    def test_init_unsupported_kind(self):
        """Test initialization with unsupported git provider"""
        with pytest.raises(NotImplementedError, match="Git provider 'github' is not supported yet"):
            GitServerInterface("https://github.com", kind="github")

    @patch('mmodabot.git_interface.gitlab.Gitlab', new=MagicMock())
    def test_preset_project_by_repo_url(self):
        """Test setting project from repo URL"""
        mock_gl_instance = MagicMock()
        mock_gl_instance.url = "https://gitlab.example.com"
        mock_project = MagicMock()
        mock_gl_instance.projects.get.return_value = mock_project

        git_interface = GitServerInterface(mock_gl_instance)
        git_interface.preset_project_by_repo_url("https://gitlab.example.com/user/repo.git")

        mock_gl_instance.projects.get.assert_called_once_with("user/repo")
        assert git_interface.project == mock_project

