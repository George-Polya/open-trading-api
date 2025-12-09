# Task ID: 10

**Title:** 백테스트 API 엔드포인트와 결과 집계/차트 데이터 생성

**Status:** done

**Dependencies:** 1 ✓, 2 ✓, 7 ✓, 8 ✓, 9 ✓

**Priority:** medium

**Description:** PRD 6.1의 REST 엔드포인트를 FastAPI로 구현하고 로그 스케일 차트/지표 계산을 제공합니다.

**Details:**

Implementation:
- Implement routers/backtest.py with endpoints:
  * POST /api/v1/backtest/generate → uses BacktestCodeGenerator (task7) to return code/summary/model_info.
  * POST /api/v1/backtest/execute → accepts code or reference, enqueues job via CodeExecutor (task9).
  * GET /api/v1/backtest/{job_id}/result → returns stored BacktestResult (code, metrics, trades).
  * GET /api/v1/backtest/{job_id}/chart/equity → returns log-scale equity + benchmark series; compute log scaling on backend using pandas Series.apply(np.log10).
  * GET /api/v1/config/llm-providers & /config/data-sources → read from factories to return provider metadata.
- Add result aggregator app/services/result_formatter.py to compute metrics (total_return, CAGR, MDD, Sharpe, Sortino, Calmar) and supporting datasets (drawdown series, allocation stack, monthly heatmap) referencing PRD 3.3.
- Provide ability to display generated code via API for transparency.
Pseudo Handler Example:
```
@router.post("/generate")
async def generate(req:BacktestRequest, generator:BacktestCodeGenerator=Depends(...)):
    code = await generator.generate(...)
    return code
```
- Ensure responses follow JSON schema described in PRD (daily_values, benchmark_values, trades, metrics, metadata about LLM/data sources).

**Test Strategy:**

- FastAPI TestClient tests covering success + validation errors for each route.
- Use freezer to simulate deterministic metrics; assert log-scale output equals numpy.log results.
- Contract tests verifying JSON schema using pydantic validate_call or jsonschema.

## Subtasks

### 10.1. Implement Result Calculation Service

**Status:** done  
**Dependencies:** 10.2  

Create a service to calculate financial metrics (CAGR, MDD, Sharpe, Sortino) and process chart data.

**Details:**

Implement `app/services/result_formatter.py`. This class should accept raw trade lists and daily equity series (pandas Series/DataFrame). It must calculate: Total Return, CAGR, MDD, Sharpe Ratio, Sortino Ratio, and Calmar Ratio. It should also provide a method to generate log-scale equity curves using `np.log10` and formatting datasets for frontend charting (e.g., drawdown series, monthly heatmap data).

### 10.2. Implement Configuration and Generation Endpoints

**Status:** done  
**Dependencies:** 10.1, 10.2, 10.3  

Create the Backtest router and implement endpoints for retrieving configuration and generating backtest code.

**Details:**

Create `app/api/v1/endpoints/backtest.py`. Implement `GET /config/llm-providers` and `GET /config/data-sources` to return available options from factories. Implement `POST /backtest/generate` which accepts `BacktestRequest`, injects `BacktestCodeGenerator` (interface), and returns the generated Python code and model info. Ensure proper Pydantic model response serialization.

### 10.3. Implement Execution Endpoint

**Status:** done  
**Dependencies:** 10.2  

Implement the endpoint to execute generated backtest strategies.

**Details:**

Add `POST /backtest/execute` to `app/api/v1/endpoints/backtest.py`. This endpoint should accept a payload containing the code to run (or a reference ID). It must integrate with the `CodeExecutor` service (from Task 9) to enqueue or run the job asynchronously. It should return a `job_id` for tracking.

### 10.4. Implement Result Retrieval and Chart Endpoints

**Status:** done  
**Dependencies:** 10.1, 10.3  

Implement endpoints to fetch backtest results and specific chart data.

**Details:**

Add `GET /backtest/{job_id}/result` to return the full `BacktestResult` object (metrics, trades, logs). Add `GET /backtest/{job_id}/chart/equity` to return the specific log-scaled equity curve and benchmark series prepared by `ResultFormatter`. Ensure `job_id` lookup integrates with the persistence layer or memory store defined in `CodeExecutor`.

### 10.5. Register Router and Integrate with Main App

**Status:** done  
**Dependencies:** 10.2, 10.3, 10.4  

Wire the new backtest router into the main FastAPI application and finalize API documentation details.

**Details:**

Update `app/main.py` (or `app/api/api.py`) to include the `backtest` router with the prefix `/api/v1`. Verify that all dependency injection (generators, executors, formatters) is correctly wired in `app/core/container.py` or via FastAPI `Depends`. Ensure OpenAPI schema (Swagger UI) correctly displays the new endpoints and models.
