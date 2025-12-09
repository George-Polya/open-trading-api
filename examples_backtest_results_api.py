"""
Example usage of Backtest Results and Chart API Endpoints.

This script demonstrates how to:
1. Submit a backtest for execution
2. Poll for job completion
3. Retrieve formatted results with metrics
4. Fetch specific chart data (equity, drawdown, monthly returns)

Prerequisites:
- FastAPI server running on localhost:8000
- Valid backtest code or generated code reference
"""

import asyncio
import httpx
import time
from typing import Any


API_BASE_URL = "http://localhost:8000/api/v1"


async def submit_backtest(code: str) -> str:
    """
    Submit a backtest for execution.

    Args:
        code: Python backtest code to execute

    Returns:
        Job ID for tracking
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{API_BASE_URL}/backtest/execute",
            json={
                "code": code,
                "params": {},
                "async_mode": True,
            },
        )
        response.raise_for_status()

        data = response.json()
        job_id = data["job_id"]
        print(f"✓ Backtest submitted: {job_id}")
        print(f"  Status: {data['status']}")
        print(f"  Message: {data['message']}")

        return job_id


async def poll_job_status(job_id: str, max_wait_seconds: int = 300) -> str:
    """
    Poll job status until completion or timeout.

    Args:
        job_id: The job identifier
        max_wait_seconds: Maximum time to wait

    Returns:
        Final job status
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        start_time = time.time()

        while time.time() - start_time < max_wait_seconds:
            response = await client.get(f"{API_BASE_URL}/backtest/status/{job_id}")
            response.raise_for_status()

            data = response.json()
            status = data["status"]

            print(f"  Status: {status}", end="\r")

            if status in ["completed", "failed", "timeout", "cancelled"]:
                print()  # New line after final status
                return status

            await asyncio.sleep(2)  # Poll every 2 seconds

        raise TimeoutError(f"Job did not complete within {max_wait_seconds} seconds")


async def get_formatted_results(job_id: str) -> dict[str, Any]:
    """
    Get comprehensive formatted backtest results.

    Returns results with:
    - Performance metrics (CAGR, Sharpe, MDD, etc.)
    - Equity curve data
    - Drawdown series
    - Monthly returns heatmap
    - Trade list
    - Execution logs

    Args:
        job_id: The job identifier

    Returns:
        Complete formatted results dictionary
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(f"{API_BASE_URL}/backtest/{job_id}/result")
        response.raise_for_status()

        data = response.json()

        print(f"\n✓ Formatted Results for {job_id}")
        print(f"  Status: {data['status']}")

        # Display metrics
        metrics = data["metrics"]
        print("\n  Performance Metrics:")
        print(f"    Total Return: {metrics['total_return']:.2f}%")
        print(f"    CAGR: {metrics['cagr']:.2f}%")
        print(f"    Max Drawdown: {metrics['max_drawdown']:.2f}%")
        print(f"    Sharpe Ratio: {metrics['sharpe_ratio']:.2f}")
        print(f"    Sortino Ratio: {metrics['sortino_ratio']:.2f}")
        print(f"    Calmar Ratio: {metrics['calmar_ratio']:.2f}")
        print(f"    Volatility: {metrics['volatility']:.2f}%")
        print(f"    Total Trades: {metrics['total_trades']}")
        print(f"    Win Rate: {metrics['win_rate']:.2f}%")

        # Display chart info
        equity_curve = data["equity_curve"]
        print(f"\n  Equity Curve:")
        print(f"    Data Points: {len(equity_curve['strategy'])}")
        print(f"    Log Scale: {equity_curve['log_scale']}")
        print(f"    Has Benchmark: {equity_curve['benchmark'] is not None}")

        print(f"\n  Drawdown Series:")
        print(f"    Data Points: {len(data['drawdown']['data'])}")

        print(f"\n  Monthly Heatmap:")
        heatmap = data["monthly_heatmap"]
        print(f"    Years: {heatmap['years']}")
        print(f"    Months: {len(heatmap['months'])}")

        print(f"\n  Trades: {len(data['trades'])} executed")

        return data


async def get_equity_chart(
    job_id: str,
    log_scale: bool = True,
    include_benchmark: bool = True,
) -> dict[str, Any]:
    """
    Get equity curve data for charting.

    Args:
        job_id: The job identifier
        log_scale: Apply log10 transformation
        include_benchmark: Include benchmark comparison

    Returns:
        Equity chart data dictionary
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        params = {
            "log_scale": log_scale,
            "include_benchmark": include_benchmark,
        }

        response = await client.get(
            f"{API_BASE_URL}/backtest/{job_id}/chart/equity",
            params=params,
        )
        response.raise_for_status()

        data = response.json()

        print(f"\n✓ Equity Chart Data for {job_id}")
        print(f"  Strategy Points: {len(data['strategy'])}")
        print(f"  Benchmark Points: {len(data['benchmark']) if data['benchmark'] else 0}")
        print(f"  Log Scale: {data['log_scale']}")

        # Sample first and last points
        if data["strategy"]:
            first = data["strategy"][0]
            last = data["strategy"][-1]
            print(f"  First Point: {first['date']} = {first['value']:.4f}")
            print(f"  Last Point: {last['date']} = {last['value']:.4f}")

        return data


async def get_drawdown_chart(job_id: str) -> dict[str, Any]:
    """
    Get drawdown series data for charting.

    Args:
        job_id: The job identifier

    Returns:
        Drawdown chart data dictionary
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{API_BASE_URL}/backtest/{job_id}/chart/drawdown"
        )
        response.raise_for_status()

        data = response.json()

        print(f"\n✓ Drawdown Chart Data for {job_id}")
        print(f"  Data Points: {len(data['data'])}")

        # Find maximum drawdown
        if data["data"]:
            max_dd = min(point["value"] for point in data["data"])
            print(f"  Maximum Drawdown: {max_dd:.2f}%")

            # Find when it occurred
            max_dd_point = next(p for p in data["data"] if p["value"] == max_dd)
            print(f"  Occurred On: {max_dd_point['date']}")

        return data


async def get_monthly_returns(job_id: str) -> dict[str, Any]:
    """
    Get monthly returns heatmap data.

    Args:
        job_id: The job identifier

    Returns:
        Monthly returns heatmap dictionary
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{API_BASE_URL}/backtest/{job_id}/chart/monthly-returns"
        )
        response.raise_for_status()

        data = response.json()

        print(f"\n✓ Monthly Returns Heatmap for {job_id}")
        print(f"  Years: {data['years']}")
        print(f"  Months: {len(data['months'])}")

        # Display as table
        print("\n  Monthly Returns Table:")
        print("  Year  ", " ".join(f"{month:>6}" for month in data["months"]))
        print("  " + "-" * 90)

        for year, returns in zip(data["years"], data["returns"]):
            returns_str = " ".join(
                f"{ret:>6.2f}" if ret is not None else "  N/A " for ret in returns
            )
            print(f"  {year}  {returns_str}")

        return data


async def main():
    """
    Main example workflow.
    """
    print("=" * 80)
    print("Backtest Results API Example")
    print("=" * 80)

    # Example backtest code (simple buy and hold)
    sample_code = """
import pandas as pd
import numpy as np

# Mock backtest execution
dates = pd.date_range('2023-01-01', '2023-12-31', freq='D')
equity = 100000 * (1 + np.cumsum(np.random.randn(len(dates)) * 0.01))

# Create result data
result = {
    'equity_series': [
        {'date': date.strftime('%Y-%m-%d'), 'value': float(value)}
        for date, value in zip(dates, equity)
    ],
    'trades': [
        {'ticker': 'AAPL', 'action': 'BUY', 'quantity': 100, 'price': 150.0,
         'date': '2023-06-01', 'profit': 0},
        {'ticker': 'AAPL', 'action': 'SELL', 'quantity': 100, 'price': 165.0,
         'date': '2023-09-01', 'profit': 1500.0},
    ],
    'start_date': '2023-01-01',
    'end_date': '2023-12-31',
}

print(result)
"""

    try:
        # Step 1: Submit backtest
        print("\n[1/6] Submitting backtest...")
        job_id = await submit_backtest(sample_code)

        # Step 2: Wait for completion
        print("\n[2/6] Waiting for completion...")
        status = await poll_job_status(job_id)

        if status != "completed":
            print(f"✗ Job ended with status: {status}")
            return

        print("✓ Job completed successfully")

        # Step 3: Get formatted results
        print("\n[3/6] Fetching formatted results...")
        results = await get_formatted_results(job_id)

        # Step 4: Get equity chart
        print("\n[4/6] Fetching equity chart data...")
        equity_data = await get_equity_chart(job_id, log_scale=True, include_benchmark=False)

        # Step 5: Get drawdown chart
        print("\n[5/6] Fetching drawdown chart data...")
        drawdown_data = await get_drawdown_chart(job_id)

        # Step 6: Get monthly returns
        print("\n[6/6] Fetching monthly returns...")
        monthly_data = await get_monthly_returns(job_id)

        print("\n" + "=" * 80)
        print("✓ All data retrieved successfully!")
        print("=" * 80)

        # Summary
        print("\nSummary:")
        print(f"  Job ID: {job_id}")
        print(f"  CAGR: {results['metrics']['cagr']:.2f}%")
        print(f"  Sharpe Ratio: {results['metrics']['sharpe_ratio']:.2f}")
        print(f"  Max Drawdown: {results['metrics']['max_drawdown']:.2f}%")
        print(f"  Win Rate: {results['metrics']['win_rate']:.2f}%")
        print(f"  Total Trades: {results['metrics']['total_trades']}")

    except httpx.HTTPError as e:
        print(f"\n✗ HTTP Error: {e}")
        if hasattr(e, "response") and e.response is not None:
            print(f"  Status Code: {e.response.status_code}")
            print(f"  Response: {e.response.text}")
    except Exception as e:
        print(f"\n✗ Error: {e}")


if __name__ == "__main__":
    asyncio.run(main())
