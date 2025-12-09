"""
Job storage interface and implementations.

Provides abstract base class for job storage and an in-memory
implementation for MVP/testing purposes.
"""

import asyncio
from abc import ABC, abstractmethod
from typing import Optional

from app.models.execution import ExecutionJob, JobStatus


class JobNotFoundError(Exception):
    """Raised when a job is not found in storage."""

    def __init__(self, job_id: str):
        self.job_id = job_id
        super().__init__(f"Job not found: {job_id}")


class JobStorage(ABC):
    """
    Abstract base class for job storage.

    Defines the interface for storing and retrieving execution jobs.
    Implementations may use in-memory storage, Redis, databases, etc.
    """

    @abstractmethod
    async def create(self, job: ExecutionJob) -> ExecutionJob:
        """
        Create a new job in storage.

        Args:
            job: The job to store.

        Returns:
            The stored job (may have updated fields).

        Raises:
            ValueError: If a job with the same ID already exists.
        """
        ...

    @abstractmethod
    async def get(self, job_id: str) -> ExecutionJob:
        """
        Retrieve a job by ID.

        Args:
            job_id: The job ID.

        Returns:
            The job.

        Raises:
            JobNotFoundError: If the job does not exist.
        """
        ...

    @abstractmethod
    async def get_or_none(self, job_id: str) -> Optional[ExecutionJob]:
        """
        Retrieve a job by ID or None if not found.

        Args:
            job_id: The job ID.

        Returns:
            The job or None.
        """
        ...

    @abstractmethod
    async def update(self, job: ExecutionJob) -> ExecutionJob:
        """
        Update an existing job.

        Args:
            job: The job with updated fields.

        Returns:
            The updated job.

        Raises:
            JobNotFoundError: If the job does not exist.
        """
        ...

    @abstractmethod
    async def delete(self, job_id: str) -> bool:
        """
        Delete a job by ID.

        Args:
            job_id: The job ID.

        Returns:
            True if the job was deleted, False if not found.
        """
        ...

    @abstractmethod
    async def list_by_status(
        self, status: Optional[JobStatus] = None, limit: int = 100
    ) -> list[ExecutionJob]:
        """
        List jobs, optionally filtered by status.

        Args:
            status: Filter by status (None for all).
            limit: Maximum number of jobs to return.

        Returns:
            List of jobs.
        """
        ...

    @abstractmethod
    async def cleanup_old_jobs(self, max_age_seconds: int) -> int:
        """
        Remove jobs older than the specified age.

        Args:
            max_age_seconds: Maximum age in seconds.

        Returns:
            Number of jobs removed.
        """
        ...


class InMemoryJobStorage(JobStorage):
    """
    In-memory job storage implementation.

    Uses a dictionary to store jobs. Suitable for MVP and testing.
    Not suitable for production (no persistence, single-instance only).

    Thread-safety is provided via asyncio.Lock.
    """

    def __init__(self):
        """Initialize the in-memory storage."""
        self._jobs: dict[str, ExecutionJob] = {}
        self._lock = asyncio.Lock()

    async def create(self, job: ExecutionJob) -> ExecutionJob:
        """
        Create a new job in storage.

        Args:
            job: The job to store.

        Returns:
            The stored job.

        Raises:
            ValueError: If a job with the same ID already exists.
        """
        async with self._lock:
            if job.job_id in self._jobs:
                raise ValueError(f"Job already exists: {job.job_id}")
            self._jobs[job.job_id] = job
            return job

    async def get(self, job_id: str) -> ExecutionJob:
        """
        Retrieve a job by ID.

        Args:
            job_id: The job ID.

        Returns:
            The job.

        Raises:
            JobNotFoundError: If the job does not exist.
        """
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise JobNotFoundError(job_id)
            return job

    async def get_or_none(self, job_id: str) -> Optional[ExecutionJob]:
        """
        Retrieve a job by ID or None if not found.

        Args:
            job_id: The job ID.

        Returns:
            The job or None.
        """
        async with self._lock:
            return self._jobs.get(job_id)

    async def update(self, job: ExecutionJob) -> ExecutionJob:
        """
        Update an existing job.

        Args:
            job: The job with updated fields.

        Returns:
            The updated job.

        Raises:
            JobNotFoundError: If the job does not exist.
        """
        async with self._lock:
            if job.job_id not in self._jobs:
                raise JobNotFoundError(job.job_id)
            self._jobs[job.job_id] = job
            return job

    async def delete(self, job_id: str) -> bool:
        """
        Delete a job by ID.

        Args:
            job_id: The job ID.

        Returns:
            True if the job was deleted, False if not found.
        """
        async with self._lock:
            if job_id in self._jobs:
                del self._jobs[job_id]
                return True
            return False

    async def list_by_status(
        self, status: Optional[JobStatus] = None, limit: int = 100
    ) -> list[ExecutionJob]:
        """
        List jobs, optionally filtered by status.

        Args:
            status: Filter by status (None for all).
            limit: Maximum number of jobs to return.

        Returns:
            List of jobs sorted by creation time (newest first).
        """
        async with self._lock:
            jobs = list(self._jobs.values())

            if status is not None:
                jobs = [j for j in jobs if j.status == status]

            # Sort by creation time, newest first
            jobs.sort(key=lambda j: j.created_at, reverse=True)

            return jobs[:limit]

    async def cleanup_old_jobs(self, max_age_seconds: int) -> int:
        """
        Remove jobs older than the specified age.

        Only removes jobs in terminal states (completed, failed, cancelled).

        Args:
            max_age_seconds: Maximum age in seconds.

        Returns:
            Number of jobs removed.
        """
        from datetime import datetime, timedelta, timezone

        async with self._lock:
            cutoff = datetime.now(timezone.utc) - timedelta(seconds=max_age_seconds)
            to_remove = []

            for job_id, job in self._jobs.items():
                if job.is_terminal and job.created_at < cutoff:
                    to_remove.append(job_id)

            for job_id in to_remove:
                del self._jobs[job_id]

            return len(to_remove)

    async def clear(self) -> None:
        """Clear all jobs from storage. Useful for testing."""
        async with self._lock:
            self._jobs.clear()

    @property
    def job_count(self) -> int:
        """Get the number of jobs in storage."""
        return len(self._jobs)
