# Task ID: 8

**Title:** CodeValidator 및 정적 보안 검사기 구축

**Status:** done

**Dependencies:** 7 ✓

**Priority:** medium

**Description:** 생성 코드에 대한 안전성·품질 검증기를 구현해 금지 패턴을 차단합니다.

**Details:**

Implementation:
- Create app/services/code_validator.py that parses AST to detect banned nodes (Import/os, subprocess, eval/exec, with open mode write, network libs) as listed in PRD 7.1.
- Provide lint checks: ensure only approved imports (pandas, numpy, data_provider usage) and JSON result schema enforced by verifying code includes result dict with required keys.
- Add optional black formatting attempt + compile() check to catch syntax errors.
Pseudo Flow:
```
class CodeValidator:
    def validate(code:str) -> ValidationResult:
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and node.func.id in BANNED_CALLS: ...
        return ValidationResult(is_valid=True, errors=[])
```
- Provide ValidationResult dataclass with errors list; integrate with task7.

**Test Strategy:**

- pytest: feed malicious snippets (os.system) to ensure validator fails with helpful error message.
- Provide golden-pass test with PRD sample strategy to confirm valid.
- Use coverage to ensure >90% of rule branches executed.

## Subtasks

### 8.1. Define ValidationResult Model and Security Constants

**Status:** done  
**Dependencies:** None  

Create the data structure for validation outcomes and define lists of allowed/banned modules.

**Details:**

In a new file `app/services/code_validator.py` (or shared models), define `ValidationResult` dataclass/Pydantic model with fields `is_valid: bool` and `errors: List[str]`. Define constants for `BANNED_IMPORTS` (os, sys, subprocess, etc.), `BANNED_FUNCTIONS` (eval, exec, open), and `ALLOWED_IMPORTS` (pandas, numpy, backtesting, app.data_provider).

### 8.2. Implement AST Parsing and Syntax Check

**Status:** done  
**Dependencies:** 8.1  

Implement the base `CodeValidator` class with syntax checking capabilities.

**Details:**

Create `class CodeValidator` in `app/services/code_validator.py`. Add a method `check_syntax(code: str) -> List[str]` that uses `ast.parse(code)` and `compile(code, ..., mode='exec')` to catch syntax errors. This serves as the first line of defense before detailed AST analysis.

### 8.3. Implement Security Validation Logic via AST

**Status:** done  
**Dependencies:** 8.2  

Traverse the AST to detect banned imports, functions, and dangerous patterns.

**Details:**

Add `validate_security(tree: ast.AST) -> List[str]` to `CodeValidator`. Use `ast.walk` or `NodeVisitor` to check `Import`, `ImportFrom` against `BANNED_IMPORTS` and `Call` nodes against `BANNED_FUNCTIONS`. Specifically check `Call` nodes for `open()` and verify arguments to block write mode if possible, or ban `open` entirely.

### 8.4. Implement Logical Structure and Output Schema Validation

**Status:** done  
**Dependencies:** 8.3  

Ensure the code follows the required logical structure for the backtest engine.

**Details:**

Add `validate_structure(tree: ast.AST) -> List[str]`. Verify that the code assigns a variable named `result` (check `Assign` nodes). Optionally check if specific required keys (e.g., 'equity_curve', 'trades') are present in the dictionary assignment if static analysis permits, or just ensure the `result` variable exists.

### 8.5. Integrate Formatting and Finalize Validator Service

**Status:** done  
**Dependencies:** 8.4  

Combine all checks into a main validate method and add optional auto-formatting.

**Details:**

Implement the main `validate(code: str) -> ValidationResult` method that calls syntax, security, and structure checks in order. Integrate `black` (optional) to format code if valid. Return the final `ValidationResult`. Register `CodeValidator` in the dependency injection container if applicable.
