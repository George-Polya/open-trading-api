"""
ResultFormatter Service - Usage Examples

This module demonstrates how to use the ResultFormatter service to process
backtest results and generate comprehensive financial metrics and chart data.
"""

import pandas as pd
import numpy as np
from datetime import date, timedelta
from app.services.result_formatter import (
    ResultFormatter,
    create_result_formatter,
    PerformanceMetrics,
    FormattedResults,
)


def example_basic_usage() -> None:
    """Basic usage example: Format simple backtest results."""
    print("=" * 80)
    print("Example 1: Basic Usage")
    print("=" * 80)

    # Create sample equity curve (1 year of daily data)
    dates = pd.date_range("2023-01-01", "2023-12-31", freq="D")
    np.random.seed(42)

    # Simulate equity growth with volatility
    returns = np.random.normal(0.0008, 0.015, len(dates))  # ~20% annual return, 23% volatility
    equity_values = [100000.0]
    for ret in returns[:-1]:
        equity_values.append(equity_values[-1] * (1 + ret))

    equity_series = pd.Series(equity_values, index=dates)

    # Sample trades
    trades = [
        {"profit": 1500, "entry": 100000, "exit": 101500},
        {"profit": -800, "entry": 101500, "exit": 100700},
        {"profit": 2200, "entry": 100700, "exit": 102900},
    ]

    # Create formatter and process results
    formatter = create_result_formatter(risk_free_rate=0.02)

    results = formatter.format_results(
        equity_series=equity_series,
        trades=trades,
        start_date=date(2023, 1, 1),
        end_date=date(2023, 12, 31),
        use_log_scale=True,
    )

    # Display metrics
    print("\nPerformance Metrics:")
    print(f"  Total Return: {results.metrics.total_return:.2f}%")
    print(f"  CAGR: {results.metrics.cagr:.2f}%")
    print(f"  Max Drawdown: {results.metrics.max_drawdown:.2f}%")
    print(f"  Sharpe Ratio: {results.metrics.sharpe_ratio:.2f}")
    print(f"  Sortino Ratio: {results.metrics.sortino_ratio:.2f}")
    print(f"  Calmar Ratio: {results.metrics.calmar_ratio:.2f}")
    print(f"  Volatility: {results.metrics.volatility:.2f}%")
    print(f"\nTrade Statistics:")
    print(f"  Total Trades: {results.metrics.total_trades}")
    print(f"  Win Rate: {results.metrics.win_rate:.2f}%")
    print(f"  Winning Trades: {results.metrics.winning_trades}")
    print(f"  Losing Trades: {results.metrics.losing_trades}")

    print(f"\nChart Data:")
    print(f"  Equity Curve Points: {len(results.equity_curve.strategy)}")
    print(f"  Drawdown Points: {len(results.drawdown.data)}")
    print(f"  Heatmap Years: {results.monthly_heatmap.years}")
    print(f"  Log Scale: {results.equity_curve.log_scale}")


def example_with_benchmark() -> None:
    """Example: Compare strategy with benchmark."""
    print("\n" + "=" * 80)
    print("Example 2: Strategy vs Benchmark Comparison")
    print("=" * 80)

    # Create sample data
    dates = pd.date_range("2023-01-01", "2023-12-31", freq="D")
    np.random.seed(42)

    # Strategy: Higher return, higher volatility
    strategy_returns = np.random.normal(0.001, 0.015, len(dates))
    strategy_values = [100000.0]
    for ret in strategy_returns[:-1]:
        strategy_values.append(strategy_values[-1] * (1 + ret))
    strategy_equity = pd.Series(strategy_values, index=dates)

    # Benchmark: Lower return, lower volatility (e.g., S&P 500)
    benchmark_returns = np.random.normal(0.0005, 0.01, len(dates))
    benchmark_values = [100000.0]
    for ret in benchmark_returns[:-1]:
        benchmark_values.append(benchmark_values[-1] * (1 + ret))
    benchmark_equity = pd.Series(benchmark_values, index=dates)

    # Format results with benchmark
    formatter = create_result_formatter(risk_free_rate=0.02)
    results = formatter.format_results(
        equity_series=strategy_equity,
        trades=[],
        start_date=date(2023, 1, 1),
        end_date=date(2023, 12, 31),
        benchmark_series=benchmark_equity,
        use_log_scale=False,
    )

    # Calculate benchmark metrics for comparison
    benchmark_metrics = formatter.calculate_metrics(
        benchmark_equity, [], date(2023, 1, 1), date(2023, 12, 31)
    )

    print("\nStrategy vs Benchmark:")
    print(f"  Strategy Return: {results.metrics.total_return:.2f}%")
    print(f"  Benchmark Return: {benchmark_metrics.total_return:.2f}%")
    print(f"  Alpha: {results.metrics.total_return - benchmark_metrics.total_return:.2f}%")

    print(f"\n  Strategy Sharpe: {results.metrics.sharpe_ratio:.2f}")
    print(f"  Benchmark Sharpe: {benchmark_metrics.sharpe_ratio:.2f}")

    print(f"\n  Strategy Max DD: {results.metrics.max_drawdown:.2f}%")
    print(f"  Benchmark Max DD: {benchmark_metrics.max_drawdown:.2f}%")

    print(f"\n  Benchmark Data Available: {results.equity_curve.benchmark is not None}")


def example_individual_metrics() -> None:
    """Example: Calculate individual metrics separately."""
    print("\n" + "=" * 80)
    print("Example 3: Individual Metric Calculations")
    print("=" * 80)

    # Create sample equity curve
    dates = pd.date_range("2023-01-01", "2023-12-31", freq="D")
    equity = pd.Series(np.linspace(100000, 120000, len(dates)), index=dates)

    formatter = create_result_formatter()

    # Calculate individual components
    log_equity = formatter.generate_log_scale_equity(equity)
    drawdown_series = formatter.generate_drawdown_series(equity)
    monthly_heatmap = formatter.generate_monthly_heatmap(equity)

    print("\nLog-Scale Equity:")
    print(f"  Original first value: {equity.iloc[0]:.2f}")
    print(f"  Log-scale first value: {log_equity.iloc[0]:.4f}")
    print(f"  Original last value: {equity.iloc[-1]:.2f}")
    print(f"  Log-scale last value: {log_equity.iloc[-1]:.4f}")

    print("\nDrawdown Series:")
    print(f"  Maximum drawdown: {abs(drawdown_series.min()):.2f}%")
    print(f"  Average drawdown: {abs(drawdown_series.mean()):.2f}%")

    print("\nMonthly Heatmap:")
    print(f"  Years covered: {monthly_heatmap.years}")
    print(f"  Months in year: {len(monthly_heatmap.months)}")
    print(f"  Sample monthly return (Jan): {monthly_heatmap.returns[0][0]:.2f}%")


def example_edge_cases() -> None:
    """Example: Handling edge cases."""
    print("\n" + "=" * 80)
    print("Example 4: Edge Case Handling")
    print("=" * 80)

    formatter = create_result_formatter()

    # Empty series
    empty_series = pd.Series([], dtype=float)
    empty_metrics = formatter.calculate_metrics(
        empty_series, [], date(2023, 1, 1), date(2023, 12, 31)
    )
    print("\nEmpty Series:")
    print(f"  Total Return: {empty_metrics.total_return}")
    print(f"  CAGR: {empty_metrics.cagr}")

    # Constant equity (no volatility)
    dates = pd.date_range("2023-01-01", periods=100, freq="D")
    constant_equity = pd.Series([100000] * 100, index=dates)
    constant_metrics = formatter.calculate_metrics(
        constant_equity, [], date(2023, 1, 1), date(2023, 4, 10)
    )
    print("\nConstant Equity (No Volatility):")
    print(f"  Total Return: {constant_metrics.total_return}")
    print(f"  Volatility: {constant_metrics.volatility}")
    print(f"  Max Drawdown: {constant_metrics.max_drawdown}")

    # Equity with severe drawdown
    dates = pd.date_range("2023-01-01", periods=5, freq="D")
    severe_dd_equity = pd.Series([100000, 90000, 70000, 75000, 85000], index=dates)
    dd_series = formatter.generate_drawdown_series(severe_dd_equity)
    print("\nSevere Drawdown:")
    print(f"  Maximum drawdown: {abs(dd_series.min()):.2f}%")
    print(f"  Drawdown at trough: {dd_series.iloc[2]:.2f}%")


def example_api_response_format() -> None:
    """Example: Format results for API response."""
    print("\n" + "=" * 80)
    print("Example 5: API Response Formatting")
    print("=" * 80)

    # Create sample data
    dates = pd.date_range("2023-01-01", periods=10, freq="D")
    equity = pd.Series(range(100000, 100100, 10), index=dates)
    trades = [{"profit": 50, "entry": 100000, "exit": 100050}]

    formatter = create_result_formatter()
    results = formatter.format_results(
        equity, trades, date(2023, 1, 1), date(2023, 1, 10), use_log_scale=True
    )

    # Convert to dict (JSON-serializable)
    response_dict = {
        "metrics": results.metrics.model_dump(),
        "equity_curve": {
            "strategy": [
                {"date": p.date, "value": p.value}
                for p in results.equity_curve.strategy
            ],
            "benchmark": None,
            "log_scale": results.equity_curve.log_scale,
        },
        "drawdown": {
            "data": [{"date": p.date, "value": p.value} for p in results.drawdown.data]
        },
        "monthly_heatmap": results.monthly_heatmap.model_dump(),
    }

    print("\nAPI Response Structure:")
    print(f"  Metrics keys: {list(response_dict['metrics'].keys())}")
    print(f"  Equity curve points: {len(response_dict['equity_curve']['strategy'])}")
    print(f"  Sample equity point: {response_dict['equity_curve']['strategy'][0]}")
    print(f"  Drawdown points: {len(response_dict['drawdown']['data'])}")
    print(f"  Heatmap years: {response_dict['monthly_heatmap']['years']}")


def main() -> None:
    """Run all examples."""
    example_basic_usage()
    example_with_benchmark()
    example_individual_metrics()
    example_edge_cases()
    example_api_response_format()

    print("\n" + "=" * 80)
    print("All examples completed successfully!")
    print("=" * 80)


if __name__ == "__main__":
    main()
