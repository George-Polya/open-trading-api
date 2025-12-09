# Task ID: 6

**Title:** 보조 데이터 소스 어댑터 및 DataProviderFactory 구현

**Status:** done

**Dependencies:** 5 ✓

**Priority:** medium

**Description:** KIS 장애 대비 YFinance·Mock 제공자를 추가하고 팩토리로 선택 가능하게 합니다.

**Details:**

Implementation:
- Create app/providers/data/yfinance.py leveraging yfinance.AsyncAPI (or asyncio.to_thread with yfinance.download) for overseas fallback; convert timezone to UTC aware.
- Create app/providers/data/mock.py to synthesize deterministic PriceData for testing/backfills.
- Implement app/providers/data/factory.py reading settings.data.provider ("kis"|"yfinance"|"mock") to instantiate proper adapter, mirroring LLM factory pattern.
- Add caching decorator or TTL to reduce KIS rate limit per PRD risk table (data caching layer suggestion).
Pseudo:
```
class DataProviderFactory:
    if cfg.provider == "kis": return KISDataProvider(...)
    elif cfg.provider == "yfinance": return YFinanceProvider(...)
```
- Extend config schema to include fallback order, using list of providers for failover.

**Test Strategy:**

- Unit test verifying factory returns fallback provider when config toggled.
- Mock yfinance responses to ensure DataFrame columns normalized identical to KIS provider.
- Add test to ensure fallback order is respected when primary raises custom DataUnavailableError.

## Subtasks

### 6.1. Implement YFinanceDataProvider Adapter

**Status:** done  
**Dependencies:** None  

Create the YFinance data provider implementation ensuring UTC timezone conversion and proper async wrapping of the blocking yfinance library.

**Details:**

Create `app/providers/data/yfinance.py` implementing the `DataProvider` abstract base class (defined in Task 5). Use `yfinance` library (e.g., `yfinance.Ticker`, `download`). Since `yfinance` is synchronous, wrap calls (like `history`) using `asyncio.to_thread` to prevent blocking the event loop. Ensure all returned `PriceData` objects have UTC-aware datetimes. Map YFinance columns (Open, High, Low, Close, Volume) to the standard schema.

### 6.2. Implement MockDataProvider for Testing

**Status:** done  
**Dependencies:** None  

Develop a mock data provider that generates deterministic synthetic price data for testing and backfilling scenarios without external API calls.

**Details:**

Create `app/providers/data/mock.py` implementing the `DataProvider` interface. It should accept seed parameters or configuration to generate deterministic sine-wave or linear trend price data. Implement `get_daily_prices`, `get_current_price`, and `get_ticker_info` to return consistent dummy data. This is crucial for offline development and unit testing of strategies.

### 6.3. Enhance Config Schema for Data Providers

**Status:** done  
**Dependencies:** None  

Update the application configuration to support selecting data providers and defining a fallback order.

**Details:**

Modify `app/core/config.py` (and potentially `config.yaml` schema definition) to include a `data_providers` section. Add fields for `primary_provider` (enum: kis, yfinance, mock) and `fallback_providers` (list[str]). Ensure validation logic exists to check if the selected provider is configured (e.g., check for API keys if KIS is selected).

### 6.4. Implement DataProviderFactory with Caching

**Status:** done  
**Dependencies:** 6.1, 6.2, 6.3  

Create the factory class to instantiate the correct provider based on config and apply caching strategies to minimize API usage.

**Details:**

Create `app/providers/data/factory.py`. Implement `get_data_provider()` which reads `settings.data_provider` and instantiates `KISDataProvider` (from Task 5), `YFinanceDataProvider`, or `MockDataProvider`. Add a caching layer (e.g., `alru_cache` or a custom decorator around `get_daily_prices`) to reduce redundant calls, specifically for the KIS adapter to handle rate limits.

### 6.5. Implement Fallback Mechanism and Integration Tests

**Status:** done  
**Dependencies:** 6.4  

Implement logic to automatically switch to fallback providers if the primary provider fails, and verify the entire flow.

**Details:**

Implement a composite or proxy provider (or enhance the Factory/Service layer) that attempts to fetch data from the primary provider. If a specific exception (e.g., `DataUnavailableError`, `RateLimitError`) occurs, it should retry using the next provider in the `fallback_providers` list. Ensure the errors are logged correctly.
