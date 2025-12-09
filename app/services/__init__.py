"""
Application services module.

Contains business logic services for the backtest application.
"""

from app.services.code_generator import (
    BacktestCodeGenerator,
    CodeGenerationError,
    ValidationError,
)
from app.services.code_validator import (
    ASTCodeValidator,
    ValidationError as ValidatorError,
    ValidationResult,
    create_code_validator,
    BANNED_IMPORTS,
    BANNED_FUNCTIONS,
    ALLOWED_IMPORTS,
)
from app.services.execution import (
    # Storage
    JobStorage,
    InMemoryJobStorage,
    JobNotFoundError,
    # Backends
    ExecutionBackend,
    ExecutionError,
    ExecutionTimeoutError,
    LocalBackend,
    DockerBackend,
    DEFAULT_PYTHON_IMAGE,
    # Workspace
    WorkspaceManager,
    LocalWorkspaceManager,
    DooDBWorkspaceManager,
    WorkspaceError,
    create_workspace_manager,
    # Manager
    BackendFactory,
    JobManager,
    create_job_manager,
)
from app.services.result_formatter import (
    ResultFormatter,
    StandardMetricsCalculator,
    PerformanceMetrics,
    EquityCurveData,
    DrawdownData,
    MonthlyHeatmapData,
    FormattedResults,
    ChartDataPoint,
    create_result_formatter,
)

__all__ = [
    # Code Generator
    "BacktestCodeGenerator",
    "CodeGenerationError",
    "ValidationError",
    # Code Validator
    "ASTCodeValidator",
    "ValidatorError",
    "ValidationResult",
    "create_code_validator",
    "BANNED_IMPORTS",
    "BANNED_FUNCTIONS",
    "ALLOWED_IMPORTS",
    # Execution - Storage
    "JobStorage",
    "InMemoryJobStorage",
    "JobNotFoundError",
    # Execution - Backends
    "ExecutionBackend",
    "ExecutionError",
    "ExecutionTimeoutError",
    "LocalBackend",
    "DockerBackend",
    "DEFAULT_PYTHON_IMAGE",
    # Execution - Workspace
    "WorkspaceManager",
    "LocalWorkspaceManager",
    "DooDBWorkspaceManager",
    "WorkspaceError",
    "create_workspace_manager",
    # Execution - Manager
    "BackendFactory",
    "JobManager",
    "create_job_manager",
    # Result Formatter
    "ResultFormatter",
    "StandardMetricsCalculator",
    "PerformanceMetrics",
    "EquityCurveData",
    "DrawdownData",
    "MonthlyHeatmapData",
    "FormattedResults",
    "ChartDataPoint",
    "create_result_formatter",
]
