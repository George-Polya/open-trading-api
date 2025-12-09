"""
Unit tests for Dash application initialization and layout.

Tests that the Dash app is properly configured and can be mounted
onto FastAPI.
"""

import pytest
from unittest.mock import patch, MagicMock


class TestDashAppCreation:
    """Tests for Dash application factory."""

    def test_create_dash_app_returns_dash_instance(self):
        """Test that create_dash_app returns a Dash application."""
        from app.dashboard.app import create_dash_app
        import dash

        app = create_dash_app()
        assert isinstance(app, dash.Dash)

    def test_dash_app_has_correct_title(self):
        """Test that the app has the correct title."""
        from app.dashboard.app import create_dash_app, APP_TITLE

        app = create_dash_app()
        assert app.title == APP_TITLE

    def test_dash_app_has_bootstrap_stylesheet(self):
        """Test that Bootstrap stylesheet is included."""
        from app.dashboard.app import create_dash_app
        import dash_bootstrap_components as dbc

        app = create_dash_app()

        # Check external stylesheets contain Bootstrap
        stylesheets = app.config.external_stylesheets
        assert dbc.themes.BOOTSTRAP in stylesheets

    def test_dash_app_requests_pathname_prefix(self):
        """Test that the requests pathname prefix is set correctly."""
        from app.dashboard.app import create_dash_app

        custom_prefix = "/test-dashboard/"
        app = create_dash_app(requests_pathname_prefix=custom_prefix)

        assert app.config.requests_pathname_prefix == custom_prefix

    def test_dash_app_suppress_callback_exceptions(self):
        """Test that callback exceptions are suppressed for dynamic content."""
        from app.dashboard.app import create_dash_app

        app = create_dash_app()
        assert app.config.suppress_callback_exceptions is True


class TestDashAppLayout:
    """Tests for Dash application layout."""

    def test_create_layout_returns_container(self):
        """Test that create_layout returns a Bootstrap Container."""
        from app.dashboard.layout import create_layout
        import dash_bootstrap_components as dbc

        layout = create_layout()
        assert isinstance(layout, dbc.Container)

    def test_layout_has_stores(self):
        """Test that the layout includes data stores."""
        from app.dashboard.layout import create_layout
        from dash import dcc

        layout = create_layout()

        # Find stores in layout
        store_ids = ["store-generated-code", "store-job-id", "store-job-status", "store-results"]

        for store_id in store_ids:
            found = _find_component_by_type_and_id(layout, dcc.Store, store_id)
            assert found is not None, f"Store '{store_id}' not found in layout"

    def test_layout_has_interval_component(self):
        """Test that the layout includes an interval component for polling."""
        from app.dashboard.layout import create_layout
        from dash import dcc

        layout = create_layout()

        interval = _find_component_by_type_and_id(layout, dcc.Interval, "interval-polling")
        assert interval is not None

    def test_layout_has_action_buttons(self):
        """Test that the layout includes generate and execute buttons."""
        from app.dashboard.layout import create_layout
        import dash_bootstrap_components as dbc

        layout = create_layout()

        generate_btn = _find_component_by_id(layout, "btn-generate")
        execute_btn = _find_component_by_id(layout, "btn-execute")

        assert generate_btn is not None, "Generate button not found"
        assert execute_btn is not None, "Execute button not found"


class TestFastAPIIntegration:
    """Tests for FastAPI integration."""

    def test_mount_dashboard_imports_correctly(self):
        """Test that mount_dashboard can be imported."""
        from app.main import mount_dashboard

        assert callable(mount_dashboard)

    def test_app_has_dashboard_route(self):
        """Test that the FastAPI app has the dashboard mounted."""
        from app.main import app

        # Check routes for dashboard mount
        routes = [route.path for route in app.routes]

        # The dashboard is mounted at /dashboard
        assert any("/dashboard" in route for route in routes)


class TestCallbackValidation:
    """Tests for callback input validation."""

    def test_validate_inputs_empty_strategy(self):
        """Test validation rejects empty strategy."""
        from app.dashboard.callbacks import _validate_inputs

        error = _validate_inputs(
            strategy="",
            start_date="2020-01-01",
            end_date="2023-01-01",
            initial_capital=100000,
            benchmarks="SPY",
        )

        assert error is not None
        assert "strategy" in error.lower()

    def test_validate_inputs_missing_dates(self):
        """Test validation rejects missing dates."""
        from app.dashboard.callbacks import _validate_inputs

        error = _validate_inputs(
            strategy="A valid strategy description for testing",
            start_date=None,
            end_date="2023-01-01",
            initial_capital=100000,
            benchmarks="SPY",
        )

        assert error is not None
        assert "date" in error.lower()

    def test_validate_inputs_invalid_capital(self):
        """Test validation rejects invalid capital."""
        from app.dashboard.callbacks import _validate_inputs

        error = _validate_inputs(
            strategy="A valid strategy description for testing",
            start_date="2020-01-01",
            end_date="2023-01-01",
            initial_capital=0,
            benchmarks="SPY",
        )

        assert error is not None
        assert "capital" in error.lower()

    def test_validate_inputs_missing_benchmarks(self):
        """Test validation rejects missing benchmarks."""
        from app.dashboard.callbacks import _validate_inputs

        error = _validate_inputs(
            strategy="A valid strategy description for testing",
            start_date="2020-01-01",
            end_date="2023-01-01",
            initial_capital=100000,
            benchmarks="",
        )

        assert error is not None
        assert "benchmark" in error.lower()

    def test_validate_inputs_valid(self):
        """Test validation passes for valid inputs."""
        from app.dashboard.callbacks import _validate_inputs

        error = _validate_inputs(
            strategy="A valid strategy description for testing purposes",
            start_date="2020-01-01",
            end_date="2023-01-01",
            initial_capital=100000,
            benchmarks="SPY, QQQ",
        )

        assert error is None


def _find_component_by_id(component, target_id: str):
    """Recursively find a component by ID."""
    if hasattr(component, "id") and component.id == target_id:
        return component

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


def _find_component_by_type_and_id(component, component_type, target_id: str):
    """Recursively find a component by type and ID."""
    if isinstance(component, component_type) and hasattr(component, "id") and component.id == target_id:
        return component

    if hasattr(component, "children"):
        children = component.children
        if children is None:
            return None

        if not isinstance(children, list):
            children = [children]

        for child in children:
            if child is not None:
                result = _find_component_by_type_and_id(child, component_type, target_id)
                if result is not None:
                    return result

    return None
