# Backtest Execution API Endpoints

This document describes the backtest execution endpoints implemented in Task 10.3.

## Overview

The backtest execution API provides endpoints for submitting Python backtest code for execution in a sandboxed environment, tracking job status, and retrieving results.

## Base URL

```
/api/v1/backtest
```

## Endpoints

### 1. Execute Backtest

Submit backtest code for execution.

**Endpoint:** `POST /api/v1/backtest/execute`

**Request Body:**

```json
{
  "code": "string",              // Python code to execute (optional if code_reference provided)
  "code_reference": "string",    // Reference ID to previously generated code (optional if code provided)
  "params": {},                  // Execution parameters (optional, default: {})
  "timeout": 300,                // Timeout in seconds (optional, max: 600)
  "async_mode": true             // Async (true) or sync (false) mode (optional, default: true)
}
```

**Response (Async Mode - 202 Accepted):**

```json
{
  "job_id": "backtest-abc123def456",
  "status": "pending",
  "message": "Backtest submitted successfully. Use job_id to track progress.",
  "result": null
}
```

**Response (Sync Mode - 200 OK):**

```json
{
  "job_id": "backtest-abc123def456",
  "status": "completed",
  "message": "Backtest execution completed successfully.",
  "result": {
    "success": true,
    "job_id": "backtest-abc123def456",
    "status": "completed",
    "data": {
      "portfolio_value": 150000,
      "returns": 0.5
    },
    "error": null,
    "logs": "Execution logs...",
    "duration_seconds": 2.5
  }
}
```

**Error Responses:**

- `400 Bad Request`: Invalid request (missing code, both code and code_reference provided, etc.)
- `501 Not Implemented`: Code reference feature not yet implemented
- `500 Internal Server Error`: Execution system failure

### 2. Get Job Status

Get the current status of a backtest execution job.

**Endpoint:** `GET /api/v1/backtest/status/{job_id}`

**Response (200 OK):**

```json
{
  "job_id": "backtest-abc123def456",
  "status": "running"
}
```

**Error Responses:**

- `404 Not Found`: Job not found

### 3. Get Job Result

Get the result of a completed backtest execution job.

**Endpoint:** `GET /api/v1/backtest/result/{job_id}`

**Response (200 OK):**

```json
{
  "success": true,
  "job_id": "backtest-abc123def456",
  "status": "completed",
  "data": {
    "portfolio_value": 150000,
    "returns": 0.5
  },
  "error": null,
  "logs": "Execution logs...",
  "duration_seconds": 2.5
}
```

**Error Responses:**

- `404 Not Found`: Job not found

## Job Status Values

- `pending`: Job is queued for execution
- `running`: Job is currently executing
- `completed`: Job completed successfully
- `failed`: Job failed with an error
- `cancelled`: Job was cancelled
- `timeout`: Job exceeded timeout limit

## Usage Examples

### Async Mode (Default)

Submit a backtest and poll for status:

```python
import requests

# Submit backtest
response = requests.post(
    "http://localhost:8000/api/v1/backtest/execute",
    json={
        "code": "print('Hello, backtest!')",
        "params": {"ticker": "AAPL"}
    }
)
job_id = response.json()["job_id"]

# Poll for status
status_response = requests.get(
    f"http://localhost:8000/api/v1/backtest/status/{job_id}"
)
print(status_response.json())

# Get result when completed
result_response = requests.get(
    f"http://localhost:8000/api/v1/backtest/result/{job_id}"
)
print(result_response.json())
```

### Sync Mode

Submit a backtest and wait for completion:

```python
import requests

response = requests.post(
    "http://localhost:8000/api/v1/backtest/execute",
    json={
        "code": "print('Hello, backtest!')",
        "params": {"ticker": "AAPL"},
        "async_mode": False  # Wait for completion
    }
)
result = response.json()["result"]
print(result)
```

## Implementation Details

### Architecture

- **Endpoint:** `/mnt/c/Users/wlska/Documents/gitlab/open-trading-api/app/api/v1/endpoints/backtest.py`
- **Container Integration:** `/mnt/c/Users/wlska/Documents/gitlab/open-trading-api/app/core/container.py`
- **Router Registration:** `/mnt/c/Users/wlska/Documents/gitlab/open-trading-api/app/main.py`

### Dependency Injection

The `JobManager` is provided as a singleton through the `Container` class:

```python
from app.core.container import get_job_manager_dep

@router.post("/execute")
async def execute_backtest(
    request: ExecuteBacktestRequest,
    response: Response,
    job_manager: JobManager = Depends(get_job_manager_dep),
):
    ...
```

### Request Validation

- Exactly one of `code` or `code_reference` must be provided
- Code cannot be empty or whitespace-only
- Timeout must be between 1 and 600 seconds
- Code length must not exceed 100,000 characters

### Status Codes

- **202 Accepted**: Async mode - job submitted successfully
- **200 OK**: Sync mode - job completed
- **400 Bad Request**: Validation error
- **404 Not Found**: Job not found
- **501 Not Implemented**: Code reference not yet implemented
- **500 Internal Server Error**: Execution system failure

## Testing

Comprehensive test suite located at:
`/mnt/c/Users/wlska/Documents/gitlab/open-trading-api/tests/api/v1/test_backtest_execute.py`

Run tests:

```bash
conda run -n py3.13 pytest tests/api/v1/test_backtest_execute.py -v
```

Test coverage includes:
- Async and sync execution modes
- Request validation (missing code, invalid timeout, etc.)
- Error handling (job not found, execution failures)
- Complete workflow (submit → status → result)
- Edge cases (empty code, code reference, etc.)

## Future Enhancements

- Implement code reference lookup for reusing previously generated code
- Add batch execution support
- Implement job cancellation endpoint
- Add job listing/filtering endpoint
- Support streaming execution logs
