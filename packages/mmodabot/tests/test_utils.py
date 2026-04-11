import pytest
from unittest.mock import patch, MagicMock
from mmodabot.utils import (
    get_pypi_package_info, _parse_git_spec, resolve_git_reference,
    get_unique_spec, split_registry_image_ref, get_registry_api_base
)


class TestUtils:

    @pytest.fixture
    def mock_requests_git_ref_success(self):
        with patch('requests.get') as mock_get:
            # Create a mock response
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = """\
001e# service=git-upload-pack
0000015b85cf57f171c007a60a052b11415984f2daf6279b HEADmulti_ack include-tag symref=HEAD:refs/heads/master filter object-format=sha1 agent=git/github-10b0b59c793c-Linux
0040a9ad697497d05502c433c8bfc3167ac96c0e5c46 refs/heads/develop
003f85cf57f171c007a60a052b11415984f2daf6279b refs/heads/master
003f3904bd04108ff8f6b4d44529ef03c2d8074ce094 refs/tags/v1.3.20
003f550d560dfa43e6d8c2904deb6cb293cf4b7ad871 refs/tags/v1.3.21
0000"""

            # Set the mock response
            mock_get.return_value = mock_response
            yield mock_get


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

    def test_resolve_git_reference_head(self, mock_requests_git_ref_success):
        """Test successful git reference resolution: HEAD"""
        result = resolve_git_reference("https://github.com/user/repo.git", "HEAD")

        assert result == "85cf57f171c007a60a052b11415984f2daf6279b"
        mock_requests_git_ref_success.assert_called_once()

    def test_resolve_git_reference_branch(self, mock_requests_git_ref_success):
        """Test successful git reference resolution: branch"""
        result = resolve_git_reference("https://github.com/user/repo.git", "master")

        assert result == "85cf57f171c007a60a052b11415984f2daf6279b"
        mock_requests_git_ref_success.assert_called_once()

    def test_resolve_git_reference_tag(self, mock_requests_git_ref_success):
        """Test successful git reference resolution: tag"""
        result = resolve_git_reference("https://github.com/user/repo.git", "v1.3.20")

        assert result == "3904bd04108ff8f6b4d44529ef03c2d8074ce094"
        mock_requests_git_ref_success.assert_called_once()

    def test_resolve_git_reference_not_exist(self, mock_requests_git_ref_success):
        """Test wrong git reference resolution"""
        with pytest.raises(RuntimeError) as e:
            result = resolve_git_reference("https://github.com/user/repo.git", "spam")
            assert e.value == "Ref spam not found in https://github.com/user/repo.git"

        mock_requests_git_ref_success.assert_called_once()

    @patch('mmodabot.utils.requests.get')
    def test_resolve_git_reference_norepo(self, mock_get):
        """Test git reference resolution: wrong repo"""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Repository not found."

        # Set the mock response
        mock_get.return_value = mock_response
        with pytest.raises(RuntimeError) as e:
            result = resolve_git_reference("https://github.com/user/repo.git", "v1.3.20")
            assert e.value.startswith("Failed to discover refs in https://github.com/user/repo.git.")
        
        mock_get.assert_called_once()

    @patch('mmodabot.utils.resolve_git_reference')
    def test_get_unique_spec_git_ref(self, mock_resolve):
        """Test get_unique_spec with git reference"""
        mock_resolve.return_value = "abc123"

        result = get_unique_spec("git+https://github.com/user/repo.git@main")

        assert result == "abc123"
        mock_resolve.assert_called_once_with("https://github.com/user/repo.git", "main")


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