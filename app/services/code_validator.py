"""
Code Validator Service - AST-based Security and Quality Validation.

This module implements static analysis for generated backtest code to ensure:
1. Syntax correctness
2. Security (no dangerous imports/functions)
3. Structural compliance (required variables/patterns)
4. Optional code formatting

Follows SOLID principles with clear separation of concerns.
"""

import ast
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol


# =============================================================================
# Task 8.1: ValidationResult Model and Security Constants
# =============================================================================


class SecurityLevel(Enum):
    """Security level for validation messages."""

    ERROR = "error"  # Critical issues that fail validation
    WARNING = "warning"  # Non-critical issues that should be reviewed


@dataclass
class ValidationError:
    """
    Represents a single validation issue.

    Attributes:
        message: Human-readable error message
        line: Line number where the issue was detected (optional)
        column: Column number where the issue was detected (optional)
        level: Security level (error or warning)
        rule: The rule that was violated
    """

    message: str
    line: int | None = None
    column: int | None = None
    level: SecurityLevel = SecurityLevel.ERROR
    rule: str = ""

    def __str__(self) -> str:
        """Format error message with location if available."""
        location = ""
        if self.line is not None:
            location = f" at line {self.line}"
            if self.column is not None:
                location += f", column {self.column}"
        return f"[{self.level.value.upper()}] {self.message}{location}"


@dataclass
class ValidationResult:
    """
    Result of code validation.

    Attributes:
        is_valid: Whether the code passed all validation checks
        errors: List of error-level issues (cause validation failure)
        warnings: List of warning-level issues (informational)
        formatted_code: Optionally formatted code if formatting was applied
    """

    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    formatted_code: str | None = None


# Security Constants
BANNED_IMPORTS: frozenset[str] = frozenset(
    {
        # System access
        "os",
        "sys",
        "subprocess",
        "shutil",
        "pathlib",
        # Code execution
        "importlib",
        "builtins",
        "__builtins__",
        # Network access
        "socket",
        "http",
        "urllib",
        "requests",
        "httpx",
        "aiohttp",
        "ftplib",
        "smtplib",
        "telnetlib",
        # Process/threading
        "multiprocessing",
        "threading",
        "concurrent",
        "asyncio",
        # File manipulation
        "pickle",
        "shelve",
        "marshal",
        # Code inspection/manipulation
        "inspect",
        "dis",
        "code",
        "codeop",
        "ast",
        "types",
        "ctypes",
        # Dangerous utilities
        "pty",
        "tty",
        "pipes",
        "tempfile",
        "glob",
        "fnmatch",
    }
)

BANNED_FUNCTIONS: frozenset[str] = frozenset(
    {
        # Code execution
        "eval",
        "exec",
        "compile",
        "__import__",
        "globals",
        "locals",
        # Object manipulation
        "getattr",
        "setattr",
        "delattr",
        "hasattr",
        # File operations
        "open",
        "input",
        # Dangerous built-ins
        "breakpoint",
        "exit",
        "quit",
        "help",
        "license",
        "credits",
        "copyright",
        "memoryview",
        "bytearray",
    }
)

BANNED_METHODS: frozenset[str] = frozenset(
    {
        # File-like operations
        "read",
        "write",
        "readline",
        "readlines",
        "writelines",
        # System operations
        "system",
        "popen",
        "spawn",
        "fork",
        "kill",
        # Subprocess operations (subprocess module itself is not in ALLOWED_IMPORTS)
        "call",
        "check_call",
        "check_output",
        "Popen",
        # Note: "run" removed to allow bt.run(), Backtest.run() etc.
        # subprocess.run() is blocked by import restriction
    }
)

ALLOWED_IMPORTS: frozenset[str] = frozenset(
    {
        # Data analysis
        "pandas",
        "numpy",
        "scipy",
        # Backtesting framework
        "backtesting",
        "bt",
        # Visualization (for reports)
        "matplotlib",
        "plotly",
        # Technical analysis
        "ta",
        "talib",
        # Math and statistics
        "math",
        "statistics",
        "decimal",
        "fractions",
        # Date/time
        "datetime",
        "dateutil",
        # Collections and typing
        "collections",
        "typing",
        "dataclasses",
        "enum",
        "functools",
        "itertools",
        "operator",
        # App-specific modules
        "app",
        "app.data_provider",
        "app.providers",
    }
)

# Required output variable name
REQUIRED_RESULT_VARIABLE: str = "result"

# Required keys in result dictionary (for structural validation)
REQUIRED_RESULT_KEYS: frozenset[str] = frozenset(
    {
        "equity_series",
        "trades",
    }
)


# =============================================================================
# Validator Protocol
# =============================================================================


class CodeValidatorProtocol(Protocol):
    """
    Protocol for code validators.

    Allows dependency injection of different validation strategies.
    """

    def validate(self, code: str) -> ValidationResult:
        """
        Validate generated Python code.

        Args:
            code: Python code string to validate

        Returns:
            ValidationResult indicating success/failure and any issues
        """
        ...


# =============================================================================
# Task 8.2: AST Parsing and Syntax Check
# =============================================================================


class ASTCodeValidator:
    """
    AST-based code validator for generated backtest code.

    This validator performs static analysis using Python's AST module to detect:
    - Syntax errors
    - Dangerous imports and function calls
    - Missing required structures
    - Security policy violations

    Example:
        validator = ASTCodeValidator()
        result = validator.validate(code)
        if not result.is_valid:
            print("Validation failed:", result.errors)
    """

    def __init__(
        self,
        banned_imports: frozenset[str] | None = None,
        banned_functions: frozenset[str] | None = None,
        banned_methods: frozenset[str] | None = None,
        allowed_imports: frozenset[str] | None = None,
        enable_formatting: bool = True,
        strict_mode: bool = False,
    ):
        """
        Initialize the validator with security rules.

        Args:
            banned_imports: Set of module names that are not allowed
            banned_functions: Set of function names that are not allowed
            banned_methods: Set of method names that are not allowed
            allowed_imports: Set of allowed module names (whitelist mode if set)
            enable_formatting: Whether to attempt code formatting with black
            strict_mode: If True, treat warnings as errors
        """
        self.banned_imports = banned_imports or BANNED_IMPORTS
        self.banned_functions = banned_functions or BANNED_FUNCTIONS
        self.banned_methods = banned_methods or BANNED_METHODS
        self.allowed_imports = allowed_imports or ALLOWED_IMPORTS
        self.enable_formatting = enable_formatting
        self.strict_mode = strict_mode

    def check_syntax(self, code: str) -> list[ValidationError]:
        """
        Check code for syntax errors using ast.parse and compile.

        This is the first line of defense before detailed AST analysis.

        Args:
            code: Python code string to check

        Returns:
            List of ValidationError objects for any syntax errors found
        """
        errors: list[ValidationError] = []

        # Try to parse as AST
        try:
            ast.parse(code)
        except SyntaxError as e:
            errors.append(
                ValidationError(
                    message=f"Syntax error: {e.msg}",
                    line=e.lineno,
                    column=e.offset,
                    level=SecurityLevel.ERROR,
                    rule="syntax_parse",
                )
            )
            return errors  # Can't continue if parsing fails

        # Try to compile (catches some issues ast.parse misses)
        try:
            compile(code, "<generated>", "exec")
        except SyntaxError as e:
            errors.append(
                ValidationError(
                    message=f"Compilation error: {e.msg}",
                    line=e.lineno,
                    column=e.offset,
                    level=SecurityLevel.ERROR,
                    rule="syntax_compile",
                )
            )
        except ValueError as e:
            # ValueError can occur for certain code constructs
            errors.append(
                ValidationError(
                    message=f"Value error during compilation: {e}",
                    level=SecurityLevel.ERROR,
                    rule="syntax_compile",
                )
            )

        return errors

    # =========================================================================
    # Task 8.3: Security Validation Logic via AST
    # =========================================================================

    def validate_security(self, tree: ast.AST) -> list[ValidationError]:
        """
        Traverse the AST to detect banned imports, functions, and patterns.

        Checks for:
        - Banned module imports (import os, from subprocess import *)
        - Banned function calls (eval(), exec(), open())
        - Banned method calls (os.system(), subprocess.call())
        - Attribute access to banned modules

        Args:
            tree: Parsed AST tree

        Returns:
            List of ValidationError objects for security violations
        """
        errors: list[ValidationError] = []

        for node in ast.walk(tree):
            # Check import statements
            if isinstance(node, ast.Import):
                errors.extend(self._check_import(node))
            elif isinstance(node, ast.ImportFrom):
                errors.extend(self._check_import_from(node))

            # Check function/method calls
            elif isinstance(node, ast.Call):
                errors.extend(self._check_call(node))

            # Check attribute access (e.g., os.path)
            elif isinstance(node, ast.Attribute):
                errors.extend(self._check_attribute_access(node))

        return errors

    def _check_import(self, node: ast.Import) -> list[ValidationError]:
        """Check 'import x' statements for banned modules."""
        errors: list[ValidationError] = []

        for alias in node.names:
            module_name = alias.name.split(".")[0]

            if module_name in self.banned_imports:
                errors.append(
                    ValidationError(
                        message=f"Banned import: '{alias.name}' is not allowed",
                        line=node.lineno,
                        column=node.col_offset,
                        level=SecurityLevel.ERROR,
                        rule="banned_import",
                    )
                )
            elif not self._is_import_allowed(alias.name):
                errors.append(
                    ValidationError(
                        message=f"Unapproved import: '{alias.name}' is not in the allowed list",
                        line=node.lineno,
                        column=node.col_offset,
                        level=SecurityLevel.WARNING,
                        rule="unapproved_import",
                    )
                )

        return errors

    def _check_import_from(self, node: ast.ImportFrom) -> list[ValidationError]:
        """Check 'from x import y' statements for banned modules."""
        errors: list[ValidationError] = []

        if node.module is None:
            return errors

        module_name = node.module.split(".")[0]

        if module_name in self.banned_imports:
            errors.append(
                ValidationError(
                    message=f"Banned import: 'from {node.module}' is not allowed",
                    line=node.lineno,
                    column=node.col_offset,
                    level=SecurityLevel.ERROR,
                    rule="banned_import_from",
                )
            )
        elif not self._is_import_allowed(node.module):
            errors.append(
                ValidationError(
                    message=f"Unapproved import: 'from {node.module}' is not in the allowed list",
                    line=node.lineno,
                    column=node.col_offset,
                    level=SecurityLevel.WARNING,
                    rule="unapproved_import_from",
                )
            )

        # Check for 'from x import *' (wildcard import)
        for alias in node.names:
            if alias.name == "*":
                errors.append(
                    ValidationError(
                        message=f"Wildcard import: 'from {node.module} import *' is not allowed",
                        line=node.lineno,
                        column=node.col_offset,
                        level=SecurityLevel.WARNING,
                        rule="wildcard_import",
                    )
                )

        return errors

    def _is_import_allowed(self, module_path: str) -> bool:
        """Check if a module import is in the allowed list."""
        # Check exact match
        if module_path in self.allowed_imports:
            return True

        # Check if it's a submodule of an allowed module
        parts = module_path.split(".")
        for i in range(len(parts)):
            parent = ".".join(parts[: i + 1])
            if parent in self.allowed_imports:
                return True

        return False

    def _check_call(self, node: ast.Call) -> list[ValidationError]:
        """Check function/method calls for banned operations."""
        errors: list[ValidationError] = []

        func_name = self._get_call_name(node)

        if func_name:
            # Check for banned function calls
            base_name = func_name.split(".")[-1]

            if base_name in self.banned_functions:
                errors.append(
                    ValidationError(
                        message=f"Banned function: '{func_name}()' is not allowed",
                        line=node.lineno,
                        column=node.col_offset,
                        level=SecurityLevel.ERROR,
                        rule="banned_function",
                    )
                )

            # Check for banned method calls
            if base_name in self.banned_methods:
                errors.append(
                    ValidationError(
                        message=f"Banned method: '{func_name}()' is not allowed",
                        line=node.lineno,
                        column=node.col_offset,
                        level=SecurityLevel.ERROR,
                        rule="banned_method",
                    )
                )

            # Check for module.function patterns (e.g., os.system)
            if "." in func_name:
                module_part = func_name.split(".")[0]
                if module_part in self.banned_imports:
                    errors.append(
                        ValidationError(
                            message=f"Banned module access: '{func_name}()' accesses banned module '{module_part}'",
                            line=node.lineno,
                            column=node.col_offset,
                            level=SecurityLevel.ERROR,
                            rule="banned_module_call",
                        )
                    )

        return errors

    def _check_attribute_access(self, node: ast.Attribute) -> list[ValidationError]:
        """Check attribute access for banned module usage."""
        errors: list[ValidationError] = []

        # Get the full attribute chain (e.g., 'os.path.join')
        attr_chain = self._get_attribute_chain(node)

        if attr_chain:
            root = attr_chain.split(".")[0]
            if root in self.banned_imports:
                errors.append(
                    ValidationError(
                        message=f"Banned module access: accessing '{attr_chain}' from banned module '{root}'",
                        line=node.lineno,
                        column=node.col_offset,
                        level=SecurityLevel.ERROR,
                        rule="banned_attribute_access",
                    )
                )

        return errors

    def _get_call_name(self, node: ast.Call) -> str | None:
        """Extract the function/method name from a Call node."""
        if isinstance(node.func, ast.Name):
            return node.func.id
        elif isinstance(node.func, ast.Attribute):
            return self._get_attribute_chain(node.func)
        return None

    def _get_attribute_chain(self, node: ast.Attribute) -> str | None:
        """Build the full attribute chain string (e.g., 'os.path.join')."""
        parts: list[str] = [node.attr]
        current = node.value

        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value

        if isinstance(current, ast.Name):
            parts.append(current.id)
            return ".".join(reversed(parts))

        return None

    # =========================================================================
    # Task 8.4: Logical Structure and Output Schema Validation
    # =========================================================================

    def validate_structure(self, tree: ast.AST) -> list[ValidationError]:
        """
        Verify the code follows the required logical structure.

        Checks for:
        - Presence of 'result' variable assignment
        - Strategy class definition (optional)
        - Required method definitions (optional)

        Args:
            tree: Parsed AST tree

        Returns:
            List of ValidationError objects for structural issues
        """
        errors: list[ValidationError] = []

        # Track what we find
        has_result_assignment = False
        has_strategy_class = False
        result_keys: set[str] = set()

        for node in ast.walk(tree):
            # Check for result variable assignment
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == REQUIRED_RESULT_VARIABLE:
                        has_result_assignment = True
                        # Try to extract dictionary keys if it's a dict literal
                        result_keys.update(self._extract_dict_keys(node.value))

            # Check for named assignment (result := {...})
            elif isinstance(node, ast.NamedExpr):
                if node.target.id == REQUIRED_RESULT_VARIABLE:
                    has_result_assignment = True
                    result_keys.update(self._extract_dict_keys(node.value))

            # Check for Strategy class definition
            elif isinstance(node, ast.ClassDef):
                if "Strategy" in node.name:
                    has_strategy_class = True

        # Validate findings
        if not has_result_assignment:
            errors.append(
                ValidationError(
                    message=f"Missing required variable: '{REQUIRED_RESULT_VARIABLE}' must be assigned",
                    level=SecurityLevel.WARNING,
                    rule="missing_result_variable",
                )
            )

        # Check for required keys in result dictionary (if we could extract them)
        if has_result_assignment and result_keys:
            missing_keys = REQUIRED_RESULT_KEYS - result_keys
            if missing_keys:
                errors.append(
                    ValidationError(
                        message=f"Missing keys in result: {', '.join(sorted(missing_keys))}",
                        level=SecurityLevel.WARNING,
                        rule="missing_result_keys",
                    )
                )

        # Strategy class is a recommendation, not requirement
        if not has_strategy_class:
            errors.append(
                ValidationError(
                    message="No Strategy class found (expected class name containing 'Strategy')",
                    level=SecurityLevel.WARNING,
                    rule="missing_strategy_class",
                )
            )

        return errors

    def _extract_dict_keys(self, node: ast.expr) -> set[str]:
        """Extract dictionary keys from an AST node if it's a dict literal."""
        keys: set[str] = set()

        if isinstance(node, ast.Dict):
            for key in node.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    keys.add(key.value)
                elif isinstance(key, ast.Str):  # Python < 3.8 compatibility
                    keys.add(key.s)

        return keys

    # =========================================================================
    # Task 8.5: Integrate Formatting and Finalize Validator Service
    # =========================================================================

    def format_code(self, code: str) -> tuple[str, list[ValidationError]]:
        """
        Attempt to format code using black.

        Args:
            code: Python code string to format

        Returns:
            Tuple of (formatted_code, errors)
            If formatting fails, returns original code with error
        """
        errors: list[ValidationError] = []

        if not self.enable_formatting:
            return code, errors

        try:
            import black

            formatted = black.format_str(code, mode=black.Mode())
            return formatted, errors
        except ImportError:
            errors.append(
                ValidationError(
                    message="black formatter not available",
                    level=SecurityLevel.WARNING,
                    rule="formatter_unavailable",
                )
            )
            return code, errors
        except black.InvalidInput as e:
            errors.append(
                ValidationError(
                    message=f"Code formatting failed: {e}",
                    level=SecurityLevel.WARNING,
                    rule="format_failed",
                )
            )
            return code, errors
        except Exception as e:
            errors.append(
                ValidationError(
                    message=f"Unexpected formatting error: {e}",
                    level=SecurityLevel.WARNING,
                    rule="format_error",
                )
            )
            return code, errors

    def validate(self, code: str) -> ValidationResult:
        """
        Main validation method that orchestrates all checks.

        Performs the following checks in order:
        1. Syntax validation (ast.parse + compile)
        2. Security validation (banned imports/functions)
        3. Structure validation (required variables/patterns)
        4. Optional code formatting

        Args:
            code: Python code string to validate

        Returns:
            ValidationResult with validation status and any issues
        """
        all_errors: list[ValidationError] = []

        # Step 1: Check syntax
        syntax_errors = self.check_syntax(code)
        all_errors.extend(syntax_errors)

        # If there are syntax errors, we can't proceed with AST analysis
        if any(e.level == SecurityLevel.ERROR for e in syntax_errors):
            return self._build_result(all_errors, code)

        # Parse AST for further analysis
        try:
            tree = ast.parse(code)
        except SyntaxError:
            # Should not happen since we already checked, but just in case
            return self._build_result(all_errors, code)

        # Step 2: Security validation
        security_errors = self.validate_security(tree)
        all_errors.extend(security_errors)

        # Step 3: Structure validation
        structure_errors = self.validate_structure(tree)
        all_errors.extend(structure_errors)

        # Step 4: Format code (if no critical errors)
        formatted_code = code
        critical_errors = [e for e in all_errors if e.level == SecurityLevel.ERROR]
        if not critical_errors and self.enable_formatting:
            formatted_code, format_errors = self.format_code(code)
            all_errors.extend(format_errors)

        return self._build_result(all_errors, formatted_code)

    def _build_result(
        self, validation_errors: list[ValidationError], code: str
    ) -> ValidationResult:
        """Build ValidationResult from list of ValidationError objects."""
        errors: list[str] = []
        warnings: list[str] = []

        for err in validation_errors:
            message = str(err)
            if err.level == SecurityLevel.ERROR:
                errors.append(message)
            else:
                if self.strict_mode:
                    errors.append(message)
                else:
                    warnings.append(message)

        is_valid = len(errors) == 0

        return ValidationResult(
            is_valid=is_valid,
            errors=errors,
            warnings=warnings,
            formatted_code=code if is_valid else None,
        )


# =============================================================================
# Factory Function
# =============================================================================


def create_code_validator(
    enable_formatting: bool = True,
    strict_mode: bool = False,
    custom_banned_imports: frozenset[str] | None = None,
    custom_banned_functions: frozenset[str] | None = None,
) -> ASTCodeValidator:
    """
    Factory function to create a configured ASTCodeValidator.

    Args:
        enable_formatting: Whether to enable black formatting
        strict_mode: Whether to treat warnings as errors
        custom_banned_imports: Additional banned imports to add
        custom_banned_functions: Additional banned functions to add

    Returns:
        Configured ASTCodeValidator instance
    """
    banned_imports = BANNED_IMPORTS
    banned_functions = BANNED_FUNCTIONS

    if custom_banned_imports:
        banned_imports = banned_imports | custom_banned_imports

    if custom_banned_functions:
        banned_functions = banned_functions | custom_banned_functions

    return ASTCodeValidator(
        banned_imports=banned_imports,
        banned_functions=banned_functions,
        banned_methods=BANNED_METHODS,
        allowed_imports=ALLOWED_IMPORTS,
        enable_formatting=enable_formatting,
        strict_mode=strict_mode,
    )
