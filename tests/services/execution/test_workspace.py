"""
Unit tests for workspace management.

Tests LocalWorkspaceManager and DooDBWorkspaceManager for correct
file creation, path translation, and cleanup.
"""

import json
import tempfile
from pathlib import Path

import pytest

from app.models.execution import ExecutionJob
from app.services.execution.workspace import (
    LocalWorkspaceManager,
    DooDBWorkspaceManager,
    WorkspaceError,
    WorkspaceManager,
    create_workspace_manager,
)


@pytest.fixture
def sample_job() -> ExecutionJob:
    """Create a sample execution job."""
    return ExecutionJob(
        job_id="workspace-test-001",
        code='''
def run_backtest(params):
    capital = params.get("initial_capital", 10000)
    return {"final_value": capital * 1.5}
''',
        params={"initial_capital": 50000, "tickers": ["AAPL", "GOOGL"]},
    )


class TestLocalWorkspaceManager:
    """Tests for LocalWorkspaceManager."""

    @pytest.fixture
    def manager(self) -> LocalWorkspaceManager:
        """Create a local workspace manager."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield LocalWorkspaceManager(base_path=temp_dir)

    @pytest.mark.asyncio
    async def test_create_workspace_creates_directory(
        self,
        sample_job: ExecutionJob,
    ):
        """Test that workspace directory is created."""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = LocalWorkspaceManager(base_path=temp_dir)
            workspace = await manager.create_workspace(sample_job)

            assert workspace.exists()
            assert workspace.is_dir()

    @pytest.mark.asyncio
    async def test_create_workspace_creates_code_file(
        self,
        sample_job: ExecutionJob,
    ):
        """Test that code file is created with correct content."""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = LocalWorkspaceManager(base_path=temp_dir)
            workspace = await manager.create_workspace(sample_job)

            code_file = workspace / "backtest_code.py"
            assert code_file.exists()

            content = code_file.read_text()
            assert "run_backtest" in content
            assert "initial_capital" in content

    @pytest.mark.asyncio
    async def test_create_workspace_creates_params_file(
        self,
        sample_job: ExecutionJob,
    ):
        """Test that params file is created with correct content."""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = LocalWorkspaceManager(base_path=temp_dir)
            workspace = await manager.create_workspace(sample_job)

            params_file = workspace / "params.json"
            assert params_file.exists()

            params = json.loads(params_file.read_text())
            assert params["initial_capital"] == 50000
            assert params["tickers"] == ["AAPL", "GOOGL"]

    @pytest.mark.asyncio
    async def test_create_workspace_creates_wrapper_script(
        self,
        sample_job: ExecutionJob,
    ):
        """Test that wrapper script is created."""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = LocalWorkspaceManager(base_path=temp_dir)
            workspace = await manager.create_workspace(sample_job)

            wrapper_file = workspace / "wrapper.py"
            assert wrapper_file.exists()

            content = wrapper_file.read_text()
            assert "import json" in content
            assert "run_backtest" in content
            assert "result.json" in content

    @pytest.mark.asyncio
    async def test_cleanup_workspace_removes_directory(
        self,
        sample_job: ExecutionJob,
    ):
        """Test that workspace is cleaned up correctly."""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = LocalWorkspaceManager(base_path=temp_dir)
            workspace = await manager.create_workspace(sample_job)

            assert workspace.exists()

            await manager.cleanup_workspace(workspace)

            assert not workspace.exists()

    @pytest.mark.asyncio
    async def test_cleanup_nonexistent_workspace(
        self,
    ):
        """Test that cleanup handles nonexistent workspace gracefully."""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = LocalWorkspaceManager(base_path=temp_dir)
            nonexistent = Path(temp_dir) / "nonexistent"

            # Should not raise
            await manager.cleanup_workspace(nonexistent)

    @pytest.mark.asyncio
    async def test_get_host_path_returns_same_path(
        self,
        sample_job: ExecutionJob,
    ):
        """Test that get_host_path returns the same path for local manager."""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = LocalWorkspaceManager(base_path=temp_dir)
            workspace = await manager.create_workspace(sample_job)

            host_path = manager.get_host_path(workspace)

            assert host_path == workspace

    @pytest.mark.asyncio
    async def test_workspace_name_includes_job_id(
        self,
        sample_job: ExecutionJob,
    ):
        """Test that workspace name includes job ID."""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = LocalWorkspaceManager(base_path=temp_dir)
            workspace = await manager.create_workspace(sample_job)

            assert sample_job.job_id in workspace.name

    @pytest.mark.asyncio
    async def test_workspace_uses_prefix(
        self,
        sample_job: ExecutionJob,
    ):
        """Test that workspace uses configured prefix."""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = LocalWorkspaceManager(
                base_path=temp_dir,
                prefix="custom_prefix_",
            )
            workspace = await manager.create_workspace(sample_job)

            assert workspace.name.startswith("custom_prefix_")

    @pytest.mark.asyncio
    async def test_multiple_workspaces_are_unique(
        self,
        sample_job: ExecutionJob,
    ):
        """Test that multiple workspaces for same job are unique."""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = LocalWorkspaceManager(base_path=temp_dir)

            workspace1 = await manager.create_workspace(sample_job)
            workspace2 = await manager.create_workspace(sample_job)

            assert workspace1 != workspace2
            assert workspace1.exists()
            assert workspace2.exists()


class TestDooDBWorkspaceManager:
    """Tests for DooD workspace manager."""

    @pytest.mark.asyncio
    async def test_create_workspace_creates_directory(
        self,
        sample_job: ExecutionJob,
    ):
        """Test that workspace directory is created."""
        with tempfile.TemporaryDirectory() as host_dir:
            with tempfile.TemporaryDirectory() as container_dir:
                manager = DooDBWorkspaceManager(
                    host_base_path=host_dir,
                    container_base_path=container_dir,
                )
                workspace = await manager.create_workspace(sample_job)

                assert workspace.exists()
                assert workspace.is_dir()
                assert str(workspace).startswith(container_dir)

    @pytest.mark.asyncio
    async def test_get_host_path_translates_correctly(
        self,
        sample_job: ExecutionJob,
    ):
        """Test that get_host_path translates path correctly."""
        with tempfile.TemporaryDirectory() as temp_dir:
            host_base = "/data/workspaces"  # Host path
            container_base = temp_dir  # Container path

            manager = DooDBWorkspaceManager(
                host_base_path=host_base,
                container_base_path=container_base,
            )
            workspace = await manager.create_workspace(sample_job)

            host_path = manager.get_host_path(workspace)

            # Verify translation
            assert str(host_path).startswith(host_base)
            assert workspace.name in str(host_path)

    @pytest.mark.asyncio
    async def test_get_host_path_preserves_relative_structure(
        self,
        sample_job: ExecutionJob,
    ):
        """Test that relative path structure is preserved."""
        with tempfile.TemporaryDirectory() as temp_dir:
            host_base = "/host/workspaces"
            container_base = temp_dir

            manager = DooDBWorkspaceManager(
                host_base_path=host_base,
                container_base_path=container_base,
            )
            workspace = await manager.create_workspace(sample_job)

            # Get relative path from container base
            relative = workspace.relative_to(Path(container_base))

            # Host path should have same relative structure
            host_path = manager.get_host_path(workspace)
            expected_host = Path(host_base) / relative

            assert host_path == expected_host

    @pytest.mark.asyncio
    async def test_wrapper_script_uses_workspace_mount(
        self,
        sample_job: ExecutionJob,
    ):
        """Test that wrapper script uses /workspace mount point."""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = DooDBWorkspaceManager(
                host_base_path="/host/path",
                container_base_path=temp_dir,
            )
            workspace = await manager.create_workspace(sample_job)

            wrapper_content = (workspace / "wrapper.py").read_text()

            # Should use /workspace for container
            assert '"/workspace"' in wrapper_content

    @pytest.mark.asyncio
    async def test_cleanup_removes_workspace(
        self,
        sample_job: ExecutionJob,
    ):
        """Test that cleanup removes workspace directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = DooDBWorkspaceManager(
                host_base_path="/host/path",
                container_base_path=temp_dir,
            )
            workspace = await manager.create_workspace(sample_job)

            assert workspace.exists()

            await manager.cleanup_workspace(workspace)

            assert not workspace.exists()

    @pytest.mark.asyncio
    async def test_same_base_paths(
        self,
        sample_job: ExecutionJob,
    ):
        """Test when host and container paths are the same."""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = DooDBWorkspaceManager(
                host_base_path=temp_dir,
                container_base_path=temp_dir,
            )
            workspace = await manager.create_workspace(sample_job)

            host_path = manager.get_host_path(workspace)

            # Should be equal
            assert host_path == workspace


class TestCreateWorkspaceManager:
    """Tests for the factory function."""

    def test_create_local_manager(self):
        """Test creating a local workspace manager."""
        manager = create_workspace_manager(backend_type="local")

        assert isinstance(manager, LocalWorkspaceManager)

    def test_create_local_manager_with_path(self):
        """Test creating a local workspace manager with base path."""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = create_workspace_manager(
                backend_type="local",
                host_base_path=temp_dir,
            )

            assert isinstance(manager, LocalWorkspaceManager)

    def test_create_docker_manager(self):
        """Test creating a Docker workspace manager."""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = create_workspace_manager(
                backend_type="docker",
                host_base_path="/host/workspaces",
                container_base_path=temp_dir,
            )

            assert isinstance(manager, DooDBWorkspaceManager)

    def test_create_docker_manager_requires_host_path(self):
        """Test that Docker manager requires host_base_path."""
        with pytest.raises(ValueError, match="host_base_path"):
            create_workspace_manager(backend_type="docker")


class TestWorkspaceManagerInterface:
    """Tests for WorkspaceManager interface compliance."""

    def test_local_manager_implements_interface(self):
        """Test LocalWorkspaceManager implements WorkspaceManager."""
        assert issubclass(LocalWorkspaceManager, WorkspaceManager)

    def test_dood_manager_implements_interface(self):
        """Test DooDBWorkspaceManager implements WorkspaceManager."""
        assert issubclass(DooDBWorkspaceManager, WorkspaceManager)
