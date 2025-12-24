"""
Result Formatter Service - Financial Metrics and Chart Data Processing.

This module implements comprehensive financial metrics calculation and chart data
formatting for backtest results. It provides:
1. Performance metrics (returns, CAGR, Sharpe, Sortino, Calmar)
2. Risk metrics (MDD, volatility, drawdown series)
3. Chart data formatting (equity curves, drawdowns, monthly heatmaps)
4. Log-scale transformations for visualization

Follows SOLID principles with clear separation of concerns and comprehensive
type hints for maintainability.
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from datetime import date
from typing import Protocol, Any
from pydantic import BaseModel, Field, ConfigDict, field_validator


# =============================================================================
# Result Models
# =============================================================================


class PerformanceMetrics(BaseModel):
    """
    Performance metrics for a backtest.

    Attributes:
        total_return: Total return as percentage (e.g., 25.5 for 25.5%)
        cagr: Compound Annual Growth Rate as percentage
        max_drawdown: Maximum drawdown as percentage (positive value)
        sharpe_ratio: Risk-adjusted return (annualized)
        sortino_ratio: Downside risk-adjusted return (annualized)
        calmar_ratio: CAGR / Max Drawdown
        volatility: Annualized volatility as percentage
        total_trades: Total number of trades executed
        winning_trades: Number of profitable trades
        losing_trades: Number of losing trades
        win_rate: Percentage of winning trades
    """

    model_config = ConfigDict(frozen=True)

    total_return: float = Field(..., description="Total return as percentage")
    cagr: float = Field(..., description="Compound Annual Growth Rate as percentage")
    max_drawdown: float = Field(..., description="Maximum drawdown as percentage")
    sharpe_ratio: float = Field(..., description="Risk-adjusted return (annualized)")
    sortino_ratio: float = Field(..., description="Downside risk-adjusted return")
    calmar_ratio: float = Field(..., description="CAGR / Max Drawdown")
    volatility: float = Field(..., description="Annualized volatility as percentage")
    total_trades: int = Field(default=0, description="Total number of trades")
    winning_trades: int = Field(default=0, description="Number of profitable trades")
    losing_trades: int = Field(default=0, description="Number of losing trades")
    win_rate: float = Field(default=0.0, description="Percentage of winning trades")


class ChartDataPoint(BaseModel):
    """
    Single data point for chart visualization.

    Attributes:
        date: Date of the data point (ISO format string)
        value: Value at this date
    """

    model_config = ConfigDict(frozen=True)

    date: str = Field(..., description="Date in ISO format (YYYY-MM-DD)")
    value: float = Field(..., description="Value at this date")

    @field_validator("date", mode="before")
    @classmethod
    def validate_date_format(cls, v: Any) -> str:
        """Ensure date is in ISO format string."""
        if isinstance(v, (date, pd.Timestamp)):
            return v.strftime("%Y-%m-%d")
        return str(v)


class EquityCurveData(BaseModel):
    """
    Equity curve data for charting.

    Attributes:
        strategy: List of data points for the strategy equity curve
        benchmark: Optional list of data points for benchmark comparison
        log_scale: Whether the data is in log scale
    """

    model_config = ConfigDict(frozen=False)

    strategy: list[ChartDataPoint] = Field(
        ..., description="Strategy equity curve data points"
    )
    benchmark: list[ChartDataPoint] | None = Field(
        default=None, description="Benchmark equity curve data points"
    )
    log_scale: bool = Field(default=False, description="Whether data is in log scale")


class DrawdownData(BaseModel):
    """
    Drawdown series data for charting.

    Attributes:
        data: List of drawdown data points (as negative percentages)
    """

    model_config = ConfigDict(frozen=True)

    data: list[ChartDataPoint] = Field(..., description="Drawdown data points")


class MonthlyHeatmapData(BaseModel):
    """
    Monthly returns heatmap data.

    Attributes:
        years: List of years
        months: List of month names
        returns: 2D array of monthly returns (years x months)
    """

    model_config = ConfigDict(frozen=True)

    years: list[int] = Field(..., description="List of years")
    months: list[str] = Field(
        default=[
            "Jan",
            "Feb",
            "Mar",
            "Apr",
            "May",
            "Jun",
            "Jul",
            "Aug",
            "Sep",
            "Oct",
            "Nov",
            "Dec",
        ],
        description="List of month names",
    )
    returns: list[list[float | None]] = Field(
        ..., description="2D array of monthly returns (years x months)"
    )


class FormattedResults(BaseModel):
    """
    Complete formatted results for API response.

    Attributes:
        metrics: Performance and risk metrics
        equity_curve: Equity curve data for charting
        drawdown: Drawdown series data
        monthly_heatmap: Monthly returns heatmap data
    """

    model_config = ConfigDict(frozen=False)

    metrics: PerformanceMetrics = Field(..., description="Performance metrics")
    equity_curve: EquityCurveData = Field(..., description="Equity curve data")
    drawdown: DrawdownData = Field(..., description="Drawdown series data")
    monthly_heatmap: MonthlyHeatmapData = Field(
        ..., description="Monthly returns heatmap"
    )


# =============================================================================
# Calculator Protocol (Dependency Inversion)
# =============================================================================


class MetricsCalculator(Protocol):
    """Protocol for metrics calculation strategies."""

    def calculate_total_return(self, equity_series: pd.Series) -> float:
        """Calculate total return percentage."""
        ...

    def calculate_cagr(
        self, equity_series: pd.Series, start_date: pd.Timestamp, end_date: pd.Timestamp
    ) -> float:
        """Calculate Compound Annual Growth Rate."""
        ...

    def calculate_max_drawdown(self, equity_series: pd.Series) -> float:
        """Calculate maximum drawdown percentage."""
        ...

    def calculate_sharpe_ratio(self, returns: pd.Series, risk_free_rate: float) -> float:
        """Calculate annualized Sharpe ratio."""
        ...

    def calculate_sortino_ratio(
        self, returns: pd.Series, risk_free_rate: float
    ) -> float:
        """Calculate annualized Sortino ratio."""
        ...


# =============================================================================
# Concrete Calculator Implementation
# =============================================================================


@dataclass
class StandardMetricsCalculator:
    """
    Standard implementation of financial metrics calculations.

    Uses industry-standard formulas for all metrics with annualization
    based on 252 trading days per year.

    Attributes:
        trading_days_per_year: Number of trading days for annualization (default: 252)
        risk_free_rate: Annual risk-free rate for Sharpe/Sortino (default: 0.0)
    """

    trading_days_per_year: int = 252
    risk_free_rate: float = 0.0

    def calculate_total_return(self, equity_series: pd.Series) -> float:
        """
        Calculate total return percentage.

        Args:
            equity_series: Daily equity values

        Returns:
            Total return as percentage (e.g., 25.5 for 25.5% return)
        """
        if len(equity_series) == 0:
            return 0.0

        initial_value = equity_series.iloc[0]
        final_value = equity_series.iloc[-1]

        if initial_value == 0:
            return 0.0

        return ((final_value - initial_value) / initial_value) * 100

    def calculate_cagr(
        self, equity_series: pd.Series, start_date: pd.Timestamp, end_date: pd.Timestamp
    ) -> float:
        """
        Calculate Compound Annual Growth Rate.

        Args:
            equity_series: Daily equity values
            start_date: Backtest start date
            end_date: Backtest end date

        Returns:
            CAGR as percentage
        """
        if len(equity_series) == 0:
            return 0.0

        initial_value = equity_series.iloc[0]
        final_value = equity_series.iloc[-1]

        if initial_value == 0:
            return 0.0

        # Calculate years (including fractional years)
        days = (end_date - start_date).days
        years = days / 365.25

        if years <= 0:
            return 0.0

        # CAGR = (final_value / initial_value) ^ (1 / years) - 1
        # Handle negative final values (account blown up)
        ratio = final_value / initial_value
        if ratio <= 0:
            return -100.0  # Complete loss or worse

        cagr = ratio ** (1 / years) - 1
        return cagr * 100

    def calculate_max_drawdown(self, equity_series: pd.Series) -> float:
        """
        Calculate maximum drawdown percentage.

        Args:
            equity_series: Daily equity values

        Returns:
            Maximum drawdown as positive percentage (e.g., 15.5 for 15.5% drawdown)
        """
        if len(equity_series) == 0:
            return 0.0

        # Calculate running maximum
        running_max = equity_series.expanding().max()

        # Calculate drawdown series
        drawdown = (equity_series - running_max) / running_max

        # Return maximum drawdown as positive percentage
        return abs(drawdown.min()) * 100

    def calculate_sharpe_ratio(self, returns: pd.Series, risk_free_rate: float) -> float:
        """
        Calculate annualized Sharpe ratio.

        Args:
            returns: Daily returns series
            risk_free_rate: Annual risk-free rate (as decimal, e.g., 0.02 for 2%)

        Returns:
            Annualized Sharpe ratio
        """
        if len(returns) == 0 or returns.std() == 0:
            return 0.0

        # Convert annual risk-free rate to daily
        daily_rf = (1 + risk_free_rate) ** (1 / self.trading_days_per_year) - 1

        # Calculate excess returns
        excess_returns = returns - daily_rf

        # Sharpe = mean(excess_returns) / std(returns) * sqrt(trading_days)
        sharpe = (excess_returns.mean() / returns.std()) * np.sqrt(
            self.trading_days_per_year
        )

        return sharpe

    def calculate_sortino_ratio(
        self, returns: pd.Series, risk_free_rate: float
    ) -> float:
        """
        Calculate annualized Sortino ratio.

        Similar to Sharpe but only penalizes downside volatility.

        Args:
            returns: Daily returns series
            risk_free_rate: Annual risk-free rate (as decimal)

        Returns:
            Annualized Sortino ratio
        """
        if len(returns) == 0:
            return 0.0

        # Convert annual risk-free rate to daily
        daily_rf = (1 + risk_free_rate) ** (1 / self.trading_days_per_year) - 1

        # Calculate excess returns
        excess_returns = returns - daily_rf

        # Calculate downside deviation (only negative returns)
        downside_returns = returns[returns < 0]
        if len(downside_returns) == 0 or downside_returns.std() == 0:
            return 0.0

        downside_std = downside_returns.std()

        # Sortino = mean(excess_returns) / downside_std * sqrt(trading_days)
        sortino = (excess_returns.mean() / downside_std) * np.sqrt(
            self.trading_days_per_year
        )

        return sortino

    def calculate_volatility(self, returns: pd.Series) -> float:
        """
        Calculate annualized volatility.

        Args:
            returns: Daily returns series

        Returns:
            Annualized volatility as percentage
        """
        if len(returns) == 0:
            return 0.0

        # Annualized volatility = std(daily_returns) * sqrt(trading_days) * 100
        return returns.std() * np.sqrt(self.trading_days_per_year) * 100


# =============================================================================
# Result Formatter Service
# =============================================================================


class ResultFormatter:
    """
    Service for formatting backtest results into structured data.

    This service handles:
    1. Financial metrics calculation
    2. Chart data formatting
    3. Log-scale transformations
    4. Monthly heatmap generation

    Attributes:
        calculator: Metrics calculator implementation
    """

    def __init__(
        self,
        calculator: MetricsCalculator | None = None,
        risk_free_rate: float = 0.0,
    ):
        """
        Initialize the result formatter.

        Args:
            calculator: Optional custom metrics calculator (uses standard if None)
            risk_free_rate: Annual risk-free rate for Sharpe/Sortino (default: 0.0)
        """
        self.calculator = calculator or StandardMetricsCalculator(
            risk_free_rate=risk_free_rate
        )

    def calculate_metrics(
        self,
        equity_series: pd.Series,
        trades: list[dict[str, Any]],
        start_date: date,
        end_date: date,
    ) -> PerformanceMetrics:
        """
        Calculate comprehensive performance metrics.

        Args:
            equity_series: Daily equity values (indexed by date)
            trades: List of trade dictionaries with profit/loss info
            start_date: Backtest start date
            end_date: Backtest end date

        Returns:
            PerformanceMetrics instance with all calculated metrics
        """
        # Convert dates to pandas timestamps
        start_ts = pd.Timestamp(start_date)
        end_ts = pd.Timestamp(end_date)

        # Calculate returns series
        returns = equity_series.pct_change().dropna()

        # Calculate basic metrics
        total_return = self.calculator.calculate_total_return(equity_series)
        cagr = self.calculator.calculate_cagr(equity_series, start_ts, end_ts)
        max_drawdown = self.calculator.calculate_max_drawdown(equity_series)
        volatility = self.calculator.calculate_volatility(returns)

        # Calculate risk-adjusted metrics
        risk_free_rate = getattr(self.calculator, "risk_free_rate", 0.0)
        sharpe_ratio = self.calculator.calculate_sharpe_ratio(returns, risk_free_rate)
        sortino_ratio = self.calculator.calculate_sortino_ratio(returns, risk_free_rate)

        # Calculate Calmar ratio (CAGR / Max Drawdown)
        calmar_ratio = cagr / max_drawdown if max_drawdown > 0 else 0.0

        # Analyze trades
        total_trades = len(trades)
        winning_trades = sum(1 for t in trades if t.get("profit", 0) > 0)
        losing_trades = sum(1 for t in trades if t.get("profit", 0) < 0)
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0

        return PerformanceMetrics(
            total_return=total_return,
            cagr=cagr,
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            calmar_ratio=calmar_ratio,
            volatility=volatility,
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
        )

    def generate_log_scale_equity(self, equity_series: pd.Series) -> pd.Series:
        """
        Generate log-scale equity curve for visualization.

        Uses log10 transformation to better show percentage changes.

        Args:
            equity_series: Daily equity values

        Returns:
            Log10-transformed equity series
        """
        # Replace zeros and negative values with small positive value
        # to avoid log(0) or log(negative)
        equity_clean = equity_series.copy()
        min_positive = equity_clean[equity_clean > 0].min() if (equity_clean > 0).any() else 1
        equity_clean = equity_clean.clip(lower=min_positive * 0.01)

        return np.log10(equity_clean)

    def generate_drawdown_series(self, equity_series: pd.Series) -> pd.Series:
        """
        Generate drawdown series as percentages.

        Args:
            equity_series: Daily equity values

        Returns:
            Drawdown series (negative percentages, e.g., -10.5 for 10.5% drawdown)
        """
        if len(equity_series) == 0:
            return pd.Series([], dtype=float)

        # Calculate running maximum
        running_max = equity_series.expanding().max()

        # Calculate drawdown as percentage
        drawdown = ((equity_series - running_max) / running_max) * 100

        return drawdown

    def generate_monthly_heatmap(self, equity_series: pd.Series) -> MonthlyHeatmapData:
        """
        Generate monthly returns heatmap data.

        Args:
            equity_series: Daily equity values (indexed by date)

        Returns:
            MonthlyHeatmapData with monthly returns organized by year and month
        """
        if len(equity_series) == 0:
            return MonthlyHeatmapData(years=[], returns=[])

        # Resample to monthly frequency (end of month)
        monthly_equity = equity_series.resample("ME").last()

        # Calculate monthly returns
        monthly_returns = monthly_equity.pct_change() * 100  # As percentage

        # Organize by year and month
        years = sorted(monthly_returns.index.year.unique())
        returns_matrix: list[list[float | None]] = []

        for year in years:
            year_returns: list[float | None] = [None] * 12
            year_data = monthly_returns[monthly_returns.index.year == year]

            for month_idx, ret in year_data.items():
                month = month_idx.month - 1  # 0-indexed
                year_returns[month] = ret

            returns_matrix.append(year_returns)

        return MonthlyHeatmapData(years=years, returns=returns_matrix)

    def format_for_chart(
        self,
        equity_series: pd.Series,
        benchmark_series: pd.Series | None = None,
        use_log_scale: bool = False,
    ) -> EquityCurveData:
        """
        Format equity data for frontend charting.

        Args:
            equity_series: Daily equity values for strategy
            benchmark_series: Optional daily equity values for benchmark
            use_log_scale: Whether to apply log10 transformation

        Returns:
            EquityCurveData ready for chart rendering
        """
        # Apply log scale if requested
        strategy_data = equity_series
        if use_log_scale:
            strategy_data = self.generate_log_scale_equity(equity_series)

        # Convert to chart data points
        strategy_points = [
            ChartDataPoint(date=idx.strftime("%Y-%m-%d"), value=val)
            for idx, val in strategy_data.items()
        ]

        # Process benchmark if provided
        benchmark_points = None
        if benchmark_series is not None:
            benchmark_data = benchmark_series
            if use_log_scale:
                benchmark_data = self.generate_log_scale_equity(benchmark_series)

            benchmark_points = [
                ChartDataPoint(date=idx.strftime("%Y-%m-%d"), value=val)
                for idx, val in benchmark_data.items()
            ]

        return EquityCurveData(
            strategy=strategy_points,
            benchmark=benchmark_points,
            log_scale=use_log_scale,
        )

    def format_results(
        self,
        equity_series: pd.Series,
        trades: list[dict[str, Any]],
        start_date: date,
        end_date: date,
        benchmark_series: pd.Series | None = None,
        use_log_scale: bool = False,
    ) -> FormattedResults:
        """
        Format complete backtest results.

        This is the main entry point that orchestrates all formatting operations.

        Args:
            equity_series: Daily equity values for strategy
            trades: List of trade dictionaries
            start_date: Backtest start date
            end_date: Backtest end date
            benchmark_series: Optional benchmark equity series
            use_log_scale: Whether to use log scale for equity curves

        Returns:
            FormattedResults with all metrics and chart data
        """
        # Calculate metrics
        metrics = self.calculate_metrics(equity_series, trades, start_date, end_date)

        # Format equity curve
        equity_curve = self.format_for_chart(
            equity_series, benchmark_series, use_log_scale
        )

        # Generate drawdown series
        drawdown_series = self.generate_drawdown_series(equity_series)
        drawdown_points = [
            ChartDataPoint(date=idx.strftime("%Y-%m-%d"), value=val)
            for idx, val in drawdown_series.items()
        ]
        drawdown = DrawdownData(data=drawdown_points)

        # Generate monthly heatmap
        monthly_heatmap = self.generate_monthly_heatmap(equity_series)

        return FormattedResults(
            metrics=metrics,
            equity_curve=equity_curve,
            drawdown=drawdown,
            monthly_heatmap=monthly_heatmap,
        )


# =============================================================================
# Factory Function
# =============================================================================


def create_result_formatter(risk_free_rate: float = 0.0) -> ResultFormatter:
    """
    Factory function to create a ResultFormatter instance.

    Args:
        risk_free_rate: Annual risk-free rate for Sharpe/Sortino calculations

    Returns:
        ResultFormatter instance ready to use
    """
    return ResultFormatter(risk_free_rate=risk_free_rate)
