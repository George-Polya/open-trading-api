"""
Unit tests for dashboard UI components.

Tests that component functions return valid Dash component trees
with correct IDs and default values.
"""

import pytest
from dash import html
import dash_bootstrap_components as dbc


class TestStrategyInputCard:
    """Tests for StrategyInputCard component."""

    def test_create_strategy_input_card_returns_card(self):
        """Test that create_strategy_input_card returns a dbc.Card."""
        from app.dashboard.components.inputs import create_strategy_input_card

        card = create_strategy_input_card()
        assert isinstance(card, dbc.Card)

    def test_strategy_input_card_has_textarea(self):
        """Test that the card contains a textarea with correct ID."""
        from app.dashboard.components.inputs import create_strategy_input_card

        card = create_strategy_input_card()

        # Find textarea in component tree
        textarea_found = _find_component_by_id(card, "textarea-strategy")
        assert textarea_found is not None

    def test_strategy_input_card_has_character_counter(self):
        """Test that the card contains a character counter."""
        from app.dashboard.components.inputs import create_strategy_input_card

        card = create_strategy_input_card()

        counter_found = _find_component_by_id(card, "text-strategy-counter")
        assert counter_found is not None


class TestBacktestConfigCard:
    """Tests for BacktestConfigCard component."""

    def test_create_backtest_config_card_returns_card(self):
        """Test that create_backtest_config_card returns a dbc.Card."""
        from app.dashboard.components.inputs import create_backtest_config_card

        card = create_backtest_config_card()
        assert isinstance(card, dbc.Card)

    def test_config_card_has_date_picker(self):
        """Test that the card contains a date picker range."""
        from app.dashboard.components.inputs import create_backtest_config_card

        card = create_backtest_config_card()

        datepicker_found = _find_component_by_id(card, "datepicker-range")
        assert datepicker_found is not None

    def test_config_card_has_capital_input(self):
        """Test that the card contains a capital input."""
        from app.dashboard.components.inputs import create_backtest_config_card

        card = create_backtest_config_card()

        capital_found = _find_component_by_id(card, "input-capital")
        assert capital_found is not None

    def test_config_card_has_benchmark_input(self):
        """Test that the card contains a benchmark input."""
        from app.dashboard.components.inputs import create_backtest_config_card

        card = create_backtest_config_card()

        benchmark_found = _find_component_by_id(card, "input-benchmarks")
        assert benchmark_found is not None

    def test_config_card_has_dividend_checkbox(self):
        """Test that the card contains a dividend reinvestment checkbox."""
        from app.dashboard.components.inputs import create_backtest_config_card

        card = create_backtest_config_card()

        checkbox_found = _find_component_by_id(card, "checkbox-dividend")
        assert checkbox_found is not None


class TestCodeViewerCard:
    """Tests for CodeViewerCard component."""

    def test_create_code_viewer_card_returns_card(self):
        """Test that create_code_viewer_card returns a dbc.Card."""
        from app.dashboard.components.code_view import create_code_viewer_card

        card = create_code_viewer_card()
        assert isinstance(card, dbc.Card)

    def test_code_viewer_has_markdown_component(self):
        """Test that the card contains a markdown component."""
        from app.dashboard.components.code_view import create_code_viewer_card

        card = create_code_viewer_card()

        markdown_found = _find_component_by_id(card, "markdown-code")
        assert markdown_found is not None

    def test_code_viewer_has_copy_button(self):
        """Test that the card contains a copy button."""
        from app.dashboard.components.code_view import create_code_viewer_card

        card = create_code_viewer_card()

        copy_btn_found = _find_component_by_id(card, "btn-copy-code")
        assert copy_btn_found is not None

    def test_format_code_for_display(self):
        """Test that code formatting adds markdown code fence."""
        from app.dashboard.components.code_view import format_code_for_display

        code = "print('hello')"
        formatted = format_code_for_display(code)

        assert formatted.startswith("```python")
        assert formatted.endswith("```")
        assert code in formatted


class TestMetricsComponents:
    """Tests for metrics display components."""

    def test_create_metric_card_returns_card(self):
        """Test that create_metric_card returns a dbc.Card."""
        from app.dashboard.components.metrics import create_metric_card

        card = create_metric_card(
            title="CAGR",
            value="12.5%",
            icon="fas fa-chart-line",
            color="success",
        )
        assert isinstance(card, dbc.Card)

    def test_create_metrics_row_returns_row(self):
        """Test that create_metrics_row returns a dbc.Row."""
        from app.dashboard.components.metrics import create_metrics_row

        row = create_metrics_row()
        assert isinstance(row, dbc.Row)

    def test_create_metrics_row_with_data(self):
        """Test that create_metrics_row handles metric data correctly."""
        from app.dashboard.components.metrics import create_metrics_row

        metrics = {
            "total_return": 25.5,
            "cagr": 12.3,
            "max_drawdown": 15.2,
            "sharpe_ratio": 1.5,
            "sortino_ratio": 2.1,
            "calmar_ratio": 0.81,
        }

        row = create_metrics_row(metrics)
        assert isinstance(row, dbc.Row)

    def test_create_results_dashboard_returns_card(self):
        """Test that create_results_dashboard returns a dbc.Card."""
        from app.dashboard.components.metrics import create_results_dashboard

        card = create_results_dashboard()
        assert isinstance(card, dbc.Card)

    def test_create_job_status_badge(self):
        """Test that create_job_status_badge returns correct badges."""
        from app.dashboard.components.metrics import create_job_status_badge

        for status in ["pending", "running", "completed", "failed"]:
            badge = create_job_status_badge(status)
            assert isinstance(badge, dbc.Badge)


def _find_component_by_id(component, target_id: str):
    """
    Recursively search for a component with the given ID.

    Args:
        component: Dash component to search.
        target_id: ID to find.

    Returns:
        The component if found, None otherwise.
    """
    if hasattr(component, "id") and component.id == target_id:
        return component

    # Check children
    if hasattr(component, "children"):
        children = component.children
        if children is None:
            return None

        if not isinstance(children, list):
            children = [children]

        for child in children:
            if child is not None:
                result = _find_component_by_id(child, target_id)
                if result is not None:
                    return result

    return None
