# Quick Start: Backtest Results API

## Getting Started in 5 Minutes

### 1. Submit a Backtest

```bash
curl -X POST "http://localhost:8000/api/v1/backtest/execute" \
  -H "Content-Type: application/json" \
  -d '{
    "code": "print({\"equity_series\": [{\"date\": \"2023-01-01\", \"value\": 100000}], \"trades\": []})",
    "async_mode": true
  }'
```

Response:
```json
{
  "job_id": "backtest-abc123def456",
  "status": "pending",
  "message": "Backtest submitted successfully..."
}
```

### 2. Check Status

```bash
curl "http://localhost:8000/api/v1/backtest/status/backtest-abc123def456"
```

Response:
```json
{
  "job_id": "backtest-abc123def456",
  "status": "completed"
}
```

### 3. Get Formatted Results

```bash
curl "http://localhost:8000/api/v1/backtest/backtest-abc123def456/result"
```

Response includes:
- Performance metrics (CAGR, Sharpe, MDD, etc.)
- Equity curve with log scale
- Drawdown series
- Monthly returns heatmap
- Trade list
- Execution logs

### 4. Get Specific Charts

**Equity Curve:**
```bash
curl "http://localhost:8000/api/v1/backtest/backtest-abc123def456/chart/equity?log_scale=true"
```

**Drawdown:**
```bash
curl "http://localhost:8000/api/v1/backtest/backtest-abc123def456/chart/drawdown"
```

**Monthly Returns:**
```bash
curl "http://localhost:8000/api/v1/backtest/backtest-abc123def456/chart/monthly-returns"
```

---

## Python Client

```python
import httpx
import asyncio

async def get_backtest_results(job_id: str):
    async with httpx.AsyncClient() as client:
        # Get comprehensive results
        response = await client.get(
            f"http://localhost:8000/api/v1/backtest/{job_id}/result"
        )
        data = response.json()

        # Print key metrics
        metrics = data['metrics']
        print(f"CAGR: {metrics['cagr']:.2f}%")
        print(f"Sharpe: {metrics['sharpe_ratio']:.2f}")
        print(f"Max DD: {metrics['max_drawdown']:.2f}%")
        print(f"Win Rate: {metrics['win_rate']:.2f}%")

        return data

# Run it
asyncio.run(get_backtest_results("backtest-abc123def456"))
```

---

## JavaScript/Frontend

```javascript
// Fetch results
async function fetchBacktestResults(jobId) {
  const response = await fetch(`/api/v1/backtest/${jobId}/result`);
  const data = await response.json();

  // Display metrics
  document.getElementById('cagr').textContent =
    `${data.metrics.cagr.toFixed(2)}%`;
  document.getElementById('sharpe').textContent =
    data.metrics.sharpe_ratio.toFixed(2);

  return data;
}

// Fetch equity chart
async function fetchEquityChart(jobId) {
  const response = await fetch(
    `/api/v1/backtest/${jobId}/chart/equity?log_scale=true`
  );
  const data = await response.json();

  // Plot with Chart.js/Plotly
  const dates = data.strategy.map(p => p.date);
  const values = data.strategy.map(p => p.value);

  // ... render chart
}

// Fetch monthly heatmap
async function fetchMonthlyHeatmap(jobId) {
  const response = await fetch(
    `/api/v1/backtest/${jobId}/chart/monthly-returns`
  );
  const data = await response.json();

  // Render heatmap with Plotly
  Plotly.newPlot('heatmap', [{
    z: data.returns,
    x: data.months,
    y: data.years,
    type: 'heatmap',
    colorscale: 'RdYlGn'
  }]);
}
```

---

## Response Schemas

### Metrics Object

```typescript
interface PerformanceMetrics {
  total_return: number;      // %
  cagr: number;              // %
  max_drawdown: number;      // %
  sharpe_ratio: number;
  sortino_ratio: number;
  calmar_ratio: number;
  volatility: number;        // %
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate: number;          // %
}
```

### Equity Curve

```typescript
interface EquityCurveData {
  strategy: Array<{date: string, value: number}>;
  benchmark?: Array<{date: string, value: number}>;
  log_scale: boolean;
}
```

### Drawdown

```typescript
interface DrawdownData {
  data: Array<{
    date: string;
    value: number;  // Negative percentage
  }>;
}
```

### Monthly Returns

```typescript
interface MonthlyReturnsData {
  years: number[];
  months: string[];  // Always 12 months
  returns: Array<Array<number | null>>;  // years × months
}
```

---

## Error Handling

```python
try:
    response = await client.get(f"/api/v1/backtest/{job_id}/result")
    response.raise_for_status()
    data = response.json()

except httpx.HTTPStatusError as e:
    if e.response.status_code == 404:
        print("Job not found")
    elif e.response.status_code == 409:
        print("Job not completed yet")
    elif e.response.status_code == 500:
        print("Error formatting results")
        print(e.response.json()["detail"])
```

---

## Complete Workflow

```python
import httpx
import asyncio
import time

async def complete_workflow():
    async with httpx.AsyncClient(timeout=30.0) as client:
        # 1. Submit backtest
        submit_response = await client.post(
            "http://localhost:8000/api/v1/backtest/execute",
            json={"code": "...", "async_mode": True}
        )
        job_id = submit_response.json()["job_id"]
        print(f"Submitted: {job_id}")

        # 2. Poll for completion
        while True:
            status_response = await client.get(
                f"http://localhost:8000/api/v1/backtest/status/{job_id}"
            )
            status = status_response.json()["status"]

            if status == "completed":
                break
            elif status in ["failed", "timeout", "cancelled"]:
                print(f"Job ended with status: {status}")
                return

            await asyncio.sleep(2)

        # 3. Get results
        results_response = await client.get(
            f"http://localhost:8000/api/v1/backtest/{job_id}/result"
        )
        results = results_response.json()

        # 4. Get charts
        equity_response = await client.get(
            f"http://localhost:8000/api/v1/backtest/{job_id}/chart/equity"
        )
        equity = equity_response.json()

        drawdown_response = await client.get(
            f"http://localhost:8000/api/v1/backtest/{job_id}/chart/drawdown"
        )
        drawdown = drawdown_response.json()

        monthly_response = await client.get(
            f"http://localhost:8000/api/v1/backtest/{job_id}/chart/monthly-returns"
        )
        monthly = monthly_response.json()

        # Display summary
        print(f"\nResults for {job_id}:")
        print(f"  CAGR: {results['metrics']['cagr']:.2f}%")
        print(f"  Sharpe: {results['metrics']['sharpe_ratio']:.2f}")
        print(f"  Max DD: {results['metrics']['max_drawdown']:.2f}%")
        print(f"  Trades: {results['metrics']['total_trades']}")
        print(f"  Win Rate: {results['metrics']['win_rate']:.2f}%")

asyncio.run(complete_workflow())
```

---

## Testing

Run the test suite:
```bash
pytest tests/api/v1/test_backtest_results.py -v
```

---

## Documentation

Full documentation: [BACKTEST_RESULTS_API.md](docs/BACKTEST_RESULTS_API.md)

Example script: [examples_backtest_results_api.py](examples_backtest_results_api.py)

---

## Common Issues

### Job Not Found (404)
- Check job_id is correct
- Job may have been cleaned up (expired)

### Job Not Completed (409)
- Job is still running - wait and retry
- Check status endpoint first

### Missing Equity Data (500)
- Backtest code must output `equity_series`
- Check data format matches expected schema

### Log Scale Issues
- Use `log_scale=false` for linear scale
- Log scale better shows percentage changes

---

## Tips

1. **Use log scale** for equity curves (better visualization)
2. **Poll status** before fetching results
3. **Cache results** for completed jobs
4. **Handle 409** by retrying after delay
5. **Check benchmark** availability before requesting

---

## Support

For issues or questions:
- Check [BACKTEST_RESULTS_API.md](docs/BACKTEST_RESULTS_API.md)
- Review [examples_backtest_results_api.py](examples_backtest_results_api.py)
- Run tests: `pytest tests/api/v1/test_backtest_results.py -v`
