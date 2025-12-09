# Task ID: 2

**Title:** 백테스트 도메인 모델 및 요청 밸리데이션 정의

**Status:** done

**Dependencies:** 1 ✓

**Priority:** medium

**Description:** 입력 파라미터/응답 구조를 Pydantic 모델로 정의해 자연어 전략 파라미터를 일관되게 검증합니다.

**Details:**

Implementation:
- Create app/models/backtest.py defining BacktestParams (strategy_text, start/end date, initial_capital, contribution cadence/amount, optional fees/slippage/dividend flags, benchmark tickers list, chosen LLM provider/model) following PRD section 3.1.
- Include enums for ContributionFrequency (MONTHLY/QUARTERLY/SEMIA NNUAL/ANNUAL) and ProviderType (openrouter/anthropic/openai).
- Model BacktestRequest with fields strategy:str, params:BacktestParams.
- Define GeneratedCode + ModelInfo schemas.

**Test Strategy:**

- pytest: instantiate BacktestParams with invalid ranges to assert ValidationError.
- Snapshot test verifying dict() output matches expected JSON contract used later by FastAPI.
- Use hypothesis-dateutil for property tests around date ordering.

## Subtasks

### 2.1. Define Enums and Constants

**Status:** completed  
**Dependencies:** None  

Create enums for ProviderType, ContributionFrequency, etc.

**Details:**

Define Enum classes in app/models/enums.py or similar.

### 2.2. Create BacktestParams Model

**Status:** completed  
**Dependencies:** 2.1  

Implement Pydantic model for backtest configuration parameters.

**Details:**

Define BacktestParams with fields for capital, dates, fees, etc. Add validators for date ranges and positive numbers.

### 2.3. Create Request/Response Models

**Status:** completed  
**Dependencies:** 2.2  

Implement BacktestRequest and result models.

**Details:**

Define request schema wrapping strategy text and params. Define result schema for code, charts, and metrics.

### 2.4. Define GeneratedCode Model

**Status:** completed  
**Dependencies:** None  

Create model for LLM generated code and metadata.

**Details:**

Define schema for source code, summary, and parsed dependencies/tickers.

### 2.5. Unit Tests for Models

**Status:** completed  
**Dependencies:** 2.2, 2.3  

Write validation tests for the Pydantic models.

**Details:**

Create tests/models/test_backtest.py. Verify validation logic catches invalid inputs.
