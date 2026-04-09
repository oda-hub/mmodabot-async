import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from kubernetes import client
from mmodabot.k8s_interface import K8SInterface


class TestK8SInterface:
    @pytest.fixture
    def k8s_interface(self):
        """Create K8SInterface instance for testing"""
        return K8SInterface(namespace="test-namespace", job_concurrency=2, job_queue_size=10)

    @patch('mmodabot.k8s_interface.core_v1')
    def test_get_cm_success(self, mock_core_v1, k8s_interface):
        """Test successful ConfigMap retrieval"""
        mock_cm = MagicMock()
        mock_core_v1.read_namespaced_config_map.return_value = mock_cm

        result = k8s_interface.get_cm("test-cm")

        assert result == mock_cm
        mock_core_v1.read_namespaced_config_map.assert_called_once_with(
            name="test-cm", namespace="test-namespace"
        )

    @patch('mmodabot.k8s_interface.core_v1')
    def test_get_cm_not_found_quiet(self, mock_core_v1, k8s_interface):
        """Test ConfigMap not found with quiet=True"""
        from kubernetes.client.exceptions import ApiException
        mock_core_v1.read_namespaced_config_map.side_effect = ApiException(status=404)

        result = k8s_interface.get_cm("test-cm", quiet=True)

        assert result is None

    @patch('mmodabot.k8s_interface.core_v1')
    def test_get_cm_not_found_verbose(self, mock_core_v1, k8s_interface):
        """Test ConfigMap not found with quiet=False"""
        from kubernetes.client.exceptions import ApiException
        mock_core_v1.read_namespaced_config_map.side_effect = ApiException(status=404)

        with patch('mmodabot.k8s_interface.logger') as mock_logger:
            result = k8s_interface.get_cm("test-cm", quiet=False)

            assert result is None
            mock_logger.error.assert_called_once()

    @patch('mmodabot.k8s_interface.core_v1')
    def test_read_cm_data(self, mock_core_v1, k8s_interface):
        """Test reading ConfigMap data"""
        mock_cm = MagicMock()
        mock_cm.data = {"key1": "value1", "key2": "value2"}
        mock_core_v1.read_namespaced_config_map.return_value = mock_cm

        result = k8s_interface.read_cm_data("test-cm")

        expected = {"key1": "value1", "key2": "value2"}
        assert result == expected

    @patch('mmodabot.k8s_interface.core_v1')
    def test_read_cm_data_none_data(self, mock_core_v1, k8s_interface):
        """Test reading ConfigMap data when data is None"""
        mock_cm = MagicMock()
        mock_cm.data = None
        mock_core_v1.read_namespaced_config_map.return_value = mock_cm

        result = k8s_interface.read_cm_data("test-cm")

        assert result == {}

    @patch('mmodabot.k8s_interface.core_v1')
    def test_create_cm_success(self, mock_core_v1, k8s_interface):
        """Test successful ConfigMap creation"""
        mock_cm = MagicMock()
        mock_core_v1.create_namespaced_config_map.return_value = mock_cm

        result = k8s_interface.create_cm("test-cm", {"key": "value"})

        assert result == mock_cm
        mock_core_v1.create_namespaced_config_map.assert_called_once()

    @patch('mmodabot.k8s_interface.core_v1')
    def test_create_cm_failure(self, mock_core_v1, k8s_interface):
        """Test ConfigMap creation failure"""
        from kubernetes.client.exceptions import ApiException
        mock_core_v1.create_namespaced_config_map.side_effect = ApiException(status=500)

        with patch('mmodabot.k8s_interface.logger') as mock_logger:
            result = k8s_interface.create_cm("test-cm", {"key": "value"})

            assert result is None
            mock_logger.error.assert_called_once()

    @patch('mmodabot.k8s_interface.core_v1')
    def test_update_cm_success(self, mock_core_v1, k8s_interface):
        """Test successful ConfigMap update"""
        mock_cm = MagicMock()
        mock_core_v1.patch_namespaced_config_map.return_value = mock_cm

        result = k8s_interface.update_cm("test-cm", {"key": "value"})

        assert result == mock_cm
        mock_core_v1.patch_namespaced_config_map.assert_called_once()

    @patch('mmodabot.k8s_interface.core_v1')
    def test_delete_cm_success(self, mock_core_v1, k8s_interface):
        """Test successful ConfigMap deletion"""
        k8s_interface.delete_cm("test-cm")

        mock_core_v1.delete_namespaced_config_map.assert_called_once_with(
            name="test-cm", namespace="test-namespace"
        )

    @patch('mmodabot.k8s_interface.core_v1')
    def test_delete_cm_failure(self, mock_core_v1, k8s_interface):
        """Test ConfigMap deletion failure"""
        from kubernetes.client.exceptions import ApiException
        mock_core_v1.delete_namespaced_config_map.side_effect = ApiException(status=500)

        with patch('mmodabot.k8s_interface.logger') as mock_logger:
            k8s_interface.delete_cm("test-cm")

            mock_logger.error.assert_called_once()

    @patch('mmodabot.k8s_interface.core_v1')
    def test_verify_secret_exists(self, mock_core_v1, k8s_interface):
        """Test verifying existing secret"""
        result = k8s_interface.verify_secret("test-secret")

        assert result is True
        mock_core_v1.read_namespaced_secret.assert_called_once_with(
            name="test-secret", namespace="test-namespace"
        )

    @patch('mmodabot.k8s_interface.core_v1')
    def test_verify_secret_not_found(self, mock_core_v1, k8s_interface):
        """Test verifying non-existent secret"""
        from kubernetes.client.exceptions import ApiException
        mock_core_v1.read_namespaced_secret.side_effect = ApiException(status=404)

        with patch('mmodabot.k8s_interface.logger') as mock_logger:
            result = k8s_interface.verify_secret("test-secret")

            assert result is False
            mock_logger.warning.assert_called_once()

    @patch('mmodabot.k8s_interface.core_v1')
    def test_read_secret(self, mock_core_v1, k8s_interface):
        """Test reading secret data"""
        import base64
        mock_secret = MagicMock()
        mock_secret.data = {
            "key1": base64.b64encode(b"value1").decode(),
            "key2": base64.b64encode(b"value2").decode()
        }
        mock_core_v1.read_namespaced_secret.return_value = mock_secret

        result = k8s_interface.read_secret("test-secret")

        expected = {"key1": "value1", "key2": "value2"}
        assert result == expected

    @patch('mmodabot.k8s_interface.core_v1')
    def test_extract_pod_logs(self, mock_core_v1, k8s_interface):
        """Test extracting pod logs"""
        mock_pod_list = MagicMock()
        mock_pod = MagicMock()
        mock_pod.metadata.name = "test-pod"
        mock_pod_list.items = [mock_pod]

        mock_logs = "test logs content"
        mock_core_v1.read_namespaced_pod_log.return_value = mock_logs

        with patch('mmodabot.k8s_interface.batch_v1') as mock_batch_v1:
            mock_job = MagicMock()
            mock_job.spec.selector.match_labels = {"job-name": "test-job"}
            mock_batch_v1.read_namespaced_job.return_value = mock_job

            result = k8s_interface.extract_pod_logs("test-job", tail_lines=100)

            assert result == mock_logs
            mock_core_v1.read_namespaced_pod_log.assert_called_once()

    @pytest.mark.asyncio
    async def test_submit_job(self, k8s_interface):
        """Test submitting a job"""
        job_manifest = {"apiVersion": "batch/v1", "metadata": {"name": "test-job"}}

        # Mock the queue as not full
        k8s_interface.job_queue = AsyncMock()
        k8s_interface.job_queue.put = AsyncMock()

        await k8s_interface.submit_job("test-job-id", job_manifest)

        k8s_interface.job_queue.put.assert_called_once_with(("test-job-id", job_manifest))

    @pytest.mark.asyncio
    async def test_cancel_job(self, k8s_interface):
        """Test canceling a job
        
        The K8s job is not deleted directly by cancel() - it's cleaned up by
        ttlSecondsAfterFinished in the job template. This test verifies that
        cancel() marks the job as cancelled and cancels the asyncio task.
        """
        # Setup running job
        k8s_interface.jobs["test-job-id"] = {"status": "running", "manifest": {}}
        
        # Mock the running task
        mock_task = MagicMock()
        k8s_interface.running_tasks["test-job-id"] = mock_task

        await k8s_interface.cancel("test-job-id")

        # Verify job is marked as cancelled
        assert "test-job-id" in k8s_interface.cancelled_jobs
        # Verify job status is updated
        assert k8s_interface.jobs["test-job-id"]["status"] == "cancelled"
        # Verify task cancellation was requested
        mock_task.cancel.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancel_job_not_found(self, k8s_interface):
        """Test canceling a non-existent job"""
        await k8s_interface.cancel("non-existent-job-id")

        # Should still mark as cancelled
        assert "non-existent-job-id" in k8s_interface.cancelled_jobs

    @pytest.mark.asyncio
    async def test_cancel_queued_job(self, k8s_interface):
        """Test canceling a queued job (no running task)"""
        # Setup queued job (no task)
        k8s_interface.jobs["test-job-id"] = {"status": "queued", "manifest": {}}

        await k8s_interface.cancel("test-job-id")

        # Should still be marked as cancelled
        assert "test-job-id" in k8s_interface.cancelled_jobs
        assert k8s_interface.jobs["test-job-id"]["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_run_job_workers(self, k8s_interface):
        """Test starting job workers"""
        with patch.object(k8s_interface, 'job_worker') as mock_worker:
            mock_worker.return_value = AsyncMock()

            # Start workers
            await k8s_interface.run_job_workers()

            # Should have started 2 workers (job_concurrency = 2)
            assert mock_worker.call_count == 2

    @pytest.mark.asyncio
    async def test_stop_job_workers(self, k8s_interface):
        """Test stopping job workers"""
        # Add some dummy worker tasks and running tasks
        event = asyncio.Event()
        task1 = asyncio.create_task(event.wait())
        task2 = asyncio.create_task(event.wait())
        k8s_interface.job_workers = [task1, task2]
        k8s_interface.running_tasks = {
            "task1": MagicMock(),
            "task2": MagicMock()
        }

        await k8s_interface.stop_job_workers()

        # Worker tasks should be cancelled and awaited
        assert task1.cancelled()
        assert task2.cancelled()

        # Running tasks should be cancelled as well
        for task in k8s_interface.running_tasks.values():
            task.cancel.assert_called_once()