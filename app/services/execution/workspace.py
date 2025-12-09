"""
Workspace preparation and host volume management for code execution.

Handles temporary directory creation, code file serialization, and
path translation for Docker out of Docker (DooD) volume mounting.
"""

import json
import logging
import os
import shutil
import tempfile
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
import uuid

from app.models.execution import ExecutionJob

logger = logging.getLogger(__name__)


class WorkspaceError(Exception):
    """Exception raised for workspace-related errors."""

    pass


class WorkspaceManager(ABC):
    """
    Abstract base class for workspace management.

    Defines the interface for creating, populating, and cleaning up
    execution workspaces.
    """

    @abstractmethod
    async def create_workspace(self, job: ExecutionJob) -> Path:
        """
        Create a workspace for the given job.

        Args:
            job: The execution job.

        Returns:
            Path to the created workspace directory.
        """
        ...

    @abstractmethod
    async def cleanup_workspace(self, workspace_path: Path) -> None:
        """
        Clean up a workspace.

        Args:
            workspace_path: Path to the workspace to clean up.
        """
        ...

    @abstractmethod
    def get_host_path(self, workspace_path: Path) -> Path:
        """
        Get the host filesystem path for a workspace.

        For DooD, the path used to create the workspace may differ from
        the path needed for volume mounting on the host.

        Args:
            workspace_path: The workspace path (as seen from this process).

        Returns:
            The path on the host filesystem (for volume mounting).
        """
        ...


class LocalWorkspaceManager(WorkspaceManager):
    """
    Local workspace manager for direct filesystem access.

    Creates workspaces in a local directory. Suitable for:
    - LocalBackend execution
    - Development/testing environments
    - Non-containerized deployments

    The host path and local path are the same.
    """

    def __init__(
        self,
        base_path: Optional[str] = None,
        prefix: str = "backtest_",
    ):
        """
        Initialize the local workspace manager.

        Args:
            base_path: Base directory for workspaces. If None, uses system temp.
            prefix: Prefix for workspace directory names.
        """
        if base_path:
            self._base_path = Path(base_path)
            self._base_path.mkdir(parents=True, exist_ok=True)
        else:
            self._base_path = Path(tempfile.gettempdir())

        self._prefix = prefix

    async def create_workspace(self, job: ExecutionJob) -> Path:
        """
        Create a workspace for the given job.

        Creates a directory with:
        - backtest_code.py: The code to execute
        - params.json: Execution parameters
        - wrapper.py: Wrapper script for execution

        Args:
            job: The execution job.

        Returns:
            Path to the created workspace directory.
        """
        # Create unique directory name
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        dir_name = f"{self._prefix}{job.job_id}_{timestamp}_{unique_id}"

        workspace = self._base_path / dir_name
        workspace.mkdir(parents=True, exist_ok=True)

        try:
            # Write code file
            code_file = workspace / "backtest_code.py"
            code_file.write_text(job.code, encoding="utf-8")

            # Write params file
            params_file = workspace / "params.json"
            params_file.write_text(
                json.dumps(job.params, indent=2, default=str),
                encoding="utf-8",
            )

            # Write wrapper script
            wrapper_file = workspace / "wrapper.py"
            wrapper_file.write_text(
                self._create_wrapper_script(),
                encoding="utf-8",
            )

            logger.info(f"Created workspace for job {job.job_id}: {workspace}")
            return workspace

        except Exception as e:
            # Clean up on error
            shutil.rmtree(workspace, ignore_errors=True)
            raise WorkspaceError(f"Failed to create workspace: {e}") from e

    async def cleanup_workspace(self, workspace_path: Path) -> None:
        """
        Clean up a workspace.

        Args:
            workspace_path: Path to the workspace to clean up.
        """
        try:
            if workspace_path.exists():
                shutil.rmtree(workspace_path)
                logger.info(f"Cleaned up workspace: {workspace_path}")
        except Exception as e:
            logger.warning(f"Failed to clean up workspace {workspace_path}: {e}")

    def get_host_path(self, workspace_path: Path) -> Path:
        """
        Get the host filesystem path for a workspace.

        For LocalWorkspaceManager, the path is unchanged.

        Args:
            workspace_path: The workspace path.

        Returns:
            The same path.
        """
        return workspace_path

    def _create_wrapper_script(self) -> str:
        """Create the wrapper script for code execution."""
        return '''
"""Wrapper script for backtest execution."""
import json
import sys
import traceback
from pathlib import Path

def main():
    workspace = Path(__file__).parent
    code_file = workspace / "backtest_code.py"
    params_file = workspace / "params.json"
    result_file = workspace / "result.json"

    try:
        # Load params
        with open(params_file, "r", encoding="utf-8") as f:
            params = json.load(f)

        # Initialize result
        result = {"status": "success"}

        # Read and execute the code
        with open(code_file, "r", encoding="utf-8") as f:
            code = f.read()

        # Create namespace for execution
        namespace = {"params": params, "__name__": "__main__"}

        # Execute the code
        exec(code, namespace)

        # Check if run_backtest function was defined
        if "run_backtest" in namespace:
            backtest_result = namespace["run_backtest"](params)
            if isinstance(backtest_result, dict):
                result.update(backtest_result)

        # Write result
        with open(result_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, default=str)

        print("Execution completed successfully")

    except Exception as e:
        error_result = {
            "status": "error",
            "error": str(e),
            "traceback": traceback.format_exc()
        }
        with open(result_file, "w", encoding="utf-8") as f:
            json.dump(error_result, f, indent=2)
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
'''


class DooDBWorkspaceManager(WorkspaceManager):
    """
    Docker out of Docker (DooD) workspace manager.

    Handles path translation between the container's view of the
    filesystem and the host's view, which is necessary when mounting
    volumes from sibling containers.

    Example:
        If this service runs in a container with volume mount:
            host:/data/workspaces -> container:/workspaces

        When creating a workspace at /workspaces/job_123,
        the sibling container needs the host path: /data/workspaces/job_123

    This manager handles the translation automatically.
    """

    def __init__(
        self,
        host_base_path: str,
        container_base_path: Optional[str] = None,
        prefix: str = "backtest_",
    ):
        """
        Initialize the DooD workspace manager.

        Args:
            host_base_path: Base path on the HOST filesystem for workspaces.
                           This is the path that sibling containers will use.
            container_base_path: Base path in THIS container for workspaces.
                                If None, same as host_base_path (direct host access).
            prefix: Prefix for workspace directory names.
        """
        self._host_base_path = Path(host_base_path)
        self._container_base_path = Path(container_base_path or host_base_path)
        self._prefix = prefix

        # Ensure the container path exists
        self._container_base_path.mkdir(parents=True, exist_ok=True)

    async def create_workspace(self, job: ExecutionJob) -> Path:
        """
        Create a workspace for the given job.

        Creates the workspace at the container base path but returns
        a path object. Use get_host_path() to get the path for volume mounting.

        Args:
            job: The execution job.

        Returns:
            Path to the created workspace (container view).
        """
        # Create unique directory name
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        dir_name = f"{self._prefix}{job.job_id}_{timestamp}_{unique_id}"

        workspace = self._container_base_path / dir_name
        workspace.mkdir(parents=True, exist_ok=True)

        try:
            # Write code file
            code_file = workspace / "backtest_code.py"
            code_file.write_text(job.code, encoding="utf-8")

            # Write params file
            params_file = workspace / "params.json"
            params_file.write_text(
                json.dumps(job.params, indent=2, default=str),
                encoding="utf-8",
            )

            # Write wrapper script (for container execution)
            wrapper_file = workspace / "wrapper.py"
            wrapper_file.write_text(
                self._create_container_wrapper_script(),
                encoding="utf-8",
            )

            logger.info(
                f"Created DooD workspace for job {job.job_id}: "
                f"container={workspace}, host={self.get_host_path(workspace)}"
            )
            return workspace

        except Exception as e:
            shutil.rmtree(workspace, ignore_errors=True)
            raise WorkspaceError(f"Failed to create workspace: {e}") from e

    async def cleanup_workspace(self, workspace_path: Path) -> None:
        """
        Clean up a workspace.

        Args:
            workspace_path: Path to the workspace (container view).
        """
        try:
            if workspace_path.exists():
                shutil.rmtree(workspace_path)
                logger.info(f"Cleaned up DooD workspace: {workspace_path}")
        except Exception as e:
            logger.warning(f"Failed to clean up workspace {workspace_path}: {e}")

    def get_host_path(self, workspace_path: Path) -> Path:
        """
        Get the host filesystem path for a workspace.

        Translates the container path to the host path.

        Args:
            workspace_path: The workspace path (container view).

        Returns:
            The path on the host filesystem (for volume mounting).
        """
        # Get the relative path from container base
        try:
            relative_path = workspace_path.relative_to(self._container_base_path)
        except ValueError:
            # Path is not relative to container base, use as-is
            logger.warning(
                f"Workspace path {workspace_path} is not under "
                f"container base {self._container_base_path}"
            )
            return workspace_path

        # Construct host path
        return self._host_base_path / relative_path

    def _create_container_wrapper_script(self) -> str:
        """Create wrapper script for container execution."""
        return '''
"""Wrapper script for backtest execution in container."""
import json
import sys
import traceback
from pathlib import Path

def main():
    # In container, workspace is mounted at /workspace
    workspace = Path("/workspace")
    code_file = workspace / "backtest_code.py"
    params_file = workspace / "params.json"
    result_file = workspace / "result.json"

    try:
        # Load params
        with open(params_file, "r", encoding="utf-8") as f:
            params = json.load(f)

        # Initialize result
        result = {"status": "success"}

        # Read and execute the code
        with open(code_file, "r", encoding="utf-8") as f:
            code = f.read()

        # Create namespace for execution
        namespace = {"params": params, "__name__": "__main__"}

        # Execute the code
        exec(code, namespace)

        # Check if run_backtest function was defined
        if "run_backtest" in namespace:
            backtest_result = namespace["run_backtest"](params)
            if isinstance(backtest_result, dict):
                result.update(backtest_result)

        # Write result
        with open(result_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, default=str)

        print("Execution completed successfully")

    except Exception as e:
        error_result = {
            "status": "error",
            "error": str(e),
            "traceback": traceback.format_exc()
        }
        with open(result_file, "w", encoding="utf-8") as f:
            json.dump(error_result, f, indent=2)
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
'''


def create_workspace_manager(
    backend_type: str = "local",
    host_base_path: Optional[str] = None,
    container_base_path: Optional[str] = None,
) -> WorkspaceManager:
    """
    Factory function to create a workspace manager.

    Args:
        backend_type: Type of workspace manager ("local" or "docker").
        host_base_path: Base path on host filesystem (for Docker).
        container_base_path: Base path in container (for Docker).

    Returns:
        WorkspaceManager instance.
    """
    if backend_type == "docker":
        if not host_base_path:
            raise ValueError("host_base_path is required for Docker workspace manager")
        return DooDBWorkspaceManager(
            host_base_path=host_base_path,
            container_base_path=container_base_path,
        )
    else:
        return LocalWorkspaceManager(base_path=host_base_path)
