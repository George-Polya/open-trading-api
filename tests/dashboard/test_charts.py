"""
Unit tests for chart creation functions.

Tests that chart functions return valid Plotly Figure objects
with correct data series and layout properties.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import plotly.graph_objects as go


class TestEquityChart:
    """Tests for equity curve chart creation."""

    @pytest.fixture
    def sample_equity_df(self) -> pd.DataFrame:
        """Create sample equity data for testing."""
        dates = pd.date_range(start="2020-01-01", periods=252, freq="B")
        np.random.seed(42)

        # Simulate equity curve with drift
        returns = np.random.normal(0.0005, 0.02, len(dates))
        equity = 100000 * np.exp(np.cumsum(returns))

        df = pd.DataFrame({"strategy": equity}, index=dates)

        # Add benchmark
        bench_returns = np.random.normal(0.0003, 0.015, len(dates))
        df["benchmark"] = 100000 * np.exp(np.cumsum(bench_returns))

        return df

    def test_create_equity_chart_returns_figure(self, sample_equity_df):
        """Test that create_equity_chart returns a Plotly Figure."""
        from app.dashboard.components.charts import create_equity_chart

        fig = create_equity_chart(sample_equity_df)
        assert isinstance(fig, go.Figure)

    def test_equity_chart_has_strategy_trace(self, sample_equity_df):
        """Test that the chart includes a strategy trace."""
        from app.dashboard.components.charts import create_equity_chart

        fig = create_equity_chart(sample_equity_df)

        trace_names = [trace.name for trace in fig.data]
        assert "Strategy" in trace_names

    def test_equity_chart_has_benchmark_trace(self, sample_equity_df):
        """Test that the chart includes a benchmark trace when available."""
        from app.dashboard.components.charts import create_equity_chart

        fig = create_equity_chart(sample_equity_df, include_benchmark=True)

        trace_names = [trace.name for trace in fig.data]
        assert "Benchmark" in trace_names

    def test_equity_chart_log_scale(self, sample_equity_df):
        """Test that log scale option is applied correctly."""
        from app.dashboard.components.charts import create_equity_chart

        fig = create_equity_chart(sample_equity_df, log_scale=True)

        # Check y-axis type
        assert fig.layout.yaxis.type == "log"

    def test_equity_chart_linear_scale(self, sample_equity_df):
        """Test that linear scale is applied by default."""
        from app.dashboard.components.charts import create_equity_chart

        fig = create_equity_chart(sample_equity_df, log_scale=False)

        # Check y-axis type
        assert fig.layout.yaxis.type == "linear"


class TestDrawdownChart:
    """Tests for drawdown chart creation."""

    @pytest.fixture
    def sample_drawdown_series(self) -> pd.Series:
        """Create sample drawdown data for testing."""
        dates = pd.date_range(start="2020-01-01", periods=252, freq="B")
        np.random.seed(42)

        # Simulate drawdown series (negative values)
        drawdown = np.zeros(len(dates))
        for i in range(1, len(dates)):
            change = np.random.normal(0, 2)
            drawdown[i] = max(min(drawdown[i - 1] + change, 0), -30)

        return pd.Series(drawdown, index=dates)

    def test_create_drawdown_chart_returns_figure(self, sample_drawdown_series):
        """Test that create_drawdown_chart returns a Plotly Figure."""
        from app.dashboard.components.charts import create_drawdown_chart

        fig = create_drawdown_chart(sample_drawdown_series)
        assert isinstance(fig, go.Figure)

    def test_drawdown_chart_has_fill(self, sample_drawdown_series):
        """Test that the drawdown chart has fill area."""
        from app.dashboard.components.charts import create_drawdown_chart

        fig = create_drawdown_chart(sample_drawdown_series)

        # Check that trace has fill
        assert fig.data[0].fill == "tozeroy"

    def test_drawdown_chart_has_annotation(self, sample_drawdown_series):
        """Test that the chart has max drawdown annotation."""
        from app.dashboard.components.charts import create_drawdown_chart

        fig = create_drawdown_chart(sample_drawdown_series)

        # Check for annotation
        assert len(fig.layout.annotations) > 0


class TestMonthlyHeatmap:
    """Tests for monthly returns heatmap creation."""

    @pytest.fixture
    def sample_heatmap_data(self):
        """Create sample monthly heatmap data."""

        class MockHeatmapData:
            years = [2020, 2021, 2022]
            months = [
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
            ]
            returns = [
                [1.5, -0.5, 2.0, 1.0, -1.5, 0.5, 2.5, -0.8, 1.2, 0.8, -0.3, 1.8],
                [0.8, 1.2, -1.0, 2.5, 0.3, -0.7, 1.5, 2.0, -0.5, 1.0, 1.8, 0.5],
                [-0.5, 0.8, 1.5, -1.2, 2.0, 0.5, -0.3, 1.0, None, None, None, None],
            ]

        return MockHeatmapData()

    def test_create_monthly_heatmap_returns_figure(self, sample_heatmap_data):
        """Test that create_monthly_heatmap returns a Plotly Figure."""
        from app.dashboard.components.charts import create_monthly_heatmap

        fig = create_monthly_heatmap(sample_heatmap_data)
        assert isinstance(fig, go.Figure)

    def test_heatmap_has_correct_dimensions(self, sample_heatmap_data):
        """Test that the heatmap has correct number of rows and columns."""
        from app.dashboard.components.charts import create_monthly_heatmap

        fig = create_monthly_heatmap(sample_heatmap_data)

        # Check z data dimensions
        z_data = fig.data[0].z
        assert len(z_data) == 3  # 3 years
        assert len(z_data[0]) == 12  # 12 months


class TestAssetAllocationChart:
    """Tests for asset allocation stacked area chart."""

    @pytest.fixture
    def sample_allocation_df(self) -> pd.DataFrame:
        """Create sample allocation data for testing."""
        dates = pd.date_range(start="2020-01-01", periods=12, freq="ME")

        df = pd.DataFrame(
            {
                "AAPL": [30, 28, 32, 25, 30, 28, 35, 30, 28, 32, 30, 28],
                "GOOGL": [25, 27, 23, 30, 25, 27, 20, 25, 27, 23, 25, 27],
                "MSFT": [20, 22, 18, 20, 20, 22, 20, 20, 22, 18, 20, 22],
                "AMZN": [15, 13, 17, 15, 15, 13, 15, 15, 13, 17, 15, 13],
                "Cash": [10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10],
            },
            index=dates,
        )

        return df

    def test_create_asset_allocation_chart_returns_figure(self, sample_allocation_df):
        """Test that create_asset_allocation_chart returns a Plotly Figure."""
        from app.dashboard.components.charts import create_asset_allocation_chart

        fig = create_asset_allocation_chart(sample_allocation_df)
        assert isinstance(fig, go.Figure)

    def test_allocation_chart_has_traces_for_all_assets(self, sample_allocation_df):
        """Test that the chart has a trace for each asset."""
        from app.dashboard.components.charts import create_asset_allocation_chart

        fig = create_asset_allocation_chart(sample_allocation_df)

        trace_names = [trace.name for trace in fig.data]
        for asset in sample_allocation_df.columns:
            assert asset in trace_names

    def test_allocation_chart_uses_stack_group(self, sample_allocation_df):
        """Test that traces use stackgroup for stacking."""
        from app.dashboard.components.charts import create_asset_allocation_chart

        fig = create_asset_allocation_chart(sample_allocation_df)

        for trace in fig.data:
            assert trace.stackgroup == "one"


class TestCombinedChart:
    """Tests for combined equity and drawdown chart."""

    @pytest.fixture
    def sample_data(self):
        """Create sample data for combined chart."""
        dates = pd.date_range(start="2020-01-01", periods=100, freq="B")
        np.random.seed(42)

        # Equity
        returns = np.random.normal(0.0005, 0.02, len(dates))
        equity = 100000 * np.exp(np.cumsum(returns))
        equity_series = pd.Series(equity, index=dates)

        # Drawdown
        running_max = equity_series.expanding().max()
        drawdown = ((equity_series - running_max) / running_max) * 100

        return equity_series, drawdown

    def test_create_combined_chart_returns_figure(self, sample_data):
        """Test that create_combined_chart returns a Plotly Figure."""
        from app.dashboard.components.charts import create_combined_chart

        equity_series, drawdown_series = sample_data
        fig = create_combined_chart(equity_series, drawdown_series)
        assert isinstance(fig, go.Figure)

    def test_combined_chart_has_two_traces(self, sample_data):
        """Test that the combined chart has traces for both equity and drawdown."""
        from app.dashboard.components.charts import create_combined_chart

        equity_series, drawdown_series = sample_data
        fig = create_combined_chart(equity_series, drawdown_series)

        assert len(fig.data) == 2
