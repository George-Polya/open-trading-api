"""
Execution backend interface and LocalBackend implementation.

Provides an abstract base class for code execution backends and a
local subprocess-based implementation for development/testing.
"""

import asyncio
import json
import logging
import os
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional

from app.models.execution import ExecutionJob, ExecutionResult, JobStatus

logger = logging.getLogger(__name__)


class ExecutionError(Exception):
    """Base exception for execution errors."""

    pass


class ExecutionTimeoutError(ExecutionError):
    """Raised when code execution times out."""

    pass


class ExecutionBackend(ABC):
    """
    Abstract base class for code execution backends.

    Defines the interface for executing code in a sandboxed environment.
    Implementations may use local subprocesses, Docker containers, or
    Kubernetes pods for execution.
    """

    @abstractmethod
    async def execute(
        self,
        job: ExecutionJob,
        workspace_path: Optional[Path] = None,
    ) -> ExecutionResult:
        """
        Execute code for a given job.

        Args:
            job: The execution job containing code and parameters.
            workspace_path: Optional path to a prepared workspace directory
                           containing the code file and any dependencies.

        Returns:
            ExecutionResult with success status and result data.
        """
        ...

    @abstractmethod
    async def get_status(self, job_id: str) -> JobStatus:
        """
        Get the current status of a job.

        Args:
            job_id: The job ID.

        Returns:
            Current job status.
        """
        ...

    @abstractmethod
    async def cleanup(self, job_id: str) -> None:
        """
        Clean up resources associated with a job.

        Args:
            job_id: The job ID.
        """
        ...

    @abstractmethod
    async def cancel(self, job_id: str) -> bool:
        """
        Cancel a running job.

        Args:
            job_id: The job ID.

        Returns:
            True if the job was cancelled, False if not found or already complete.
        """
        ...


class LocalBackend(ExecutionBackend):
    """
    Local subprocess-based execution backend.

    Executes code using asyncio.create_subprocess_exec. Suitable for
    development and testing but NOT for production use (no sandboxing).

    Features:
    - Timeout handling
    - stdout/stderr capture
    - Environment variable isolation
    - Working directory isolation
    """

    def __init__(
        self,
        python_executable: str = "python",
        default_timeout: int = 300,
        allowed_modules: Optional[list[str]] = None,
    ):
        """
        Initialize the LocalBackend.

        Args:
            python_executable: Path to Python executable.
            default_timeout: Default timeout in seconds.
            allowed_modules: List of allowed module names (for documentation only,
                           not enforced at runtime in LocalBackend).
        """
        self._python = python_executable
        self._default_timeout = default_timeout
        self._allowed_modules = allowed_modules or []
        self._running_jobs: dict[str, asyncio.subprocess.Process] = {}
        self._job_statuses: dict[str, JobStatus] = {}

    async def execute(
        self,
        job: ExecutionJob,
        workspace_path: Optional[Path] = None,
    ) -> ExecutionResult:
        """
        Execute code locally using subprocess.

        Args:
            job: The execution job containing code and parameters.
            workspace_path: Optional path to workspace directory.

        Returns:
            ExecutionResult with success status and result data.
        """
        logger.info(f"LocalBackend executing job: {job.job_id}")

        # Mark job as running
        job.mark_running()
        self._job_statuses[job.job_id] = JobStatus.RUNNING

        # Create temporary workspace if not provided
        if workspace_path is None:
            temp_dir = tempfile.mkdtemp(prefix=f"backtest_{job.job_id}_")
            workspace_path = Path(temp_dir)
            cleanup_workspace = True
        else:
            cleanup_workspace = False

        try:
            # Write code to file
            code_file = workspace_path / "backtest_code.py"
            code_file.write_text(job.code, encoding="utf-8")

            # Write params to JSON file
            params_file = workspace_path / "params.json"
            params_file.write_text(json.dumps(job.params), encoding="utf-8")

            # Prepare wrapper script that executes the code and captures results
            wrapper_code = self._create_wrapper_script(code_file, params_file)
            wrapper_file = workspace_path / "wrapper.py"
            wrapper_file.write_text(wrapper_code, encoding="utf-8")

            # Create isolated environment
            env = self._create_isolated_env(workspace_path)

            # Execute the wrapper script
            timeout = job.timeout_seconds or self._default_timeout
            stdout, stderr, return_code = await self._run_subprocess(
                str(wrapper_file),
                cwd=workspace_path,
                env=env,
                timeout=timeout,
                job_id=job.job_id,
            )

            # Process result - always try to read result file first
            result_file = workspace_path / "result.json"
            result_data = None
            if result_file.exists():
                try:
                    result_data = json.loads(result_file.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    pass

            if return_code == 0:
                # Success case
                if result_data is None:
                    result_data = {"stdout": stdout}

                job.mark_completed(result_data, logs=stdout + stderr)
                self._job_statuses[job.job_id] = JobStatus.COMPLETED
            else:
                # Error case - but still include result data if available
                error_msg = stderr or f"Process exited with code {return_code}"
                if result_data and "error" in result_data:
                    error_msg = result_data.get("error", error_msg)

                job.mark_failed(error_msg, logs=stdout + stderr)
                job.result = result_data  # Store error details in result
                self._job_statuses[job.job_id] = JobStatus.FAILED

            return ExecutionResult.from_job(job)

        except asyncio.TimeoutError:
            logger.warning(f"Job {job.job_id} timed out")
            job.mark_timeout()
            self._job_statuses[job.job_id] = JobStatus.TIMEOUT
            return ExecutionResult.from_job(job)

        except Exception as e:
            logger.exception(f"Job {job.job_id} failed with exception")
            job.mark_failed(str(e))
            self._job_statuses[job.job_id] = JobStatus.FAILED
            return ExecutionResult.from_job(job)

        finally:
            # Clean up process tracking
            self._running_jobs.pop(job.job_id, None)

            # Clean up workspace if we created it
            if cleanup_workspace and workspace_path.exists():
                import shutil

                try:
                    shutil.rmtree(workspace_path)
                except Exception as e:
                    logger.warning(f"Failed to cleanup workspace: {e}")

    async def _run_subprocess(
        self,
        script_path: str,
        cwd: Path,
        env: dict[str, str],
        timeout: int,
        job_id: str,
    ) -> tuple[str, str, int]:
        """
        Run a subprocess with timeout.

        Args:
            script_path: Path to the script to execute.
            cwd: Working directory.
            env: Environment variables.
            timeout: Timeout in seconds.
            job_id: Job ID for tracking.

        Returns:
            Tuple of (stdout, stderr, return_code).

        Raises:
            asyncio.TimeoutError: If execution times out.
        """
        process = await asyncio.create_subprocess_exec(
            self._python,
            script_path,
            cwd=cwd,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # Track the process
        self._running_jobs[job_id] = process

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout,
            )
            return (
                stdout.decode("utf-8", errors="replace"),
                stderr.decode("utf-8", errors="replace"),
                process.returncode or 0,
            )
        except asyncio.TimeoutError:
            # Kill the process
            process.kill()
            await process.wait()
            raise

    def _create_wrapper_script(self, code_file: Path, params_file: Path) -> str:
        """
        Create a wrapper script that executes the code and captures results.

        Args:
            code_file: Path to the main code file.
            params_file: Path to the params JSON file.

        Returns:
            Python wrapper script content.
        """
        return f'''
"""Wrapper script for backtest execution with robust error handling."""
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
        # Default behavior: use all available cash
        return _original_buy(self, size=size, limit=limit, stop=stop, sl=sl, tp=tp)

    # Validate size
    try:
        size = float(size)
    except (TypeError, ValueError):
        print(f"Warning: Invalid size {{size}}, skipping buy order", file=sys.stderr)
        return None

    # Check for invalid values
    if np.isnan(size) or np.isinf(size):
        print(f"Warning: size is NaN/inf, skipping buy order", file=sys.stderr)
        return None

    if size <= 0:
        # Skip order silently - this is common when cash is depleted
        return None

    # If size >= 1, ensure it's a reasonable whole number
    if size >= 1:
        size = int(size)
        if size < 1:
            return None
    # If 0 < size < 1, it's a fraction of equity (valid)

    try:
        return _original_buy(self, size=size, limit=limit, stop=stop, sl=sl, tp=tp)
    except Exception as e:
        print(f"Warning: buy order failed: {{e}}", file=sys.stderr)
        return None


def _safe_sell(self, size=None, limit=None, stop=None, sl=None, tp=None):
    """
    Safe wrapper for Strategy.sell() that validates size parameter.
    """
    if size is None:
        return _original_sell(self, size=size, limit=limit, stop=stop, sl=sl, tp=tp)

    try:
        size = float(size)
    except (TypeError, ValueError):
        print(f"Warning: Invalid size {{size}}, skipping sell order", file=sys.stderr)
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
        print(f"Warning: sell order failed: {{e}}", file=sys.stderr)
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

    Reads pre-fetched CSV files from the workspace `data/` directory.
    The data is injected by the backtest service before execution.
    """
    workspace = Path(__file__).parent
    data_dir = workspace / "data"

    result: dict[str, pd.DataFrame] = {{}}
    if not data_dir.exists():
        print(f"Warning: Data directory {{data_dir}} does not exist", file=sys.stderr)
        return result

    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)

    for ticker in tickers:
        csv_path = data_dir / f"{{ticker}}.csv"
        if not csv_path.exists():
            print(f"Warning: Data file not found for {{ticker}}: {{csv_path}}", file=sys.stderr)
            continue
        try:
            df = pd.read_csv(csv_path, index_col=0, parse_dates=True)
            # Handle timezone-aware vs timezone-naive comparison
            if df.index.tz is not None:
                df.index = df.index.tz_localize(None)
            df = df[(df.index >= start_dt) & (df.index <= end_dt)]
            result[ticker] = df
            print(f"Loaded {{len(df)}} records for {{ticker}}")
        except Exception as e:
            print(f"Warning: Failed to load data for {{ticker}}: {{e}}", file=sys.stderr)

    return result


# =============================================================================
# MAIN EXECUTION
# =============================================================================

def main():
    try:
        # Load params
        with open("{params_file}", "r") as f:
            params = json.load(f)

        # Execute the backtest code
        result = {{"status": "success"}}

        # Execute the code file
        with open("{code_file}", "r") as f:
            code = f.read()

        # Create a namespace for execution with all needed imports
        namespace = {{
            "params": params,
            "__name__": "__main__",
            "load_data": load_data,
            "pd": pd,
            "np": np,
            "Strategy": Strategy,
            "Backtest": Backtest,
        }}

        # Execute the code
        exec(code, namespace)

        # Check if the code defined a 'run_backtest' function
        if "run_backtest" in namespace:
            backtest_result = namespace["run_backtest"](params)
            if isinstance(backtest_result, dict):
                result.update(backtest_result)

        # Save result
        with open("result.json", "w") as f:
            json.dump(result, f)

        print("Execution completed successfully")

    except Exception as e:
        error_result = {{
            "status": "error",
            "error": str(e),
            "traceback": traceback.format_exc()
        }}
        with open("result.json", "w") as f:
            json.dump(error_result, f)
        print(f"Error: {{e}}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
'''

    def _create_isolated_env(self, workspace_path: Path) -> dict[str, str]:
        """
        Create an isolated environment for subprocess execution.

        Args:
            workspace_path: Working directory path.

        Returns:
            Environment variables dictionary.
        """
        # Start with minimal environment
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "PYTHONPATH": str(workspace_path),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUNBUFFERED": "1",
            # Prevent access to user home directory configs
            "HOME": str(workspace_path),
            "USERPROFILE": str(workspace_path),
        }

        # Add virtual environment if present
        virtual_env = os.environ.get("VIRTUAL_ENV")
        if virtual_env:
            env["VIRTUAL_ENV"] = virtual_env
            env["PATH"] = f"{virtual_env}/bin:{env['PATH']}"

        # Add conda environment if present
        conda_prefix = os.environ.get("CONDA_PREFIX")
        if conda_prefix:
            env["CONDA_PREFIX"] = conda_prefix
            env["PATH"] = f"{conda_prefix}/bin:{env['PATH']}"

        return env

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
        # Remove from tracking dicts
        self._running_jobs.pop(job_id, None)
        self._job_statuses.pop(job_id, None)

    async def cancel(self, job_id: str) -> bool:
        """
        Cancel a running job.

        Args:
            job_id: The job ID.

        Returns:
            True if the job was cancelled, False if not found or already complete.
        """
        process = self._running_jobs.get(job_id)
        if process is None:
            return False

        # Check if process is still running
        if process.returncode is not None:
            return False

        # Kill the process
        try:
            process.kill()
            await process.wait()
            self._job_statuses[job_id] = JobStatus.CANCELLED
            return True
        except Exception as e:
            logger.warning(f"Failed to cancel job {job_id}: {e}")
            return False

    @property
    def running_job_count(self) -> int:
        """Get the number of currently running jobs."""
        return len(self._running_jobs)
