# Task ID: 1

**Title:** FastAPI 애플리케이션 골격과 설정 로더 구축

**Status:** done

**Dependencies:** None

**Priority:** medium

**Description:** 새 백엔드 서비스를 위해 FastAPI 기반 앱 구조와 설정 로딩/DI 컨테이너를 마련합니다.

**Details:**

Implementation:
- Create app/core/config.py that loads config.yaml via pydantic BaseSettings, supports llm/data/execution sections described in PRD.
- Add app/main.py initializing FastAPI, wiring lifespan for httpx AsyncClient closing, and exposing /health for readiness.
- Introduce dependency container (e.g., app/core/container.py) using lru_cache to instantiate settings and later providers.
Pseudo:
```
settings = Settings()
app = FastAPI()
@app.on_event("startup")
async def init_container()...
```

**Test Strategy:**

- Write pytest for /health endpoint using httpx AsyncClient to ensure 200 response.
- Add unit test validating Settings loads config mock (use tmp_path + monkeypatch for env overrides).
- Execute mypy/ruff if configured to verify dependency structure.

## Subtasks

### 1.1. Initialize Project Structure

**Status:** completed  
**Dependencies:** None  

Set up the basic directory structure (app/core, app/api, app/models, tests).

**Details:**

Create the root folders and __init__.py files. Initialize git repository.

### 1.2. Implement Configuration Loading

**Status:** completed  
**Dependencies:** 1.1  

Create app/core/config.py using Pydantic BaseSettings.

**Details:**

Define Settings class mapping to config.yaml and environment variables. Include sections for LLM, Data, and Execution settings.

### 1.3. Create FastAPI Entry Point

**Status:** completed  
**Dependencies:** 1.2  

Create app/main.py with FastAPI app initialization.

**Details:**

Instantiate FastAPI. Add health check route. Configure CORS if necessary.

### 1.4. Implement Dependency Container

**Status:** completed  
**Dependencies:** 1.2  

Setup DI container pattern for Settings and Service injection.

**Details:**

Create app/core/container.py. Use lru_cache for singleton settings. Prepare structure for provider injection.

### 1.5. Setup Logging and Error Handling

**Status:** completed  
**Dependencies:** 1.3  

Configure logging format and basic exception handlers.

**Details:**

Configure structlog or standard logging. Add global exception handler middleware.
