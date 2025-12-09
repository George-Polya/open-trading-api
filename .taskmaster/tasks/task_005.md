# Task ID: 5

**Title:** DataProvider 인터페이스와 KISDataProvider 구현

**Status:** done

**Dependencies:** 1 ✓

**Priority:** medium

**Description:** KIS 샘플 코드를 활용해 데이터 제공자 추상화 및 기본 구현을 만듭니다.

**Details:**

Implementation:
- Define app/providers/data/base.py with PriceData dataclass + abstract methods get_daily_prices/get_current_price/get_ticker_info/get_available_date_range mirroring PRD 2.3.1.
- Implement app/providers/data/kis.py that reuses synchronous helpers from `examples_user/kis_auth.py:1` and category-specific functions such as `examples_user/overseas_stock/overseas_stock_functions.py:1` via composition rather than duplication.
- Wrap blocking KIS calls inside asyncio.to_thread for async compatibility and transform DataFrame columns to standardized schema (date/open/high/low/close/volume) using pandas 2.3 installed via pyproject.
- Provide exchange detection logic (symbol digits => KRX) and caching of auth tokens (call ka.auth once, reuse trenv) referencing existing pattern.
Pseudo Outline:
```
class KISDataProvider(DataProvider):
    async def get_daily_prices(...):
        df = await to_thread(inquire_daily_chartprice,...)
        return self._normalize(df)
```
- Register provider with DI container + settings (svr/prod vs vps) as per PRD 4.2.

**Test Strategy:**

- pytest-asyncio tests mocking inquire_daily_chartprice/inquire_daily_itemchartprice to assert normalization and exchange routing.
- Integration test hitting real functions guarded by VCR or skip if env missing (to respect API limits).
- Add caching test verifying repeated get_daily_prices avoids duplicate auth.

## Subtasks

### 5.1. Define DataProvider Interface and Data Models

**Status:** done  
**Dependencies:** None  

Create the abstract base class and data models for data providers in app/providers/data/base.py.

**Details:**

Define `PriceData` dataclass (date, open, high, low, close, volume) and abstract class `DataProvider` with async methods: `get_daily_prices`, `get_current_price`, `get_ticker_info`, `get_available_date_range`. Ensure types are consistent with PRD 2.3.1.

### 5.2. Implement KIS Authentication and Session Management

**Status:** done  
**Dependencies:** 5.1  

Port KIS authentication logic from examples to the provider structure, ensuring thread safety and token reuse.

**Details:**

In `app/providers/data/kis.py`, implement a helper class or method to handle auth using `examples_user/kis_auth.py`. Cache the authentication token (using `ka.auth`) to reuse across requests and prevent redundant API calls. Load credentials from `settings.data`.

### 5.3. Implement Async Wrappers for KIS API Calls

**Status:** done  
**Dependencies:** 5.2  

Wrap synchronous KIS API calls (KRX and Overseas) in asyncio.to_thread for non-blocking execution.

**Details:**

Integrate functions from `examples_user/overseas_stock/overseas_stock_functions.py` and equivalent domestic functions. Create internal methods in `KISDataProvider` that run these blocking calls via `asyncio.to_thread`. Implement exchange detection logic based on symbol format.

### 5.4. Implement Data Normalization and Public Methods

**Status:** done  
**Dependencies:** 5.3  

Implement the public API methods of KISDataProvider, normalizing KIS response DataFrames to the standard PriceData schema.

**Details:**

Implement `get_daily_prices` and others. Transform the KIS-specific DataFrame columns (which vary by domestic/overseas) into the standard `date, open, high, low, close, volume` format defined in `PriceData`. Handle timezone adjustments if necessary.

### 5.5. Register KISDataProvider with DI Container

**Status:** done  
**Dependencies:** 5.4  

Configure the application to use KISDataProvider based on settings and ensure it is injectable.

**Details:**

Update `app/core/container.py` (or where DI is handled) to instantiate `KISDataProvider` when configured. Pass necessary config (APP_KEY, APP_SECRET, MODE) from `settings`. Verify initialization handles both Real and VPS/Paper modes.
