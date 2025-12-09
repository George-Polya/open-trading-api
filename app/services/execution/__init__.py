"""
Execution services module.

Provides code execution backend implementations and job management.
"""

from app.services.execution.storage import (
    JobStorage,
    InMemoryJobStorage,
    JobNotFoundError,
)
from app.services.execution.backend import (
    ExecutionBackend,
    ExecutionError,
    ExecutionTimeoutError,
    LocalBackend,
)
from app.services.execution.docker_backend import (
    DockerBackend,
    DEFAULT_PYTHON_IMAGE,
)
from app.services.execution.workspace import (
    WorkspaceManager,
    LocalWorkspaceManager,
    DooDBWorkspaceManager,
    WorkspaceError,
    create_workspace_manager,
)
from app.services.execution.manager import (
    BackendFactory,
    JobManager,
    create_job_manager,
)

__all__ = [
    # Storage
    "JobStorage",
    "InMemoryJobStorage",
    "JobNotFoundError",
    # Backend
    "ExecutionBackend",
    "ExecutionError",
    "ExecutionTimeoutError",
    "LocalBackend",
    # Docker Backend
    "DockerBackend",
    "DEFAULT_PYTHON_IMAGE",
    # Workspace
    "WorkspaceManager",
    "LocalWorkspaceManager",
    "DooDBWorkspaceManager",
    "WorkspaceError",
    "create_workspace_manager",
    # Manager
    "BackendFactory",
    "JobManager",
    "create_job_manager",
]
