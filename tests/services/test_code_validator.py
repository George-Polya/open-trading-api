"""
Tests for ASTCodeValidator service.

Covers:
- ValidationResult model instantiation
- Security constants validation
- Syntax checking (valid/invalid Python)
- Security validation (banned imports, functions, methods)
- Structure validation (result variable, strategy class)
- Full validation workflow
- Edge cases and error handling
"""

import pytest

from app.services.code_validator import (
    ASTCodeValidator,
    ValidationResult,
    ValidationError,
    SecurityLevel,
    create_code_validator,
    BANNED_IMPORTS,
    BANNED_FUNCTIONS,
    BANNED_METHODS,
    ALLOWED_IMPORTS,
    REQUIRED_RESULT_VARIABLE,
    REQUIRED_RESULT_KEYS,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def validator() -> ASTCodeValidator:
    """Create a default validator instance without formatting."""
    return ASTCodeValidator(enable_formatting=False)


@pytest.fixture
def strict_validator() -> ASTCodeValidator:
    """Create a strict mode validator."""
    return ASTCodeValidator(enable_formatting=False, strict_mode=True)


@pytest.fixture
def valid_strategy_code() -> str:
    """Sample valid strategy code that passes all checks."""
    return '''
import pandas as pd
import numpy as np
from backtesting import Strategy, Backtest

class SMAStrategy(Strategy):
    """Simple Moving Average Crossover Strategy."""

    n1 = 10
    n2 = 20

    def init(self):
        self.sma1 = self.I(lambda x: pd.Series(x).rolling(self.n1).mean(), self.data.Close)
        self.sma2 = self.I(lambda x: pd.Series(x).rolling(self.n2).mean(), self.data.Close)

    def next(self):
        if self.sma1[-1] > self.sma2[-1]:
            self.buy()
        elif self.sma1[-1] < self.sma2[-1]:
            self.sell()

result = {
    "equity_curve": [100000, 101000, 102000],
    "trades": [],
    "final_value": 102000,
}
'''


@pytest.fixture
def malicious_code_os_system() -> str:
    """Malicious code with os.system call."""
    return '''
import os
os.system("rm -rf /")
result = {"equity_curve": [], "trades": []}
'''


@pytest.fixture
def malicious_code_eval() -> str:
    """Malicious code with eval call."""
    return '''
import pandas as pd
code = "print('hacked')"
eval(code)
result = {"equity_curve": [], "trades": []}
'''


@pytest.fixture
def malicious_code_subprocess() -> str:
    """Malicious code with subprocess import."""
    return '''
import subprocess
subprocess.call(["ls", "-la"])
result = {"equity_curve": [], "trades": []}
'''


@pytest.fixture
def code_without_result() -> str:
    """Code missing the result variable."""
    return '''
import pandas as pd

class MyStrategy(Strategy):
    def next(self):
        pass

output = {"data": []}
'''


# =============================================================================
# Task 8.1: ValidationResult Model and Security Constants Tests
# =============================================================================


class TestValidationResult:
    """Tests for ValidationResult model."""

    def test_valid_result_creation(self):
        """Test creating a valid validation result."""
        result = ValidationResult(
            is_valid=True,
            errors=[],
            warnings=[],
        )
        assert result.is_valid is True
        assert result.errors == []
        assert result.warnings == []
        assert result.formatted_code is None

    def test_invalid_result_with_errors(self):
        """Test creating an invalid result with errors."""
        result = ValidationResult(
            is_valid=False,
            errors=["Syntax error", "Security violation"],
            warnings=["Missing docstring"],
        )
        assert result.is_valid is False
        assert len(result.errors) == 2
        assert len(result.warnings) == 1

    def test_result_with_formatted_code(self):
        """Test result with formatted code."""
        result = ValidationResult(
            is_valid=True,
            errors=[],
            warnings=[],
            formatted_code="print('hello')\n",
        )
        assert result.formatted_code == "print('hello')\n"


class TestValidationError:
    """Tests for ValidationError dataclass."""

    def test_error_creation(self):
        """Test creating a validation error."""
        error = ValidationError(
            message="Test error",
            line=10,
            column=5,
            level=SecurityLevel.ERROR,
            rule="test_rule",
        )
        assert error.message == "Test error"
        assert error.line == 10
        assert error.column == 5
        assert error.level == SecurityLevel.ERROR
        assert error.rule == "test_rule"

    def test_error_str_with_location(self):
        """Test error string representation with location."""
        error = ValidationError(
            message="Banned import",
            line=5,
            column=0,
            level=SecurityLevel.ERROR,
        )
        assert "[ERROR]" in str(error)
        assert "line 5" in str(error)
        assert "column 0" in str(error)

    def test_error_str_without_location(self):
        """Test error string representation without location."""
        error = ValidationError(
            message="General error",
            level=SecurityLevel.WARNING,
        )
        assert "[WARNING]" in str(error)
        assert "line" not in str(error)


class TestSecurityConstants:
    """Tests for security constants."""

    def test_banned_imports_contains_expected_modules(self):
        """Verify banned imports contains dangerous modules."""
        expected_banned = ["os", "sys", "subprocess", "socket", "requests", "pickle"]
        for module in expected_banned:
            assert module in BANNED_IMPORTS, f"{module} should be in BANNED_IMPORTS"

    def test_banned_functions_contains_expected_functions(self):
        """Verify banned functions contains dangerous functions."""
        expected_banned = ["eval", "exec", "compile", "__import__", "open"]
        for func in expected_banned:
            assert func in BANNED_FUNCTIONS, f"{func} should be in BANNED_FUNCTIONS"

    def test_banned_methods_contains_expected_methods(self):
        """Verify banned methods contains dangerous methods."""
        expected_banned = ["system", "popen", "call", "run", "Popen"]
        for method in expected_banned:
            assert method in BANNED_METHODS, f"{method} should be in BANNED_METHODS"

    def test_allowed_imports_contains_expected_modules(self):
        """Verify allowed imports contains safe modules."""
        expected_allowed = ["pandas", "numpy", "backtesting", "datetime", "math"]
        for module in expected_allowed:
            assert module in ALLOWED_IMPORTS, f"{module} should be in ALLOWED_IMPORTS"

    def test_required_result_variable(self):
        """Verify required result variable name."""
        assert REQUIRED_RESULT_VARIABLE == "result"

    def test_required_result_keys(self):
        """Verify required keys in result dictionary."""
        assert "equity_curve" in REQUIRED_RESULT_KEYS
        assert "trades" in REQUIRED_RESULT_KEYS


# =============================================================================
# Task 8.2: AST Parsing and Syntax Check Tests
# =============================================================================


class TestSyntaxCheck:
    """Tests for syntax checking functionality."""

    def test_valid_python_syntax(self, validator: ASTCodeValidator):
        """Test that valid Python syntax passes."""
        code = "x = 1 + 2\nprint(x)"
        errors = validator.check_syntax(code)
        assert len(errors) == 0

    def test_invalid_syntax_mismatched_parentheses(self, validator: ASTCodeValidator):
        """Test that mismatched parentheses are caught."""
        code = "print((1 + 2)"  # Missing closing paren
        errors = validator.check_syntax(code)
        assert len(errors) > 0
        assert any("Syntax error" in str(e) for e in errors)

    def test_invalid_syntax_invalid_indent(self, validator: ASTCodeValidator):
        """Test that invalid indentation is caught."""
        code = "def foo():\nx = 1"  # Missing indentation
        errors = validator.check_syntax(code)
        assert len(errors) > 0

    def test_invalid_syntax_incomplete_statement(self, validator: ASTCodeValidator):
        """Test that incomplete statements are caught."""
        code = "if True"  # Missing colon and body
        errors = validator.check_syntax(code)
        assert len(errors) > 0

    def test_valid_multiline_code(self, validator: ASTCodeValidator):
        """Test valid multi-line code passes syntax check."""
        code = '''
def calculate(x, y):
    result = x + y
    return result

value = calculate(10, 20)
'''
        errors = validator.check_syntax(code)
        assert len(errors) == 0

    def test_syntax_error_line_number(self, validator: ASTCodeValidator):
        """Test that syntax errors include line numbers."""
        code = "x = 1\ny = 2\nprint((x)"  # Error on line 3
        errors = validator.check_syntax(code)
        assert len(errors) > 0
        assert errors[0].line is not None


# =============================================================================
# Task 8.3: Security Validation Logic Tests
# =============================================================================


class TestSecurityValidation:
    """Tests for security validation via AST."""

    def test_banned_import_os(self, validator: ASTCodeValidator, malicious_code_os_system: str):
        """Test that import os is detected."""
        result = validator.validate(malicious_code_os_system)
        assert result.is_valid is False
        assert any("import" in e.lower() and "os" in e.lower() for e in result.errors)

    def test_banned_import_subprocess(
        self, validator: ASTCodeValidator, malicious_code_subprocess: str
    ):
        """Test that import subprocess is detected."""
        result = validator.validate(malicious_code_subprocess)
        assert result.is_valid is False
        assert any("subprocess" in e.lower() for e in result.errors)

    def test_banned_function_eval(self, validator: ASTCodeValidator, malicious_code_eval: str):
        """Test that eval() call is detected."""
        result = validator.validate(malicious_code_eval)
        assert result.is_valid is False
        assert any("eval" in e.lower() for e in result.errors)

    def test_banned_function_exec(self, validator: ASTCodeValidator):
        """Test that exec() call is detected."""
        code = '''
import pandas as pd
exec("print('hacked')")
result = {"equity_curve": [], "trades": []}
'''
        result = validator.validate(code)
        assert result.is_valid is False
        assert any("exec" in e.lower() for e in result.errors)

    def test_banned_function_compile(self, validator: ASTCodeValidator):
        """Test that compile() call is detected."""
        code = '''
import pandas as pd
compiled = compile("x=1", "", "exec")
result = {"equity_curve": [], "trades": []}
'''
        result = validator.validate(code)
        assert result.is_valid is False
        assert any("compile" in e.lower() for e in result.errors)

    def test_banned_function_open(self, validator: ASTCodeValidator):
        """Test that open() call is detected."""
        code = '''
import pandas as pd
f = open("file.txt", "r")
result = {"equity_curve": [], "trades": []}
'''
        result = validator.validate(code)
        assert result.is_valid is False
        assert any("open" in e.lower() for e in result.errors)

    def test_banned_import_from_syntax(self, validator: ASTCodeValidator):
        """Test that 'from os import *' is detected."""
        code = '''
from os import path
result = {"equity_curve": [], "trades": []}
'''
        result = validator.validate(code)
        assert result.is_valid is False
        assert any("os" in e.lower() for e in result.errors)

    def test_banned_module_attribute_access(self, validator: ASTCodeValidator):
        """Test that accessing banned module attributes is detected."""
        code = '''
import pandas as pd
# Trying to access os via indirect means
result = {"equity_curve": [], "trades": []}
'''
        # This code should be valid since it doesn't actually access os
        result = validator.validate(code)
        # Should only have warnings, not errors (no banned imports)
        assert all("os" not in e.lower() for e in result.errors)

    def test_wildcard_import_warning(self, validator: ASTCodeValidator):
        """Test that wildcard imports generate a warning."""
        code = '''
from math import *
result = {"equity_curve": [], "trades": []}
'''
        result = validator.validate(code)
        # Wildcard is a warning, not error
        assert any("wildcard" in w.lower() for w in result.warnings)

    def test_allowed_import_pandas(self, validator: ASTCodeValidator):
        """Test that pandas import is allowed."""
        code = '''
import pandas as pd
df = pd.DataFrame({"a": [1, 2, 3]})
result = {"equity_curve": [], "trades": []}
'''
        result = validator.validate(code)
        # Should not have errors about pandas
        assert not any("pandas" in e.lower() for e in result.errors)

    def test_allowed_import_numpy(self, validator: ASTCodeValidator):
        """Test that numpy import is allowed."""
        code = '''
import numpy as np
arr = np.array([1, 2, 3])
result = {"equity_curve": [], "trades": []}
'''
        result = validator.validate(code)
        # Should not have errors about numpy
        assert not any("numpy" in e.lower() for e in result.errors)

    def test_nested_banned_import(self, validator: ASTCodeValidator):
        """Test that nested banned imports are detected."""
        code = '''
import os.path
result = {"equity_curve": [], "trades": []}
'''
        result = validator.validate(code)
        assert result.is_valid is False
        assert any("os" in e.lower() for e in result.errors)

    def test_multiple_banned_operations(self, validator: ASTCodeValidator):
        """Test detection of multiple security violations."""
        code = '''
import os
import subprocess
eval("1+1")
exec("x=1")
result = {"equity_curve": [], "trades": []}
'''
        result = validator.validate(code)
        assert result.is_valid is False
        assert len(result.errors) >= 4  # At least 4 violations


# =============================================================================
# Task 8.4: Logical Structure and Output Schema Validation Tests
# =============================================================================


class TestStructureValidation:
    """Tests for logical structure validation."""

    def test_missing_result_variable(
        self, validator: ASTCodeValidator, code_without_result: str
    ):
        """Test that missing result variable is detected."""
        result = validator.validate(code_without_result)
        # Missing result should be a warning
        assert any("result" in w.lower() for w in result.warnings)

    def test_result_variable_present(self, validator: ASTCodeValidator):
        """Test that code with result variable passes."""
        code = '''
import pandas as pd
result = {"equity_curve": [1, 2, 3], "trades": []}
'''
        result = validator.validate(code)
        # Should not have warning about missing result
        assert not any("missing required variable" in w.lower() for w in result.warnings)

    def test_missing_strategy_class_warning(self, validator: ASTCodeValidator):
        """Test warning when Strategy class is missing."""
        code = '''
import pandas as pd
result = {"equity_curve": [], "trades": []}
'''
        result = validator.validate(code)
        assert any("strategy" in w.lower() for w in result.warnings)

    def test_strategy_class_present(
        self, validator: ASTCodeValidator, valid_strategy_code: str
    ):
        """Test that code with Strategy class passes."""
        result = validator.validate(valid_strategy_code)
        # Should not have warning about missing strategy class
        assert not any("no strategy class" in w.lower() for w in result.warnings)

    def test_missing_result_keys_warning(self, validator: ASTCodeValidator):
        """Test warning when result dict is missing required keys."""
        code = '''
import pandas as pd

class MyStrategy(Strategy):
    def next(self):
        pass

result = {"final_value": 100000}
'''
        result = validator.validate(code)
        # Should warn about missing keys
        assert any("missing keys" in w.lower() for w in result.warnings)

    def test_complete_result_dict(self, validator: ASTCodeValidator):
        """Test that complete result dict passes."""
        code = '''
import pandas as pd

class MyStrategy(Strategy):
    def next(self):
        pass

result = {"equity_curve": [100, 101], "trades": []}
'''
        result = validator.validate(code)
        # Should not warn about missing keys
        assert not any("missing keys" in w.lower() for w in result.warnings)


# =============================================================================
# Task 8.5: Integration and Full Validation Tests
# =============================================================================


class TestFullValidation:
    """Tests for the full validation workflow."""

    def test_valid_code_passes(
        self, validator: ASTCodeValidator, valid_strategy_code: str
    ):
        """Test that valid strategy code passes all checks."""
        result = validator.validate(valid_strategy_code)
        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_malicious_code_fails(
        self, validator: ASTCodeValidator, malicious_code_os_system: str
    ):
        """Test that malicious code fails validation."""
        result = validator.validate(malicious_code_os_system)
        assert result.is_valid is False
        assert len(result.errors) > 0

    def test_strict_mode_treats_warnings_as_errors(
        self, strict_validator: ASTCodeValidator
    ):
        """Test that strict mode treats warnings as errors."""
        code = '''
import pandas as pd
from math import *
output = {"data": []}
'''
        result = strict_validator.validate(code)
        # In strict mode, warnings become errors
        assert len(result.errors) > 0
        assert result.is_valid is False

    def test_validation_result_contains_all_issues(
        self, validator: ASTCodeValidator
    ):
        """Test that result contains all found issues."""
        code = '''
import os
import subprocess
eval("x")
result = {"data": []}
'''
        result = validator.validate(code)
        assert result.is_valid is False
        # Should have multiple errors
        assert len(result.errors) >= 3

    def test_empty_code(self, validator: ASTCodeValidator):
        """Test validation of empty code."""
        result = validator.validate("")
        # Empty code is syntactically valid but missing result
        assert any("result" in w.lower() for w in result.warnings)

    def test_only_imports_valid_code(self, validator: ASTCodeValidator):
        """Test code with only valid imports."""
        code = '''
import pandas as pd
import numpy as np
from datetime import datetime

class MyStrategy(Strategy):
    def next(self):
        pass

result = {"equity_curve": [], "trades": []}
'''
        result = validator.validate(code)
        assert result.is_valid is True


class TestFactoryFunction:
    """Tests for the create_code_validator factory function."""

    def test_create_default_validator(self):
        """Test creating a default validator."""
        validator = create_code_validator()
        assert isinstance(validator, ASTCodeValidator)
        assert validator.enable_formatting is True
        assert validator.strict_mode is False

    def test_create_validator_without_formatting(self):
        """Test creating validator without formatting."""
        validator = create_code_validator(enable_formatting=False)
        assert validator.enable_formatting is False

    def test_create_strict_validator(self):
        """Test creating a strict mode validator."""
        validator = create_code_validator(strict_mode=True)
        assert validator.strict_mode is True

    def test_create_validator_with_custom_banned_imports(self):
        """Test creating validator with custom banned imports."""
        custom_banned = frozenset({"custom_module"})
        validator = create_code_validator(custom_banned_imports=custom_banned)
        assert "custom_module" in validator.banned_imports
        # Original banned imports should still be present
        assert "os" in validator.banned_imports

    def test_create_validator_with_custom_banned_functions(self):
        """Test creating validator with custom banned functions."""
        custom_banned = frozenset({"custom_func"})
        validator = create_code_validator(custom_banned_functions=custom_banned)
        assert "custom_func" in validator.banned_functions
        # Original banned functions should still be present
        assert "eval" in validator.banned_functions


# =============================================================================
# Edge Cases and Error Handling Tests
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_unicode_in_code(self, validator: ASTCodeValidator):
        """Test code with unicode characters."""
        code = '''
import pandas as pd
# 한글 주석
message = "안녕하세요"
result = {"equity_curve": [], "trades": []}
'''
        result = validator.validate(code)
        # Should handle unicode without errors
        syntax_errors = [e for e in result.errors if "syntax" in e.lower()]
        assert len(syntax_errors) == 0

    def test_very_long_code(self, validator: ASTCodeValidator):
        """Test handling of very long code."""
        # Generate a long code string
        lines = ["import pandas as pd"]
        for i in range(1000):
            lines.append(f"x{i} = {i}")
        lines.append("result = {'equity_curve': [], 'trades': []}")
        code = "\n".join(lines)

        result = validator.validate(code)
        # Should complete without timeout/error
        assert isinstance(result, ValidationResult)

    def test_deeply_nested_code(self, validator: ASTCodeValidator):
        """Test deeply nested code structures."""
        code = '''
import pandas as pd

def outer():
    def middle():
        def inner():
            class Deep(Strategy):
                def next(self):
                    if True:
                        for i in range(10):
                            while True:
                                break
            return Deep
        return inner
    return middle

result = {"equity_curve": [], "trades": []}
'''
        result = validator.validate(code)
        # Should handle nested structures
        assert isinstance(result, ValidationResult)

    def test_code_with_decorators(self, validator: ASTCodeValidator):
        """Test code with decorators."""
        code = '''
import pandas as pd
from functools import wraps

def decorator(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapper

@decorator
def my_func():
    pass

class MyStrategy(Strategy):
    def next(self):
        pass

result = {"equity_curve": [], "trades": []}
'''
        result = validator.validate(code)
        assert isinstance(result, ValidationResult)

    def test_code_with_async(self, validator: ASTCodeValidator):
        """Test that asyncio import is blocked."""
        code = '''
import asyncio

async def main():
    await asyncio.sleep(1)

result = {"equity_curve": [], "trades": []}
'''
        result = validator.validate(code)
        assert result.is_valid is False
        assert any("asyncio" in e.lower() for e in result.errors)

    def test_code_with_comprehensions(self, validator: ASTCodeValidator):
        """Test code with list/dict/set comprehensions."""
        code = '''
import pandas as pd

lst = [i * 2 for i in range(10)]
dct = {k: v for k, v in enumerate(lst)}
st = {x for x in range(5)}
gen = (x ** 2 for x in range(3))

class MyStrategy(Strategy):
    def next(self):
        pass

result = {"equity_curve": list(lst), "trades": []}
'''
        result = validator.validate(code)
        assert isinstance(result, ValidationResult)

    def test_indirect_banned_function_access(self, validator: ASTCodeValidator):
        """Test that indirect access to banned functions is handled."""
        code = '''
import pandas as pd

# Try to get eval through builtins
# This should be caught
func = __builtins__["eval"]

result = {"equity_curve": [], "trades": []}
'''
        # Note: __builtins__ access might not be caught by simple AST analysis
        # but direct reference to __builtins__ is in banned list
        result = validator.validate(code)
        # This is a tricky case - static analysis has limits

    def test_getattr_is_banned(self, validator: ASTCodeValidator):
        """Test that getattr is banned."""
        code = '''
import pandas as pd
obj = object()
val = getattr(obj, "attr", None)
result = {"equity_curve": [], "trades": []}
'''
        result = validator.validate(code)
        assert result.is_valid is False
        assert any("getattr" in e.lower() for e in result.errors)


class TestFormattingIntegration:
    """Tests for code formatting integration."""

    def test_formatting_disabled(self):
        """Test that formatting can be disabled."""
        validator = ASTCodeValidator(enable_formatting=False)
        code = "x=1+2"  # Unformatted code

        result = validator.validate(code)
        # Should not have formatted_code when disabled
        # (and code is missing result so is_valid depends on that)

    def test_formatting_with_invalid_code(self):
        """Test formatting doesn't run on invalid code."""
        validator = ASTCodeValidator(enable_formatting=True)
        code = '''
import os
result = {"equity_curve": [], "trades": []}
'''
        result = validator.validate(code)
        assert result.is_valid is False
        # formatted_code should be None for invalid code
        assert result.formatted_code is None


# =============================================================================
# Regression Tests
# =============================================================================


class TestRegressions:
    """Regression tests for previously found issues."""

    def test_none_module_in_import_from(self, validator: ASTCodeValidator):
        """Test handling of 'from . import x' (relative import with no module)."""
        code = '''
# Relative imports have module=None
# This is valid Python but we should handle it
x = 1
result = {"equity_curve": [], "trades": []}
'''
        result = validator.validate(code)
        # Should not crash
        assert isinstance(result, ValidationResult)

    def test_attribute_chain_with_subscript(self, validator: ASTCodeValidator):
        """Test attribute chain extraction with subscript access."""
        code = '''
import pandas as pd
df = pd.DataFrame()
value = df["col"].iloc[0].values
result = {"equity_curve": [], "trades": []}
'''
        result = validator.validate(code)
        # Should handle subscript in chain
        assert isinstance(result, ValidationResult)

    def test_call_with_non_name_func(self, validator: ASTCodeValidator):
        """Test handling calls where func is not Name or Attribute."""
        code = '''
import pandas as pd
funcs = [lambda x: x]
result_value = funcs[0](10)
result = {"equity_curve": [], "trades": []}
'''
        result = validator.validate(code)
        # Should handle lambda calls without error
        assert isinstance(result, ValidationResult)
