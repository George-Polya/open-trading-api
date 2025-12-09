"""
Job Manager Service for orchestrating backtest code execution.

Provides a high-level interface for submitting, tracking, and retrieving
backtest execution jobs. Integrates with storage, workspace management,
and execution backends.
"""

import asyncio
import json
import logging
import uuid
from datetime import date
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from app.core.config import ExecutionProvider, Settings, get_settings
from app.models.execution import ExecutionJob, ExecutionResult, JobStatus
from app.providers.data.base import DataProvider, PriceData
from app.services.execution.backend import ExecutionBackend, LocalBackend
from app.services.execution.docker_backend import DockerBackend, DEFAULT_PYTHON_IMAGE
from app.services.execution.storage import InMemoryJobStorage, JobStorage, JobNotFoundError
from app.services.execution.workspace import (
    WorkspaceManager,
    LocalWorkspaceManager,
    DooDBWorkspaceManager,
    create_workspace_manager,
)

logger = logging.getLogger(__name__)


class BackendFactory:
    """
    Factory for creating execution backends.

    Creates the appropriate backend based on configuration settings.
    """

    @staticmethod
    def create(
        settings: Optional[Settings] = None,
        provider: Optional[ExecutionProvider] = None,
    ) -> ExecutionBackend:
        """
        Create an execution backend based on settings.

        Args:
            settings: Application settings. If None, loads from config.
            provider: Override provider selection. If None, uses settings.

        Returns:
            ExecutionBackend instance.

        Raises:
            ValueError: If provider is not supported.
        """
        if settings is None:
            settings = get_settings()

        if provider is None:
            provider = settings.execution.provider

        execution_config = settings.execution

        if provider == ExecutionProvider.LOCAL:
            return LocalBackend(
                python_executable="python",
                default_timeout=execution_config.timeout,
                allowed_modules=execution_config.allowed_modules,
            )

        elif provider == ExecutionProvider.DOCKER:
            return DockerBackend(
                python_image=DEFAULT_PYTHON_IMAGE,
                default_timeout=execution_config.timeout,
                memory_limit=execution_config.memory_limit,
                network_mode="none",  # Isolated by default
            )

        else:
            raise ValueError(f"Unsupported execution provider: {provider}")

    @staticmethod
    def create_local(timeout: int = 300) -> LocalBackend:
        """
        Create a LocalBackend for development/testing.

        Args:
            timeout: Default timeout in seconds.

        Returns:
            LocalBackend instance.
        """
        return LocalBackend(
            python_executable="python",
            default_timeout=timeout,
        )

    @staticmethod
    def create_docker(
        memory_limit: str = "2g",
        timeout: int = 300,
        python_image: str = DEFAULT_PYTHON_IMAGE,
    ) -> DockerBackend:
        """
        Create a DockerBackend for production use.

        Args:
            memory_limit: Memory limit for containers.
            timeout: Default timeout in seconds.
            python_image: Docker image for Python execution.

        Returns:
            DockerBackend instance.
        """
        return DockerBackend(
            python_image=python_image,
            default_timeout=timeout,
            memory_limit=memory_limit,
            network_mode="none",
        )


class JobManager:
    """
    Job Manager Service for orchestrating backtest execution.

    Provides a high-level interface for:
    - Submitting backtest code for execution
    - Tracking job status
    - Retrieving execution results
    - Managing job lifecycle

    Usage:
        manager = JobManager()
        result = await manager.run_backtest(code, params)

        # Or for async execution:
        job_id = await manager.submit_backtest(code, params)
        status = await manager.get_job_status(job_id)
        result = await manager.get_job_result(job_id)
    """

    def __init__(
        self,
        backend: Optional[ExecutionBackend] = None,
        storage: Optional[JobStorage] = None,
        workspace_manager: Optional[WorkspaceManager] = None,
        data_provider: Optional[DataProvider] = None,
        settings: Optional[Settings] = None,
    ):
        """
        Initialize the Job Manager.

        Args:
            backend: Execution backend. If None, created from settings.
            storage: Job storage. If None, uses InMemoryJobStorage.
            workspace_manager: Workspace manager. If None, uses LocalWorkspaceManager.
            data_provider: Data provider for fetching market data. Required for data injection.
            settings: Application settings. If None, loads from config.
        """
        self._settings = settings or get_settings()

        # Initialize backend
        if backend is not None:
            self._backend = backend
        else:
            self._backend = BackendFactory.create(self._settings)

        # Initialize storage
        self._storage = storage or InMemoryJobStorage()

        # Initialize workspace manager
        if workspace_manager is not None:
            self._workspace_manager = workspace_manager
        else:
            self._workspace_manager = create_workspace_manager(
                backend_type="local"
                if self._settings.execution.provider == ExecutionProvider.LOCAL
                else "docker"
            )

        # Data provider for fetching market data
        self._data_provider = data_provider

    @property
    def backend(self) -> ExecutionBackend:
        """Get the execution backend."""
        return self._backend

    @property
    def storage(self) -> JobStorage:
        """Get the job storage."""
        return self._storage

    async def run_backtest(
        self,
        code: str,
        params: dict[str, Any],
        timeout: Optional[int] = None,
    ) -> ExecutionResult:
        """
        Run a backtest synchronously (blocking until complete).

        This is a convenience method that submits a job and waits for it
        to complete. For long-running backtests, consider using
        submit_backtest() and poll get_job_status() instead.

        Args:
            code: Python code to execute.
            params: Backtest parameters. Should include:
                - tickers: List of ticker symbols for data fetching
                - start_date: Start date (ISO format string or date object)
                - end_date: End date (ISO format string or date object)
            timeout: Optional timeout override.

        Returns:
            ExecutionResult with the backtest results.
        """
        workspace = None

        # Create job
        job_id = self._generate_job_id()
        job = ExecutionJob(
            job_id=job_id,
            code=code,
            params=params,
            timeout_seconds=timeout or self._settings.execution.timeout,
        )

        # Store job
        await self._storage.create(job)

        try:
            # Create workspace
            workspace = await self._workspace_manager.create_workspace(job)

            # Get host path for volume mounting (for Docker)
            host_workspace = self._workspace_manager.get_host_path(workspace)

            # Fetch and save market data if tickers are provided
            tickers = params.get("tickers", [])
            start_date_str = params.get("start_date")
            end_date_str = params.get("end_date")

            if tickers and start_date_str and end_date_str:
                # Parse dates
                if isinstance(start_date_str, str):
                    start_dt = date.fromisoformat(start_date_str)
                else:
                    start_dt = start_date_str

                if isinstance(end_date_str, str):
                    end_dt = date.fromisoformat(end_date_str)
                else:
                    end_dt = end_date_str

                logger.info(f"Fetching data for tickers: {tickers}")

                # Fetch market data
                market_data = await self._fetch_market_data(tickers, start_dt, end_dt)

                # Save data to workspace
                if market_data:
                    self._save_data_to_workspace(host_workspace, market_data)
                else:
                    logger.warning("No market data fetched")

            # Execute
            result = await self._backend.execute(job, workspace_path=host_workspace)

            # Update job in storage
            await self._storage.update(job)

            return result

        except Exception as e:
            # Update job with error
            job.mark_failed(str(e))
            await self._storage.update(job)
            return ExecutionResult.from_job(job)

        finally:
            # Cleanup workspace (if needed)
            try:
                if workspace:
                    await self._workspace_manager.cleanup_workspace(workspace)
            except Exception:
                pass

    async def submit_backtest(
        self,
        code: str,
        params: dict[str, Any],
        timeout: Optional[int] = None,
    ) -> str:
        """
        Submit a backtest for asynchronous execution.

        Returns immediately with a job ID. Use get_job_status() and
        get_job_result() to track and retrieve results.

        Args:
            code: Python code to execute.
            params: Backtest parameters.
            timeout: Optional timeout override.

        Returns:
            Job ID for tracking.
        """
        import asyncio

        # Create job
        job_id = self._generate_job_id()
        job = ExecutionJob(
            job_id=job_id,
            code=code,
            params=params,
            timeout_seconds=timeout or self._settings.execution.timeout,
        )

        # Store job
        await self._storage.create(job)

        # Execute in background
        asyncio.create_task(self._execute_job(job))

        return job_id

    async def _execute_job(self, job: ExecutionJob) -> None:
        """
        Execute a job in the background.

        Args:
            job: The job to execute.
        """
        workspace = None
        try:
            # Create workspace
            workspace = await self._workspace_manager.create_workspace(job)
            host_workspace = self._workspace_manager.get_host_path(workspace)

            # Fetch and save market data if tickers are provided
            params = job.params
            tickers = params.get("tickers", [])
            start_date_str = params.get("start_date")
            end_date_str = params.get("end_date")

            if tickers and start_date_str and end_date_str:
                # Parse dates
                if isinstance(start_date_str, str):
                    start_dt = date.fromisoformat(start_date_str)
                else:
                    start_dt = start_date_str

                if isinstance(end_date_str, str):
                    end_dt = date.fromisoformat(end_date_str)
                else:
                    end_dt = end_date_str

                logger.info(f"Fetching data for tickers: {tickers}")

                # Fetch market data
                market_data = await self._fetch_market_data(tickers, start_dt, end_dt)

                # Save data to workspace
                if market_data:
                    self._save_data_to_workspace(host_workspace, market_data)
                else:
                    logger.warning("No market data fetched")

            # Execute
            await self._backend.execute(job, workspace_path=host_workspace)

            # Update storage
            await self._storage.update(job)

        except Exception as e:
            logger.exception(f"Job {job.job_id} failed with exception")
            job.mark_failed(str(e))
            try:
                await self._storage.update(job)
            except JobNotFoundError:
                pass

        finally:
            # Cleanup workspace
            try:
                if workspace:
                    await self._workspace_manager.cleanup_workspace(workspace)
            except Exception:
                pass

    async def get_job_status(self, job_id: str) -> JobStatus:
        """
        Get the status of a job.

        Args:
            job_id: The job ID.

        Returns:
            Current job status.

        Raises:
            JobNotFoundError: If the job does not exist.
        """
        job = await self._storage.get(job_id)
        return job.status

    async def get_job_result(self, job_id: str) -> ExecutionResult:
        """
        Get the result of a completed job.

        Args:
            job_id: The job ID.

        Returns:
            ExecutionResult with the job results.

        Raises:
            JobNotFoundError: If the job does not exist.
        """
        job = await self._storage.get(job_id)
        return ExecutionResult.from_job(job)

    async def get_job(self, job_id: str) -> ExecutionJob:
        """
        Get the full job object.

        Args:
            job_id: The job ID.

        Returns:
            The ExecutionJob instance.

        Raises:
            JobNotFoundError: If the job does not exist.
        """
        return await self._storage.get(job_id)

    async def cancel_job(self, job_id: str) -> bool:
        """
        Cancel a running job.

        Args:
            job_id: The job ID.

        Returns:
            True if the job was cancelled, False otherwise.
        """
        # Try to cancel in backend
        cancelled = await self._backend.cancel(job_id)

        if cancelled:
            # Update storage
            try:
                job = await self._storage.get(job_id)
                job.mark_cancelled()
                await self._storage.update(job)
            except JobNotFoundError:
                pass

        return cancelled

    async def list_jobs(
        self,
        status: Optional[JobStatus] = None,
        limit: int = 100,
    ) -> list[ExecutionJob]:
        """
        List jobs, optionally filtered by status.

        Args:
            status: Filter by status (None for all).
            limit: Maximum number of jobs to return.

        Returns:
            List of ExecutionJob instances.
        """
        return await self._storage.list_by_status(status=status, limit=limit)

    async def cleanup_old_jobs(self, max_age_seconds: int = 3600) -> int:
        """
        Clean up old completed jobs.

        Args:
            max_age_seconds: Maximum age in seconds.

        Returns:
            Number of jobs cleaned up.
        """
        return await self._storage.cleanup_old_jobs(max_age_seconds)

    async def _fetch_market_data(
        self,
        tickers: list[str],
        start_date: date,
        end_date: date,
    ) -> dict[str, pd.DataFrame]:
        """
        Fetch market data for the given tickers.

        Args:
            tickers: List of ticker symbols.
            start_date: Start date for data.
            end_date: End date for data.

        Returns:
            Dictionary mapping ticker to DataFrame with OHLCV data.
        """
        if not self._data_provider:
            logger.warning("No data provider configured, skipping data fetch")
            return {}

        data: dict[str, pd.DataFrame] = {}

        async def fetch_ticker(ticker: str) -> tuple[str, pd.DataFrame | None]:
            try:
                price_data = await self._data_provider.get_daily_prices(
                    ticker, start_date, end_date
                )
                if price_data:
                    df = self._price_data_to_dataframe(price_data)
                    return ticker, df
                return ticker, None
            except Exception as e:
                logger.warning(f"Failed to fetch data for {ticker}: {e}")
                return ticker, None

        # Fetch data concurrently
        tasks = [fetch_ticker(ticker) for ticker in tickers]
        results = await asyncio.gather(*tasks)

        for ticker, df in results:
            if df is not None and not df.empty:
                data[ticker] = df
                logger.info(f"Fetched {len(df)} records for {ticker}")

        return data

    def _price_data_to_dataframe(self, price_data: list[PriceData]) -> pd.DataFrame:
        """
        Convert PriceData list to pandas DataFrame.

        Args:
            price_data: List of PriceData objects.

        Returns:
            DataFrame with OHLCV columns.
        """
        records = []
        for p in price_data:
            records.append({
                "date": p.date.isoformat(),
                "open": float(p.open),
                "high": float(p.high),
                "low": float(p.low),
                "close": float(p.close),
                "volume": p.volume,
                "adjusted_close": float(p.adjusted_close) if p.adjusted_close else None,
            })

        df = pd.DataFrame(records)
        if not df.empty:
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date").sort_index()
        return df

    def _save_data_to_workspace(
        self,
        workspace: Path,
        data: dict[str, pd.DataFrame],
    ) -> None:
        """
        Save market data to workspace as CSV files.

        Args:
            workspace: Workspace directory path.
            data: Dictionary mapping ticker to DataFrame.
        """
        data_dir = workspace / "data"
        data_dir.mkdir(exist_ok=True)

        # Save each ticker's data as CSV
        for ticker, df in data.items():
            csv_path = data_dir / f"{ticker}.csv"
            df.to_csv(csv_path)
            logger.info(f"Saved data for {ticker} to {csv_path}")

        # Save ticker list for the wrapper script
        tickers_file = data_dir / "tickers.json"
        tickers_file.write_text(json.dumps(list(data.keys())))

    async def close(self) -> None:
        """
        Close the job manager and release resources.

        Should be called during application shutdown.
        """
        # Close backend if it has a close method
        if hasattr(self._backend, "close"):
            await self._backend.close()

    def _generate_job_id(self) -> str:
        """Generate a unique job ID."""
        return f"backtest-{uuid.uuid4().hex[:12]}"


def create_job_manager(
    settings: Optional[Settings] = None,
    use_docker: Optional[bool] = None,
    data_provider: Optional[DataProvider] = None,
) -> JobManager:
    """
    Factory function to create a JobManager.

    Args:
        settings: Application settings. If None, loads from config.
        use_docker: Override to use Docker backend. If None, uses settings.
        data_provider: Data provider for fetching market data. Required for data injection.

    Returns:
        Configured JobManager instance.
    """
    if settings is None:
        settings = get_settings()

    # Determine backend type
    if use_docker is not None:
        provider = ExecutionProvider.DOCKER if use_docker else ExecutionProvider.LOCAL
        backend = BackendFactory.create(settings, provider=provider)
    else:
        backend = BackendFactory.create(settings)

    # Create workspace manager based on backend type
    is_docker = isinstance(backend, DockerBackend)
    workspace_manager = create_workspace_manager(
        backend_type="docker" if is_docker else "local",
        host_base_path="/tmp/backtest_workspaces" if is_docker else None,
    )

    return JobManager(
        backend=backend,
        workspace_manager=workspace_manager,
        data_provider=data_provider,
        settings=settings,
    )
