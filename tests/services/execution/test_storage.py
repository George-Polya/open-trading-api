"""
Unit tests for job storage implementations.

Tests InMemoryJobStorage ensuring CRUD operations work for ExecutionJob
objects and status updates persist correctly in memory.
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.models.execution import ExecutionJob, JobStatus
from app.services.execution.storage import (
    InMemoryJobStorage,
    JobNotFoundError,
)


@pytest.fixture
def storage() -> InMemoryJobStorage:
    """Create a fresh in-memory storage instance."""
    return InMemoryJobStorage()


@pytest.fixture
def sample_job() -> ExecutionJob:
    """Create a sample execution job."""
    return ExecutionJob(
        job_id="test-job-001",
        code="print('Hello, World!')",
        params={"initial_capital": 10000},
    )


class TestInMemoryJobStorage:
    """Tests for InMemoryJobStorage."""

    @pytest.mark.asyncio
    async def test_create_job(
        self, storage: InMemoryJobStorage, sample_job: ExecutionJob
    ):
        """Test creating a new job."""
        created = await storage.create(sample_job)

        assert created.job_id == sample_job.job_id
        assert created.status == JobStatus.PENDING
        assert storage.job_count == 1

    @pytest.mark.asyncio
    async def test_create_duplicate_job_raises(
        self, storage: InMemoryJobStorage, sample_job: ExecutionJob
    ):
        """Test that creating a duplicate job raises ValueError."""
        await storage.create(sample_job)

        with pytest.raises(ValueError, match="Job already exists"):
            await storage.create(sample_job)

    @pytest.mark.asyncio
    async def test_get_existing_job(
        self, storage: InMemoryJobStorage, sample_job: ExecutionJob
    ):
        """Test retrieving an existing job."""
        await storage.create(sample_job)

        retrieved = await storage.get(sample_job.job_id)

        assert retrieved.job_id == sample_job.job_id
        assert retrieved.code == sample_job.code

    @pytest.mark.asyncio
    async def test_get_nonexistent_job_raises(self, storage: InMemoryJobStorage):
        """Test that getting a nonexistent job raises JobNotFoundError."""
        with pytest.raises(JobNotFoundError) as exc_info:
            await storage.get("nonexistent-job")

        assert exc_info.value.job_id == "nonexistent-job"

    @pytest.mark.asyncio
    async def test_get_or_none_existing_job(
        self, storage: InMemoryJobStorage, sample_job: ExecutionJob
    ):
        """Test get_or_none with existing job."""
        await storage.create(sample_job)

        retrieved = await storage.get_or_none(sample_job.job_id)

        assert retrieved is not None
        assert retrieved.job_id == sample_job.job_id

    @pytest.mark.asyncio
    async def test_get_or_none_nonexistent_job(self, storage: InMemoryJobStorage):
        """Test get_or_none with nonexistent job returns None."""
        retrieved = await storage.get_or_none("nonexistent-job")

        assert retrieved is None

    @pytest.mark.asyncio
    async def test_update_job(
        self, storage: InMemoryJobStorage, sample_job: ExecutionJob
    ):
        """Test updating an existing job."""
        await storage.create(sample_job)

        # Update the job
        sample_job.mark_running()
        updated = await storage.update(sample_job)

        assert updated.status == JobStatus.RUNNING
        assert updated.started_at is not None

        # Verify persistence
        retrieved = await storage.get(sample_job.job_id)
        assert retrieved.status == JobStatus.RUNNING

    @pytest.mark.asyncio
    async def test_update_nonexistent_job_raises(
        self, storage: InMemoryJobStorage, sample_job: ExecutionJob
    ):
        """Test that updating a nonexistent job raises JobNotFoundError."""
        with pytest.raises(JobNotFoundError):
            await storage.update(sample_job)

    @pytest.mark.asyncio
    async def test_delete_existing_job(
        self, storage: InMemoryJobStorage, sample_job: ExecutionJob
    ):
        """Test deleting an existing job."""
        await storage.create(sample_job)
        assert storage.job_count == 1

        result = await storage.delete(sample_job.job_id)

        assert result is True
        assert storage.job_count == 0

    @pytest.mark.asyncio
    async def test_delete_nonexistent_job(self, storage: InMemoryJobStorage):
        """Test deleting a nonexistent job returns False."""
        result = await storage.delete("nonexistent-job")

        assert result is False

    @pytest.mark.asyncio
    async def test_list_all_jobs(self, storage: InMemoryJobStorage):
        """Test listing all jobs."""
        # Create multiple jobs
        for i in range(5):
            job = ExecutionJob(
                job_id=f"job-{i}",
                code=f"print({i})",
            )
            await storage.create(job)

        jobs = await storage.list_by_status()

        assert len(jobs) == 5

    @pytest.mark.asyncio
    async def test_list_jobs_by_status(self, storage: InMemoryJobStorage):
        """Test listing jobs filtered by status."""
        # Create jobs with different statuses
        pending_job = ExecutionJob(job_id="pending-1", code="code")
        running_job = ExecutionJob(job_id="running-1", code="code")
        completed_job = ExecutionJob(job_id="completed-1", code="code")

        await storage.create(pending_job)
        await storage.create(running_job)
        await storage.create(completed_job)

        running_job.mark_running()
        await storage.update(running_job)

        completed_job.mark_running()
        completed_job.mark_completed({"result": "success"})
        await storage.update(completed_job)

        # Filter by status
        pending_jobs = await storage.list_by_status(status=JobStatus.PENDING)
        running_jobs = await storage.list_by_status(status=JobStatus.RUNNING)
        completed_jobs = await storage.list_by_status(status=JobStatus.COMPLETED)

        assert len(pending_jobs) == 1
        assert len(running_jobs) == 1
        assert len(completed_jobs) == 1

    @pytest.mark.asyncio
    async def test_list_jobs_with_limit(self, storage: InMemoryJobStorage):
        """Test listing jobs with limit."""
        for i in range(10):
            job = ExecutionJob(job_id=f"job-{i}", code="code")
            await storage.create(job)

        jobs = await storage.list_by_status(limit=5)

        assert len(jobs) == 5

    @pytest.mark.asyncio
    async def test_cleanup_old_jobs(self, storage: InMemoryJobStorage):
        """Test cleaning up old jobs."""
        # Create old completed job
        old_job = ExecutionJob(job_id="old-job", code="code")
        old_job.created_at = datetime.now(timezone.utc) - timedelta(hours=2)
        old_job.mark_running()
        old_job.mark_completed({"result": "done"})
        await storage.create(old_job)

        # Create recent completed job
        recent_job = ExecutionJob(job_id="recent-job", code="code")
        recent_job.mark_running()
        recent_job.mark_completed({"result": "done"})
        await storage.create(recent_job)

        # Create old but still running job (should not be cleaned)
        running_job = ExecutionJob(job_id="running-job", code="code")
        running_job.created_at = datetime.now(timezone.utc) - timedelta(hours=2)
        running_job.mark_running()
        await storage.create(running_job)

        # Cleanup jobs older than 1 hour
        removed = await storage.cleanup_old_jobs(max_age_seconds=3600)

        assert removed == 1
        assert storage.job_count == 2
        assert await storage.get_or_none("old-job") is None
        assert await storage.get_or_none("recent-job") is not None
        assert await storage.get_or_none("running-job") is not None

    @pytest.mark.asyncio
    async def test_clear_storage(self, storage: InMemoryJobStorage):
        """Test clearing all jobs from storage."""
        for i in range(5):
            job = ExecutionJob(job_id=f"job-{i}", code="code")
            await storage.create(job)

        assert storage.job_count == 5

        await storage.clear()

        assert storage.job_count == 0

    @pytest.mark.asyncio
    async def test_concurrent_access(self, storage: InMemoryJobStorage):
        """Test concurrent access to storage."""

        async def create_job(job_id: str):
            job = ExecutionJob(job_id=job_id, code="code")
            return await storage.create(job)

        # Create multiple jobs concurrently
        tasks = [create_job(f"job-{i}") for i in range(20)]
        results = await asyncio.gather(*tasks)

        assert len(results) == 20
        assert storage.job_count == 20


class TestExecutionJobModel:
    """Tests for ExecutionJob model methods."""

    def test_mark_running(self, sample_job: ExecutionJob):
        """Test marking a job as running."""
        sample_job.mark_running()

        assert sample_job.status == JobStatus.RUNNING
        assert sample_job.started_at is not None

    def test_mark_completed(self, sample_job: ExecutionJob):
        """Test marking a job as completed."""
        sample_job.mark_running()
        sample_job.mark_completed({"value": 12345}, logs="Execution completed")

        assert sample_job.status == JobStatus.COMPLETED
        assert sample_job.completed_at is not None
        assert sample_job.result == {"value": 12345}
        assert "Execution completed" in sample_job.logs

    def test_mark_failed(self, sample_job: ExecutionJob):
        """Test marking a job as failed."""
        sample_job.mark_running()
        sample_job.mark_failed("Runtime error", logs="Error details")

        assert sample_job.status == JobStatus.FAILED
        assert sample_job.completed_at is not None
        assert sample_job.error == "Runtime error"
        assert "Error details" in sample_job.logs

    def test_mark_timeout(self, sample_job: ExecutionJob):
        """Test marking a job as timed out."""
        sample_job.mark_running()
        sample_job.mark_timeout(logs="Timeout logs")

        assert sample_job.status == JobStatus.TIMEOUT
        assert sample_job.completed_at is not None
        assert "timed out" in sample_job.error.lower()
        assert "Timeout logs" in sample_job.logs

    def test_mark_cancelled(self, sample_job: ExecutionJob):
        """Test marking a job as cancelled."""
        sample_job.mark_cancelled()

        assert sample_job.status == JobStatus.CANCELLED
        assert sample_job.completed_at is not None

    def test_is_terminal(self, sample_job: ExecutionJob):
        """Test is_terminal property."""
        assert not sample_job.is_terminal

        sample_job.mark_running()
        assert not sample_job.is_terminal

        sample_job.mark_completed({"result": "done"})
        assert sample_job.is_terminal

    def test_duration_seconds(self, sample_job: ExecutionJob):
        """Test duration_seconds property."""
        assert sample_job.duration_seconds is None

        sample_job.mark_running()
        # Sleep briefly to get measurable duration
        import time

        time.sleep(0.1)
        sample_job.mark_completed({})

        assert sample_job.duration_seconds is not None
        assert sample_job.duration_seconds >= 0.1

    def test_append_logs(self, sample_job: ExecutionJob):
        """Test appending logs."""
        sample_job.append_logs("Line 1\n")
        sample_job.append_logs("Line 2\n")

        assert "Line 1" in sample_job.logs
        assert "Line 2" in sample_job.logs


class TestExecutionResult:
    """Tests for ExecutionResult model."""

    def test_from_completed_job(self, sample_job: ExecutionJob):
        """Test creating ExecutionResult from a completed job."""
        sample_job.mark_running()
        sample_job.mark_completed({"portfolio_value": 15000}, logs="Done")

        from app.models.execution import ExecutionResult

        result = ExecutionResult.from_job(sample_job)

        assert result.success is True
        assert result.job_id == sample_job.job_id
        assert result.status == JobStatus.COMPLETED
        assert result.data == {"portfolio_value": 15000}
        assert result.error is None
        assert result.duration_seconds is not None

    def test_from_failed_job(self, sample_job: ExecutionJob):
        """Test creating ExecutionResult from a failed job."""
        sample_job.mark_running()
        sample_job.mark_failed("Something went wrong")

        from app.models.execution import ExecutionResult

        result = ExecutionResult.from_job(sample_job)

        assert result.success is False
        assert result.status == JobStatus.FAILED
        assert result.error == "Something went wrong"
        assert result.data is None
