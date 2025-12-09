# Task ID: 9

**Title:** Docker 샌드박스 코드 실행기와 잡 매니저 구현

**Status:** done

**Dependencies:** 8 ✓

**Priority:** medium

**Description:** 생성된 코드를 안전하게 실행하고 비동기 잡 ID로 결과를 관리합니다.

**Details:**

Implementation:
- Create `app/services/execution/backend.py` defining abstract `ExecutionBackend` with methods `execute`, `get_status`, and `cleanup` to support future K8s expansion.
- Implement `DockerBackend` (Docker out of Docker) using `aiodocker` or `docker-py`. It should mount `/var/run/docker.sock` to spawn sibling containers for isolation.
- Implement `LocalBackend` as a fallback for development using `asyncio.subprocess`.
- Update `docker-compose.yml` to include the socket mount volume: `/var/run/docker.sock:/var/run/docker.sock`.
- Implement job storage (Redis or in-memory dict for MVP) mapping job_id→status/result in `app/services/execution/storage.py`.
- Enforce static module allowlist and mount data provider proxy.

Pseudo Outline:
```python
class ExecutionBackend(ABC):
    @abstractmethod
    async def execute(self, job_id: str, code: str, params: dict) -> ExecutionJob: ...

class DockerBackend(ExecutionBackend):
    # Uses Docker out of Docker (DooD) to run sibling containers
    async def execute(...): ...
```

**Test Strategy:**

- Use `pytest` with `unittest.mock` to mock `aiodocker` client interactions, ensuring correct container creation parameters (DooD config).
- Verify `LocalBackend` executes code safely in a subprocess with restricted environment.
- Integration test: Run a safe code snippet to confirm the entire pipeline (Job creation -> Backend execution -> Result storage).
- Verify security constraints (e.g., attempt to access host file system via invalid volume mounts).

## Subtasks

### 9.1. Define Execution Job Models and Storage Interface

**Status:** done  
**Dependencies:** None  

Create the data models for tracking job execution status and an abstract interface for job storage.

**Details:**

Create `app/models/execution.py` defining `ExecutionJob` (fields: job_id, status [PENDING, RUNNING, COMPLETED, FAILED], result, logs, timestamps). Create `app/services/execution/storage.py` with an abstract base class `JobStorage` and a simple `InMemoryJobStorage` implementation (dict-based) for MVP. This will allow async tracking of code execution tasks.

### 9.2. Define ExecutionBackend Interface and LocalBackend Implementation

**Status:** done  
**Dependencies:** 9.1  

Establish the abstract backend interface and a local subprocess-based implementation for development.

**Details:**

Create `app/services/execution/backend.py`. Define abstract `ExecutionBackend` with methods: `execute`, `get_status`, and `cleanup`. Implement `LocalBackend` that uses `asyncio.create_subprocess_exec` to run code locally. Ensure it captures stdout/stderr and handles timeouts. This serves as the dev/test fallback.

### 9.3. Implement DockerBackend with DooD Support

**Status:** done  
**Dependencies:** 9.2  

Build the Docker-based backend using Docker out of Docker (DooD) to run code in sibling containers.

**Details:**

Extend `ExecutionBackend` to create `DockerBackend` in `app/services/execution/docker_backend.py`. Use `aiodocker` or `docker-py` to interact with the mounted host socket (`/var/run/docker.sock`). Implement logic to spawn *sibling* containers (python:3.13-slim) with `network_mode='none'` (or restricted), memory limits, and timeouts. Ensure shared volumes are handled correctly (host paths must be used for DooD volume mounting).

### 9.4. Implement Workspace Preparation and Host Volume Management

**Status:** done  
**Dependencies:** 9.2, 9.3  

Develop logic to prepare temp workspaces and ensure they are accessible to sibling containers.

**Details:**

Add helper methods in `app/services/execution/manager.py` (or similar) to create a temporary directory for each job on the host (or a named volume). Serialize params and write code files. For DooD, ensure the path passed to `DockerBackend` is the *host* path, not the container path, or use a shared named volume strategy so the sibling container can access the injected code.
<info added on 2025-12-09T08:51:06.579Z>
Implemented Data Injection features to support offline analysis in the sandbox:
- Injected `DataProvider` into `JobManager` and updated `container.py` configuration.
- Added `_fetch_market_data()` to asynchronously fetch ticker data via KIS API and `_price_data_to_dataframe()` for conversion.
- Implemented `_save_data_to_workspace()` to persist data as CSV files within the workspace `data/` directory.
- Enhanced `wrapper.py` with `load_data()` to enable seamless CSV reading inside the isolated container.
- Updated `GeneratedCode` model with a `tickers` field and overhauled prompt templates to instruct the LLM on using `load_data`.
- Enforced security by maintaining `network:none` in Docker and handling all data fetching on the host side, ensuring no credentials are exposed to the sandbox.
</info added on 2025-12-09T08:51:06.579Z>

### 9.5. Integrate Backend Factory and Job Manager Service

**Status:** done  
**Dependencies:** 9.1, 9.2, 9.3  

Create a service to orchestrate job creation, execution, and backend selection.

**Details:**

Create `app/services/execution/manager.py`. Implement a factory to choose between `DockerBackend` and `LocalBackend` based on `app.core.config`. Update `docker-compose.yml` documentation/examples to include socket mounting. Implement `run_backtest(code, params)` to orchestrate the flow: Job Creation -> Backend Execution -> Result Update.
