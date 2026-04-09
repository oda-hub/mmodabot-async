import pytest
from unittest.mock import Mock, patch, MagicMock
from fastapi.testclient import TestClient

from mmoda_drupal_module_controller.main import (
    app,
    get_module_name,
    install_module_job,
    delete_module_job,
)
from mmoda_drupal_module_controller.jobs import jobs, create_job, get_job, append_log, update_job
from mmoda_drupal_module_controller.drush import is_module_enabled


@pytest.fixture
def client():
    """Create a FastAPI test client."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def clear_jobs():
    """Clear jobs before and after each test."""
    jobs.clear()
    yield
    jobs.clear()


class TestDrushFunctions:
    """Test drush utility functions."""

    @patch("mmoda_drupal_module_controller.drush.run_drush_capture")
    def test_is_module_enabled_true(self, mock_capture):
        """Test checking if a module is enabled - returns True."""
        mock_capture.return_value = "Package  Name     Status    Version\nmmoda_test  mmoda_test  Enabled   8.x-1.0"
        
        result = is_module_enabled("mmoda_test")
        
        assert result is True
        mock_capture.assert_called_once_with(["pm-list", "--status=enabled", "--package=mmoda_test"])

    @patch("mmoda_drupal_module_controller.drush.run_drush_capture")
    def test_is_module_enabled_false(self, mock_capture):
        """Test checking if a module is enabled - returns False."""
        mock_capture.return_value = "Package  Name     Status    Version\nother_mod  other_mod  Enabled   8.x-1.0"
        
        result = is_module_enabled("mmoda_test")
        
        assert result is False

    @patch("mmoda_drupal_module_controller.drush.run_drush_capture")
    def test_is_module_enabled_error(self, mock_capture):
        """Test checking if a module is enabled - handles drush error."""
        mock_capture.side_effect = RuntimeError("Drush command failed")
        
        result = is_module_enabled("mmoda_test")
        
        assert result is False
    """Test the get_module_name utility function."""

    def test_get_module_name_basic(self):
        """Test basic module name generation."""
        assert get_module_name("my_instrument") == "mmoda_my_instrument"

    def test_get_module_name_with_hyphen(self):
        """Test module name generation with hyphens."""
        assert get_module_name("my-instrument") == "mmoda_my-instrument"

    def test_get_module_name_with_numbers(self):
        """Test module name generation with numbers."""
        assert get_module_name("instrument2") == "mmoda_instrument2"


class TestInstallModuleJob:
    """Test the install_module_job background task."""

    @patch("mmoda_drupal_module_controller.main.drush_lock")
    @patch("mmoda_drupal_module_controller.main.create_module")
    @patch("mmoda_drupal_module_controller.main.enable_module")
    @patch("mmoda_drupal_module_controller.main.disable_module")
    @patch("mmoda_drupal_module_controller.main.uninstall_module")
    @patch("mmoda_drupal_module_controller.main.delete_module")
    @patch("mmoda_drupal_module_controller.main.clear_cache")
    @patch("mmoda_drupal_module_controller.main.is_module_enabled")
    def test_successful_new_install(
        self,
        mock_is_enabled,
        mock_clear_cache,
        mock_delete_module,
        mock_uninstall,
        mock_disable,
        mock_enable,
        mock_create,
        mock_lock,
    ):
        """Test successful installation of a new module."""
        mock_is_enabled.return_value = False  # Module doesn't exist
        mock_lock.return_value.__enter__ = Mock(return_value=None)
        mock_lock.return_value.__exit__ = Mock(return_value=None)
        job_id = "test-job-123"
        create_job(job_id)

        # Execute
        install_module_job(
            job_id=job_id,
            instr_name="test_instr",
            title="Test Instrument",
            messenger="test@example.com",
            creative_work_status="development",
            acknowledgement="Thanks",
            instrument_version="1.0",
            instrument_version_link="http://example.com",
            help_html="<p>Help</p>",
        )

        # Assert
        mock_is_enabled.assert_called_once_with("mmoda_test_instr")
        assert mock_create.called
        assert mock_enable.called
        assert mock_clear_cache.called
        # Should not call disable/uninstall/delete for new install
        assert not mock_disable.called
        assert not mock_uninstall.called
        assert not mock_delete_module.called

        mock_create.assert_called_once_with(
            instr_name="test_instr",
            title="Test Instrument",
            messenger="test@example.com",
            creative_work_status="development",
            acknowledgement="Thanks",
            instrument_version="1.0",
            instrument_version_link="http://example.com",
            help_html="<p>Help</p>",
        )
        mock_enable.assert_called_once_with(job_id, "mmoda_test_instr")
        
        # Check job status
        job = get_job(job_id)
        assert job["status"] == "done"
        assert job["result"] == "installed"
        assert len(job["logs"]) > 0
        assert "Installing new module" in " ".join(job["logs"])

    @patch("mmoda_drupal_module_controller.main.drush_lock")
    @patch("mmoda_drupal_module_controller.main.create_module")
    @patch("mmoda_drupal_module_controller.main.enable_module")
    @patch("mmoda_drupal_module_controller.main.disable_module")
    @patch("mmoda_drupal_module_controller.main.uninstall_module")
    @patch("mmoda_drupal_module_controller.main.delete_module")
    @patch("mmoda_drupal_module_controller.main.clear_cache")
    @patch("mmoda_drupal_module_controller.main.is_module_enabled")
    def test_successful_reinstall(
        self,
        mock_is_enabled,
        mock_clear_cache,
        mock_delete_module,
        mock_uninstall,
        mock_disable,
        mock_enable,
        mock_create,
        mock_lock,
    ):
        """Test successful reinstallation of an existing module."""
        mock_is_enabled.return_value = True  # Module already exists
        mock_lock.return_value.__enter__ = Mock(return_value=None)
        mock_lock.return_value.__exit__ = Mock(return_value=None)
        job_id = "test-job-reinstall"
        create_job(job_id)

        # Execute
        install_module_job(
            job_id=job_id,
            instr_name="existing_instr",
            title="Existing Instrument",
        )

        # Assert
        mock_is_enabled.assert_called_once_with("mmoda_existing_instr")
        # Should perform uninstall sequence first
        assert mock_disable.called
        assert mock_uninstall.called
        assert mock_delete_module.called
        assert mock_clear_cache.call_count == 2  # Once after uninstall, once after install
        # Then create and enable
        assert mock_create.called
        assert mock_enable.called

        mock_disable.assert_called_once_with(job_id, "mmoda_existing_instr")
        mock_uninstall.assert_called_once_with(job_id, "mmoda_existing_instr")
        mock_delete_module.assert_called_once_with("existing_instr")
        mock_create.assert_called_once()
        mock_enable.assert_called_once_with(job_id, "mmoda_existing_instr")
        
        # Check job status
        job = get_job(job_id)
        assert job["status"] == "done"
        assert job["result"] == "installed"
        logs = " ".join(job["logs"])
        assert "Module already exists, performing reinstall" in logs
        assert "Disabling existing module" in logs
        assert "Uninstalling existing module" in logs
        assert "Removing existing files" in logs

    @patch("mmoda_drupal_module_controller.main.drush_lock")
    @patch("mmoda_drupal_module_controller.main.create_module")
    @patch("mmoda_drupal_module_controller.main.enable_module")
    @patch("mmoda_drupal_module_controller.main.clear_cache")
    @patch("mmoda_drupal_module_controller.main.is_module_enabled")
    def test_install_with_defaults(
        self, mock_is_enabled, mock_clear_cache, mock_enable, mock_create, mock_lock
    ):
        """Test module installation with default parameters."""
        mock_is_enabled.return_value = False
        mock_lock.return_value.__enter__ = Mock(return_value=None)
        mock_lock.return_value.__exit__ = Mock(return_value=None)
        job_id = "test-job-456"
        create_job(job_id)

        install_module_job(job_id, "simple_instr", "Simple Instrument")

        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["instr_name"] == "simple_instr"
        assert call_kwargs["title"] == "Simple Instrument"
        assert call_kwargs["messenger"] == ""
        assert call_kwargs["creative_work_status"] == "development"

    @patch("mmoda_drupal_module_controller.main.drush_lock")
    @patch("mmoda_drupal_module_controller.main.create_module")
    @patch("mmoda_drupal_module_controller.main.is_module_enabled")
    def test_install_creation_failure(self, mock_is_enabled, mock_create, mock_lock):
        """Test handling of creation failure."""
        mock_is_enabled.return_value = False
        mock_lock.return_value.__enter__ = Mock(return_value=None)
        mock_lock.return_value.__exit__ = Mock(return_value=None)
        mock_create.side_effect = RuntimeError("Generator failed")
        
        job_id = "test-job-error"
        create_job(job_id)

        install_module_job(job_id, "bad_instr", "Bad Instrument")

        job = get_job(job_id)
        assert job["status"] == "failed"
        assert "Generator failed" in job["error"]

    @patch("mmoda_drupal_module_controller.main.drush_lock")
    @patch("mmoda_drupal_module_controller.main.create_module")
    @patch("mmoda_drupal_module_controller.main.enable_module")
    @patch("mmoda_drupal_module_controller.main.is_module_enabled")
    def test_install_enable_failure(self, mock_is_enabled, mock_enable, mock_create, mock_lock):
        """Test handling of enable failure."""
        mock_is_enabled.return_value = False
        mock_lock.return_value.__enter__ = Mock(return_value=None)
        mock_lock.return_value.__exit__ = Mock(return_value=None)
        mock_enable.side_effect = RuntimeError("Drush command failed")
        
        job_id = "test-job-enable-error"
        create_job(job_id)

        install_module_job(job_id, "enable_fail", "Enable Fail")

        job = get_job(job_id)
        assert job["status"] == "failed"
        assert "Drush command failed" in job["error"]

    @patch("mmoda_drupal_module_controller.main.drush_lock")
    @patch("mmoda_drupal_module_controller.main.create_module")
    @patch("mmoda_drupal_module_controller.main.enable_module")
    @patch("mmoda_drupal_module_controller.main.disable_module")
    @patch("mmoda_drupal_module_controller.main.uninstall_module")
    @patch("mmoda_drupal_module_controller.main.delete_module")
    @patch("mmoda_drupal_module_controller.main.clear_cache")
    @patch("mmoda_drupal_module_controller.main.is_module_enabled")
    def test_install_logs_progress(
        self,
        mock_is_enabled,
        mock_clear_cache,
        mock_delete_module,
        mock_uninstall,
        mock_disable,
        mock_enable,
        mock_create,
        mock_lock,
    ):
        """Test that installation logs progress."""
        mock_is_enabled.return_value = False
        mock_lock.return_value.__enter__ = Mock(return_value=None)
        mock_lock.return_value.__exit__ = Mock(return_value=None)
        job_id = "test-job-logs"
        create_job(job_id)

        install_module_job(job_id, "logged_instr", "Logged Instrument")

        job = get_job(job_id)
        logs = job["logs"]
        assert "Waiting for lock..." in logs
        assert "Lock acquired" in logs
        assert "Installing new module" in logs
        assert "Creating module" in logs
        assert "Enabling module" in logs
        assert "Clearing cache" in logs


class TestDeleteModuleJob:
    """Test the delete_module_job background task."""

    @patch("mmoda_drupal_module_controller.main.drush_lock")
    @patch("mmoda_drupal_module_controller.main.disable_module")
    @patch("mmoda_drupal_module_controller.main.uninstall_module")
    @patch("mmoda_drupal_module_controller.main.delete_module")
    @patch("mmoda_drupal_module_controller.main.clear_cache")
    def test_successful_delete(
        self,
        mock_clear_cache,
        mock_delete_module,
        mock_uninstall,
        mock_disable,
        mock_lock,
    ):
        """Test successful module deletion."""
        mock_lock.return_value.__enter__ = Mock(return_value=None)
        mock_lock.return_value.__exit__ = Mock(return_value=None)
        job_id = "test-delete-123"
        create_job(job_id)

        delete_module_job(job_id, "remove_me")

        assert mock_disable.called
        assert mock_uninstall.called
        assert mock_delete_module.called
        assert mock_clear_cache.called
        mock_disable.assert_called_once_with(job_id, "mmoda_remove_me")
        mock_uninstall.assert_called_once_with(job_id, "mmoda_remove_me")
        mock_delete_module.assert_called_once_with("remove_me")

        job = get_job(job_id)
        assert job["status"] == "done"
        assert job["result"] == "removed"

    @patch("mmoda_drupal_module_controller.main.drush_lock")
    @patch("mmoda_drupal_module_controller.main.disable_module")
    def test_delete_disable_failure(self, mock_disable, mock_lock):
        """Test handling of disable failure during deletion."""
        mock_lock.return_value.__enter__ = Mock(return_value=None)
        mock_lock.return_value.__exit__ = Mock(return_value=None)
        mock_disable.side_effect = RuntimeError("Drush command failed")
        
        job_id = "test-delete-error"
        create_job(job_id)

        delete_module_job(job_id, "bad_module")

        job = get_job(job_id)
        assert job["status"] == "failed"
        assert "Drush command failed" in job["error"]

    @patch("mmoda_drupal_module_controller.main.drush_lock")
    @patch("mmoda_drupal_module_controller.main.disable_module")
    @patch("mmoda_drupal_module_controller.main.uninstall_module")
    @patch("mmoda_drupal_module_controller.main.delete_module")
    @patch("mmoda_drupal_module_controller.main.clear_cache")
    def test_delete_logs_progress(
        self,
        mock_clear_cache,
        mock_delete_module,
        mock_uninstall,
        mock_disable,
        mock_lock,
    ):
        """Test that deletion logs progress."""
        mock_lock.return_value.__enter__ = Mock(return_value=None)
        mock_lock.return_value.__exit__ = Mock(return_value=None)
        job_id = "test-delete-logs"
        create_job(job_id)

        delete_module_job(job_id, "logged_module")

        job = get_job(job_id)
        logs = job["logs"]
        assert "Waiting for lock..." in logs
        assert "Lock acquired" in logs
        assert "Disabling module" in logs
        assert "Uninstalling module" in logs
        assert "Removing files" in logs
        assert "Clearing cache" in logs


class TestCreateModuleEndpoint:
    """Test the POST /modules endpoint."""

    @patch("mmoda_drupal_module_controller.main.install_module_job")
    def test_create_module_endpoint(self, mock_job, client):
        """Test creating a module via API."""
        payload = {
            "instr_name": "my_tool",
            "title": "My Tool",
            "messenger": "test@example.com",
            "creative_work_status": "development",
        }

        response = client.post("/modules", json=payload)

        assert response.status_code == 202
        data = response.json()
        assert "job_id" in data
        assert data["status"] == "queued"

    @patch("mmoda_drupal_module_controller.main.install_module_job")
    def test_create_module_endpoint_response_model(self, mock_job, client):
        """Response model should match ModuleJobCreated."""
        payload = {
            "instr_name": "my_tool2",
            "title": "My Tool 2",
        }

        response = client.post("/modules", json=payload)

        assert response.status_code == 202
        data = response.json()
        assert set(data.keys()) == {"job_id", "status"}
        assert isinstance(data["job_id"], str)
        assert data["status"] == "queued"

    @patch("mmoda_drupal_module_controller.main.install_module_job")
    def test_create_module_endpoint_minimal(self, mock_job, client):
        """Test creating a module with minimal payload."""
        payload = {"instr_name": "minimal", "title": "Minimal Tool"}

        response = client.post("/modules", json=payload)

        assert response.status_code == 202
        data = response.json()
        assert "job_id" in data

    def test_create_module_endpoint_missing_required(self, client):
        """Test creating a module with missing required fields."""
        payload = {"instr_name": "incomplete"}

        response = client.post("/modules", json=payload)

        assert response.status_code == 422  # Validation error


class TestDeleteModuleEndpoint:
    """Test the DELETE /modules/{instr_name} endpoint."""

    @patch("mmoda_drupal_module_controller.main.delete_module_job")
    def test_delete_module_endpoint(self, mock_job, client):
        """Test deleting a module via API."""
        response = client.delete("/modules/my_tool")

        assert response.status_code == 202
        data = response.json()
        assert "job_id" in data
        assert data["status"] == "queued"

    @patch("mmoda_drupal_module_controller.main.delete_module_job")
    def test_delete_module_endpoint_response_model(self, mock_job, client):
        """Response model should match ModuleJobCreated."""
        response = client.delete("/modules/my_tool")

        assert response.status_code == 202
        data = response.json()
        assert set(data.keys()) == {"job_id", "status"}
        assert isinstance(data["job_id"], str)
        assert data["status"] == "queued"


class TestJobStatus:
    """Test the GET /jobs/{job_id} endpoint."""

    def test_get_job_status_existing(self, client):
        """Test retrieving status of existing job."""
        job_id = "test-job-123"
        create_job(job_id)

        response = client.get(f"/jobs/{job_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "queued"
        assert data["created_at"]
        assert data["logs"] == []
        assert data.get("result") is None
        assert data.get("error") is None

    def test_get_job_status_response_model(self, client):
        """Response model should match JobStatus."""
        job_id = "test-job-model"
        create_job(job_id)
        append_log(job_id, "initialized")
        update_job(job_id, status="running")

        response = client.get(f"/jobs/{job_id}")

        assert response.status_code == 200
        data = response.json()
        assert set(data.keys()) == {"status", "created_at", "logs", "result", "error"}
        assert data["status"] == "running"
        assert isinstance(data["created_at"], float)
        assert data["logs"] == ["initialized"]
        assert data["result"] is None
        assert data["error"] is None

    def test_get_job_status_nonexistent(self, client):
        """Test retrieving status of nonexistent job."""
        response = client.get("/jobs/nonexistent-job")

        assert response.status_code == 404

    def test_get_job_status_with_logs(self, client):
        """Test retrieving job status with logs."""
        from mmoda_drupal_module_controller.jobs import append_log, update_job
        
        job_id = "test-job-logs"
        create_job(job_id)
        append_log(job_id, "Step 1")
        append_log(job_id, "Step 2")
        update_job(job_id, status="running")

        response = client.get(f"/jobs/{job_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "running"
        assert len(data["logs"]) == 2
        assert data["logs"][0] == "Step 1"
