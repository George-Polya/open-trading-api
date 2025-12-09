# Task ID: 11

**Title:** Frontend Web Application Implementation (Python Dash)

**Status:** done

**Dependencies:** 10 ✓

**Priority:** medium

**Description:** Develop the Python Dash-based user interface for strategy input, backtest configuration, generated code inspection, and interactive performance visualization dashboards, enabling a single-stack solution.

**Details:**

Implementation steps:
1. **Setup**: Initialize Dash application structure in `app/dashboard/` and configure `dash-bootstrap-components` for UI styling.
2. **Layout & Components**:
   - Implement `StrategyInputCard` with a textarea for natural language strategy input.
   - Build `BacktestConfigCard` mirroring `BacktestParams` from `app/models/backtest.py` (dates, capital, benchmarks, etc.).
   - Create `CodeViewerCard` to display and inspect generated code.
   - Develop `ResultsDashboard` as the container for charts and metrics.
3. **Callbacks & Logic**:
   - Implement Dash callbacks for form validation and API interaction.
   - Connect to `POST /api/v1/backtest/generate` and `execute` endpoints.
   - Implement result polling mechanisms to handle asynchronous backtest execution.
4. **Visualization (Plotly)**:
   - `EquityChart`: Line chart with Log/Linear scale toggle.
   - `DrawdownChart`: Area chart displaying drawdown over time.
   - `AssetAllocationChart`: Stacked area chart for portfolio composition.
   - `MonthlyReturnsHeatmap`: Grid visualization of monthly returns.
5. **Metrics**:
   - Implement `MetricCard` components to display CAGR, MDD, Sharpe, Sortino, and Calmar ratios.
6. **Integration**:
   - Mount the Dash app onto the main FastAPI instance using `WSGIMiddleware` or configure it for standalone execution modes.

**Test Strategy:**

1. **Unit Testing**: Use `pytest` to test callback logic and state transformations independently of the browser.
2. **Integration Testing**: Use `dash.testing` (Selenium-based) to verify the complete user flow (Input -> Generate -> Execute -> Visualize).
3. **API Mocking**: Mock API responses for `/generate` and `/execute` endpoints to test UI behavior in isolation from the backend/LLM services.

## Subtasks

### 11.1. Dash App Initialization and FastAPI Mounting

**Status:** done  
**Dependencies:** None  

Initialize the Dash application instance with Bootstrap support and mount it onto the main FastAPI application using WSGIMiddleware.

**Details:**

Create `app/dashboard/app.py` to initialize `dash.Dash` with `external_stylesheets=[dbc.themes.BOOTSTRAP]`. Configure the server object. In `app/main.py`, import the Dash app and mount it (e.g., `app.mount('/dashboard', WSGIMiddleware(dash_app.server))`). Ensure static asset configuration is compatible with the mounting path.

### 11.2. Input and Configuration Layout Components

**Status:** done  
**Dependencies:** 11.1  

Implement UI components for strategy input and backtest configuration mirroring the Pydantic models.

**Details:**

Create `app/dashboard/components/inputs.py`. Implement `StrategyInputCard` (Textarea). Implement `BacktestConfigCard` using `dbc.Card`, `dbc.Input`, and `dcc.DatePickerRange`. Fields must match `BacktestParams` from `app/models/backtest.py` (start_date, end_date, initial_capital, benchmark_tickers). Use `id`s accessible by callbacks.

### 11.3. Callbacks for Generation and Execution Logic

**Status:** done  
**Dependencies:** 11.2  

Develop Dash callbacks to handle form submission, API interaction, and state management for the backtest process.

**Details:**

Create `app/dashboard/callbacks.py`. Implement callbacks to: 1. Validate inputs. 2. Call `POST /api/v1/backtest/generate` (using `requests` or internal service). 3. Update `CodeViewerCard` (create component in `components/code_view.py`) with generated code. 4. Call `POST .../execute`. 5. Implement polling via `dcc.Interval` to check for results.

### 11.4. Performance Visualization Charts (Plotly)

**Status:** done  
**Dependencies:** 11.3  

Implement specific Plotly charting functions for equity curves, drawdowns, and asset allocation.

**Details:**

Create `app/dashboard/components/charts.py`. Implement: `create_equity_chart(df)` (Line chart with linear/log toggle), `create_drawdown_chart(df)` (Area chart, red fill), `create_asset_allocation_chart(df)` (Stacked area), and `create_monthly_heatmap(df)`. These functions should accept pandas DataFrames and return `plotly.graph_objects.Figure`.

### 11.5. Results Dashboard Assembly and Metrics

**Status:** done  
**Dependencies:** 11.4  

Assemble the final results view with metric cards and integrate all visualization components into the main layout.

**Details:**

Create `app/dashboard/components/metrics.py` for `MetricCard` (CAGR, MDD, Sharpe). Update `app/dashboard/layout.py` to arrange `StrategyInputCard`, `BacktestConfigCard`, `CodeViewerCard`, and the Results section (Charts + Metrics) using `dbc.Container`, `dbc.Row`, and `dbc.Col`. Wire up the results callbacks to populate these containers upon successful backtest.
