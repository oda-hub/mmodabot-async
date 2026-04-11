import hashlib
import os
import tempfile
from unittest.mock import MagicMock, patch

from mmodabot.config import BuilderConfig, Config
import pytest


class TestConfig:
    @pytest.fixture
    def mock_dockerfile_path(self):
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as df:
            df.write("SPAM")
            fn = df.name
        yield fn
        os.remove(fn)

    def test_default(self):
        config = Config()
        assert config.namespace == "default"
        assert config.monitor.groups == []
        assert config.monitor.repos == []
        assert config.builder.nb2w_version_spec == ""

    def test_set_param(self):
        config = Config(
            namespace = "other",
            registrar = {'url': 'http://localhost:9999/'}
        )
        assert config.namespace == 'other'
        assert str(config.registrar.url) == 'http://localhost:9999/'


    def test_dockerfile_content(self, mock_dockerfile_path):
        config = Config(builder=BuilderConfig(dockerfile_path=mock_dockerfile_path))
        assert config.builder.dockerfile_content == 'SPAM'

    def test_job_tmpl_content(self):
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as df:
            df.write("ham: eggs")
            job_tmpl_path = df.name

        config = Config(builder=BuilderConfig(job_tmpl_path=job_tmpl_path))
        assert config.builder.job_tmpl == 'ham: eggs'
        os.remove(job_tmpl_path)

    @pytest.fixture()
    def expected_hash(self):
        hash_base = hashlib.sha256()
        hash_base.update(b'SPAM')
        hash_base.update(b'1.0.0')

    @patch('mmodabot.utils.resolve_git_reference')
    @patch('mmodabot.config.get_pypi_package_info', return_value = {"info": {"version": "1.0.0"}})
    def test_hash_base_empty_nb2w_version(self, mock_pypi, mock_resolve_git_ref, mock_dockerfile_path):
        expected_hash = hashlib.sha256()
        expected_hash.update(b'SPAM')
        expected_hash.update(b'1.0.0')

        config = Config(builder=BuilderConfig(dockerfile_path=mock_dockerfile_path))

        mock_pypi.assert_called_once_with("nb2workflow")
        mock_resolve_git_ref.assert_not_called()
        
        assert config.hash_base.hexdigest() == expected_hash.hexdigest()

    @patch('mmodabot.utils.resolve_git_reference')
    @patch('mmodabot.config.get_pypi_package_info')
    def test_hash_base_given_nb2w_version(self, mock_pypi, mock_resolve_git_ref, mock_dockerfile_path):
        expected_hash = hashlib.sha256()
        expected_hash.update(b'SPAM')
        expected_hash.update(b'1.1.1')

        config = Config(builder=BuilderConfig(dockerfile_path=mock_dockerfile_path, nb2w_version_spec='1.1.1'))

        mock_pypi.assert_not_called()
        mock_resolve_git_ref.assert_not_called()
        
        assert config.hash_base.hexdigest() == expected_hash.hexdigest()

    @patch('mmodabot.utils.resolve_git_reference', return_value="12345678")
    @patch('mmodabot.config.get_pypi_package_info')
    def test_hash_base_given_nb2w_gitbranch(self, mock_pypi, mock_resolve_git_ref, mock_dockerfile_path):
        expected_hash = hashlib.sha256()
        expected_hash.update(b'SPAM')
        expected_hash.update(b'12345678')

        config = Config(builder=BuilderConfig(dockerfile_path=mock_dockerfile_path, nb2w_version_spec='http://github.com/oda-hub/nb2workflow@feature-branch'))

        mock_pypi.assert_not_called()
        mock_resolve_git_ref.assert_called_once_with('http://github.com/oda-hub/nb2workflow', 'feature-branch')
        
        assert config.hash_base.hexdigest() == expected_hash.hexdigest()

    @patch('mmodabot.utils.resolve_git_reference', return_value="12345678")
    @patch('mmodabot.config.get_pypi_package_info')
    def test_hash_base_given_nb2w_githead(self, mock_pypi, mock_resolve_git_ref, mock_dockerfile_path):
        expected_hash = hashlib.sha256()
        expected_hash.update(b'SPAM')
        expected_hash.update(b'12345678')

        config = Config(builder=BuilderConfig(dockerfile_path=mock_dockerfile_path, nb2w_version_spec='http://github.com/oda-hub/nb2workflow'))

        mock_pypi.assert_not_called()
        mock_resolve_git_ref.assert_called_once_with('http://github.com/oda-hub/nb2workflow', 'HEAD')
        
        assert config.hash_base.hexdigest() == expected_hash.hexdigest()

    @patch('mmodabot.utils.resolve_git_reference', return_value="12345678")
    @patch('mmodabot.config.get_pypi_package_info')
    def test_hash_base_given_nb2w_gitplus(self, mock_pypi, mock_resolve_git_ref, mock_dockerfile_path):
        expected_hash = hashlib.sha256()
        expected_hash.update(b'SPAM')
        expected_hash.update(b'12345678')

        config = Config(builder=BuilderConfig(dockerfile_path=mock_dockerfile_path, nb2w_version_spec='git+http://github.com/oda-hub/nb2workflow.git@master'))

        mock_pypi.assert_not_called()
        mock_resolve_git_ref.assert_called_once_with('http://github.com/oda-hub/nb2workflow.git', 'master')
        
        assert config.hash_base.hexdigest() == expected_hash.hexdigest()