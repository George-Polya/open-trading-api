"""
Unit tests for Job Manager and Backend Factory.

Tests the orchestration layer for backtest execution including
job submission, status tracking, and result retrieval.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import tempfile

import pytest

from app.core.config import ExecutionProvider, Settings, ExecutionConfig
from app.models.execution import ExecutionJob, ExecutionResult, JobStatus
from app.services.execution.backend import LocalBackend
from app.services.execution.docker_backend import DockerBackend
from app.services.execution.storage import InMemoryJobStorage
from app.services.execution.workspace import LocalWorkspaceManager
from app.services.execution.manager import (
    BackendFactory,
    JobManager,
    create_job_manager,
)


def create_mock_settings(
    provider: ExecutionProvider = ExecutionProvider.LOCAL,
    timeout: int = 300,
    memory_limit: str = "2g",
    allowed_modules: list[str] | None = None,
) -> MagicMock:
    """Create a properly configured mock Settings object."""
    mock_settings = MagicMock(spec=Settings)
    mock_execution = MagicMock(spec=ExecutionConfig)
    mock_execution.provider = provider
    mock_execution.timeout = timeout
    mock_execution.memory_limit = memory_limit
    mock_execution.allowed_modules = allowed_modules or []
    mock_settings.execution = mock_execution
    return mock_settings


class TestBackendFactory:
    """Tests for BackendFactory."""

    def test_create_local_backend(self):
        """Test creating a local backend."""
        backend = BackendFactory.create_local(timeout=60)

        assert isinstance(backend, LocalBackend)

    def test_create_docker_backend(self):
        """Test creating a docker backend."""
        backend = BackendFactory.create_docker(
            memory_limit="1g",
            timeout=120,
        )

        assert isinstance(backend, DockerBackend)

    @patch("app.services.execution.manager.get_settings")
    def test_create_from_settings_local(self, mock_get_settings):
        """Test creating backend from settings with local provider."""
        mock_settings = create_mock_settings(
            provider=ExecutionProvider.LOCAL,
            timeout=300,
            allowed_modules=["pandas", "numpy"],
        )
        mock_get_settings.return_value = mock_settings

        backend = BackendFactory.create()

        assert isinstance(backend, LocalBackend)

    @patch("app.services.execution.manager.get_settings")
    def test_create_from_settings_docker(self, mock_get_settings):
        """Test creating backend from settings with docker provider."""
        mock_settings = create_mock_settings(
            provider=ExecutionProvider.DOCKER,
            timeout=300,
            memory_limit="2g",
        )
        mock_get_settings.return_value = mock_settings

        backend = BackendFactory.create()

        assert isinstance(backend, DockerBackend)

    def test_create_with_invalid_provider(self):
        """Test that invalid provider raises ValueError."""
        mock_settings = create_mock_settings(provider=ExecutionProvider.LOCAL)
        mock_settings.execution.provider = "invalid_provider"

        with pytest.raises(ValueError, match="Unsupported"):
            BackendFactory.create(settings=mock_settings)


class TestJobManager:
    """Tests for JobManager."""

    @pytest.fixture
    def mock_backend(self) -> LocalBackend:
        """Create a mock backend."""
        backend = MagicMock(spec=LocalBackend)
        backend.execute = AsyncMock(return_value=ExecutionResult(
            success=True,
            job_id="test-job",
            status=JobStatus.COMPLETED,
            data={"portfolio_value": 15000},
            logs="Execution completed",
        ))
        backend.cancel = AsyncMock(return_value=True)
        return backend

    @pytest.fixture
    def storage(self) -> InMemoryJobStorage:
        """Create a storage instance."""
        return InMemoryJobStorage()

    @pytest.fixture
    def workspace_manager(self) -> LocalWorkspaceManager:
        """Create a workspace manager."""
        return LocalWorkspaceManager()

    @pytest.fixture
    def job_manager(
        self,
        mock_backend,
        storage,
        workspace_manager,
    ) -> JobManager:
        """Create a JobManager with mocked dependencies."""
        mock_settings = create_mock_settings(
            provider=ExecutionProvider.LOCAL,
            timeout=300,
        )

        return JobManager(
            backend=mock_backend,
            storage=storage,
            workspace_manager=workspace_manager,
            settings=mock_settings,
        )

    @pytest.mark.asyncio
    async def test_run_backtest_success(self, job_manager: JobManager):
        """Test successful backtest execution."""
        code = "def run_backtest(params): return {'result': 'success'}"
        params = {"initial_capital": 10000}

        result = await job_manager.run_backtest(code, params)

        assert result.success is True
        assert result.status == JobStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_run_backtest_stores_job(
        self,
        job_manager: JobManager,
        storage: InMemoryJobStorage,
    ):
        """Test that job is stored during execution."""
        code = "def run_backtest(params): return {}"
        params = {}

        await job_manager.run_backtest(code, params)

        # Check job is in storage
        jobs = await storage.list_by_status()
        assert len(jobs) == 1

    @pytest.mark.asyncio
    async def test_submit_backtest_returns_job_id(self, job_manager: JobManager):
        """Test that submit_backtest returns a job ID."""
        code = "def run_backtest(params): return {}"
        params = {}

        job_id = await job_manager.submit_backtest(code, params)

        assert job_id is not None
        assert job_id.startswith("backtest-")

    @pytest.mark.asyncio
    async def test_get_job_status(
        self,
        job_manager: JobManager,
        storage: InMemoryJobStorage,
    ):
        """Test getting job status."""
        # Create a job directly in storage
        job = ExecutionJob(
            job_id="test-status-job",
            code="print('test')",
            params={},
        )
        await storage.create(job)

        status = await job_manager.get_job_status("test-status-job")

        assert status == JobStatus.PENDING

    @pytest.mark.asyncio
    async def test_get_job_result(
        self,
        job_manager: JobManager,
        storage: InMemoryJobStorage,
    ):
        """Test getting job result."""
        # Create a completed job
        job = ExecutionJob(
            job_id="test-result-job",
            code="print('test')",
            params={},
        )
        job.mark_running()
        job.mark_completed({"portfolio_value": 20000})
        await storage.create(job)

        result = await job_manager.get_job_result("test-result-job")

        assert result.success is True
        assert result.data["portfolio_value"] == 20000

    @pytest.mark.asyncio
    async def test_cancel_job(
        self,
        job_manager: JobManager,
        storage: InMemoryJobStorage,
    ):
        """Test cancelling a job."""
        # Create a running job
        job = ExecutionJob(
            job_id="test-cancel-job",
            code="import time; time.sleep(100)",
            params={},
        )
        job.mark_running()
        await storage.create(job)

        cancelled = await job_manager.cancel_job("test-cancel-job")

        assert cancelled is True

    @pytest.mark.asyncio
    async def test_list_jobs(
        self,
        job_manager: JobManager,
        storage: InMemoryJobStorage,
    ):
        """Test listing jobs."""
        # Create multiple jobs
        for i in range(5):
            job = ExecutionJob(
                job_id=f"list-test-{i}",
                code="print()",
                params={},
            )
            await storage.create(job)

        jobs = await job_manager.list_jobs()

        assert len(jobs) == 5

    @pytest.mark.asyncio
    async def test_list_jobs_with_status_filter(
        self,
        job_manager: JobManager,
        storage: InMemoryJobStorage,
    ):
        """Test listing jobs filtered by status."""
        # Create jobs with different statuses
        pending_job = ExecutionJob(job_id="pending-1", code="", params={})
        completed_job = ExecutionJob(job_id="completed-1", code="", params={})
        completed_job.mark_running()
        completed_job.mark_completed({})

        await storage.create(pending_job)
        await storage.create(completed_job)

        pending_jobs = await job_manager.list_jobs(status=JobStatus.PENDING)
        completed_jobs = await job_manager.list_jobs(status=JobStatus.COMPLETED)

        assert len(pending_jobs) == 1
        assert len(completed_jobs) == 1

    @pytest.mark.asyncio
    async def test_cleanup_old_jobs(
        self,
        job_manager: JobManager,
        storage: InMemoryJobStorage,
    ):
        """Test cleaning up old jobs."""
        from datetime import datetime, timedelta, timezone

        # Create old completed job
        old_job = ExecutionJob(job_id="old-job", code="", params={})
        old_job.created_at = datetime.now(timezone.utc) - timedelta(hours=2)
        old_job.mark_running()
        old_job.mark_completed({})
        await storage.create(old_job)

        # Create recent job
        recent_job = ExecutionJob(job_id="recent-job", code="", params={})
        recent_job.mark_running()
        recent_job.mark_completed({})
        await storage.create(recent_job)

        # Cleanup jobs older than 1 hour
        removed = await job_manager.cleanup_old_jobs(max_age_seconds=3600)

        assert removed == 1

    @pytest.mark.asyncio
    async def test_get_job(
        self,
        job_manager: JobManager,
        storage: InMemoryJobStorage,
    ):
        """Test getting full job object."""
        job = ExecutionJob(
            job_id="test-get-job",
            code="test code",
            params={"key": "value"},
        )
        await storage.create(job)

        retrieved = await job_manager.get_job("test-get-job")

        assert retrieved.job_id == "test-get-job"
        assert retrieved.code == "test code"
        assert retrieved.params == {"key": "value"}


class TestJobManagerWithRealBackend:
    """Integration tests with real LocalBackend."""

    @pytest.fixture
    def real_job_manager(self) -> JobManager:
        """Create a JobManager with real LocalBackend."""
        backend = LocalBackend(default_timeout=30)
        storage = InMemoryJobStorage()
        workspace_manager = LocalWorkspaceManager()

        mock_settings = create_mock_settings(
            provider=ExecutionProvider.LOCAL,
            timeout=30,
        )

        return JobManager(
            backend=backend,
            storage=storage,
            workspace_manager=workspace_manager,
            settings=mock_settings,
        )

    @pytest.mark.asyncio
    async def test_run_simple_code(self, real_job_manager: JobManager):
        """Test running simple code with real backend."""
        code = '''
def run_backtest(params):
    return {"result": params["value"] * 2}
'''
        params = {"value": 21}

        result = await real_job_manager.run_backtest(code, params)

        assert result.success is True
        assert result.data["result"] == 42

    @pytest.mark.asyncio
    async def test_run_failing_code(self, real_job_manager: JobManager):
        """Test running code that raises an error."""
        code = '''
def run_backtest(params):
    raise ValueError("Test error")
'''
        result = await real_job_manager.run_backtest(code, {})

        assert result.success is False
        assert result.status == JobStatus.FAILED


class TestCreateJobManager:
    """Tests for the factory function."""

    @patch("app.services.execution.manager.get_settings")
    def test_create_with_local_settings(self, mock_get_settings):
        """Test creating job manager with local settings."""
        mock_settings = create_mock_settings(
            provider=ExecutionProvider.LOCAL,
            timeout=300,
            allowed_modules=[],
        )
        mock_get_settings.return_value = mock_settings

        manager = create_job_manager()

        assert isinstance(manager.backend, LocalBackend)

    @patch("app.services.execution.manager.get_settings")
    def test_create_with_docker_override(self, mock_get_settings):
        """Test creating job manager with Docker override."""
        mock_settings = create_mock_settings(
            provider=ExecutionProvider.LOCAL,
            timeout=300,
            memory_limit="2g",
        )
        mock_get_settings.return_value = mock_settings

        manager = create_job_manager(use_docker=True)

        assert isinstance(manager.backend, DockerBackend)

    @patch("app.services.execution.manager.get_settings")
    def test_create_with_local_override(self, mock_get_settings):
        """Test creating job manager with local override."""
        mock_settings = create_mock_settings(
            provider=ExecutionProvider.DOCKER,
            timeout=300,
            allowed_modules=[],
        )
        mock_get_settings.return_value = mock_settings

        manager = create_job_manager(use_docker=False)

        assert isinstance(manager.backend, LocalBackend)
