"""
Unit tests for DockerBackend.

Tests DockerBackend using mocked Docker client to verify correct
container creation parameters and DooD configuration.
"""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import tempfile

import pytest

from app.models.execution import ExecutionJob, JobStatus
from app.services.execution.backend import ExecutionBackend
from app.services.execution.docker_backend import (
    DockerBackend,
    DEFAULT_PYTHON_IMAGE,
)


@pytest.fixture
def docker_backend() -> DockerBackend:
    """Create a DockerBackend instance for testing."""
    return DockerBackend(
        python_image="python:3.13-slim",
        default_timeout=30,
        memory_limit="1g",
        cpu_period=100000,
        cpu_quota=50000,  # 0.5 CPU
        network_mode="none",
        host_workspace_base="/tmp/test_workspaces",
    )


@pytest.fixture
def simple_job() -> ExecutionJob:
    """Create a simple execution job."""
    return ExecutionJob(
        job_id="docker-test-001",
        code="print('Hello from Docker!')",
        params={"initial_capital": 10000},
    )


class TestDockerBackendConfiguration:
    """Tests for DockerBackend configuration."""

    def test_default_python_image(self):
        """Test default Python image constant."""
        assert DEFAULT_PYTHON_IMAGE == "backtest-runner:latest"

    def test_backend_initialization(self, docker_backend: DockerBackend):
        """Test DockerBackend initializes with correct settings."""
        assert docker_backend._python_image == "python:3.13-slim"
        assert docker_backend._default_timeout == 30
        assert docker_backend._memory_limit == "1g"
        assert docker_backend._cpu_period == 100000
        assert docker_backend._cpu_quota == 50000
        assert docker_backend._network_mode == "none"

    def test_is_execution_backend(self, docker_backend: DockerBackend):
        """Test DockerBackend is an ExecutionBackend."""
        assert isinstance(docker_backend, ExecutionBackend)

    def test_parse_memory_limit_gigabytes(self, docker_backend: DockerBackend):
        """Test memory limit parsing for gigabytes."""
        assert docker_backend._parse_memory_limit("2g") == 2 * 1024 * 1024 * 1024

    def test_parse_memory_limit_megabytes(self, docker_backend: DockerBackend):
        """Test memory limit parsing for megabytes."""
        assert docker_backend._parse_memory_limit("512m") == 512 * 1024 * 1024

    def test_parse_memory_limit_kilobytes(self, docker_backend: DockerBackend):
        """Test memory limit parsing for kilobytes."""
        assert docker_backend._parse_memory_limit("1024k") == 1024 * 1024

    def test_parse_memory_limit_bytes(self, docker_backend: DockerBackend):
        """Test memory limit parsing for raw bytes."""
        assert docker_backend._parse_memory_limit("1073741824") == 1073741824


class TestDockerBackendWithMocks:
    """Tests for DockerBackend using mocked Docker client."""

    @pytest.fixture
    def mock_docker(self):
        """Create a mock Docker client."""
        mock = MagicMock()
        mock.images = MagicMock()
        mock.images.inspect = AsyncMock()
        mock.images.pull = AsyncMock()
        mock.containers = MagicMock()
        mock.close = AsyncMock()
        return mock

    @pytest.fixture
    def mock_container(self):
        """Create a mock container."""
        container = MagicMock()
        container.id = "test-container-id-123"
        container.start = AsyncMock()
        container.wait = AsyncMock(return_value={"StatusCode": 0})
        container.log = AsyncMock(return_value=["Execution completed successfully\n"])
        container.kill = AsyncMock()
        container.delete = AsyncMock()
        return container

    @pytest.mark.asyncio
    async def test_execute_creates_container_with_correct_config(
        self,
        docker_backend: DockerBackend,
        simple_job: ExecutionJob,
        mock_docker: MagicMock,
        mock_container: MagicMock,
    ):
        """Test that execute creates container with correct configuration."""
        # Setup mocks
        mock_docker.containers.create = AsyncMock(return_value=mock_container)
        mock_docker.containers.container = MagicMock(return_value=mock_container)

        # Patch Docker client creation
        with patch.object(docker_backend, "_get_docker_client", return_value=mock_docker):
            with tempfile.TemporaryDirectory() as temp_dir:
                workspace = Path(temp_dir)

                result = await docker_backend.execute(simple_job, workspace_path=workspace)

        # Verify container was created
        mock_docker.containers.create.assert_called_once()

        # Get the config that was passed
        call_kwargs = mock_docker.containers.create.call_args
        config = call_kwargs.kwargs.get("config") or call_kwargs.args[0]

        # Verify configuration
        assert config["Image"] == "python:3.13-slim"
        assert config["Cmd"] == ["python", "/workspace/wrapper.py"]
        assert config["WorkingDir"] == "/workspace"

        # Verify host config
        host_config = config["HostConfig"]
        assert host_config["Memory"] == 1 * 1024 * 1024 * 1024  # 1g
        assert host_config["CpuPeriod"] == 100000
        assert host_config["CpuQuota"] == 50000
        assert host_config["NetworkMode"] == "none"

        # Verify security options
        assert "ALL" in host_config["CapDrop"]
        assert "no-new-privileges" in host_config["SecurityOpt"]

    @pytest.mark.asyncio
    async def test_execute_pulls_image_if_not_exists(
        self,
        docker_backend: DockerBackend,
        simple_job: ExecutionJob,
        mock_docker: MagicMock,
        mock_container: MagicMock,
    ):
        """Test that execute pulls image if it doesn't exist."""
        # Setup mocks - image doesn't exist
        mock_docker.images.inspect = AsyncMock(side_effect=Exception("Image not found"))
        mock_docker.containers.create = AsyncMock(return_value=mock_container)
        mock_docker.containers.container = MagicMock(return_value=mock_container)

        with patch.object(docker_backend, "_get_docker_client", return_value=mock_docker):
            with tempfile.TemporaryDirectory() as temp_dir:
                workspace = Path(temp_dir)
                await docker_backend.execute(simple_job, workspace_path=workspace)

        # Verify image was pulled
        mock_docker.images.pull.assert_called_once_with("python:3.13-slim")

    @pytest.mark.asyncio
    async def test_execute_mounts_workspace_correctly(
        self,
        docker_backend: DockerBackend,
        simple_job: ExecutionJob,
        mock_docker: MagicMock,
        mock_container: MagicMock,
    ):
        """Test that workspace is mounted correctly for DooD."""
        mock_docker.containers.create = AsyncMock(return_value=mock_container)
        mock_docker.containers.container = MagicMock(return_value=mock_container)

        with patch.object(docker_backend, "_get_docker_client", return_value=mock_docker):
            with tempfile.TemporaryDirectory() as temp_dir:
                workspace = Path(temp_dir)
                await docker_backend.execute(simple_job, workspace_path=workspace)

        # Get the config
        call_kwargs = mock_docker.containers.create.call_args
        config = call_kwargs.kwargs.get("config") or call_kwargs.args[0]

        # Verify bind mount
        binds = config["HostConfig"]["Binds"]
        assert len(binds) == 1
        assert binds[0].endswith(":/workspace:rw")

    @pytest.mark.asyncio
    async def test_execute_sets_job_labels(
        self,
        docker_backend: DockerBackend,
        simple_job: ExecutionJob,
        mock_docker: MagicMock,
        mock_container: MagicMock,
    ):
        """Test that container has correct labels."""
        mock_docker.containers.create = AsyncMock(return_value=mock_container)
        mock_docker.containers.container = MagicMock(return_value=mock_container)

        with patch.object(docker_backend, "_get_docker_client", return_value=mock_docker):
            with tempfile.TemporaryDirectory() as temp_dir:
                workspace = Path(temp_dir)
                await docker_backend.execute(simple_job, workspace_path=workspace)

        # Get the config
        call_kwargs = mock_docker.containers.create.call_args
        config = call_kwargs.kwargs.get("config") or call_kwargs.args[0]

        # Verify labels
        labels = config["Labels"]
        assert labels["backtest.job_id"] == simple_job.job_id
        assert labels["backtest.managed"] == "true"

    @pytest.mark.asyncio
    async def test_execute_returns_success_result(
        self,
        docker_backend: DockerBackend,
        simple_job: ExecutionJob,
        mock_docker: MagicMock,
        mock_container: MagicMock,
    ):
        """Test that successful execution returns correct result."""
        mock_docker.containers.create = AsyncMock(return_value=mock_container)
        mock_docker.containers.container = MagicMock(return_value=mock_container)

        with patch.object(docker_backend, "_get_docker_client", return_value=mock_docker):
            with tempfile.TemporaryDirectory() as temp_dir:
                workspace = Path(temp_dir)

                result = await docker_backend.execute(simple_job, workspace_path=workspace)

        assert result.success is True
        assert result.status == JobStatus.COMPLETED
        assert result.job_id == simple_job.job_id

    @pytest.mark.asyncio
    async def test_execute_handles_container_failure(
        self,
        docker_backend: DockerBackend,
        simple_job: ExecutionJob,
        mock_docker: MagicMock,
        mock_container: MagicMock,
    ):
        """Test that container failure is handled correctly."""
        # Container exits with error
        mock_container.wait = AsyncMock(return_value={"StatusCode": 1})
        mock_container.log = AsyncMock(return_value=["Error: Something went wrong\n"])

        mock_docker.containers.create = AsyncMock(return_value=mock_container)
        mock_docker.containers.container = MagicMock(return_value=mock_container)

        with patch.object(docker_backend, "_get_docker_client", return_value=mock_docker):
            with tempfile.TemporaryDirectory() as temp_dir:
                workspace = Path(temp_dir)
                result = await docker_backend.execute(simple_job, workspace_path=workspace)

        assert result.success is False
        assert result.status == JobStatus.FAILED

    @pytest.mark.asyncio
    async def test_execute_handles_timeout(
        self,
        docker_backend: DockerBackend,
        mock_docker: MagicMock,
        mock_container: MagicMock,
    ):
        """Test that timeout is handled correctly."""
        job = ExecutionJob(
            job_id="timeout-test",
            code="import time; time.sleep(100)",
            params={},
            timeout_seconds=1,
        )

        # Container wait times out
        mock_container.wait = AsyncMock(side_effect=asyncio.TimeoutError())

        mock_docker.containers.create = AsyncMock(return_value=mock_container)
        mock_docker.containers.container = MagicMock(return_value=mock_container)

        with patch.object(docker_backend, "_get_docker_client", return_value=mock_docker):
            with tempfile.TemporaryDirectory() as temp_dir:
                workspace = Path(temp_dir)
                result = await docker_backend.execute(job, workspace_path=workspace)

        assert result.success is False
        assert result.status == JobStatus.TIMEOUT
        assert "timed out" in result.error.lower()

        # Verify container was killed
        mock_container.kill.assert_called()

    @pytest.mark.asyncio
    async def test_execute_cleans_up_container(
        self,
        docker_backend: DockerBackend,
        simple_job: ExecutionJob,
        mock_docker: MagicMock,
        mock_container: MagicMock,
    ):
        """Test that container is cleaned up after execution."""
        mock_docker.containers.create = AsyncMock(return_value=mock_container)
        mock_docker.containers.container = MagicMock(return_value=mock_container)

        with patch.object(docker_backend, "_get_docker_client", return_value=mock_docker):
            with tempfile.TemporaryDirectory() as temp_dir:
                workspace = Path(temp_dir)
                await docker_backend.execute(simple_job, workspace_path=workspace)

        # Verify container was deleted
        mock_container.delete.assert_called_with(force=True)

    @pytest.mark.asyncio
    async def test_cancel_kills_container(
        self,
        docker_backend: DockerBackend,
        mock_docker: MagicMock,
        mock_container: MagicMock,
    ):
        """Test that cancel kills the container."""
        job_id = "cancel-test"
        docker_backend._running_containers[job_id] = mock_container.id
        docker_backend._job_statuses[job_id] = JobStatus.RUNNING

        mock_docker.containers.container = MagicMock(return_value=mock_container)

        with patch.object(docker_backend, "_get_docker_client", return_value=mock_docker):
            result = await docker_backend.cancel(job_id)

        assert result is True
        mock_container.kill.assert_called_once()
        assert docker_backend._job_statuses[job_id] == JobStatus.CANCELLED


class TestDockerBackendWorkspace:
    """Tests for workspace preparation."""

    @pytest.mark.asyncio
    async def test_prepare_workspace_creates_files(
        self,
        docker_backend: DockerBackend,
        simple_job: ExecutionJob,
    ):
        """Test that workspace is prepared with correct files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)

            await docker_backend._prepare_workspace(workspace, simple_job)

            # Check files exist
            assert (workspace / "backtest_code.py").exists()
            assert (workspace / "params.json").exists()
            assert (workspace / "wrapper.py").exists()

            # Check content
            code_content = (workspace / "backtest_code.py").read_text()
            assert simple_job.code in code_content

    def test_wrapper_script_content(self, docker_backend: DockerBackend):
        """Test wrapper script contains necessary components."""
        wrapper = docker_backend._create_wrapper_script()

        # Check required imports
        assert "import json" in wrapper
        assert "import sys" in wrapper
        assert "import traceback" in wrapper

        # Check workspace paths
        assert '"/workspace"' in wrapper
        assert "backtest_code.py" in wrapper
        assert "params.json" in wrapper
        assert "result.json" in wrapper

        # Check error handling
        assert "try:" in wrapper
        assert "except Exception" in wrapper

        # Check run_backtest handling
        assert "run_backtest" in wrapper


class TestDockerBackendStatus:
    """Tests for status tracking."""

    @pytest.mark.asyncio
    async def test_get_status_unknown_job(self, docker_backend: DockerBackend):
        """Test getting status of unknown job returns PENDING."""
        status = await docker_backend.get_status("unknown-job")
        assert status == JobStatus.PENDING

    @pytest.mark.asyncio
    async def test_cleanup_removes_tracking(self, docker_backend: DockerBackend):
        """Test that cleanup removes job tracking."""
        job_id = "cleanup-test"
        docker_backend._job_statuses[job_id] = JobStatus.COMPLETED

        await docker_backend.cleanup(job_id)

        assert job_id not in docker_backend._job_statuses

    def test_running_container_count(self, docker_backend: DockerBackend):
        """Test running container count tracking."""
        assert docker_backend.running_container_count == 0

        docker_backend._running_containers["job1"] = "container1"
        docker_backend._running_containers["job2"] = "container2"

        assert docker_backend.running_container_count == 2
