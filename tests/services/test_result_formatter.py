"""
Tests for ResultFormatter service.

Covers:
- Performance metrics calculation (returns, CAGR, MDD, Sharpe, Sortino, Calmar)
- Log-scale equity curve transformation
- Drawdown series generation
- Monthly heatmap data generation
- Chart data formatting
- Edge cases (empty series, single value, negative values, zeros)
- Full integration workflow
"""

import numpy as np
import pandas as pd
import pytest
from datetime import date, timedelta

from app.services.result_formatter import (
    ResultFormatter,
    StandardMetricsCalculator,
    PerformanceMetrics,
    EquityCurveData,
    DrawdownData,
    MonthlyHeatmapData,
    FormattedResults,
    ChartDataPoint,
    create_result_formatter,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def formatter() -> ResultFormatter:
    """Create a default ResultFormatter instance."""
    return ResultFormatter(risk_free_rate=0.02)


@pytest.fixture
def calculator() -> StandardMetricsCalculator:
    """Create a StandardMetricsCalculator instance."""
    return StandardMetricsCalculator(risk_free_rate=0.02)


@pytest.fixture
def constant_growth_equity() -> pd.Series:
    """
    Create a constant growth equity series for testing.

    Grows from 10,000 to 20,000 over 252 trading days (1 year).
    Expected CAGR: 100%, Total Return: 100%
    """
    dates = pd.date_range("2023-01-01", periods=253, freq="D")
    # Linear growth from 10000 to 20000
    values = np.linspace(10000, 20000, 253)
    return pd.Series(values, index=dates)


@pytest.fixture
def volatile_equity() -> pd.Series:
    """
    Create a volatile equity series with drawdowns.

    Simulates realistic market movements with drawdowns.
    """
    dates = pd.date_range("2023-01-01", periods=253, freq="D")
    np.random.seed(42)  # For reproducibility

    # Start with 100,000
    values = [100000.0]

    # Simulate daily returns with volatility
    for _ in range(252):
        daily_return = np.random.normal(0.0005, 0.01)  # 0.05% mean, 1% std
        values.append(values[-1] * (1 + daily_return))

    return pd.Series(values, index=dates)


@pytest.fixture
def sample_trades() -> list[dict]:
    """Sample trades list with wins and losses."""
    return [
        {"profit": 100.0, "entry": 10000, "exit": 10100},
        {"profit": -50.0, "entry": 10100, "exit": 10050},
        {"profit": 200.0, "entry": 10050, "exit": 10250},
        {"profit": -75.0, "entry": 10250, "exit": 10175},
        {"profit": 150.0, "entry": 10175, "exit": 10325},
    ]


@pytest.fixture
def multi_year_equity() -> pd.Series:
    """Create a multi-year equity series for heatmap testing."""
    # 3 years of daily data
    dates = pd.date_range("2021-01-01", "2023-12-31", freq="D")
    np.random.seed(42)

    values = [100000.0]
    for _ in range(len(dates) - 1):
        daily_return = np.random.normal(0.0003, 0.008)
        values.append(values[-1] * (1 + daily_return))

    return pd.Series(values, index=dates)


# =============================================================================
# Test StandardMetricsCalculator
# =============================================================================


def test_calculator_total_return_constant_growth(
    calculator: StandardMetricsCalculator,
    constant_growth_equity: pd.Series,
) -> None:
    """Test total return calculation with constant growth."""
    total_return = calculator.calculate_total_return(constant_growth_equity)

    # Should be exactly 100% (10000 to 20000)
    assert abs(total_return - 100.0) < 0.01


def test_calculator_total_return_empty_series(
    calculator: StandardMetricsCalculator,
) -> None:
    """Test total return with empty series."""
    empty_series = pd.Series([], dtype=float)
    total_return = calculator.calculate_total_return(empty_series)

    assert total_return == 0.0


def test_calculator_total_return_zero_initial(
    calculator: StandardMetricsCalculator,
) -> None:
    """Test total return with zero initial value."""
    series = pd.Series([0, 100, 200])
    total_return = calculator.calculate_total_return(series)

    assert total_return == 0.0


def test_calculator_cagr_one_year_double(
    calculator: StandardMetricsCalculator,
    constant_growth_equity: pd.Series,
) -> None:
    """Test CAGR calculation for 1 year doubling."""
    start_date = pd.Timestamp("2023-01-01")
    end_date = pd.Timestamp("2023-12-31")

    cagr = calculator.calculate_cagr(constant_growth_equity, start_date, end_date)

    # CAGR should be approximately 100% for doubling in ~1 year
    # (Exact value depends on 364 days vs 365 days)
    assert 95.0 < cagr < 105.0


def test_calculator_cagr_two_years(calculator: StandardMetricsCalculator) -> None:
    """Test CAGR calculation for 2 years."""
    dates = pd.date_range("2021-01-01", "2022-12-31", freq="D")
    # Double over 2 years: CAGR = sqrt(2) - 1 ≈ 41.4%
    start_value = 10000
    end_value = 20000
    values = np.linspace(start_value, end_value, len(dates))

    equity = pd.Series(values, index=dates)
    start_date = pd.Timestamp("2021-01-01")
    end_date = pd.Timestamp("2022-12-31")

    cagr = calculator.calculate_cagr(equity, start_date, end_date)

    # CAGR = (2)^(1/2) - 1 = 0.414... ≈ 41.4%
    assert 40.0 < cagr < 43.0


def test_calculator_cagr_empty_series(calculator: StandardMetricsCalculator) -> None:
    """Test CAGR with empty series."""
    empty_series = pd.Series([], dtype=float)
    start_date = pd.Timestamp("2023-01-01")
    end_date = pd.Timestamp("2023-12-31")

    cagr = calculator.calculate_cagr(empty_series, start_date, end_date)

    assert cagr == 0.0


def test_calculator_max_drawdown_no_drawdown(
    calculator: StandardMetricsCalculator,
) -> None:
    """Test max drawdown with monotonically increasing equity."""
    dates = pd.date_range("2023-01-01", periods=10, freq="D")
    values = range(10000, 10010)
    equity = pd.Series(values, index=dates)

    mdd = calculator.calculate_max_drawdown(equity)

    # No drawdown, should be 0
    assert mdd == 0.0


def test_calculator_max_drawdown_with_drawdown(
    calculator: StandardMetricsCalculator,
) -> None:
    """Test max drawdown with known drawdown."""
    dates = pd.date_range("2023-01-01", periods=5, freq="D")
    # Peak at 10000, trough at 8000 = 20% drawdown
    values = [10000, 9500, 8000, 8500, 9000]
    equity = pd.Series(values, index=dates)

    mdd = calculator.calculate_max_drawdown(equity)

    # Max drawdown should be 20%
    assert abs(mdd - 20.0) < 0.01


def test_calculator_max_drawdown_empty_series(
    calculator: StandardMetricsCalculator,
) -> None:
    """Test max drawdown with empty series."""
    empty_series = pd.Series([], dtype=float)
    mdd = calculator.calculate_max_drawdown(empty_series)

    assert mdd == 0.0


def test_calculator_sharpe_ratio_positive_returns(
    calculator: StandardMetricsCalculator,
) -> None:
    """Test Sharpe ratio with positive returns."""
    # Consistent positive returns of 0.1% daily
    returns = pd.Series([0.001] * 252)

    sharpe = calculator.calculate_sharpe_ratio(returns, 0.02)

    # Should be positive since returns > risk-free rate
    assert sharpe > 0


def test_calculator_sharpe_ratio_zero_volatility(
    calculator: StandardMetricsCalculator,
) -> None:
    """Test Sharpe ratio with zero volatility."""
    # All returns are identical = zero volatility
    returns = pd.Series([0.001] * 252)
    # Make them all exactly the same
    returns = pd.Series([0.0] * 252)

    sharpe = calculator.calculate_sharpe_ratio(returns, 0.02)

    # Should return 0 when std is 0
    assert sharpe == 0.0


def test_calculator_sharpe_ratio_empty_returns(
    calculator: StandardMetricsCalculator,
) -> None:
    """Test Sharpe ratio with empty returns."""
    empty_returns = pd.Series([], dtype=float)
    sharpe = calculator.calculate_sharpe_ratio(empty_returns, 0.02)

    assert sharpe == 0.0


def test_calculator_sortino_ratio_positive_returns(
    calculator: StandardMetricsCalculator,
) -> None:
    """Test Sortino ratio with positive returns."""
    # Mix of positive and negative returns
    np.random.seed(42)
    returns = pd.Series(np.random.normal(0.001, 0.005, 252))

    sortino = calculator.calculate_sortino_ratio(returns, 0.02)

    # Should be a reasonable value
    assert -10 < sortino < 10


def test_calculator_sortino_ratio_no_downside(
    calculator: StandardMetricsCalculator,
) -> None:
    """Test Sortino ratio with no negative returns."""
    # All positive returns
    returns = pd.Series([0.001, 0.002, 0.001, 0.003] * 63)  # 252 days

    sortino = calculator.calculate_sortino_ratio(returns, 0.02)

    # Should return 0 when no downside volatility
    assert sortino == 0.0


def test_calculator_sortino_ratio_empty_returns(
    calculator: StandardMetricsCalculator,
) -> None:
    """Test Sortino ratio with empty returns."""
    empty_returns = pd.Series([], dtype=float)
    sortino = calculator.calculate_sortino_ratio(empty_returns, 0.02)

    assert sortino == 0.0


def test_calculator_volatility_calculation(
    calculator: StandardMetricsCalculator,
) -> None:
    """Test volatility calculation."""
    # Create returns with known std
    np.random.seed(42)
    returns = pd.Series(np.random.normal(0, 0.01, 252))  # 1% daily std

    volatility = calculator.calculate_volatility(returns)

    # Annualized volatility should be around 1% * sqrt(252) ≈ 15.87%
    # Allow some tolerance due to random sampling
    assert 12.0 < volatility < 20.0


def test_calculator_volatility_empty_returns(
    calculator: StandardMetricsCalculator,
) -> None:
    """Test volatility with empty returns."""
    empty_returns = pd.Series([], dtype=float)
    volatility = calculator.calculate_volatility(empty_returns)

    assert volatility == 0.0


# =============================================================================
# Test ResultFormatter Methods
# =============================================================================


def test_formatter_calculate_metrics_comprehensive(
    formatter: ResultFormatter,
    constant_growth_equity: pd.Series,
    sample_trades: list[dict],
) -> None:
    """Test comprehensive metrics calculation."""
    start_date = date(2023, 1, 1)
    end_date = date(2023, 12, 31)

    metrics = formatter.calculate_metrics(
        constant_growth_equity, sample_trades, start_date, end_date
    )

    # Validate structure
    assert isinstance(metrics, PerformanceMetrics)

    # Validate basic metrics
    assert metrics.total_return > 0
    assert metrics.cagr > 0
    assert metrics.max_drawdown >= 0
    assert metrics.volatility >= 0

    # Validate trade metrics
    assert metrics.total_trades == 5
    assert metrics.winning_trades == 3
    assert metrics.losing_trades == 2
    assert abs(metrics.win_rate - 60.0) < 0.01


def test_formatter_calculate_metrics_no_trades(
    formatter: ResultFormatter,
    constant_growth_equity: pd.Series,
) -> None:
    """Test metrics calculation with no trades."""
    start_date = date(2023, 1, 1)
    end_date = date(2023, 12, 31)

    metrics = formatter.calculate_metrics(
        constant_growth_equity, [], start_date, end_date
    )

    # Trade metrics should be zero
    assert metrics.total_trades == 0
    assert metrics.winning_trades == 0
    assert metrics.losing_trades == 0
    assert metrics.win_rate == 0.0


def test_formatter_generate_log_scale_equity(
    formatter: ResultFormatter,
    constant_growth_equity: pd.Series,
) -> None:
    """Test log-scale equity transformation."""
    log_equity = formatter.generate_log_scale_equity(constant_growth_equity)

    # Validate output
    assert len(log_equity) == len(constant_growth_equity)
    assert isinstance(log_equity, pd.Series)

    # Log scale should be monotonically increasing for increasing equity
    assert all(log_equity.diff().dropna() >= 0)


def test_formatter_generate_log_scale_with_zeros(formatter: ResultFormatter) -> None:
    """Test log-scale transformation with zero values."""
    dates = pd.date_range("2023-01-01", periods=5, freq="D")
    # Include zeros which should be handled
    values = [10000, 0, 5000, 0, 8000]
    equity = pd.Series(values, index=dates)

    log_equity = formatter.generate_log_scale_equity(equity)

    # Should not contain inf or NaN
    assert not log_equity.isnull().any()
    assert not np.isinf(log_equity).any()


def test_formatter_generate_log_scale_with_negatives(formatter: ResultFormatter) -> None:
    """Test log-scale transformation with negative values."""
    dates = pd.date_range("2023-01-01", periods=5, freq="D")
    # Include negative values
    values = [10000, -5000, 5000, 8000, 12000]
    equity = pd.Series(values, index=dates)

    log_equity = formatter.generate_log_scale_equity(equity)

    # Should not contain inf or NaN
    assert not log_equity.isnull().any()
    assert not np.isinf(log_equity).any()


def test_formatter_generate_drawdown_series(formatter: ResultFormatter) -> None:
    """Test drawdown series generation."""
    dates = pd.date_range("2023-01-01", periods=5, freq="D")
    # Peak at 10000, trough at 8000, recovery to 9500
    values = [10000, 9500, 8000, 8500, 9500]
    equity = pd.Series(values, index=dates)

    drawdown = formatter.generate_drawdown_series(equity)

    # Validate structure
    assert len(drawdown) == len(equity)
    assert isinstance(drawdown, pd.Series)

    # First value should be 0 (at peak)
    assert drawdown.iloc[0] == 0.0

    # Maximum drawdown should be at index 2 (8000 from 10000)
    expected_max_dd = ((8000 - 10000) / 10000) * 100
    assert abs(drawdown.iloc[2] - expected_max_dd) < 0.01


def test_formatter_generate_drawdown_series_empty(formatter: ResultFormatter) -> None:
    """Test drawdown series with empty equity."""
    empty_series = pd.Series([], dtype=float)
    drawdown = formatter.generate_drawdown_series(empty_series)

    assert len(drawdown) == 0


def test_formatter_generate_monthly_heatmap(
    formatter: ResultFormatter,
    multi_year_equity: pd.Series,
) -> None:
    """Test monthly heatmap generation."""
    heatmap = formatter.generate_monthly_heatmap(multi_year_equity)

    # Validate structure
    assert isinstance(heatmap, MonthlyHeatmapData)
    assert len(heatmap.years) == 3  # 2021, 2022, 2023
    assert len(heatmap.months) == 12
    assert len(heatmap.returns) == 3

    # Each year should have 12 months
    for year_returns in heatmap.returns:
        assert len(year_returns) == 12

    # Years should be in order
    assert heatmap.years == [2021, 2022, 2023]


def test_formatter_generate_monthly_heatmap_partial_year(
    formatter: ResultFormatter,
) -> None:
    """Test monthly heatmap with partial year data."""
    # Only 3 months of data
    dates = pd.date_range("2023-01-01", "2023-03-31", freq="D")
    values = np.linspace(10000, 11000, len(dates))
    equity = pd.Series(values, index=dates)

    heatmap = formatter.generate_monthly_heatmap(equity)

    # Should have 1 year
    assert len(heatmap.years) == 1
    assert heatmap.years[0] == 2023

    # Should have data for first 3 months, rest None
    year_returns = heatmap.returns[0]
    assert year_returns[0] is not None  # January
    assert year_returns[1] is not None  # February
    assert year_returns[2] is not None  # March
    assert year_returns[3] is None  # April (no data)


def test_formatter_generate_monthly_heatmap_empty(formatter: ResultFormatter) -> None:
    """Test monthly heatmap with empty equity."""
    empty_series = pd.Series([], dtype=float)
    heatmap = formatter.generate_monthly_heatmap(empty_series)

    assert len(heatmap.years) == 0
    assert len(heatmap.returns) == 0


def test_formatter_format_for_chart_basic(
    formatter: ResultFormatter,
    constant_growth_equity: pd.Series,
) -> None:
    """Test basic chart data formatting."""
    chart_data = formatter.format_for_chart(constant_growth_equity, use_log_scale=False)

    # Validate structure
    assert isinstance(chart_data, EquityCurveData)
    assert len(chart_data.strategy) == len(constant_growth_equity)
    assert chart_data.benchmark is None
    assert chart_data.log_scale is False

    # Validate data points
    first_point = chart_data.strategy[0]
    assert isinstance(first_point, ChartDataPoint)
    assert first_point.date == "2023-01-01"
    assert first_point.value == constant_growth_equity.iloc[0]


def test_formatter_format_for_chart_with_benchmark(
    formatter: ResultFormatter,
    constant_growth_equity: pd.Series,
) -> None:
    """Test chart data formatting with benchmark."""
    # Create a benchmark series
    benchmark = constant_growth_equity * 0.8  # 80% of strategy performance

    chart_data = formatter.format_for_chart(
        constant_growth_equity, benchmark_series=benchmark, use_log_scale=False
    )

    # Validate benchmark data
    assert chart_data.benchmark is not None
    assert len(chart_data.benchmark) == len(benchmark)

    # Benchmark should be lower than strategy
    assert chart_data.benchmark[0].value < chart_data.strategy[0].value


def test_formatter_format_for_chart_log_scale(
    formatter: ResultFormatter,
    constant_growth_equity: pd.Series,
) -> None:
    """Test chart data formatting with log scale."""
    chart_data = formatter.format_for_chart(constant_growth_equity, use_log_scale=True)

    assert chart_data.log_scale is True

    # Values should be log-transformed (smaller than original)
    original_value = constant_growth_equity.iloc[0]
    log_value = chart_data.strategy[0].value
    assert log_value == np.log10(original_value)


def test_formatter_format_results_complete(
    formatter: ResultFormatter,
    volatile_equity: pd.Series,
    sample_trades: list[dict],
) -> None:
    """Test complete results formatting workflow."""
    start_date = date(2023, 1, 1)
    end_date = date(2023, 12, 31)

    results = formatter.format_results(
        volatile_equity, sample_trades, start_date, end_date, use_log_scale=True
    )

    # Validate structure
    assert isinstance(results, FormattedResults)
    assert isinstance(results.metrics, PerformanceMetrics)
    assert isinstance(results.equity_curve, EquityCurveData)
    assert isinstance(results.drawdown, DrawdownData)
    assert isinstance(results.monthly_heatmap, MonthlyHeatmapData)

    # Validate metrics are calculated
    assert results.metrics.total_return != 0
    assert results.metrics.total_trades == 5

    # Validate chart data
    assert len(results.equity_curve.strategy) > 0
    assert results.equity_curve.log_scale is True

    # Validate drawdown
    assert len(results.drawdown.data) == len(volatile_equity)

    # Validate heatmap
    assert len(results.monthly_heatmap.years) >= 1


def test_formatter_format_results_with_benchmark(
    formatter: ResultFormatter,
    volatile_equity: pd.Series,
    sample_trades: list[dict],
) -> None:
    """Test results formatting with benchmark comparison."""
    start_date = date(2023, 1, 1)
    end_date = date(2023, 12, 31)

    # Create benchmark
    benchmark = volatile_equity * 0.9

    results = formatter.format_results(
        volatile_equity,
        sample_trades,
        start_date,
        end_date,
        benchmark_series=benchmark,
        use_log_scale=False,
    )

    # Should include benchmark data
    assert results.equity_curve.benchmark is not None
    assert len(results.equity_curve.benchmark) == len(benchmark)


# =============================================================================
# Test Factory Function
# =============================================================================


def test_create_result_formatter() -> None:
    """Test factory function."""
    formatter = create_result_formatter(risk_free_rate=0.03)

    assert isinstance(formatter, ResultFormatter)
    assert formatter.calculator.risk_free_rate == 0.03


def test_create_result_formatter_default() -> None:
    """Test factory function with default parameters."""
    formatter = create_result_formatter()

    assert isinstance(formatter, ResultFormatter)


# =============================================================================
# Test Edge Cases
# =============================================================================


def test_single_value_equity() -> None:
    """Test handling of single value equity series."""
    formatter = create_result_formatter()
    dates = pd.date_range("2023-01-01", periods=1, freq="D")
    equity = pd.Series([10000], index=dates)

    # Should handle single value gracefully
    metrics = formatter.calculate_metrics(
        equity, [], date(2023, 1, 1), date(2023, 1, 1)
    )

    assert metrics.total_return == 0.0
    assert metrics.max_drawdown == 0.0


def test_all_same_values_equity() -> None:
    """Test handling of constant equity series."""
    formatter = create_result_formatter()
    dates = pd.date_range("2023-01-01", periods=100, freq="D")
    equity = pd.Series([10000] * 100, index=dates)

    metrics = formatter.calculate_metrics(
        equity, [], date(2023, 1, 1), date(2023, 4, 10)
    )

    assert metrics.total_return == 0.0
    assert metrics.volatility == 0.0
    assert metrics.max_drawdown == 0.0


def test_negative_equity_values() -> None:
    """Test handling of negative equity values (account blown up)."""
    formatter = create_result_formatter()
    dates = pd.date_range("2023-01-01", periods=5, freq="D")
    # Account goes negative
    values = [10000, 5000, 1000, -1000, -5000]
    equity = pd.Series(values, index=dates)

    # Should still calculate metrics without crashing
    metrics = formatter.calculate_metrics(
        equity, [], date(2023, 1, 1), date(2023, 1, 5)
    )

    # Total return should be very negative
    assert metrics.total_return < -100
    assert metrics.max_drawdown > 100


# =============================================================================
# Test ChartDataPoint Validation
# =============================================================================


def test_chart_data_point_date_validation() -> None:
    """Test ChartDataPoint date format validation."""
    # Test with date object
    point = ChartDataPoint(date=date(2023, 1, 15), value=100.0)
    assert point.date == "2023-01-15"

    # Test with pandas Timestamp
    point = ChartDataPoint(date=pd.Timestamp("2023-01-15"), value=100.0)
    assert point.date == "2023-01-15"

    # Test with string
    point = ChartDataPoint(date="2023-01-15", value=100.0)
    assert point.date == "2023-01-15"


# =============================================================================
# Integration Tests
# =============================================================================


def test_full_workflow_integration() -> None:
    """Test complete workflow from raw data to formatted results."""
    # Create realistic backtest data
    dates = pd.date_range("2022-01-01", "2023-12-31", freq="D")
    np.random.seed(42)

    # Simulate equity curve with trend and volatility
    returns = np.random.normal(0.0005, 0.01, len(dates))
    equity_values = [100000.0]
    for ret in returns[:-1]:
        equity_values.append(equity_values[-1] * (1 + ret))

    equity = pd.Series(equity_values, index=dates)

    # Create some trades
    trades = [
        {"profit": 1000, "entry": 100000, "exit": 101000},
        {"profit": -500, "entry": 101000, "exit": 100500},
        {"profit": 2000, "entry": 100500, "exit": 102500},
    ]

    # Format results
    formatter = create_result_formatter(risk_free_rate=0.02)
    results = formatter.format_results(
        equity,
        trades,
        start_date=date(2022, 1, 1),
        end_date=date(2023, 12, 31),
        use_log_scale=True,
    )

    # Validate complete results
    assert isinstance(results, FormattedResults)

    # Metrics should be reasonable
    assert -100 < results.metrics.total_return < 1000
    assert -100 < results.metrics.cagr < 1000
    assert 0 <= results.metrics.max_drawdown <= 100
    assert -10 < results.metrics.sharpe_ratio < 10

    # Chart data should be complete
    assert len(results.equity_curve.strategy) == len(equity)
    assert len(results.drawdown.data) == len(equity)

    # Heatmap should cover 2 years
    assert 2022 in results.monthly_heatmap.years
    assert 2023 in results.monthly_heatmap.years
