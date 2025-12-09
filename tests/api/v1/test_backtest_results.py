"""
Tests for backtest result retrieval and chart endpoints.

Tests cover:
- GET /api/v1/backtest/{job_id}/result (formatted results)
- GET /api/v1/backtest/{job_id}/chart/equity
- GET /api/v1/backtest/{job_id}/chart/drawdown
- GET /api/v1/backtest/{job_id}/chart/monthly-returns
"""

import pytest
from datetime import datetime, date
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
import pandas as pd
import numpy as np

from app.main import create_app
from app.models.execution import ExecutionResult, JobStatus
from app.services.execution.storage import JobNotFoundError
from app.services.result_formatter import (
    FormattedResults,
    PerformanceMetrics,
    EquityCurveData,
    DrawdownData,
    MonthlyHeatmapData,
    ChartDataPoint,
)


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    app = create_app()
    return TestClient(app)


@pytest.fixture
def sample_equity_data():
    """Generate sample equity series data."""
    dates = pd.date_range("2023-01-01", "2023-12-31", freq="D")
    # Create a growing equity curve with some volatility
    values = 100000 * (1 + np.cumsum(np.random.randn(len(dates)) * 0.01))

    return [
        {"date": date.strftime("%Y-%m-%d"), "value": float(value)}
        for date, value in zip(dates, values)
    ]


@pytest.fixture
def sample_trades_data():
    """Generate sample trades data."""
    return [
        {
            "ticker": "AAPL",
            "action": "BUY",
            "quantity": 100,
            "price": 150.0,
            "date": "2023-06-01",
            "profit": 0,
        },
        {
            "ticker": "AAPL",
            "action": "SELL",
            "quantity": 100,
            "price": 165.0,
            "date": "2023-09-01",
            "profit": 1500.0,
        },
    ]


@pytest.fixture
def sample_execution_result(sample_equity_data, sample_trades_data):
    """Create a sample ExecutionResult with backtest data."""
    return ExecutionResult(
        success=True,
        job_id="backtest-test123",
        status=JobStatus.COMPLETED,
        data={
            "equity_series": sample_equity_data,
            "trades": sample_trades_data,
            "benchmark_series": sample_equity_data[:100],  # Shorter benchmark
            "start_date": "2023-01-01",
            "end_date": "2023-12-31",
        },
        error=None,
        logs="Backtest completed successfully",
        duration_seconds=5.2,
    )


@pytest.fixture
def mock_job_manager(sample_execution_result):
    """Create a mock JobManager for testing."""
    manager = MagicMock()
    manager.get_job_result = AsyncMock(return_value=sample_execution_result)
    manager.get_job_status = AsyncMock(return_value=JobStatus.COMPLETED)
    return manager


@pytest.fixture
def mock_result_formatter():
    """Create a mock ResultFormatter for testing."""
    formatter = MagicMock()

    # Mock format_results
    formatter.format_results = MagicMock(
        return_value=FormattedResults(
            metrics=PerformanceMetrics(
                total_return=25.5,
                cagr=23.2,
                max_drawdown=12.3,
                sharpe_ratio=1.85,
                sortino_ratio=2.15,
                calmar_ratio=1.89,
                volatility=15.2,
                total_trades=10,
                winning_trades=7,
                losing_trades=3,
                win_rate=70.0,
            ),
            equity_curve=EquityCurveData(
                strategy=[
                    ChartDataPoint(date="2023-01-01", value=100000.0),
                    ChartDataPoint(date="2023-12-31", value=125500.0),
                ],
                benchmark=[
                    ChartDataPoint(date="2023-01-01", value=100000.0),
                    ChartDataPoint(date="2023-12-31", value=110000.0),
                ],
                log_scale=True,
            ),
            drawdown=DrawdownData(
                data=[
                    ChartDataPoint(date="2023-01-01", value=0.0),
                    ChartDataPoint(date="2023-06-15", value=-12.3),
                    ChartDataPoint(date="2023-12-31", value=-2.1),
                ]
            ),
            monthly_heatmap=MonthlyHeatmapData(
                years=[2023],
                returns=[[2.5, 1.2, -0.5, 3.1, 2.0, 1.8, 0.9, -1.2, 2.3, 1.5, 0.8, 1.9]],
            ),
        )
    )

    # Mock format_for_chart
    formatter.format_for_chart = MagicMock(
        return_value=EquityCurveData(
            strategy=[
                ChartDataPoint(date="2023-01-01", value=5.0),
                ChartDataPoint(date="2023-12-31", value=5.1),
            ],
            benchmark=[
                ChartDataPoint(date="2023-01-01", value=5.0),
                ChartDataPoint(date="2023-12-31", value=5.04),
            ],
            log_scale=True,
        )
    )

    # Mock generate_drawdown_series
    mock_drawdown = pd.Series(
        [0.0, -5.2, -12.3, -8.1, -2.1],
        index=pd.to_datetime([
            "2023-01-01",
            "2023-04-01",
            "2023-06-15",
            "2023-09-01",
            "2023-12-31",
        ]),
    )
    formatter.generate_drawdown_series = MagicMock(return_value=mock_drawdown)

    # Mock generate_monthly_heatmap
    formatter.generate_monthly_heatmap = MagicMock(
        return_value=MonthlyHeatmapData(
            years=[2023],
            returns=[[2.5, 1.2, -0.5, 3.1, 2.0, 1.8, 0.9, -1.2, 2.3, 1.5, 0.8, 1.9]],
        )
    )

    return formatter


class TestGetFormattedBacktestResult:
    """Tests for GET /api/v1/backtest/{job_id}/result endpoint."""

    def test_get_formatted_result_success(self, client, mock_job_manager, mock_result_formatter):
        """Test successful retrieval of formatted backtest results."""
        with patch(
            "app.core.container.Container.get_job_manager",
            return_value=mock_job_manager,
        ), patch(
            "app.core.container.Container.get_result_formatter",
            return_value=mock_result_formatter,
        ):
            response = client.get("/api/v1/backtest/backtest-test123/result")

            assert response.status_code == 200
            data = response.json()

            # Verify response structure
            assert data["job_id"] == "backtest-test123"
            assert data["status"] == "completed"
            assert "metrics" in data
            assert "equity_curve" in data
            assert "drawdown" in data
            assert "monthly_heatmap" in data
            assert "trades" in data
            assert "logs" in data

            # Verify metrics
            metrics = data["metrics"]
            assert metrics["total_return"] == 25.5
            assert metrics["cagr"] == 23.2
            assert metrics["sharpe_ratio"] == 1.85
            assert metrics["total_trades"] == 10
            assert metrics["win_rate"] == 70.0

            # Verify job manager was called
            mock_job_manager.get_job_result.assert_called_once_with("backtest-test123")

            # Verify result formatter was called
            mock_result_formatter.format_results.assert_called_once()

    def test_get_formatted_result_job_not_found(self, client, mock_job_manager, mock_result_formatter):
        """Test 404 when job is not found."""
        mock_job_manager.get_job_result.side_effect = JobNotFoundError("Job not found")

        with patch(
            "app.core.container.Container.get_job_manager",
            return_value=mock_job_manager,
        ), patch(
            "app.core.container.Container.get_result_formatter",
            return_value=mock_result_formatter,
        ):
            response = client.get("/api/v1/backtest/nonexistent-job/result")

            assert response.status_code == 404
            assert "not found" in response.json()["detail"].lower()

    def test_get_formatted_result_job_not_completed(self, client, mock_job_manager, mock_result_formatter):
        """Test 409 when job is not completed yet."""
        incomplete_result = ExecutionResult(
            success=False,
            job_id="backtest-running",
            status=JobStatus.RUNNING,
            data=None,
            error=None,
            logs="Still running...",
            duration_seconds=None,
        )
        mock_job_manager.get_job_result.return_value = incomplete_result

        with patch(
            "app.core.container.Container.get_job_manager",
            return_value=mock_job_manager,
        ), patch(
            "app.core.container.Container.get_result_formatter",
            return_value=mock_result_formatter,
        ):
            response = client.get("/api/v1/backtest/backtest-running/result")

            assert response.status_code == 409
            assert "not completed" in response.json()["detail"].lower()

    def test_get_formatted_result_no_data(self, client, mock_job_manager, mock_result_formatter):
        """Test 500 when job completed but has no data."""
        failed_result = ExecutionResult(
            success=False,
            job_id="backtest-failed",
            status=JobStatus.COMPLETED,
            data=None,
            error="Execution failed",
            logs="Error logs",
            duration_seconds=2.5,
        )
        mock_job_manager.get_job_result.return_value = failed_result

        with patch(
            "app.core.container.Container.get_job_manager",
            return_value=mock_job_manager,
        ), patch(
            "app.core.container.Container.get_result_formatter",
            return_value=mock_result_formatter,
        ):
            response = client.get("/api/v1/backtest/backtest-failed/result")

            assert response.status_code == 500
            assert "no result data" in response.json()["detail"].lower()


class TestGetEquityChart:
    """Tests for GET /api/v1/backtest/{job_id}/chart/equity endpoint."""

    def test_get_equity_chart_success(self, client, mock_job_manager, mock_result_formatter):
        """Test successful retrieval of equity chart data."""
        with patch(
            "app.core.container.Container.get_job_manager",
            return_value=mock_job_manager,
        ), patch(
            "app.core.container.Container.get_result_formatter",
            return_value=mock_result_formatter,
        ):
            response = client.get("/api/v1/backtest/backtest-test123/chart/equity")

            assert response.status_code == 200
            data = response.json()

            assert data["job_id"] == "backtest-test123"
            assert "strategy" in data
            assert "benchmark" in data
            assert data["log_scale"] is True

            # Verify strategy data points
            assert len(data["strategy"]) > 0
            assert "date" in data["strategy"][0]
            assert "value" in data["strategy"][0]

            # Verify formatter was called
            mock_result_formatter.format_for_chart.assert_called_once()

    def test_get_equity_chart_without_log_scale(self, client, mock_job_manager, mock_result_formatter):
        """Test equity chart without log scale."""
        mock_result_formatter.format_for_chart.return_value.log_scale = False

        with patch(
            "app.core.container.Container.get_job_manager",
            return_value=mock_job_manager,
        ), patch(
            "app.core.container.Container.get_result_formatter",
            return_value=mock_result_formatter,
        ):
            response = client.get(
                "/api/v1/backtest/backtest-test123/chart/equity?log_scale=false"
            )

            assert response.status_code == 200
            data = response.json()
            assert data["log_scale"] is False

    def test_get_equity_chart_without_benchmark(self, client, mock_job_manager, mock_result_formatter):
        """Test equity chart without benchmark data."""
        with patch(
            "app.core.container.Container.get_job_manager",
            return_value=mock_job_manager,
        ), patch(
            "app.core.container.Container.get_result_formatter",
            return_value=mock_result_formatter,
        ):
            response = client.get(
                "/api/v1/backtest/backtest-test123/chart/equity?include_benchmark=false"
            )

            assert response.status_code == 200
            data = response.json()
            # Benchmark should still be in response but could be None
            assert "benchmark" in data

    def test_get_equity_chart_job_not_completed(self, client, mock_job_manager, mock_result_formatter):
        """Test 409 when job is not completed."""
        incomplete_result = ExecutionResult(
            success=False,
            job_id="backtest-pending",
            status=JobStatus.PENDING,
            data=None,
            error=None,
            logs="",
            duration_seconds=None,
        )
        mock_job_manager.get_job_result.return_value = incomplete_result

        with patch(
            "app.core.container.Container.get_job_manager",
            return_value=mock_job_manager,
        ), patch(
            "app.core.container.Container.get_result_formatter",
            return_value=mock_result_formatter,
        ):
            response = client.get("/api/v1/backtest/backtest-pending/chart/equity")

            assert response.status_code == 409
            assert "not completed" in response.json()["detail"].lower()


class TestGetDrawdownChart:
    """Tests for GET /api/v1/backtest/{job_id}/chart/drawdown endpoint."""

    def test_get_drawdown_chart_success(self, client, mock_job_manager, mock_result_formatter):
        """Test successful retrieval of drawdown chart data."""
        with patch(
            "app.core.container.Container.get_job_manager",
            return_value=mock_job_manager,
        ), patch(
            "app.core.container.Container.get_result_formatter",
            return_value=mock_result_formatter,
        ):
            response = client.get("/api/v1/backtest/backtest-test123/chart/drawdown")

            assert response.status_code == 200
            data = response.json()

            assert data["job_id"] == "backtest-test123"
            assert "data" in data
            assert len(data["data"]) > 0

            # Verify data point structure
            point = data["data"][0]
            assert "date" in point
            assert "value" in point
            assert point["value"] <= 0  # Drawdowns should be negative or zero

            # Verify formatter was called
            mock_result_formatter.generate_drawdown_series.assert_called_once()

    def test_get_drawdown_chart_job_not_found(self, client, mock_job_manager, mock_result_formatter):
        """Test 404 when job is not found."""
        mock_job_manager.get_job_result.side_effect = JobNotFoundError("Job not found")

        with patch(
            "app.core.container.Container.get_job_manager",
            return_value=mock_job_manager,
        ), patch(
            "app.core.container.Container.get_result_formatter",
            return_value=mock_result_formatter,
        ):
            response = client.get("/api/v1/backtest/nonexistent/chart/drawdown")

            assert response.status_code == 404


class TestGetMonthlyReturns:
    """Tests for GET /api/v1/backtest/{job_id}/chart/monthly-returns endpoint."""

    def test_get_monthly_returns_success(self, client, mock_job_manager, mock_result_formatter):
        """Test successful retrieval of monthly returns heatmap data."""
        with patch(
            "app.core.container.Container.get_job_manager",
            return_value=mock_job_manager,
        ), patch(
            "app.core.container.Container.get_result_formatter",
            return_value=mock_result_formatter,
        ):
            response = client.get("/api/v1/backtest/backtest-test123/chart/monthly-returns")

            assert response.status_code == 200
            data = response.json()

            assert data["job_id"] == "backtest-test123"
            assert "years" in data
            assert "months" in data
            assert "returns" in data

            # Verify structure
            assert len(data["years"]) > 0
            assert len(data["months"]) == 12
            assert len(data["returns"]) == len(data["years"])
            assert len(data["returns"][0]) == 12  # 12 months per year

            # Verify formatter was called
            mock_result_formatter.generate_monthly_heatmap.assert_called_once()

    def test_get_monthly_returns_job_not_completed(self, client, mock_job_manager, mock_result_formatter):
        """Test 409 when job is not completed."""
        incomplete_result = ExecutionResult(
            success=False,
            job_id="backtest-timeout",
            status=JobStatus.TIMEOUT,
            data=None,
            error="Execution timed out",
            logs="Timeout logs",
            duration_seconds=600.0,
        )
        mock_job_manager.get_job_result.return_value = incomplete_result

        with patch(
            "app.core.container.Container.get_job_manager",
            return_value=mock_job_manager,
        ), patch(
            "app.core.container.Container.get_result_formatter",
            return_value=mock_result_formatter,
        ):
            response = client.get("/api/v1/backtest/backtest-timeout/chart/monthly-returns")

            assert response.status_code == 409
            assert "not completed" in response.json()["detail"].lower()

    def test_get_monthly_returns_missing_equity_data(self, client, mock_job_manager, mock_result_formatter):
        """Test 500 when equity series is missing from result data."""
        bad_result = ExecutionResult(
            success=True,
            job_id="backtest-bad",
            status=JobStatus.COMPLETED,
            data={"trades": []},  # Missing equity_series
            error=None,
            logs="Completed",
            duration_seconds=5.0,
        )
        mock_job_manager.get_job_result.return_value = bad_result

        with patch(
            "app.core.container.Container.get_job_manager",
            return_value=mock_job_manager,
        ), patch(
            "app.core.container.Container.get_result_formatter",
            return_value=mock_result_formatter,
        ):
            response = client.get("/api/v1/backtest/backtest-bad/chart/monthly-returns")

            assert response.status_code == 500
            assert "missing equity_series" in response.json()["detail"].lower()


class TestChartEndpointsIntegration:
    """Integration tests for chart endpoints with real data transformations."""

    def test_log_scale_transformation(self, client, mock_job_manager):
        """Test that log scale transformation is applied correctly."""
        # Create real ResultFormatter instead of mock
        from app.services.result_formatter import create_result_formatter

        real_formatter = create_result_formatter()

        with patch(
            "app.core.container.Container.get_job_manager",
            return_value=mock_job_manager,
        ), patch(
            "app.core.container.Container.get_result_formatter",
            return_value=real_formatter,
        ):
            response = client.get(
                "/api/v1/backtest/backtest-test123/chart/equity?log_scale=true"
            )

            assert response.status_code == 200
            data = response.json()

            # With log scale, values should be logarithmic
            assert data["log_scale"] is True
            strategy_values = [point["value"] for point in data["strategy"]]

            # Log-transformed values should be much smaller than original
            # (original ~100000, log10(100000) ≈ 5)
            assert all(val < 10 for val in strategy_values)

    def test_drawdown_values_are_negative(self, client, mock_job_manager):
        """Test that drawdown values are properly negative percentages."""
        from app.services.result_formatter import create_result_formatter

        real_formatter = create_result_formatter()

        with patch(
            "app.core.container.Container.get_job_manager",
            return_value=mock_job_manager,
        ), patch(
            "app.core.container.Container.get_result_formatter",
            return_value=real_formatter,
        ):
            response = client.get("/api/v1/backtest/backtest-test123/chart/drawdown")

            assert response.status_code == 200
            data = response.json()

            # All drawdown values should be <= 0
            drawdown_values = [point["value"] for point in data["data"]]
            assert all(val <= 0 for val in drawdown_values)
