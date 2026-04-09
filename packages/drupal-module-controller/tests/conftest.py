"""Pytest configuration and shared fixtures for drupal-module-controller tests."""

import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def mock_subprocess():
    """Mock subprocess.Popen for drush commands."""
    with patch("subprocess.Popen") as mock_popen:
        mock_process = MagicMock()
        mock_process.stdout = []
        mock_process.returncode = 0
        mock_process.wait.return_value = None
        mock_popen.return_value = mock_process
        yield mock_popen


@pytest.fixture
def mock_lock_file(tmp_path):
    """Mock the drush lock file."""
    lock_file = tmp_path / "drush.lock"
    with patch("mmoda_drupal_module_controller.lock.LOCK_FILE", str(lock_file)):
        yield lock_file
