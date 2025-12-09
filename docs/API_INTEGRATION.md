# API Integration Documentation

## Overview

This document describes the API integration architecture for the Natural Language Backtesting Service. It covers router registration, dependency injection, and OpenAPI documentation.

## Architecture

### Application Entry Point

The FastAPI application is created and configured in `/mnt/c/Users/wlska/Documents/gitlab/open-trading-api/app/main.py`:

```python
from app.main import create_app

app = create_app()
```

### Router Structure

```
app/
├── api/
│   ├── __init__.py
│   └── v1/
│       ├── __init__.py          # Centralized v1 router
│       └── endpoints/
│           ├── __init__.py
│           └── backtest.py      # Backtest endpoints
```

#### Centralized Router Pattern

All API v1 endpoints are aggregated through a single router in `app/api/v1/__init__.py`:

```python
from fastapi import APIRouter
from app.api.v1.endpoints import backtest

api_router = APIRouter()
api_router.include_router(backtest.router)
```

This pattern allows for:
- Easy addition of new endpoint modules
- Consistent versioning
- Clean separation of concerns
- Centralized middleware application

#### Router Registration

The main application registers the API router with the `/api/v1` prefix:

```python
# app/main.py
from app.api.v1 import api_router

app.include_router(
    api_router,
    prefix="/api/v1",
    tags=["API v1"],
)
```

## Dependency Injection

### Container Pattern

The application uses a dependency injection container pattern implemented in `/mnt/c/Users/wlska/Documents/gitlab/open-trading-api/app/core/container.py`.

#### Core Services

The container manages the following services:

1. **Settings** - Application configuration
2. **HTTP Client** - Shared async HTTP client (httpx.AsyncClient)
3. **LLM Provider** - Language model provider for code generation
4. **Data Provider** - Market data provider (KIS, YFinance, etc.)
5. **Code Validator** - AST-based Python code validator
6. **Job Manager** - Backtest execution orchestrator
7. **Code Generator** - Natural language to code converter
8. **Result Formatter** - Backtest result formatter and analyzer

#### Lifecycle Management

The container handles startup and shutdown lifecycle events:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    container = get_container()
    await container.startup()

    yield

    # Shutdown
    await container.shutdown()
```

Startup tasks:
- Pre-initialize settings
- Create HTTP client
- Validate configuration

Shutdown tasks:
- Close HTTP client connections
- Release LLM provider resources
- Clean up data provider connections
- Shutdown job manager

#### FastAPI Dependencies

Each service is exposed as a FastAPI dependency function:

```python
from app.core.container import (
    get_settings_dep,
    get_http_client_dep,
    get_llm_provider_dep,
    get_data_provider_dep,
    get_code_validator_dep,
    get_job_manager_dep,
    get_code_generator_dep,
    get_result_formatter_dep,
)

@router.post("/generate")
async def generate_backtest_code(
    request: BacktestRequest,
    generator: BacktestCodeGenerator = Depends(get_code_generator_dep),
):
    result = await generator.generate(request)
    return result
```

### Lazy Initialization

Services are lazily initialized on first access:
- Reduces startup time
- Avoids unnecessary resource allocation
- Enables testing without full initialization

## API Endpoints

### Backtest Endpoints

All backtest endpoints are under the `/api/v1/backtest` prefix:

#### Code Generation
- `POST /api/v1/backtest/generate` - Generate backtest code from natural language

#### Execution
- `POST /api/v1/backtest/execute` - Execute backtest code (async/sync modes)
- `GET /api/v1/backtest/status/{job_id}` - Get job status
- `GET /api/v1/backtest/result/{job_id}` - Get raw execution result

#### Formatted Results
- `GET /api/v1/backtest/{job_id}/result` - Get formatted backtest result with metrics
- `GET /api/v1/backtest/{job_id}/chart/equity` - Get equity curve chart data
- `GET /api/v1/backtest/{job_id}/chart/drawdown` - Get drawdown chart data
- `GET /api/v1/backtest/{job_id}/chart/monthly-returns` - Get monthly returns heatmap

#### Configuration
- `GET /api/v1/backtest/config/llm-providers` - List available LLM providers
- `GET /api/v1/backtest/config/data-sources` - List available data sources

### Health Endpoints

- `GET /health` - Health check with configuration metadata
- `GET /` - Root endpoint with service information

## OpenAPI Documentation

### Schema Generation

OpenAPI 3.1.0 schema is automatically generated from:
- Pydantic request/response models
- FastAPI route decorators
- Docstrings and metadata

### Accessing Documentation

When `DEBUG=true` in settings:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- OpenAPI JSON: `http://localhost:8000/openapi.json`

### Example OpenAPI Schema

```json
{
  "openapi": "3.1.0",
  "info": {
    "title": "Natural Language Backtesting Service",
    "version": "0.1.0",
    "description": "AI-powered natural language backtesting service..."
  },
  "paths": {
    "/api/v1/backtest/generate": {
      "post": {
        "summary": "Generate Backtest Code",
        "tags": ["Backtest"],
        "requestBody": {
          "content": {
            "application/json": {
              "schema": {"$ref": "#/components/schemas/BacktestRequest"}
            }
          }
        },
        "responses": {
          "200": {
            "content": {
              "application/json": {
                "schema": {"$ref": "#/components/schemas/GenerateBacktestResponse"}
              }
            }
          }
        }
      }
    }
  }
}
```

## CORS Configuration

CORS is configured in `app/main.py`:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.debug else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

- **Debug mode**: Allow all origins (for development)
- **Production**: Specify allowed origins in settings

## Testing

### Test Structure

```
tests/
├── api/
│   └── v1/
│       ├── test_backtest_config.py      # Configuration endpoints
│       ├── test_backtest_execute.py     # Execution endpoints
│       ├── test_backtest_generate.py    # Generation endpoint
│       ├── test_backtest_results.py     # Result endpoints
│       └── test_backtest_e2e.py         # End-to-end integration
```

### End-to-End Test Coverage

The E2E tests (`test_backtest_e2e.py`) cover:

1. **Complete Workflows**
   - Async: Generate → Execute → Poll → Get Result
   - Sync: Generate → Execute (wait for completion)

2. **OpenAPI Schema Validation**
   - Schema generation
   - All endpoints documented
   - Request/response models
   - HTTP methods and tags

3. **Health & Configuration**
   - Health check endpoint
   - Root endpoint
   - LLM providers listing
   - Data sources listing

4. **Error Handling**
   - 404 for non-existent endpoints
   - 405 for wrong HTTP methods
   - 422 for validation errors

### Running Tests

```bash
# Run all API tests
conda run -n py3.13 pytest tests/api/v1/ -v

# Run E2E tests only
conda run -n py3.13 pytest tests/api/v1/test_backtest_e2e.py -v

# Run with coverage
conda run -n py3.13 pytest tests/api/v1/ --cov=app/api --cov-report=html
```

### Integration Verification

Run the integration verification script:

```bash
conda run -n py3.13 python scripts/verify_integration.py
```

This verifies:
- All routes properly registered
- OpenAPI schema correctly generated
- All endpoints documented
- Dependency injection working

## Adding New Endpoints

### Step 1: Create Endpoint Module

Create a new endpoint file in `app/api/v1/endpoints/`:

```python
# app/api/v1/endpoints/new_feature.py
from fastapi import APIRouter, Depends

router = APIRouter(prefix="/new-feature", tags=["New Feature"])

@router.get("/")
async def get_new_feature():
    return {"message": "New feature"}
```

### Step 2: Register in V1 Router

Update `app/api/v1/__init__.py`:

```python
from app.api.v1.endpoints import backtest, new_feature

api_router = APIRouter()
api_router.include_router(backtest.router)
api_router.include_router(new_feature.router)  # Add new router
```

### Step 3: Add Tests

Create test file in `tests/api/v1/`:

```python
# tests/api/v1/test_new_feature.py
def test_new_feature_endpoint(client):
    response = client.get("/api/v1/new-feature/")
    assert response.status_code == 200
```

### Step 4: Update E2E Tests

Add endpoint to OpenAPI schema validation in `test_backtest_e2e.py`:

```python
expected_endpoints = [
    # ... existing endpoints ...
    "/api/v1/new-feature/",
]
```

## Best Practices

### Dependency Injection

1. **Use container pattern** - All shared resources through container
2. **Lazy initialization** - Initialize services on first access
3. **Proper cleanup** - Close resources in shutdown handler
4. **Type hints** - Use TYPE_CHECKING for circular imports

### Router Organization

1. **Prefix routes** - Use router-level prefixes
2. **Group by feature** - One endpoint module per feature area
3. **Consistent naming** - Follow REST conventions
4. **Tag appropriately** - Use tags for documentation grouping

### Documentation

1. **Comprehensive docstrings** - Document all endpoints
2. **Response examples** - Provide example responses
3. **Request validation** - Use Pydantic models
4. **Error responses** - Document all error codes

### Testing

1. **Test coverage** - Aim for >80% coverage
2. **Mock dependencies** - Use mocks for external services
3. **E2E tests** - Test complete workflows
4. **Schema validation** - Verify OpenAPI generation

## Troubleshooting

### Router Not Registering

Check that the router is imported and included in `app/api/v1/__init__.py`:

```python
from app.api.v1.endpoints import backtest

api_router.include_router(backtest.router)
```

### Dependency Injection Errors

Verify the container has the dependency getter function:

```python
# In app/core/container.py
def get_service_dep() -> "Service":
    return get_container().get_service()
```

### OpenAPI Schema Missing Endpoints

Ensure:
1. Router is registered in main app
2. Endpoint has proper decorators and response models
3. Pydantic models are properly defined

### Test Failures

Common issues:
1. **Mock not configured** - Add required mocks to fixtures
2. **Container not reset** - Clear container cache between tests
3. **Async/sync mismatch** - Use AsyncMock for async functions

## References

- FastAPI Documentation: https://fastapi.tiangolo.com
- Pydantic Documentation: https://pydantic-docs.helpmanual.io
- OpenAPI Specification: https://spec.openapis.org/oas/v3.1.0

## Version History

- **0.1.0** (2025-12-09): Initial API integration
  - Centralized v1 router
  - Complete dependency injection
  - End-to-end test coverage
  - OpenAPI documentation
