# Backtest Results API Documentation

## Overview

The Backtest Results API provides endpoints for retrieving comprehensive backtest execution results, including performance metrics, equity curves, drawdown analysis, and monthly returns heatmaps.

## New Endpoints (Subtask 10.4)

### 1. GET /backtest/{job_id}/result

Retrieve comprehensive formatted backtest results with all metrics and chart data.

**Response**: `BacktestResultResponse`
- `job_id`: Job identifier
- `status`: Job status (must be "completed")
- `metrics`: Performance metrics object
  - `total_return`: Total return percentage
  - `cagr`: Compound Annual Growth Rate
  - `max_drawdown`: Maximum drawdown percentage
  - `sharpe_ratio`: Risk-adjusted return
  - `sortino_ratio`: Downside risk-adjusted return
  - `calmar_ratio`: CAGR / Max Drawdown
  - `volatility`: Annualized volatility
  - `total_trades`: Number of trades
  - `winning_trades`: Number of profitable trades
  - `losing_trades`: Number of losing trades
  - `win_rate`: Percentage of winning trades
- `equity_curve`: Equity curve data with log scale
- `drawdown`: Drawdown series data
- `monthly_heatmap`: Monthly returns heatmap
- `trades`: List of executed trades
- `logs`: Execution logs

**Status Codes**:
- `200 OK`: Results retrieved successfully
- `404 Not Found`: Job not found
- `409 Conflict`: Job not completed yet
- `500 Internal Server Error`: Result formatting failed

**Example Request**:
```bash
curl -X GET "http://localhost:8000/api/v1/backtest/backtest-abc123/result"
```

**Example Response**:
```json
{
  "job_id": "backtest-abc123",
  "status": "completed",
  "metrics": {
    "total_return": 25.5,
    "cagr": 23.2,
    "max_drawdown": 12.3,
    "sharpe_ratio": 1.85,
    "sortino_ratio": 2.15,
    "calmar_ratio": 1.89,
    "volatility": 15.2,
    "total_trades": 10,
    "winning_trades": 7,
    "losing_trades": 3,
    "win_rate": 70.0
  },
  "equity_curve": {
    "strategy": [
      {"date": "2023-01-01", "value": 5.0},
      {"date": "2023-12-31", "value": 5.1}
    ],
    "benchmark": [
      {"date": "2023-01-01", "value": 5.0},
      {"date": "2023-12-31", "value": 5.04}
    ],
    "log_scale": true
  },
  "drawdown": {
    "data": [
      {"date": "2023-01-01", "value": 0.0},
      {"date": "2023-06-15", "value": -12.3},
      {"date": "2023-12-31", "value": -2.1}
    ]
  },
  "monthly_heatmap": {
    "years": [2023],
    "months": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
    "returns": [[2.5, 1.2, -0.5, 3.1, 2.0, 1.8, 0.9, -1.2, 2.3, 1.5, 0.8, 1.9]]
  },
  "trades": [
    {
      "ticker": "AAPL",
      "action": "BUY",
      "quantity": 100,
      "price": 150.0,
      "date": "2023-06-01",
      "profit": 0
    }
  ],
  "logs": "Backtest completed successfully"
}
```

---

### 2. GET /backtest/{job_id}/chart/equity

Retrieve equity curve data for charting with optional log scale and benchmark.

**Query Parameters**:
- `log_scale` (bool, default: `true`): Apply log10 transformation
- `include_benchmark` (bool, default: `true`): Include benchmark data

**Response**: `EquityChartResponse`
- `job_id`: Job identifier
- `strategy`: List of equity data points for strategy
- `benchmark`: List of equity data points for benchmark (if available)
- `log_scale`: Whether log scale was applied

**Status Codes**:
- `200 OK`: Chart data retrieved successfully
- `404 Not Found`: Job not found
- `409 Conflict`: Job not completed yet

**Example Request**:
```bash
curl -X GET "http://localhost:8000/api/v1/backtest/backtest-abc123/chart/equity?log_scale=true&include_benchmark=true"
```

**Example Response**:
```json
{
  "job_id": "backtest-abc123",
  "strategy": [
    {"date": "2023-01-01", "value": 5.0},
    {"date": "2023-01-02", "value": 5.001},
    {"date": "2023-12-31", "value": 5.1}
  ],
  "benchmark": [
    {"date": "2023-01-01", "value": 5.0},
    {"date": "2023-12-31", "value": 5.04}
  ],
  "log_scale": true
}
```

---

### 3. GET /backtest/{job_id}/chart/drawdown

Retrieve drawdown series data for charting.

**Response**: `DrawdownChartResponse`
- `job_id`: Job identifier
- `data`: List of drawdown data points (negative percentages)

**Status Codes**:
- `200 OK`: Drawdown data retrieved successfully
- `404 Not Found`: Job not found
- `409 Conflict`: Job not completed yet

**Example Request**:
```bash
curl -X GET "http://localhost:8000/api/v1/backtest/backtest-abc123/chart/drawdown"
```

**Example Response**:
```json
{
  "job_id": "backtest-abc123",
  "data": [
    {"date": "2023-01-01", "value": 0.0},
    {"date": "2023-03-15", "value": -5.2},
    {"date": "2023-06-15", "value": -12.3},
    {"date": "2023-09-01", "value": -8.1},
    {"date": "2023-12-31", "value": -2.1}
  ]
}
```

---

### 4. GET /backtest/{job_id}/chart/monthly-returns

Retrieve monthly returns heatmap data for visualization.

**Response**: `MonthlyReturnsResponse`
- `job_id`: Job identifier
- `years`: List of years
- `months`: List of month names (always 12 months)
- `returns`: 2D array of monthly returns (years x months)

**Status Codes**:
- `200 OK`: Monthly returns data retrieved successfully
- `404 Not Found`: Job not found
- `409 Conflict`: Job not completed yet

**Example Request**:
```bash
curl -X GET "http://localhost:8000/api/v1/backtest/backtest-abc123/chart/monthly-returns"
```

**Example Response**:
```json
{
  "job_id": "backtest-abc123",
  "years": [2023, 2024],
  "months": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
  "returns": [
    [2.5, 1.2, -0.5, 3.1, 2.0, 1.8, 0.9, -1.2, 2.3, 1.5, 0.8, 1.9],
    [1.8, 2.1, 1.5, null, null, null, null, null, null, null, null, null]
  ]
}
```

Note: `null` values indicate months with no data.

---

## Implementation Details

### Architecture

The result retrieval system follows SOLID principles with clear separation of concerns:

1. **Container**: Manages dependency injection for `ResultFormatter`
2. **ResultFormatter**: Service for formatting raw backtest data
3. **Endpoints**: FastAPI endpoints for serving formatted data
4. **Models**: Pydantic models for request/response validation

### Result Formatter Service

Located at `/mnt/c/Users/wlska/Documents/gitlab/open-trading-api/app/services/result_formatter.py`

Key features:
- Financial metrics calculation (CAGR, Sharpe, Sortino, Calmar)
- Log-scale equity curve transformation
- Drawdown series generation
- Monthly returns heatmap creation
- Follows Protocol pattern for extensibility

### Dependency Injection

The `ResultFormatter` is registered in the container (`app/core/container.py`):

```python
def get_result_formatter_dep() -> "ResultFormatter":
    """FastAPI dependency for getting the result formatter."""
    return get_container().get_result_formatter()
```

### Error Handling

All endpoints implement comprehensive error handling:
- `404`: Job not found
- `409`: Job not completed (still running, failed, timeout, etc.)
- `500`: Data formatting errors or missing required data

### Data Format Requirements

The backtest execution result must contain:
- `equity_series`: List of `{"date": str, "value": float}` dictionaries
- `trades`: List of trade dictionaries with profit information
- `start_date`: ISO format date string
- `end_date`: ISO format date string
- `benchmark_series` (optional): Same format as equity_series

---

## Usage Examples

### Python Client Example

See `/mnt/c/Users/wlska/Documents/gitlab/open-trading-api/examples_backtest_results_api.py` for complete examples.

Basic workflow:
```python
import httpx

async def get_backtest_results(job_id: str):
    async with httpx.AsyncClient() as client:
        # Get comprehensive results
        response = await client.get(
            f"http://localhost:8000/api/v1/backtest/{job_id}/result"
        )
        results = response.json()

        print(f"CAGR: {results['metrics']['cagr']:.2f}%")
        print(f"Sharpe Ratio: {results['metrics']['sharpe_ratio']:.2f}")

        # Get specific chart data
        equity_response = await client.get(
            f"http://localhost:8000/api/v1/backtest/{job_id}/chart/equity",
            params={"log_scale": True}
        )
        equity_data = equity_response.json()
```

### Chart Integration

The chart endpoints provide data ready for frontend visualization libraries:

**Equity Curve (Plotly/Chart.js)**:
```javascript
fetch(`/api/v1/backtest/${jobId}/chart/equity?log_scale=true`)
  .then(res => res.json())
  .then(data => {
    const trace = {
      x: data.strategy.map(p => p.date),
      y: data.strategy.map(p => p.value),
      type: 'scatter',
      name: 'Strategy'
    };
    Plotly.newPlot('equity-chart', [trace]);
  });
```

**Monthly Heatmap (Plotly)**:
```javascript
fetch(`/api/v1/backtest/${jobId}/chart/monthly-returns`)
  .then(res => res.json())
  .then(data => {
    const heatmap = {
      z: data.returns,
      x: data.months,
      y: data.years,
      type: 'heatmap',
      colorscale: 'RdYlGn'
    };
    Plotly.newPlot('heatmap', [heatmap]);
  });
```

---

## Testing

Comprehensive tests are available at `/mnt/c/Users/wlska/Documents/gitlab/open-trading-api/tests/api/v1/test_backtest_results.py`

Run tests:
```bash
pytest tests/api/v1/test_backtest_results.py -v
```

Test coverage includes:
- Successful result retrieval
- Job not found scenarios
- Job not completed scenarios
- Missing data handling
- Log scale transformations
- Benchmark inclusion/exclusion
- Drawdown calculations
- Monthly returns heatmap generation

---

## Performance Considerations

1. **Caching**: Consider implementing result caching for completed jobs
2. **Pagination**: For large trade lists, consider adding pagination
3. **Streaming**: For very large datasets, consider streaming responses
4. **Async Processing**: All endpoints use async/await for efficient I/O

---

## Future Enhancements

Potential improvements for future versions:
1. Real-time result streaming during execution
2. Comparison of multiple backtest results
3. Custom metrics calculation
4. Export to CSV/Excel formats
5. Advanced filtering and aggregation
6. Shareable result links with authentication
7. Result versioning and history

---

## Related Documentation

- [Result Formatter Service](/mnt/c/Users/wlska/Documents/gitlab/open-trading-api/app/services/result_formatter.py)
- [Execution Manager](/mnt/c/Users/wlska/Documents/gitlab/open-trading-api/app/services/execution/manager.py)
- [Backtest API Endpoints](/mnt/c/Users/wlska/Documents/gitlab/open-trading-api/app/api/v1/endpoints/backtest.py)
- [Example Usage Script](/mnt/c/Users/wlska/Documents/gitlab/open-trading-api/examples_backtest_results_api.py)
