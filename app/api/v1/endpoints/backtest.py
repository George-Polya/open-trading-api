"""
Backtest Execution API Endpoints.

Provides endpoints for submitting and managing backtest code execution jobs.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field, field_validator

from app.core.container import (
    get_code_generator_dep,
    get_job_manager_dep,
    get_result_formatter_dep,
)
from app.models.backtest import BacktestRequest, GeneratedCode
from app.models.execution import ExecutionResult, JobStatus
from app.providers.data.factory import DataProviderFactory
from app.providers.llm.factory import LLMProviderFactory
from app.services.code_generator import (
    CodeGenerationError,
    DataAvailabilityError,
    ValidationError,
)
from app.services.execution.storage import JobNotFoundError

if TYPE_CHECKING:
    from app.services.code_generator import BacktestCodeGenerator
    from app.services.execution.manager import JobManager
    from app.services.result_formatter import ResultFormatter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/backtest", tags=["Backtest"])


# =============================================================================
# Request/Response Models
# =============================================================================


class ExecuteBacktestRequest(BaseModel):
    """
    Request model for backtest execution.

    Supports two modes:
    1. Direct code submission: Provide 'code' field
    2. Code reference: Provide 'code_reference' field (for previously generated code)

    Attributes:
        code: Python code string to execute (mutually exclusive with code_reference).
        code_reference: Reference ID to previously generated code (mutually exclusive with code).
        params: Execution parameters (e.g., backtest params dict).
        timeout: Optional timeout override in seconds (max 600).
        async_mode: If True, return immediately with job_id. If False, wait for completion.
    """

    code: Optional[str] = Field(
        default=None,
        description="Python code string to execute",
        min_length=1,
        max_length=100000,
    )
    code_reference: Optional[str] = Field(
        default=None,
        description="Reference ID to previously generated code",
        min_length=1,
        max_length=256,
    )
    params: dict[str, Any] = Field(
        default_factory=dict,
        description="Execution parameters (e.g., backtest params)",
    )
    timeout: Optional[int] = Field(
        default=None,
        gt=0,
        le=600,
        description="Optional timeout override in seconds (max 600)",
    )
    async_mode: bool = Field(
        default=True,
        description="If True, return immediately with job_id. If False, wait for completion.",
    )

    @field_validator("code", mode="after")
    @classmethod
    def validate_code_not_empty(cls, v: Optional[str]) -> Optional[str]:
        """Ensure code is not just whitespace if provided."""
        if v is not None and not v.strip():
            raise ValueError("Code cannot be empty or whitespace only")
        return v

    def get_code_to_execute(self) -> str:
        """
        Get the code string to execute.

        Returns:
            The code string from either 'code' or resolved 'code_reference'.

        Raises:
            ValueError: If neither or both fields are provided.
            NotImplementedError: If code_reference is provided (not yet implemented).
        """
        if self.code and self.code_reference:
            raise ValueError(
                "Cannot provide both 'code' and 'code_reference'. Choose one."
            )

        if not self.code and not self.code_reference:
            raise ValueError(
                "Must provide either 'code' or 'code_reference' for execution."
            )

        if self.code_reference:
            # TODO: Implement code reference lookup from storage/database
            # For now, raise NotImplementedError
            raise NotImplementedError(
                "Code reference lookup not yet implemented. Please provide code directly."
            )

        return self.code  # type: ignore[return-value]


class ExecuteBacktestResponse(BaseModel):
    """
    Response model for backtest execution.

    For async mode (default):
        Returns job_id and pending status immediately.

    For sync mode (async_mode=False):
        Waits for completion and returns full result.

    Attributes:
        job_id: Unique job identifier for tracking.
        status: Current job status.
        message: Human-readable message describing the state.
        result: Full execution result (only for sync mode when completed).
    """

    job_id: str = Field(
        ...,
        description="Unique job identifier for tracking",
    )
    status: JobStatus = Field(
        ...,
        description="Current job status",
    )
    message: str = Field(
        ...,
        description="Human-readable message describing the state",
    )
    result: Optional[ExecutionResult] = Field(
        default=None,
        description="Full execution result (only for sync mode)",
    )


class JobStatusResponse(BaseModel):
    """
    Response model for job status queries.

    Attributes:
        job_id: The job identifier.
        status: Current job status.
    """

    job_id: str = Field(..., description="The job identifier")
    status: JobStatus = Field(..., description="Current job status")


class LLMProviderInfo(BaseModel):
    """
    Information about an available LLM provider.

    Attributes:
        name: Provider name (e.g., "openrouter", "anthropic").
        description: Brief description of the provider.
        available: Whether the provider is currently available.
    """

    name: str = Field(..., description="Provider name")
    description: str = Field(..., description="Brief description of the provider")
    available: bool = Field(default=True, description="Whether the provider is available")


class DataSourceInfo(BaseModel):
    """
    Information about an available data source.

    Attributes:
        name: Data source name (e.g., "kis", "yfinance").
        description: Brief description of the data source.
        supported_exchanges: List of supported exchanges.
    """

    name: str = Field(..., description="Data source name")
    description: str = Field(..., description="Brief description of the data source")
    supported_exchanges: list[str] = Field(
        default_factory=list,
        description="List of supported exchanges",
    )


class ConfigProvidersResponse(BaseModel):
    """
    Response model for provider configuration endpoints.

    Attributes:
        providers: List of provider information.
    """

    providers: list[LLMProviderInfo] | list[DataSourceInfo] = Field(
        ...,
        description="List of available providers",
    )


class GenerateBacktestResponse(BaseModel):
    """
    Response model for backtest code generation endpoint.

    Wraps GeneratedCode with additional metadata.

    Attributes:
        generated_code: The generated code and metadata.
        tickers_found: List of ticker symbols found in the strategy.
        generation_time_seconds: Time taken to generate the code.
    """

    generated_code: GeneratedCode = Field(
        ...,
        description="Generated code and metadata",
    )
    tickers_found: list[str] = Field(
        default_factory=list,
        description="Ticker symbols found in the strategy",
    )
    generation_time_seconds: float = Field(
        ...,
        ge=0,
        description="Time taken to generate the code",
    )


class BacktestResultResponse(BaseModel):
    """
    Response model for formatted backtest results.

    Contains comprehensive performance metrics and chart data.

    Attributes:
        job_id: The job identifier.
        status: Job completion status.
        metrics: Performance and risk metrics.
        equity_curve: Equity curve data for charting.
        drawdown: Drawdown series data.
        monthly_heatmap: Monthly returns heatmap data.
        trades: List of trade details.
        logs: Execution logs.
    """

    job_id: str = Field(..., description="Job identifier")
    status: JobStatus = Field(..., description="Job status")
    metrics: dict[str, Any] = Field(..., description="Performance metrics")
    equity_curve: dict[str, Any] = Field(..., description="Equity curve data")
    drawdown: dict[str, Any] = Field(..., description="Drawdown series")
    monthly_heatmap: dict[str, Any] = Field(..., description="Monthly returns heatmap")
    trades: list[dict[str, Any]] = Field(
        default_factory=list, description="List of trades"
    )
    logs: str = Field(default="", description="Execution logs")


class EquityChartResponse(BaseModel):
    """
    Response model for equity curve chart data.

    Attributes:
        job_id: The job identifier.
        strategy: Strategy equity curve data points.
        benchmark: Optional benchmark equity curve data points.
        log_scale: Whether the data is in log scale.
    """

    job_id: str = Field(..., description="Job identifier")
    strategy: list[dict[str, Any]] = Field(..., description="Strategy data points")
    benchmark: list[dict[str, Any]] | None = Field(
        default=None, description="Benchmark data points"
    )
    log_scale: bool = Field(default=False, description="Log scale applied")


class DrawdownChartResponse(BaseModel):
    """
    Response model for drawdown chart data.

    Attributes:
        job_id: The job identifier.
        data: Drawdown data points (negative percentages).
    """

    job_id: str = Field(..., description="Job identifier")
    data: list[dict[str, Any]] = Field(..., description="Drawdown data points")


class MonthlyReturnsResponse(BaseModel):
    """
    Response model for monthly returns heatmap data.

    Attributes:
        job_id: The job identifier.
        years: List of years.
        months: List of month names.
        returns: 2D array of monthly returns.
    """

    job_id: str = Field(..., description="Job identifier")
    years: list[int] = Field(..., description="List of years")
    months: list[str] = Field(..., description="List of month names")
    returns: list[list[float | None]] = Field(
        ..., description="Monthly returns matrix"
    )


# =============================================================================
# Endpoints
# =============================================================================


@router.post(
    "/execute",
    response_model=ExecuteBacktestResponse,
    summary="Execute Backtest Code",
    description=(
        "Submit backtest code for execution. "
        "Returns a job_id for tracking. "
        "Supports both async (default) and sync execution modes."
    ),
    responses={
        202: {
            "description": "Backtest submitted successfully (async mode)",
            "content": {
                "application/json": {
                    "example": {
                        "job_id": "backtest-abc123def456",
                        "status": "pending",
                        "message": "Backtest submitted successfully. Use job_id to track progress.",
                        "result": None,
                    }
                }
            },
        },
        200: {
            "description": "Backtest completed successfully (sync mode)",
            "content": {
                "application/json": {
                    "example": {
                        "job_id": "backtest-abc123def456",
                        "status": "completed",
                        "message": "Backtest execution completed successfully.",
                        "result": {
                            "success": True,
                            "job_id": "backtest-abc123def456",
                            "status": "completed",
                            "data": {"portfolio_value": 150000, "returns": 0.5},
                            "error": None,
                            "logs": "Execution logs here...",
                            "duration_seconds": 2.5,
                        },
                    }
                }
            },
        },
        400: {"description": "Invalid request (missing code, invalid params, etc.)"},
        500: {"description": "Internal server error during execution"},
    },
)
async def execute_backtest(
    request: ExecuteBacktestRequest,
    response: Response,
    job_manager: "JobManager" = Depends(get_job_manager_dep),
) -> ExecuteBacktestResponse:
    """
    Execute backtest code.

    Submits Python code for execution in a sandboxed environment.
    Returns a job_id for tracking execution progress.

    Args:
        request: Execution request with code and parameters.
        job_manager: JobManager dependency for execution orchestration.

    Returns:
        ExecuteBacktestResponse with job_id and status.

    Raises:
        HTTPException 400: If request validation fails.
        HTTPException 500: If job submission fails.
    """
    try:
        # Validate and get code to execute
        code_to_execute = request.get_code_to_execute()

    except ValueError as e:
        logger.warning(f"Invalid backtest request: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except NotImplementedError as e:
        logger.warning(f"Feature not implemented: {e}")
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=str(e),
        )

    try:
        if request.async_mode:
            # Async mode: Submit and return immediately
            job_id = await job_manager.submit_backtest(
                code=code_to_execute,
                params=request.params,
                timeout=request.timeout,
            )

            logger.info(f"Backtest submitted successfully: {job_id}")

            # Set status code to 202 Accepted for async mode
            response.status_code = status.HTTP_202_ACCEPTED

            return ExecuteBacktestResponse(
                job_id=job_id,
                status=JobStatus.PENDING,
                message="Backtest submitted successfully. Use job_id to track progress.",
            )

        else:
            # Sync mode: Wait for completion
            logger.info("Executing backtest in synchronous mode")
            result = await job_manager.run_backtest(
                code=code_to_execute,
                params=request.params,
                timeout=request.timeout,
            )

            logger.info(
                f"Backtest execution completed: {result.job_id} "
                f"(status={result.status}, success={result.success})"
            )

            # Set status code to 200 OK for sync mode
            response.status_code = status.HTTP_200_OK

            # Determine appropriate message
            if result.success:
                message = "Backtest execution completed successfully."
            else:
                message = f"Backtest execution failed: {result.error}"

            return ExecuteBacktestResponse(
                job_id=result.job_id,
                status=result.status,
                message=message,
                result=result,
            )

    except Exception as e:
        logger.exception(f"Failed to execute backtest: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to execute backtest: {str(e)}",
        )


@router.get(
    "/status/{job_id}",
    response_model=JobStatusResponse,
    summary="Get Job Status",
    description="Get the current status of a backtest execution job.",
    responses={
        200: {"description": "Job status retrieved successfully"},
        404: {"description": "Job not found"},
    },
)
async def get_job_status(
    job_id: str,
    job_manager: "JobManager" = Depends(get_job_manager_dep),
) -> JobStatusResponse:
    """
    Get the status of a backtest execution job.

    Args:
        job_id: The job identifier.
        job_manager: JobManager dependency.

    Returns:
        JobStatusResponse with current status.

    Raises:
        HTTPException 404: If job not found.
    """
    try:
        job_status = await job_manager.get_job_status(job_id)
        return JobStatusResponse(job_id=job_id, status=job_status)

    except JobNotFoundError:
        logger.warning(f"Job not found: {job_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job not found: {job_id}",
        )


@router.get(
    "/result/{job_id}",
    response_model=ExecutionResult,
    summary="Get Job Result",
    description="Get the result of a completed backtest execution job.",
    responses={
        200: {"description": "Job result retrieved successfully"},
        404: {"description": "Job not found"},
    },
)
async def get_job_result(
    job_id: str,
    job_manager: "JobManager" = Depends(get_job_manager_dep),
) -> ExecutionResult:
    """
    Get the result of a backtest execution job.

    Args:
        job_id: The job identifier.
        job_manager: JobManager dependency.

    Returns:
        ExecutionResult with full execution details.

    Raises:
        HTTPException 404: If job not found.
    """
    try:
        result = await job_manager.get_job_result(job_id)
        return result

    except JobNotFoundError:
        logger.warning(f"Job not found: {job_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job not found: {job_id}",
        )


@router.get(
    "/{job_id}/result",
    response_model=BacktestResultResponse,
    summary="Get Formatted Backtest Result",
    description=(
        "Get comprehensive formatted backtest results including metrics, "
        "chart data, trades, and logs. Returns 409 if job is not yet completed."
    ),
    responses={
        200: {"description": "Formatted results retrieved successfully"},
        404: {"description": "Job not found"},
        409: {"description": "Job not completed yet"},
        500: {"description": "Failed to format results"},
    },
)
async def get_backtest_formatted_result(
    job_id: str,
    job_manager: "JobManager" = Depends(get_job_manager_dep),
    result_formatter: "ResultFormatter" = Depends(get_result_formatter_dep),
) -> BacktestResultResponse:
    """
    Get formatted backtest result with comprehensive metrics and chart data.

    Args:
        job_id: The job identifier.
        job_manager: JobManager dependency.
        result_formatter: ResultFormatter dependency.

    Returns:
        BacktestResultResponse with formatted metrics and chart data.

    Raises:
        HTTPException 404: If job not found.
        HTTPException 409: If job not completed.
        HTTPException 500: If result formatting fails.
    """
    try:
        # Get job result
        result = await job_manager.get_job_result(job_id)

        # Check if job is completed
        if result.status != JobStatus.COMPLETED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Job is not completed yet. Current status: {result.status}",
            )

        # Check if result has data
        if not result.success or not result.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Job completed but no result data available: {result.error}",
            )

        # Extract data from result
        data = result.data
        equity_series_data = data.get("equity_series", [])
        trades_data = data.get("trades", [])
        benchmark_data = data.get("benchmark_series")
        start_date_str = data.get("start_date")
        end_date_str = data.get("end_date")

        # Validate required data
        if not equity_series_data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Missing equity_series in result data",
            )

        # Convert equity series to pandas Series
        import pandas as pd
        from datetime import datetime

        equity_series = pd.Series(
            [point["value"] for point in equity_series_data],
            index=pd.to_datetime([point["date"] for point in equity_series_data]),
        )

        # Convert benchmark if available
        benchmark_series = None
        if benchmark_data:
            benchmark_series = pd.Series(
                [point["value"] for point in benchmark_data],
                index=pd.to_datetime([point["date"] for point in benchmark_data]),
            )

        # Parse dates
        from datetime import date as date_type

        start_date = (
            datetime.fromisoformat(start_date_str).date()
            if start_date_str
            else equity_series.index[0].date()
        )
        end_date = (
            datetime.fromisoformat(end_date_str).date()
            if end_date_str
            else equity_series.index[-1].date()
        )

        # Format results
        formatted = result_formatter.format_results(
            equity_series=equity_series,
            trades=trades_data,
            start_date=start_date,
            end_date=end_date,
            benchmark_series=benchmark_series,
            use_log_scale=False,
        )

        # Convert to response model
        return BacktestResultResponse(
            job_id=job_id,
            status=result.status,
            metrics=formatted.metrics.model_dump(),
            equity_curve=formatted.equity_curve.model_dump(),
            drawdown=formatted.drawdown.model_dump(),
            monthly_heatmap=formatted.monthly_heatmap.model_dump(),
            trades=trades_data,
            logs=result.logs,
        )

    except JobNotFoundError:
        logger.warning(f"Job not found: {job_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job not found: {job_id}",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to format results for job {job_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to format results: {str(e)}",
        )


@router.get(
    "/{job_id}/chart/equity",
    response_model=EquityChartResponse,
    summary="Get Equity Chart Data",
    description="Get equity curve data for charting with optional log scale and benchmark.",
    responses={
        200: {"description": "Equity chart data retrieved successfully"},
        404: {"description": "Job not found"},
        409: {"description": "Job not completed yet"},
    },
)
async def get_equity_chart(
    job_id: str,
    log_scale: bool = True,
    include_benchmark: bool = True,
    job_manager: "JobManager" = Depends(get_job_manager_dep),
    result_formatter: "ResultFormatter" = Depends(get_result_formatter_dep),
) -> EquityChartResponse:
    """
    Get equity curve chart data.

    Args:
        job_id: The job identifier.
        log_scale: Apply log10 transformation for better visualization.
        include_benchmark: Include benchmark data if available.
        job_manager: JobManager dependency.
        result_formatter: ResultFormatter dependency.

    Returns:
        EquityChartResponse with equity curve data.

    Raises:
        HTTPException 404: If job not found.
        HTTPException 409: If job not completed.
    """
    try:
        result = await job_manager.get_job_result(job_id)

        if result.status != JobStatus.COMPLETED or not result.data:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Job not completed or no data available. Status: {result.status}",
            )

        # Extract equity data
        data = result.data
        equity_series_data = data.get("equity_series", [])
        benchmark_data = data.get("benchmark_series") if include_benchmark else None

        if not equity_series_data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Missing equity_series in result data",
            )

        # Convert to pandas Series
        import pandas as pd

        equity_series = pd.Series(
            [point["value"] for point in equity_series_data],
            index=pd.to_datetime([point["date"] for point in equity_series_data]),
        )

        benchmark_series = None
        if benchmark_data:
            benchmark_series = pd.Series(
                [point["value"] for point in benchmark_data],
                index=pd.to_datetime([point["date"] for point in benchmark_data]),
            )

        # Format for chart
        equity_curve = result_formatter.format_for_chart(
            equity_series=equity_series,
            benchmark_series=benchmark_series,
            use_log_scale=log_scale,
        )

        # Convert to response
        return EquityChartResponse(
            job_id=job_id,
            strategy=[point.model_dump() for point in equity_curve.strategy],
            benchmark=(
                [point.model_dump() for point in equity_curve.benchmark]
                if equity_curve.benchmark
                else None
            ),
            log_scale=equity_curve.log_scale,
        )

    except JobNotFoundError:
        logger.warning(f"Job not found: {job_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job not found: {job_id}",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get equity chart for job {job_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get equity chart: {str(e)}",
        )


@router.get(
    "/{job_id}/chart/drawdown",
    response_model=DrawdownChartResponse,
    summary="Get Drawdown Chart Data",
    description="Get drawdown series data for charting.",
    responses={
        200: {"description": "Drawdown chart data retrieved successfully"},
        404: {"description": "Job not found"},
        409: {"description": "Job not completed yet"},
    },
)
async def get_drawdown_chart(
    job_id: str,
    job_manager: "JobManager" = Depends(get_job_manager_dep),
    result_formatter: "ResultFormatter" = Depends(get_result_formatter_dep),
) -> DrawdownChartResponse:
    """
    Get drawdown series chart data.

    Args:
        job_id: The job identifier.
        job_manager: JobManager dependency.
        result_formatter: ResultFormatter dependency.

    Returns:
        DrawdownChartResponse with drawdown series data.

    Raises:
        HTTPException 404: If job not found.
        HTTPException 409: If job not completed.
    """
    try:
        result = await job_manager.get_job_result(job_id)

        if result.status != JobStatus.COMPLETED or not result.data:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Job not completed or no data available. Status: {result.status}",
            )

        # Extract equity data
        data = result.data
        equity_series_data = data.get("equity_series", [])

        if not equity_series_data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Missing equity_series in result data",
            )

        # Convert to pandas Series
        import pandas as pd

        equity_series = pd.Series(
            [point["value"] for point in equity_series_data],
            index=pd.to_datetime([point["date"] for point in equity_series_data]),
        )

        # Generate drawdown series
        drawdown_series = result_formatter.generate_drawdown_series(equity_series)

        # Convert to response
        drawdown_points = [
            {"date": idx.strftime("%Y-%m-%d"), "value": val}
            for idx, val in drawdown_series.items()
        ]

        return DrawdownChartResponse(job_id=job_id, data=drawdown_points)

    except JobNotFoundError:
        logger.warning(f"Job not found: {job_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job not found: {job_id}",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get drawdown chart for job {job_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get drawdown chart: {str(e)}",
        )


@router.get(
    "/{job_id}/chart/monthly-returns",
    response_model=MonthlyReturnsResponse,
    summary="Get Monthly Returns Heatmap Data",
    description="Get monthly returns heatmap data for visualization.",
    responses={
        200: {"description": "Monthly returns data retrieved successfully"},
        404: {"description": "Job not found"},
        409: {"description": "Job not completed yet"},
    },
)
async def get_monthly_returns(
    job_id: str,
    job_manager: "JobManager" = Depends(get_job_manager_dep),
    result_formatter: "ResultFormatter" = Depends(get_result_formatter_dep),
) -> MonthlyReturnsResponse:
    """
    Get monthly returns heatmap data.

    Args:
        job_id: The job identifier.
        job_manager: JobManager dependency.
        result_formatter: ResultFormatter dependency.

    Returns:
        MonthlyReturnsResponse with monthly returns matrix.

    Raises:
        HTTPException 404: If job not found.
        HTTPException 409: If job not completed.
    """
    try:
        result = await job_manager.get_job_result(job_id)

        if result.status != JobStatus.COMPLETED or not result.data:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Job not completed or no data available. Status: {result.status}",
            )

        # Extract equity data
        data = result.data
        equity_series_data = data.get("equity_series", [])

        if not equity_series_data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Missing equity_series in result data",
            )

        # Convert to pandas Series
        import pandas as pd

        equity_series = pd.Series(
            [point["value"] for point in equity_series_data],
            index=pd.to_datetime([point["date"] for point in equity_series_data]),
        )

        # Generate monthly heatmap
        heatmap = result_formatter.generate_monthly_heatmap(equity_series)

        return MonthlyReturnsResponse(
            job_id=job_id,
            years=heatmap.years,
            months=heatmap.months,
            returns=heatmap.returns,
        )

    except JobNotFoundError:
        logger.warning(f"Job not found: {job_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job not found: {job_id}",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get monthly returns for job {job_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get monthly returns: {str(e)}",
        )


# =============================================================================
# Configuration Endpoints
# =============================================================================


@router.get(
    "/config/llm-providers",
    response_model=ConfigProvidersResponse,
    summary="Get Available LLM Providers",
    description="Returns a list of available LLM providers for code generation.",
    responses={
        200: {"description": "LLM providers retrieved successfully"},
    },
)
async def get_llm_providers() -> ConfigProvidersResponse:
    """
    Get list of available LLM providers.

    Returns:
        ConfigProvidersResponse with list of LLM provider information.
    """
    provider_names = LLMProviderFactory.get_supported_providers()

    # Provider descriptions mapping
    provider_descriptions = {
        "openrouter": "OpenRouter - Access to multiple LLM models through a unified API",
        "anthropic": "Anthropic Claude - Advanced reasoning and code generation",
        "openai": "OpenAI GPT - Industry-leading language models",
        "langchain": "LangChain - Flexible LLM framework with multiple providers",
    }

    providers = [
        LLMProviderInfo(
            name=name,
            description=provider_descriptions.get(
                name,
                f"{name.upper()} LLM provider",
            ),
            available=True,
        )
        for name in provider_names
    ]

    logger.info(f"Retrieved {len(providers)} available LLM providers")
    return ConfigProvidersResponse(providers=providers)


@router.get(
    "/config/data-sources",
    response_model=ConfigProvidersResponse,
    summary="Get Available Data Sources",
    description="Returns a list of available data sources for backtesting.",
    responses={
        200: {"description": "Data sources retrieved successfully"},
    },
)
async def get_data_sources() -> ConfigProvidersResponse:
    """
    Get list of available data sources.

    Returns:
        ConfigProvidersResponse with list of data source information.
    """
    source_names = DataProviderFactory.get_supported_providers()

    # Data source descriptions and supported exchanges
    source_info = {
        "kis": {
            "description": "Korea Investment & Securities - Korean and US market data",
            "exchanges": ["KRX", "NASDAQ", "NYSE", "AMEX"],
        },
        "yfinance": {
            "description": "Yahoo Finance - Global market data and historical prices",
            "exchanges": ["NYSE", "NASDAQ", "LSE", "TSE", "HKEX"],
        },
        "mock": {
            "description": "Mock Data Provider - For testing and development",
            "exchanges": ["MOCK"],
        },
    }

    sources = [
        DataSourceInfo(
            name=name,
            description=source_info.get(name, {}).get(
                "description",
                f"{name.upper()} data provider",
            ),
            supported_exchanges=source_info.get(name, {}).get("exchanges", []),
        )
        for name in source_names
    ]

    logger.info(f"Retrieved {len(sources)} available data sources")
    return ConfigProvidersResponse(providers=sources)


# =============================================================================
# Code Generation Endpoint
# =============================================================================


@router.post(
    "/generate",
    response_model=GenerateBacktestResponse,
    summary="Generate Backtest Code",
    description=(
        "Generate executable Python backtest code from a natural language strategy description. "
        "The generated code is validated for safety and correctness before being returned."
    ),
    responses={
        200: {
            "description": "Code generated successfully",
            "content": {
                "application/json": {
                    "example": {
                        "generated_code": {
                            "code": "# Generated Python backtest code\nclass MyStrategy(Strategy):\n    ...",
                            "strategy_summary": "Buy and hold strategy for AAPL with monthly contributions",
                            "model_info": {
                                "provider": "openrouter",
                                "model_id": "anthropic/claude-3.5-sonnet",
                                "max_tokens": 8000,
                                "supports_system_prompt": True,
                                "cost_per_1k_input": 0.003,
                                "cost_per_1k_output": 0.015,
                            },
                        },
                        "tickers_found": ["AAPL", "SPY"],
                        "generation_time_seconds": 3.5,
                    }
                }
            },
        },
        400: {"description": "Invalid request or validation error"},
        500: {"description": "Code generation failed"},
    },
)
async def generate_backtest_code(
    request: BacktestRequest,
    generator: "BacktestCodeGenerator" = Depends(get_code_generator_dep),
) -> GenerateBacktestResponse:
    """
    Generate backtest code from natural language strategy.

    Converts a natural language investment strategy description into
    executable Python backtest code using LLM providers.

    Args:
        request: BacktestRequest with strategy and parameters.
        generator: BacktestCodeGenerator dependency.

    Returns:
        GenerateBacktestResponse with generated code and metadata.

    Raises:
        HTTPException 400: If request validation fails or no tickers found.
        HTTPException 500: If code generation fails.
    """
    import time

    start_time = time.time()

    try:
        logger.info(
            f"Generating backtest code for strategy: {request.strategy[:100]}..."
        )

        # Generate the code
        generated_code = await generator.generate(request)

        # Extract tickers for the response
        tickers_found = generator._extract_tickers(
            request.strategy,
            request.params.benchmarks,
        )

        generation_time = time.time() - start_time

        logger.info(
            f"Successfully generated backtest code in {generation_time:.2f}s "
            f"(found {len(tickers_found)} tickers)"
        )

        return GenerateBacktestResponse(
            generated_code=generated_code,
            tickers_found=tickers_found,
            generation_time_seconds=round(generation_time, 2),
        )

    except ValidationError as e:
        logger.warning(f"Code validation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Generated code failed validation: {'; '.join(e.errors)}",
        )

    except DataAvailabilityError as e:
        logger.warning(f"Data availability error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Data not available: {str(e)}",
        )

    except CodeGenerationError as e:
        logger.error(f"Code generation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    except Exception as e:
        logger.exception(f"Unexpected error during code generation: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Code generation failed: {str(e)}",
        )
