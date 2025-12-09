"""
Execution job models for tracking code execution status.

Defines Pydantic models for execution jobs including status tracking,
result storage, and logging.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


def utcnow() -> datetime:
    """Get current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


class JobStatus(str, Enum):
    """
    Execution job status values.

    Tracks the lifecycle of a code execution job.
    """

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


class ExecutionJob(BaseModel):
    """
    Execution job model.

    Represents a single code execution task with status tracking,
    result storage, and logging capabilities.

    Attributes:
        job_id: Unique identifier for the job.
        status: Current job status.
        code: The code to execute.
        params: Execution parameters (e.g., backtest params).
        result: Execution result data (populated on completion).
        error: Error message if execution failed.
        logs: Execution logs (stdout/stderr).
        created_at: Job creation timestamp.
        started_at: Execution start timestamp.
        completed_at: Execution completion timestamp.
        timeout_seconds: Maximum execution time allowed.
    """

    model_config = ConfigDict(frozen=False)

    job_id: str = Field(
        ...,
        description="Unique identifier for the job",
    )
    status: JobStatus = Field(
        default=JobStatus.PENDING,
        description="Current job status",
    )
    code: str = Field(
        ...,
        description="The code to execute",
    )
    params: dict[str, Any] = Field(
        default_factory=dict,
        description="Execution parameters (e.g., backtest params)",
    )
    result: Optional[dict[str, Any]] = Field(
        default=None,
        description="Execution result data (populated on completion)",
    )
    error: Optional[str] = Field(
        default=None,
        description="Error message if execution failed",
    )
    logs: str = Field(
        default="",
        description="Execution logs (stdout/stderr)",
    )
    created_at: datetime = Field(
        default_factory=utcnow,
        description="Job creation timestamp",
    )
    started_at: Optional[datetime] = Field(
        default=None,
        description="Execution start timestamp",
    )
    completed_at: Optional[datetime] = Field(
        default=None,
        description="Execution completion timestamp",
    )
    timeout_seconds: int = Field(
        default=300,
        gt=0,
        le=600,
        description="Maximum execution time allowed in seconds",
    )

    def mark_running(self) -> "ExecutionJob":
        """Mark the job as running and set start time."""
        self.status = JobStatus.RUNNING
        self.started_at = utcnow()
        return self

    def mark_completed(
        self, result: dict[str, Any], logs: str = ""
    ) -> "ExecutionJob":
        """
        Mark the job as completed with result.

        Args:
            result: The execution result data.
            logs: Execution logs to append.

        Returns:
            Self for method chaining.
        """
        self.status = JobStatus.COMPLETED
        self.completed_at = utcnow()
        self.result = result
        if logs:
            self.logs = self.logs + logs if self.logs else logs
        return self

    def mark_failed(self, error: str, logs: str = "") -> "ExecutionJob":
        """
        Mark the job as failed with error message.

        Args:
            error: The error message.
            logs: Execution logs to append.

        Returns:
            Self for method chaining.
        """
        self.status = JobStatus.FAILED
        self.completed_at = utcnow()
        self.error = error
        if logs:
            self.logs = self.logs + logs if self.logs else logs
        return self

    def mark_timeout(self, logs: str = "") -> "ExecutionJob":
        """
        Mark the job as timed out.

        Args:
            logs: Execution logs to append.

        Returns:
            Self for method chaining.
        """
        self.status = JobStatus.TIMEOUT
        self.completed_at = utcnow()
        self.error = f"Execution timed out after {self.timeout_seconds} seconds"
        if logs:
            self.logs = self.logs + logs if self.logs else logs
        return self

    def mark_cancelled(self) -> "ExecutionJob":
        """Mark the job as cancelled."""
        self.status = JobStatus.CANCELLED
        self.completed_at = utcnow()
        return self

    def append_logs(self, logs: str) -> None:
        """Append logs to the job."""
        if logs:
            self.logs = self.logs + logs if self.logs else logs

    @property
    def is_terminal(self) -> bool:
        """Check if the job is in a terminal state."""
        return self.status in (
            JobStatus.COMPLETED,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
            JobStatus.TIMEOUT,
        )

    @property
    def duration_seconds(self) -> Optional[float]:
        """Calculate job duration in seconds."""
        if self.started_at is None:
            return None
        end_time = self.completed_at or utcnow()
        return (end_time - self.started_at).total_seconds()


class ExecutionResult(BaseModel):
    """
    Execution result model.

    Standardized result format for backtest execution.

    Attributes:
        success: Whether execution was successful.
        job_id: The job ID.
        status: Final job status.
        data: Result data (backtest results, metrics, etc.).
        error: Error message if failed.
        logs: Execution logs.
        duration_seconds: Total execution time.
    """

    model_config = ConfigDict(frozen=True)

    success: bool = Field(
        ...,
        description="Whether execution was successful",
    )
    job_id: str = Field(
        ...,
        description="The job ID",
    )
    status: JobStatus = Field(
        ...,
        description="Final job status",
    )
    data: Optional[dict[str, Any]] = Field(
        default=None,
        description="Result data (backtest results, metrics, etc.)",
    )
    error: Optional[str] = Field(
        default=None,
        description="Error message if failed",
    )
    logs: str = Field(
        default="",
        description="Execution logs",
    )
    duration_seconds: Optional[float] = Field(
        default=None,
        description="Total execution time in seconds",
    )

    @classmethod
    def from_job(cls, job: ExecutionJob) -> "ExecutionResult":
        """
        Create ExecutionResult from an ExecutionJob.

        Args:
            job: The execution job.

        Returns:
            ExecutionResult instance.
        """
        return cls(
            success=job.status == JobStatus.COMPLETED,
            job_id=job.job_id,
            status=job.status,
            data=job.result,
            error=job.error,
            logs=job.logs,
            duration_seconds=job.duration_seconds,
        )
