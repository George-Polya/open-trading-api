"""
Docker-based execution backend using Docker out of Docker (DooD).

Spawns sibling containers via the mounted Docker socket for isolated
code execution with resource limits and network restrictions.
"""

import asyncio
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Optional

from app.models.execution import ExecutionJob, ExecutionResult, JobStatus
from app.services.execution.backend import (
    ExecutionBackend,
    ExecutionError,
    ExecutionTimeoutError,
)

logger = logging.getLogger(__name__)

# Default Python image for backtest execution
DEFAULT_PYTHON_IMAGE = "backtest-runner:latest"


class DockerBackend(ExecutionBackend):
    """
    Docker-based execution backend using Docker out of Docker (DooD).

    Spawns sibling containers by communicating with the Docker daemon
    via the mounted host socket (/var/run/docker.sock). This allows
    the service container to create isolated containers on the host.

    Features:
    - Network isolation (none or restricted)
    - Memory limits
    - CPU limits
    - Execution timeout
    - Volume mounting for code injection

    Note: For DooD to work, the service container must have:
    - /var/run/docker.sock mounted as a volume
    - Appropriate permissions to communicate with Docker daemon

    Example docker-compose.yml:
        services:
          backtest-service:
            volumes:
              - /var/run/docker.sock:/var/run/docker.sock
    """

    def __init__(
        self,
        python_image: str = DEFAULT_PYTHON_IMAGE,
        default_timeout: int = 300,
        memory_limit: str = "2g",
        cpu_period: int = 100000,
        cpu_quota: int = 100000,  # 1 CPU
        network_mode: str = "none",
        docker_socket_url: Optional[str] = None,
        host_workspace_base: Optional[str] = None,
        container_workspace_base: Optional[str] = None,
    ):
        """
        Initialize the DockerBackend.

        Args:
            python_image: Docker image for Python execution.
            default_timeout: Default execution timeout in seconds.
            memory_limit: Memory limit for containers (Docker format, e.g., "2g").
            cpu_period: CPU period in microseconds.
            cpu_quota: CPU quota in microseconds.
            network_mode: Network mode ("none" for isolation, "bridge" for network).
            docker_socket_url: Docker socket URL (e.g., 'unix:///var/run/docker.sock').
                              If None, uses aiodocker default.
            host_workspace_base: Base path for workspaces on the HOST filesystem.
                                Required for DooD volume mounting.
            container_workspace_base: Base path for workspaces in THIS container.
                                     If different from host_workspace_base, path
                                     translation is needed for DooD.
        """
        self._python_image = python_image
        self._default_timeout = default_timeout
        self._memory_limit = memory_limit
        self._cpu_period = cpu_period
        self._cpu_quota = cpu_quota
        self._network_mode = network_mode
        self._docker_socket_url = docker_socket_url

        # For DooD, workspace paths need to be on the host filesystem
        # so sibling containers can access them
        self._host_workspace_base = host_workspace_base or "/tmp/backtest_workspaces"
        self._container_workspace_base = container_workspace_base or self._host_workspace_base

        # Track running containers
        self._running_containers: dict[str, str] = {}  # job_id -> container_id
        self._job_statuses: dict[str, JobStatus] = {}

        # Docker client (lazy initialized)
        self._docker: Any = None

    async def _get_docker_client(self) -> Any:
        """
        Get or create the Docker client.

        Returns:
            aiodocker.Docker client instance.

        Raises:
            ExecutionError: If Docker client cannot be created.
        """
        if self._docker is None:
            try:
                import aiodocker

                # Use explicit socket URL if provided
                socket_url = self._docker_socket_url
                if socket_url:
                    logger.debug(f"Connecting to Docker at: {socket_url}")
                    self._docker = aiodocker.Docker(url=socket_url)
                else:
                    logger.debug("Connecting to Docker with default socket")
                    self._docker = aiodocker.Docker()
            except ImportError:
                raise ExecutionError(
                    "aiodocker is required for DockerBackend. "
                    "Install it with: pip install aiodocker"
                )
            except Exception as e:
                raise ExecutionError(f"Failed to create Docker client: {e}")
        return self._docker

    async def close(self) -> None:
        """Close the Docker client."""
        if self._docker is not None:
            await self._docker.close()
            self._docker = None

    async def execute(
        self,
        job: ExecutionJob,
        workspace_path: Optional[Path] = None,
    ) -> ExecutionResult:
        """
        Execute code in a Docker container.

        Args:
            job: The execution job containing code and parameters.
            workspace_path: Path to workspace directory ON THE HOST filesystem.

        Returns:
            ExecutionResult with success status and result data.
        """
        logger.info(f"DockerBackend executing job: {job.job_id}")

        # Mark job as running
        job.mark_running()
        self._job_statuses[job.job_id] = JobStatus.RUNNING

        # Use provided workspace or create one
        if workspace_path is None:
            # Create workspace in host-accessible location
            host_workspace = Path(self._host_workspace_base) / f"job_{job.job_id}"
            host_workspace.mkdir(parents=True, exist_ok=True)
            cleanup_workspace = True
        else:
            host_workspace = workspace_path
            cleanup_workspace = False

        container_id: Optional[str] = None

        try:
            # Prepare workspace with code and params
            await self._prepare_workspace(host_workspace, job)

            # Create and run container
            timeout = job.timeout_seconds or self._default_timeout
            container_id = await self._create_container(
                job_id=job.job_id,
                host_workspace=host_workspace,
                timeout=timeout,
            )

            self._running_containers[job.job_id] = container_id

            # Wait for container to complete
            stdout, stderr, exit_code = await self._wait_for_container(
                container_id=container_id,
                timeout=timeout,
            )

            # Process result
            result_file = host_workspace / "result.json"
            result_data = None
            if result_file.exists():
                try:
                    result_data = json.loads(result_file.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    pass

            if exit_code == 0:
                if result_data is None:
                    result_data = {"stdout": stdout}

                job.mark_completed(result_data, logs=stdout + stderr)
                self._job_statuses[job.job_id] = JobStatus.COMPLETED
            else:
                error_msg = stderr or f"Container exited with code {exit_code}"
                if result_data and "error" in result_data:
                    error_msg = result_data.get("error", error_msg)

                job.mark_failed(error_msg, logs=stdout + stderr)
                job.result = result_data
                self._job_statuses[job.job_id] = JobStatus.FAILED

            return ExecutionResult.from_job(job)

        except asyncio.TimeoutError:
            logger.warning(f"Job {job.job_id} timed out")
            job.mark_timeout()
            self._job_statuses[job.job_id] = JobStatus.TIMEOUT
            return ExecutionResult.from_job(job)

        except ExecutionError:
            raise

        except Exception as e:
            logger.exception(f"Job {job.job_id} failed with exception")
            job.mark_failed(str(e))
            self._job_statuses[job.job_id] = JobStatus.FAILED
            return ExecutionResult.from_job(job)

        finally:
            # Clean up container
            if container_id:
                await self._cleanup_container(container_id)

            # Remove from tracking
            self._running_containers.pop(job.job_id, None)

            # Clean up workspace if we created it
            if cleanup_workspace and host_workspace.exists():
                import shutil

                try:
                    shutil.rmtree(host_workspace)
                except Exception as e:
                    logger.warning(f"Failed to cleanup workspace: {e}")

    async def _prepare_workspace(
        self,
        workspace: Path,
        job: ExecutionJob,
    ) -> None:
        """
        Prepare workspace with code and parameters.

        Args:
            workspace: Workspace directory path.
            job: The execution job.
        """
        # Write code
        code_file = workspace / "backtest_code.py"
        code_file.write_text(job.code, encoding="utf-8")

        # Write params
        params_file = workspace / "params.json"
        params_file.write_text(json.dumps(job.params), encoding="utf-8")

        # Write wrapper script
        wrapper_code = self._create_wrapper_script()
        wrapper_file = workspace / "wrapper.py"
        wrapper_file.write_text(wrapper_code, encoding="utf-8")

    def _create_wrapper_script(self) -> str:
        """Create wrapper script for container execution with robust error handling."""
        return '''
"""Wrapper script for backtest execution in container with robust error handling."""
import json
import sys
import traceback
from pathlib import Path

import pandas as pd
import numpy as np

# =============================================================================
# ROBUST BACKTESTING SETUP - Monkey-patch Strategy for safe buy/sell
# =============================================================================

from backtesting import Strategy, Backtest

# Store original methods
_original_buy = Strategy.buy
_original_sell = Strategy.sell


def _safe_buy(self, size=None, limit=None, stop=None, sl=None, tp=None):
    """
    Safe wrapper for Strategy.buy() that validates size parameter.

    Handles common LLM mistakes:
    - size=0 or negative → skip order
    - size is NaN or inf → skip order
    - size between 0 and 1 is fraction of equity (valid)
    - size >= 1 should be whole number of shares
    """
    if size is None:
        return _original_buy(self, size=size, limit=limit, stop=stop, sl=sl, tp=tp)

    try:
        size = float(size)
    except (TypeError, ValueError):
        print(f"Warning: Invalid size {size}, skipping buy order", file=sys.stderr)
        return None

    if np.isnan(size) or np.isinf(size):
        print(f"Warning: size is NaN/inf, skipping buy order", file=sys.stderr)
        return None

    if size <= 0:
        return None

    if size >= 1:
        size = int(size)
        if size < 1:
            return None

    try:
        return _original_buy(self, size=size, limit=limit, stop=stop, sl=sl, tp=tp)
    except Exception as e:
        print(f"Warning: buy order failed: {e}", file=sys.stderr)
        return None


def _safe_sell(self, size=None, limit=None, stop=None, sl=None, tp=None):
    """Safe wrapper for Strategy.sell() that validates size parameter."""
    if size is None:
        return _original_sell(self, size=size, limit=limit, stop=stop, sl=sl, tp=tp)

    try:
        size = float(size)
    except (TypeError, ValueError):
        print(f"Warning: Invalid size {size}, skipping sell order", file=sys.stderr)
        return None

    if np.isnan(size) or np.isinf(size):
        print(f"Warning: size is NaN/inf, skipping sell order", file=sys.stderr)
        return None

    if size <= 0:
        return None

    if size >= 1:
        size = int(size)
        if size < 1:
            return None

    try:
        return _original_sell(self, size=size, limit=limit, stop=stop, sl=sl, tp=tp)
    except Exception as e:
        print(f"Warning: sell order failed: {e}", file=sys.stderr)
        return None


# Apply monkey-patches
Strategy.buy = _safe_buy
Strategy.sell = _safe_sell

print("Robust backtesting environment initialized")


# =============================================================================
# DATA LOADING
# =============================================================================

def load_data(tickers: list[str], start_date: str, end_date: str) -> dict[str, pd.DataFrame]:
    """
    Load market data for the given tickers.

    This function reads pre-fetched CSV files from the workspace data directory.
    The data is injected by the backtest service before execution.
    """
    workspace = Path("/workspace")
    data_dir = workspace / "data"

    result = {}

    if not data_dir.exists():
        print(f"Warning: Data directory {data_dir} does not exist", file=sys.stderr)
        return result

    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)

    for ticker in tickers:
        csv_path = data_dir / f"{ticker}.csv"
        if csv_path.exists():
            try:
                df = pd.read_csv(csv_path, index_col=0, parse_dates=True)
                # Handle timezone-aware vs timezone-naive comparison
                if df.index.tz is not None:
                    df.index = df.index.tz_localize(None)
                df = df[(df.index >= start_dt) & (df.index <= end_dt)]
                result[ticker] = df
                print(f"Loaded {len(df)} records for {ticker}")
            except Exception as e:
                print(f"Warning: Failed to load data for {ticker}: {e}", file=sys.stderr)
        else:
            print(f"Warning: Data file not found for {ticker}: {csv_path}", file=sys.stderr)

    return result


# =============================================================================
# MAIN EXECUTION
# =============================================================================

def main():
    workspace = Path("/workspace")
    code_file = workspace / "backtest_code.py"
    params_file = workspace / "params.json"
    result_file = workspace / "result.json"

    try:
        # Load params
        with open(params_file, "r") as f:
            params = json.load(f)

        # Execute the backtest code
        result = {"status": "success"}

        # Read the code
        with open(code_file, "r") as f:
            code = f.read()

        # Create namespace for execution with all needed imports
        namespace = {
            "params": params,
            "__name__": "__main__",
            "load_data": load_data,
            "pd": pd,
            "np": np,
            "Strategy": Strategy,
            "Backtest": Backtest,
        }

        # Execute the code
        exec(code, namespace)

        # Check if the code defined a 'run_backtest' function
        if "run_backtest" in namespace:
            backtest_result = namespace["run_backtest"](params)
            if isinstance(backtest_result, dict):
                result.update(backtest_result)

        # Save result
        with open(result_file, "w") as f:
            json.dump(result, f)

        print("Execution completed successfully")

    except Exception as e:
        error_result = {
            "status": "error",
            "error": str(e),
            "traceback": traceback.format_exc()
        }
        with open(result_file, "w") as f:
            json.dump(error_result, f)
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
'''

    async def _create_container(
        self,
        job_id: str,
        host_workspace: Path,
        timeout: int,
    ) -> str:
        """
        Create and start a Docker container.

        Args:
            job_id: The job ID.
            host_workspace: Host path to the workspace directory.
            timeout: Execution timeout in seconds.

        Returns:
            Container ID.
        """
        docker = await self._get_docker_client()

        # Ensure the image is available
        try:
            await docker.images.inspect(self._python_image)
            logger.debug(f"Docker image '{self._python_image}' is available")
        except Exception as inspect_error:
            logger.warning(
                f"Image inspect failed for '{self._python_image}': "
                f"{type(inspect_error).__name__}: {inspect_error}"
            )
            logger.info(f"Attempting to pull image: {self._python_image}")
            try:
                await docker.images.pull(self._python_image)
            except Exception as pull_error:
                logger.error(
                    f"Image pull also failed: {type(pull_error).__name__}: {pull_error}"
                )
                raise ExecutionError(
                    f"Docker image '{self._python_image}' is not available. "
                    f"Inspect error: {inspect_error}. "
                    "Build it locally (recommended) with:\n"
                    f"  docker build -f docker/backtest-runner/Dockerfile -t {self._python_image} .\n"
                    "Or configure a different image via `execution.docker_image` in config.yaml."
                ) from pull_error

        # Container configuration
        config = {
            "Image": self._python_image,
            "Cmd": ["python", "/workspace/wrapper.py"],
            "WorkingDir": "/workspace",
            # Run as root to allow writing to mounted workspace
            # Security is maintained via CapDrop, no-new-privileges, and network isolation
            "User": "0:0",
            "HostConfig": {
                "Binds": [f"{host_workspace}:/workspace:rw"],
                "Memory": self._parse_memory_limit(self._memory_limit),
                "CpuPeriod": self._cpu_period,
                "CpuQuota": self._cpu_quota,
                "NetworkMode": self._network_mode,
                # Security options
                "ReadonlyRootfs": False,  # Need to write result.json
                "CapDrop": ["ALL"],
                "SecurityOpt": ["no-new-privileges"],
            },
            "Labels": {
                "backtest.job_id": job_id,
                "backtest.managed": "true",
            },
            "StopTimeout": timeout,
        }

        # Create container
        container = await docker.containers.create(
            config=config,
            name=f"backtest-{job_id}",
        )

        container_id = container.id

        # Start container
        await container.start()

        logger.info(f"Started container {container_id} for job {job_id}")

        return container_id

    def _parse_memory_limit(self, limit: str) -> int:
        """
        Parse memory limit string to bytes.

        Args:
            limit: Memory limit string (e.g., "2g", "512m").

        Returns:
            Memory limit in bytes.
        """
        limit = limit.lower().strip()
        multipliers = {
            "k": 1024,
            "m": 1024 * 1024,
            "g": 1024 * 1024 * 1024,
        }

        for suffix, multiplier in multipliers.items():
            if limit.endswith(suffix):
                return int(limit[:-1]) * multiplier

        return int(limit)

    async def _wait_for_container(
        self,
        container_id: str,
        timeout: int,
    ) -> tuple[str, str, int]:
        """
        Wait for container to complete.

        Args:
            container_id: Container ID.
            timeout: Timeout in seconds.

        Returns:
            Tuple of (stdout, stderr, exit_code).
        """
        docker = await self._get_docker_client()
        container = docker.containers.container(container_id)

        try:
            # Wait for container with timeout
            result = await asyncio.wait_for(
                container.wait(),
                timeout=timeout,
            )

            exit_code = result.get("StatusCode", -1)

            # Get logs
            logs = await container.log(stdout=True, stderr=True)
            stdout = "".join(logs) if logs else ""
            stderr = ""

            return stdout, stderr, exit_code

        except asyncio.TimeoutError:
            # Kill the container
            try:
                await container.kill()
            except Exception:
                pass
            raise

    async def _cleanup_container(self, container_id: str) -> None:
        """
        Clean up a container.

        Args:
            container_id: Container ID.
        """
        try:
            docker = await self._get_docker_client()
            container = docker.containers.container(container_id)

            # Try to stop if running
            try:
                await container.kill()
            except Exception:
                pass

            # Remove container
            try:
                await container.delete(force=True)
            except Exception:
                pass

        except Exception as e:
            logger.warning(f"Failed to cleanup container {container_id}: {e}")

    async def get_status(self, job_id: str) -> JobStatus:
        """
        Get the current status of a job.

        Args:
            job_id: The job ID.

        Returns:
            Current job status.
        """
        return self._job_statuses.get(job_id, JobStatus.PENDING)

    async def cleanup(self, job_id: str) -> None:
        """
        Clean up resources associated with a job.

        Args:
            job_id: The job ID.
        """
        # Clean up container if exists
        container_id = self._running_containers.pop(job_id, None)
        if container_id:
            await self._cleanup_container(container_id)

        # Remove from tracking
        self._job_statuses.pop(job_id, None)

    async def cancel(self, job_id: str) -> bool:
        """
        Cancel a running job.

        Args:
            job_id: The job ID.

        Returns:
            True if the job was cancelled, False if not found or already complete.
        """
        container_id = self._running_containers.get(job_id)
        if container_id is None:
            return False

        try:
            docker = await self._get_docker_client()
            container = docker.containers.container(container_id)

            # Kill the container
            await container.kill()
            self._job_statuses[job_id] = JobStatus.CANCELLED

            return True

        except Exception as e:
            logger.warning(f"Failed to cancel job {job_id}: {e}")
            return False

    @property
    def running_container_count(self) -> int:
        """Get the number of currently running containers."""
        return len(self._running_containers)
