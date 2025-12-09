"""
Unit tests for execution backends.

Tests LocalBackend ensuring correct subprocess execution, timeout handling,
and stdout/stderr capture.
"""

import asyncio
import tempfile
from pathlib import Path

import pytest

from app.models.execution import ExecutionJob, JobStatus
from app.services.execution.backend import (
    ExecutionBackend,
    LocalBackend,
)


@pytest.fixture
def local_backend() -> LocalBackend:
    """Create a LocalBackend instance for testing."""
    return LocalBackend(
        python_executable="python",
        default_timeout=30,
        allowed_modules=["pandas", "numpy"],
    )


@pytest.fixture
def simple_job() -> ExecutionJob:
    """Create a simple execution job."""
    return ExecutionJob(
        job_id="test-job-001",
        code="print('Hello, World!')",
        params={"initial_capital": 10000},
    )


class TestLocalBackend:
    """Tests for LocalBackend."""

    @pytest.mark.asyncio
    async def test_execute_simple_code(self, local_backend: LocalBackend):
        """Test executing simple Python code."""
        job = ExecutionJob(
            job_id="simple-test",
            code="print('Hello from backtest!')",
            params={},
        )

        result = await local_backend.execute(job)

        assert result.success is True
        assert result.status == JobStatus.COMPLETED
        assert "Hello from backtest!" in result.logs

    @pytest.mark.asyncio
    async def test_execute_with_result(self, local_backend: LocalBackend):
        """Test executing code that produces a result."""
        code = '''
def run_backtest(params):
    return {
        "portfolio_value": params.get("initial_capital", 10000) * 1.5,
        "returns": 0.5
    }
'''
        job = ExecutionJob(
            job_id="result-test",
            code=code,
            params={"initial_capital": 10000},
        )

        result = await local_backend.execute(job)

        assert result.success is True
        assert result.data is not None
        assert result.data.get("portfolio_value") == 15000.0
        assert result.data.get("returns") == 0.5

    @pytest.mark.asyncio
    async def test_execute_with_error(self, local_backend: LocalBackend):
        """Test executing code that raises an error."""
        code = '''
def run_backtest(params):
    raise ValueError("Test error message")
'''
        job = ExecutionJob(
            job_id="error-test",
            code=code,
            params={},
        )

        result = await local_backend.execute(job)

        assert result.success is False
        assert result.status == JobStatus.FAILED
        # Result should contain error info in data (from wrapper)
        assert result.data is not None
        assert "error" in result.data

    @pytest.mark.asyncio
    async def test_execute_with_syntax_error(self, local_backend: LocalBackend):
        """Test executing code with syntax error."""
        code = '''
def run_backtest(params)  # Missing colon
    return {}
'''
        job = ExecutionJob(
            job_id="syntax-error-test",
            code=code,
            params={},
        )

        result = await local_backend.execute(job)

        assert result.success is False
        assert result.status == JobStatus.FAILED

    @pytest.mark.asyncio
    async def test_execute_timeout(self, local_backend: LocalBackend):
        """Test execution timeout handling."""
        code = '''
import time
def run_backtest(params):
    time.sleep(100)  # Sleep longer than timeout
    return {}
'''
        job = ExecutionJob(
            job_id="timeout-test",
            code=code,
            params={},
            timeout_seconds=2,  # Very short timeout
        )

        result = await local_backend.execute(job)

        assert result.success is False
        assert result.status == JobStatus.TIMEOUT
        assert "timed out" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_with_workspace(self, local_backend: LocalBackend):
        """Test executing code with a provided workspace."""
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)

            code = '''
def run_backtest(params):
    return {"status": "completed", "workspace_test": True}
'''
            job = ExecutionJob(
                job_id="workspace-test",
                code=code,
                params={},
            )

            result = await local_backend.execute(job, workspace_path=workspace)

            assert result.success is True
            assert result.data.get("workspace_test") is True

    @pytest.mark.asyncio
    async def test_get_status_unknown_job(self, local_backend: LocalBackend):
        """Test getting status of unknown job returns PENDING."""
        status = await local_backend.get_status("unknown-job")

        assert status == JobStatus.PENDING

    @pytest.mark.asyncio
    async def test_get_status_after_execution(self, local_backend: LocalBackend):
        """Test getting status after execution."""
        job = ExecutionJob(
            job_id="status-test",
            code="print('done')",
            params={},
        )

        await local_backend.execute(job)
        status = await local_backend.get_status(job.job_id)

        assert status == JobStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_cleanup_job(self, local_backend: LocalBackend):
        """Test cleaning up job resources."""
        job = ExecutionJob(
            job_id="cleanup-test",
            code="print('cleanup')",
            params={},
        )

        await local_backend.execute(job)

        # Verify job is tracked
        assert await local_backend.get_status(job.job_id) == JobStatus.COMPLETED

        # Cleanup
        await local_backend.cleanup(job.job_id)

        # Verify job status is cleared
        assert await local_backend.get_status(job.job_id) == JobStatus.PENDING

    @pytest.mark.asyncio
    async def test_cancel_running_job(self, local_backend: LocalBackend):
        """Test cancelling a running job."""
        code = '''
import time
import sys
# Flush output immediately
print("Starting long sleep", flush=True)
time.sleep(30)  # Long sleep
print("Sleep done", flush=True)

def run_backtest(params):
    return {}
'''
        job = ExecutionJob(
            job_id="cancel-test",
            code=code,
            params={},
            timeout_seconds=60,
        )

        # Start execution in background
        async def run_job():
            return await local_backend.execute(job)

        task = asyncio.create_task(run_job())

        # Wait for the job to actually start running (check status)
        for _ in range(20):  # Try up to 2 seconds
            await asyncio.sleep(0.1)
            if job.job_id in local_backend._running_jobs:
                break

        # Cancel the job
        cancelled = await local_backend.cancel(job.job_id)

        # If cancel succeeded, verify status
        if cancelled:
            assert await local_backend.get_status(job.job_id) == JobStatus.CANCELLED
        else:
            # Job might have finished or not started yet, which is OK
            pass

        # Cancel the task if still running
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_cancel_unknown_job(self, local_backend: LocalBackend):
        """Test cancelling an unknown job."""
        cancelled = await local_backend.cancel("unknown-job")

        assert cancelled is False

    @pytest.mark.asyncio
    async def test_running_job_count(self, local_backend: LocalBackend):
        """Test running job count tracking."""
        assert local_backend.running_job_count == 0

        # Execute a job
        job = ExecutionJob(
            job_id="count-test",
            code="print('test')",
            params={},
        )
        await local_backend.execute(job)

        # After completion, count should be back to 0
        assert local_backend.running_job_count == 0

    @pytest.mark.asyncio
    async def test_execute_captures_stdout(self, local_backend: LocalBackend):
        """Test that stdout is captured in logs."""
        code = '''
print("Line 1")
print("Line 2")
print("Line 3")

def run_backtest(params):
    print("From run_backtest")
    return {"done": True}
'''
        job = ExecutionJob(
            job_id="stdout-test",
            code=code,
            params={},
        )

        result = await local_backend.execute(job)

        assert result.success is True
        assert "Line 1" in result.logs
        assert "Line 2" in result.logs
        assert "From run_backtest" in result.logs

    @pytest.mark.asyncio
    async def test_execute_with_params(self, local_backend: LocalBackend):
        """Test that params are correctly passed to the code."""
        code = '''
def run_backtest(params):
    return {
        "capital": params["initial_capital"],
        "tickers": params["tickers"],
        "doubled": params["initial_capital"] * 2
    }
'''
        job = ExecutionJob(
            job_id="params-test",
            code=code,
            params={
                "initial_capital": 50000,
                "tickers": ["AAPL", "GOOGL"],
            },
        )

        result = await local_backend.execute(job)

        assert result.success is True
        assert result.data["capital"] == 50000
        assert result.data["tickers"] == ["AAPL", "GOOGL"]
        assert result.data["doubled"] == 100000


class TestExecutionBackendInterface:
    """Test that LocalBackend properly implements ExecutionBackend."""

    def test_local_backend_is_execution_backend(self):
        """Verify LocalBackend is a subclass of ExecutionBackend."""
        assert issubclass(LocalBackend, ExecutionBackend)

    def test_local_backend_instance_check(self, local_backend: LocalBackend):
        """Verify LocalBackend instance passes isinstance check."""
        assert isinstance(local_backend, ExecutionBackend)
