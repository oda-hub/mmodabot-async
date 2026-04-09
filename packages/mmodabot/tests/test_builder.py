import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from mmodabot.builder import ImageBuilder
from mmodabot.status import BuildStatus


class TestImageBuilder:

    @pytest.mark.asyncio
    async def test_build_starts_job(self, builder, mock_k8interface, mock_commit):
        """Test that build() starts a job and calls notifier"""
        # Make submit_job update the jobs dict
        async def mock_submit_job(job_id, manifest):
            mock_k8interface.jobs[job_id] = {"status": "queued", "manifest": manifest}
        
        mock_k8interface.submit_job = AsyncMock(side_effect=mock_submit_job)
        
        result = await builder.build("main", mock_commit)

        assert result == BuildStatus.QUEUED
        mock_k8interface.submit_job.assert_called_once()
        assert len(mock_k8interface.jobs) == 1

    @pytest.mark.asyncio
    async def test_build_cancels_conflicting_jobs(self, builder, mock_k8interface, mock_commit):
        """Test that build() cancels older jobs for same repo"""
        # Setup existing job
        existing_job_id = f"{builder.repo_id}-oldtag"
        mock_k8interface.jobs[existing_job_id] = {"status": "running", "manifest": {}}

        with patch.object(builder, '_cancel_conflicting_builds', new_callable=AsyncMock) as mock_cancel:
            await builder.build("main", mock_commit)
            mock_cancel.assert_called_once()

    @pytest.mark.asyncio
    async def test_image_exists_true(self, builder):
        """Test image_exists returns True when registry check succeeds"""
        with patch('mmodabot.builder.tag_exists', new_callable=AsyncMock, return_value=True):
            result = await builder.image_exists("test-tag")
            assert result is True

    @pytest.mark.asyncio
    async def test_image_exists_false_on_exception(self, builder):
        """Test image_exists returns False when registry check fails"""
        with patch('mmodabot.builder.tag_exists', new_callable=AsyncMock, side_effect=Exception("Network error")):
            result = await builder.image_exists("test-tag")
            assert result is False

    @pytest.mark.asyncio
    async def test_get_target_image_tag(self, builder):
        """Test tag generation from commit hash"""
        result = await builder.get_target_image_tag("abc123")
        assert result == "test-tag"
        builder.config.hash_base.update.assert_called_once_with(b"abc123")

    def test_job_id_generation(self, builder):
        """Test job ID format"""
        job_id = builder._get_job_id("test-tag")
        expected = f"{builder.repo_id}-test-tag"
        assert job_id == expected