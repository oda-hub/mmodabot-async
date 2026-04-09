import pytest
from unittest.mock import patch, MagicMock
from mmodabot.utils import (
    get_pypi_package_info, _parse_git_spec, resolve_git_reference,
    get_unique_spec, split_registry_image_ref, get_registry_api_base
)


class TestUtils:
    @patch('mmodabot.utils.requests.get')
    def test_get_pypi_package_info_success(self, mock_get):
        """Test successful PyPI package info retrieval"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"info": {"version": "1.0.0"}}
        mock_get.return_value = mock_response

        result = get_pypi_package_info("test-package")

        assert result == {"info": {"version": "1.0.0"}}
        mock_get.assert_called_once_with("https://pypi.org/pypi/test-package/json", timeout=10)

    @patch('mmodabot.utils.requests.get')
    def test_get_pypi_package_info_not_found(self, mock_get):
        """Test PyPI package not found"""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        with pytest.raises(ValueError, match="Package 'test-package' not found"):
            get_pypi_package_info("test-package")

    @patch('mmodabot.utils.requests.get')
    def test_get_pypi_package_info_request_error(self, mock_get):
        """Test PyPI request error"""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = Exception("Server error")
        mock_get.return_value = mock_response

        with pytest.raises(Exception):
            get_pypi_package_info("test-package")

    def test_parse_git_spec_https(self):
        """Test parsing HTTPS git spec"""
        url, ref = _parse_git_spec("https://github.com/user/repo.git@v1.0.0")

        assert url == "https://github.com/user/repo.git"
        assert ref == "v1.0.0"

    def test_parse_git_spec_git_plus(self):
        """Test parsing git+ spec"""
        url, ref = _parse_git_spec("git+https://github.com/user/repo.git@main")

        assert url == "https://github.com/user/repo.git"
        assert ref == "main"

    def test_parse_git_spec_no_ref(self):
        """Test parsing git spec without ref"""
        url, ref = _parse_git_spec("https://github.com/user/repo.git")

        assert url == "https://github.com/user/repo.git"
        assert ref == "HEAD"

    def test_parse_git_spec_no_git(self):
        """Test parsing non-git spec"""
        url, ref = _parse_git_spec("1.0.0")

        assert url == "1.0.0"
        assert ref == ""

    @patch('mmodabot.utils.Git')
    def test_resolve_git_reference_success(self, mock_git_class):
        """Test successful git reference resolution"""
        mock_git = MagicMock()
        mock_git.ls_remote.return_value = "abc123456789\trefs/heads/main\n"
        mock_git_class.return_value = mock_git

        result = resolve_git_reference("https://github.com/user/repo.git", "main")

        assert result == "abc123456789"
        mock_git.ls_remote.assert_called_once_with("https://github.com/user/repo.git", "main")

    @patch('mmodabot.utils.Git')
    def test_resolve_git_reference_with_token(self, mock_git_class):
        """Test git reference resolution with token"""
        mock_git = MagicMock()
        mock_git.ls_remote.return_value = "def987654321\trefs/tags/v1.0.0\n"
        mock_git_class.return_value = mock_git

        result = resolve_git_reference("https://github.com/user/repo.git", "v1.0.0", "token123")

        assert result == "def987654321"
        mock_git.ls_remote.assert_called_once_with("https://oauth2:token123@github.com/user/repo.git", "v1.0.0")

    @patch('mmodabot.utils.Git')
    def test_resolve_git_reference_not_found(self, mock_git_class):
        """Test git reference not found"""
        mock_git = MagicMock()
        mock_git.ls_remote.return_value = ""
        mock_git_class.return_value = mock_git

        with pytest.raises(RuntimeError, match="Reference 'main' not found"):
            resolve_git_reference("https://github.com/user/repo.git", "main")

    @patch('mmodabot.utils.Git')
    def test_resolve_git_reference_command_error(self, mock_git_class):
        """Test git command error"""
        mock_git = MagicMock()
        from git import GitCommandError
        mock_git.ls_remote.side_effect = GitCommandError("git", "ls-remote failed")
        mock_git_class.return_value = mock_git

        with pytest.raises(RuntimeError, match="Git command failed"):
            resolve_git_reference("https://github.com/user/repo.git", "main")

    @patch('mmodabot.utils.resolve_git_reference')
    def test_get_unique_spec_git_ref(self, mock_resolve):
        """Test get_unique_spec with git reference"""
        mock_resolve.return_value = "abc123"

        result = get_unique_spec("git+https://github.com/user/repo.git@main")

        assert result == "abc123"
        mock_resolve.assert_called_once_with("https://github.com/user/repo.git", "main")

    @patch('mmodabot.utils.resolve_git_reference')
    def test_get_unique_spec_git_ref_with_token(self, mock_resolve):
        """Test get_unique_spec with git reference and token"""
        mock_resolve.return_value = "def456"

        result = get_unique_spec("git+https://github.com/user/repo.git@v1.0.0")

        assert result == "def456"

    def test_get_unique_spec_plain_version(self):
        """Test get_unique_spec with plain version"""
        result = get_unique_spec("1.0.0")

        assert result == "1.0.0"

    def test_split_registry_image_ref_docker_hub(self):
        """Test splitting Docker Hub image reference"""
        registry, image = split_registry_image_ref("ubuntu:latest")

        assert registry == "docker.io"
        assert image == "ubuntu:latest"

    def test_split_registry_image_ref_with_registry(self):
        """Test splitting image reference with custom registry"""
        registry, image = split_registry_image_ref("registry.example.com/myapp:v1.0")

        assert registry == "registry.example.com"
        assert image == "myapp:v1.0"

    def test_split_registry_image_ref_localhost(self):
        """Test splitting localhost image reference"""
        registry, image = split_registry_image_ref("localhost:5000/myapp:latest")

        assert registry == "localhost:5000"
        assert image == "myapp:latest"

    def test_split_registry_image_ref_invalid(self):
        """Test splitting invalid image reference"""
        with pytest.raises(ValueError, match="Invalid image reference"):
            split_registry_image_ref("")

        with pytest.raises(ValueError, match="Invalid image reference"):
            split_registry_image_ref(None)

    def test_get_registry_api_base(self):
        """Test getting registry API base URL"""
        result = get_registry_api_base("registry.example.com/myapp:v1.0")

        assert result == "registry.example.com"