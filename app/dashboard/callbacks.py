"""
Dash Callbacks for Dashboard Interactivity.

Implements callbacks for:
- Form validation
- API interaction (generate, execute)
- Result polling
- Chart updates
"""

import json
import logging
from datetime import datetime
from typing import Any

import dash
import dash_bootstrap_components as dbc
import pandas as pd
import requests
from dash import Input, Output, State, callback_context, html, no_update
from dash.exceptions import PreventUpdate

from app.dashboard.components.charts import (
    create_drawdown_chart,
    create_equity_chart,
    create_monthly_heatmap,
)
from app.dashboard.components.code_view import (
    create_model_info_badge,
    create_strategy_summary_alert,
    format_code_for_display,
)
from app.dashboard.components.metrics import (
    _create_primary_metrics_row,
    _create_secondary_metrics_row,
    create_job_status_badge,
    create_metrics_row,
    create_trade_summary_table,
)
from app.dashboard.constants import VALIDATION

logger = logging.getLogger(__name__)

# API base URL (configurable via environment)
API_BASE_URL = "http://localhost:8000/api/v1"


def register_callbacks(app: dash.Dash) -> None:
    """
    Register all callbacks for the Dash application.

    Args:
        app: Dash application instance.
    """
    _register_strategy_counter_callback(app)
    _register_generate_callback(app)
    _register_execute_callback(app)
    _register_polling_callback(app)
    _register_results_callback(app)
    _register_chart_callbacks(app)
    _register_toggle_callbacks(app)
    _register_validation_callbacks(app)


def _register_strategy_counter_callback(app: dash.Dash) -> None:
    """Register callback for strategy text character counter."""

    @app.callback(
        Output("text-strategy-counter", "children"),
        Input("textarea-strategy", "value"),
    )
    def update_character_count(strategy_text: str | None) -> str:
        """Update the character counter for strategy input."""
        count = len(strategy_text) if strategy_text else 0
        return f"{count:,} / 10,000 characters"


def _register_generate_callback(app: dash.Dash) -> None:
    """Register callback for code generation."""

    @app.callback(
        [
            Output("store-generated-code", "data"),
            Output("markdown-code", "children"),
            Output("div-model-info", "children"),
            Output("div-model-info", "style"),
            Output("div-strategy-summary", "children"),
            Output("div-strategy-summary", "style"),
            Output("div-generation-info", "children"),
            Output("div-generation-info", "style"),
            Output("btn-execute", "disabled"),
            Output("btn-copy-code", "disabled"),
            Output("div-status-message", "children"),
            Output("btn-generate", "disabled"),
            Output("icon-generate", "className"),
        ],
        Input("btn-generate", "n_clicks"),
        [
            State("textarea-strategy", "value"),
            State("datepicker-range", "start_date"),
            State("datepicker-range", "end_date"),
            State("input-capital", "value"),
            State("input-benchmarks", "value"),
            State("select-contribution-freq", "value"),
            State("input-contribution-amount", "value"),
            State("input-trading-fee", "value"),
            State("input-slippage", "value"),
            State("checkbox-dividend", "value"),
            State("checkbox-web-search", "value"),
        ],
        prevent_initial_call=True,
    )
    def generate_code(
        n_clicks: int,
        strategy: str | None,
        start_date: str | None,
        end_date: str | None,
        initial_capital: float | None,
        benchmarks: str | None,
        contribution_freq: str,
        contribution_amount: float,
        trading_fee: float,
        slippage: float,
        dividend_reinvest: bool,
        web_search_enabled: bool,
    ) -> tuple:
        """Handle code generation button click."""
        if not n_clicks:
            raise PreventUpdate

        # Validate inputs
        validation_error = _validate_inputs(
            strategy, start_date, end_date, initial_capital, benchmarks
        )
        if validation_error:
            return (
                no_update,  # store-generated-code
                no_update,  # markdown-code
                no_update,  # div-model-info children
                no_update,  # div-model-info style
                no_update,  # div-strategy-summary children
                no_update,  # div-strategy-summary style
                no_update,  # div-generation-info children
                no_update,  # div-generation-info style
                True,  # btn-execute disabled
                True,  # btn-copy-code disabled
                dbc.Alert(validation_error, color="danger"),  # div-status-message
                False,  # btn-generate disabled (re-enable)
                "fas fa-code me-2",  # icon-generate className (restore)
            )

        # Build request payload
        benchmark_list = [b.strip().upper() for b in benchmarks.split(",") if b.strip()]

        payload = {
            "strategy": strategy,
            "params": {
                "start_date": start_date,
                "end_date": end_date,
                "initial_capital": float(initial_capital),
                "benchmarks": benchmark_list,
                "contribution": {
                    "frequency": contribution_freq,
                    "amount": float(contribution_amount) if contribution_amount is not None else 0.0,
                },
                "fees": {
                    "trading_fee_percent": float(trading_fee) if trading_fee is not None else 0.015,
                    "slippage_percent": float(slippage) if slippage is not None else 0.01,
                },
                "dividend_reinvestment": dividend_reinvest,
            },
            # LLM settings override (optional, defaults from config.yaml)
            "llm_settings": {
                "web_search_enabled": bool(web_search_enabled),
            },
        }

        try:
            # Call generate API
            response = requests.post(
                f"{API_BASE_URL}/backtest/generate",
                json=payload,
                timeout=300,  # 5 minute timeout for code generation (LLM can be slow)
            )

            if response.status_code == 200:
                data = response.json()
                generated = data.get("generated_code", {})
                code = generated.get("code", "")
                summary = generated.get("strategy_summary", "")
                model_info = generated.get("model_info", {})
                gen_time = data.get("generation_time_seconds", 0)
                tickers = data.get("tickers_found", [])

                # Create model info badge
                model_badge = create_model_info_badge(
                    model_info.get("provider", "unknown"),
                    model_info.get("model_id", "unknown"),
                )

                # Create strategy summary
                summary_alert = create_strategy_summary_alert(summary)

                # Create generation info
                gen_info = html.Span(
                    [
                        html.I(className="fas fa-clock me-1"),
                        f"Generated in {gen_time:.1f}s | ",
                        html.I(className="fas fa-tag me-1"),
                        f"Tickers: {', '.join(tickers)}",
                    ]
                )

                return (
                    {"code": code, "model_info": model_info, "tickers": tickers},  # store
                    format_code_for_display(code),  # markdown
                    model_badge,  # model info
                    {"display": "block"},  # model info style
                    summary_alert,  # summary
                    {"display": "block"},  # summary style
                    gen_info,  # gen info
                    {"display": "block"},  # gen info style
                    False,  # execute button enabled
                    False,  # copy button enabled
                    dbc.Alert(
                        [
                            html.I(className="fas fa-check-circle me-2"),
                            "Code generated successfully!",
                        ],
                        color="success",
                    ),
                    False,  # btn-generate disabled (re-enable)
                    "fas fa-code me-2",  # icon-generate className (restore)
                )

            else:
                error_detail = response.json().get("detail", "Unknown error")
                return (
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    True,
                    True,
                    dbc.Alert(
                        [
                            html.I(className="fas fa-exclamation-circle me-2"),
                            f"Generation failed: {error_detail}",
                        ],
                        color="danger",
                    ),
                    False,  # btn-generate disabled (re-enable)
                    "fas fa-code me-2",  # icon-generate className (restore)
                )

        except requests.exceptions.Timeout:
            return (
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                True,
                True,
                dbc.Alert(
                    [
                        html.I(className="fas fa-clock me-2"),
                        "Request timed out. Please try again.",
                    ],
                    color="warning",
                ),
                False,  # btn-generate disabled (re-enable)
                "fas fa-code me-2",  # icon-generate className (restore)
            )
        except requests.exceptions.RequestException as e:
            logger.exception(f"API request failed: {e}")
            return (
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                True,
                True,
                dbc.Alert(
                    [
                        html.I(className="fas fa-exclamation-triangle me-2"),
                        f"API connection error: {str(e)}",
                    ],
                    color="danger",
                ),
                False,  # btn-generate disabled (re-enable)
                "fas fa-code me-2",  # icon-generate className (restore)
            )


def _register_execute_callback(app: dash.Dash) -> None:
    """Register callback for backtest execution."""

    @app.callback(
        [
            Output("store-job-id", "data"),
            Output("store-job-status", "data"),
            Output("interval-polling", "disabled"),
            Output("div-status-message", "children", allow_duplicate=True),
        ],
        Input("btn-execute", "n_clicks"),
        [
            State("store-generated-code", "data"),
            State("tabs-code", "active_tab"),
            State("textarea-custom-code", "value"),
            State("datepicker-range", "start_date"),
            State("datepicker-range", "end_date"),
            State("input-capital", "value"),
            State("input-benchmarks", "value"),
            State("select-contribution-freq", "value"),
            State("input-contribution-amount", "value"),
            State("input-trading-fee", "value"),
            State("input-slippage", "value"),
            State("checkbox-dividend", "value"),
        ],
        prevent_initial_call=True,
    )
    def execute_backtest(
        n_clicks: int,
        generated_code_data: dict | None,
        active_tab: str,
        custom_code: str | None,
        start_date: str,
        end_date: str,
        initial_capital: float,
        benchmarks: str,
        contribution_freq: str,
        contribution_amount: float,
        trading_fee: float,
        slippage: float,
        dividend_reinvest: bool,
    ) -> tuple:
        """Handle backtest execution button click."""
        if not n_clicks:
            raise PreventUpdate

        # Determine which code to use based on active tab
        if active_tab == "tab-custom" and custom_code and custom_code.strip():
            # Use custom code from user
            code = custom_code.strip()
            # Extract tickers from benchmarks for custom code
            tickers = [b.strip().upper() for b in benchmarks.split(",") if b.strip()]
        elif generated_code_data:
            # Use generated code
            code = generated_code_data.get("code", "")
            tickers = generated_code_data.get("tickers", [])
        else:
            return (
                no_update,
                no_update,
                True,  # Keep polling disabled
                dbc.Alert(
                    "No code to execute. Generate code or enter custom code in the 'Custom Code' tab.",
                    color="warning"
                ),
            )

        benchmark_list = [b.strip().upper() for b in benchmarks.split(",") if b.strip()]

        payload = {
            "code": code,
            "params": {
                # Used by the execution engine to pre-fetch CSVs into the workspace
                "tickers": tickers,
                "start_date": start_date,
                "end_date": end_date,
                "initial_capital": float(initial_capital),
                "benchmarks": benchmark_list,
                "contribution": {
                    "frequency": contribution_freq,
                    "amount": float(contribution_amount) if contribution_amount is not None else 0.0,
                },
                "fees": {
                    "trading_fee_percent": float(trading_fee) if trading_fee is not None else 0.015,
                    "slippage_percent": float(slippage) if slippage is not None else 0.01,
                },
                "dividend_reinvestment": bool(dividend_reinvest),
            },
            "async_mode": True,
        }

        try:
            response = requests.post(
                f"{API_BASE_URL}/backtest/execute",
                json=payload,
                timeout=30,
            )

            if response.status_code in (200, 202):
                data = response.json()
                job_id = data.get("job_id", "")
                status = data.get("status", "pending")

                return (
                    job_id,
                    status,
                    False,  # Enable polling
                    dbc.Alert(
                        [
                            html.I(className="fas fa-spinner fa-spin me-2"),
                            f"Backtest submitted (Job ID: {job_id[:8]}...)",
                        ],
                        color="info",
                    ),
                )
            else:
                error_detail = response.json().get("detail", "Unknown error")
                return (
                    no_update,
                    no_update,
                    True,
                    dbc.Alert(f"Execution failed: {error_detail}", color="danger"),
                )

        except requests.exceptions.RequestException as e:
            logger.exception(f"Execute API request failed: {e}")
            return (
                no_update,
                no_update,
                True,
                dbc.Alert(f"API error: {str(e)}", color="danger"),
            )


def _register_polling_callback(app: dash.Dash) -> None:
    """Register callback for polling job status."""

    @app.callback(
        [
            Output("store-job-status", "data", allow_duplicate=True),
            Output("store-results", "data"),
            Output("interval-polling", "disabled", allow_duplicate=True),
            Output("div-status-message", "children", allow_duplicate=True),
        ],
        Input("interval-polling", "n_intervals"),
        State("store-job-id", "data"),
        prevent_initial_call=True,
    )
    def poll_job_status(n_intervals: int, job_id: str | None) -> tuple:
        """Poll the API for job status updates."""
        if not job_id:
            raise PreventUpdate

        try:
            # First check status
            status_response = requests.get(
                f"{API_BASE_URL}/backtest/status/{job_id}",
                timeout=10,
            )

            if status_response.status_code != 200:
                return (
                    no_update,
                    no_update,
                    True,  # Stop polling
                    dbc.Alert("Failed to get job status.", color="warning"),
                )

            status_data = status_response.json()
            current_status = status_data.get("status", "unknown")

            if current_status == "completed":
                # Fetch full results
                results_response = requests.get(
                    f"{API_BASE_URL}/backtest/{job_id}/result",
                    timeout=30,
                )

                if results_response.status_code == 200:
                    results = results_response.json()
                    return (
                        current_status,
                        results,
                        True,  # Stop polling
                        dbc.Alert(
                            [
                                html.I(className="fas fa-check-circle me-2"),
                                "Backtest completed successfully!",
                            ],
                            color="success",
                        ),
                    )
                else:
                    error_detail = None
                    try:
                        error_detail = results_response.json().get(
                            "detail", "Unknown error"
                        )
                    except Exception:
                        error_detail = results_response.text or "Unknown error"
                    return (
                        current_status,
                        no_update,
                        True,
                        dbc.Alert(
                            f"Completed but failed to fetch results: {error_detail}",
                            color="warning",
                        ),
                    )

            elif current_status == "failed":
                error_text = None
                logs_text = None
                try:
                    result_response = requests.get(
                        f"{API_BASE_URL}/backtest/result/{job_id}",
                        timeout=10,
                    )
                    if result_response.status_code == 200:
                        payload = result_response.json()
                        error_text = payload.get("error")
                        logs_text = payload.get("logs")
                except Exception:
                    pass

                if logs_text:
                    logs_text = logs_text.strip()
                    if len(logs_text) > 1200:
                        logs_text = logs_text[:1200] + "\n... (truncated)"

                return (
                    current_status,
                    no_update,
                    True,  # Stop polling
                    dbc.Alert(
                        [
                            html.I(className="fas fa-times-circle me-2"),
                            (
                                f"Backtest execution failed: {error_text}"
                                if error_text
                                else "Backtest execution failed."
                            ),
                            html.Pre(logs_text, className="mt-2") if logs_text else None,
                        ],
                        color="danger",
                    ),
                )

            else:
                # Still running - continue polling
                return (
                    current_status,
                    no_update,
                    False,  # Continue polling
                    dbc.Alert(
                        [
                            html.I(className="fas fa-spinner fa-spin me-2"),
                            f"Running... (Poll #{n_intervals})",
                        ],
                        color="info",
                    ),
                )

        except requests.exceptions.RequestException as e:
            logger.exception(f"Polling failed: {e}")
            return (
                no_update,
                no_update,
                True,  # Stop polling on error
                dbc.Alert(f"Polling error: {str(e)}", color="warning"),
            )


def _register_results_callback(app: dash.Dash) -> None:
    """Register callback for displaying results."""

    @app.callback(
        [
            Output("div-no-results", "style"),
            Output("div-results-content", "style"),
            Output("div-primary-metrics", "children"),
            Output("div-secondary-metrics", "children"),
            Output("div-trade-summary-inline", "children"),
            Output("div-job-status-badge", "children"),
        ],
        Input("store-results", "data"),
        State("store-job-status", "data"),
        prevent_initial_call=True,
    )
    def update_results_display(results: dict | None, status: str | None) -> tuple:
        """Update the results dashboard with backtest results."""
        if not results:
            return (
                {"display": "block"},  # Show no-results placeholder
                {"display": "none"},  # Hide results content
                no_update,  # Primary metrics
                no_update,  # Secondary metrics
                no_update,  # Trade summary
                create_job_status_badge(status or "pending"),
            )

        # Extract metrics and benchmark metrics
        metrics = results.get("metrics", {})
        benchmark_metrics = results.get("benchmark_metrics")

        # Extract trades for trade summary
        trades = results.get("trades", [])

        # Create primary and secondary metric rows with benchmark comparison
        primary_metrics = _create_primary_metrics_row(metrics, benchmark_metrics)
        secondary_metrics = _create_secondary_metrics_row(metrics)

        # Create trade summary table (last 10 trades)
        trade_summary = create_trade_summary_table(trades[-10:]) if trades else html.Div(
            "No trades executed.",
            className="text-muted text-center py-3"
        )

        return (
            {"display": "none"},  # Hide no-results placeholder
            {"display": "block"},  # Show results content
            primary_metrics,  # Primary metrics row
            secondary_metrics,  # Secondary metrics row
            trade_summary,  # Trade summary table
            create_job_status_badge(status or "completed"),  # Status badge
        )


def _register_chart_callbacks(app: dash.Dash) -> None:
    """Register callbacks for chart updates."""

    @app.callback(
        Output("graph-equity", "figure"),
        [
            Input("store-results", "data"),
            Input("switch-log-scale", "value"),
        ],
        State("input-benchmarks", "value"),
        prevent_initial_call=True,
    )
    def update_equity_chart(results: dict | None, log_scale: bool, benchmarks: str | None) -> dict:
        """Update the equity curve chart."""
        if not results:
            raise PreventUpdate

        equity_data = results.get("equity_curve", {})
        strategy_points = equity_data.get("strategy", [])
        benchmark_points = equity_data.get("benchmark")

        if not strategy_points:
            raise PreventUpdate

        # Convert to DataFrame
        df = pd.DataFrame(strategy_points)
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")
        df = df.rename(columns={"value": "strategy"})

        if benchmark_points:
            bench_df = pd.DataFrame(benchmark_points)
            bench_df["date"] = pd.to_datetime(bench_df["date"])
            bench_df = bench_df.set_index("date")
            df["benchmark"] = bench_df["value"]

        # Get benchmark name from input (default to "Benchmark")
        benchmark_name = "Benchmark"
        if benchmarks and benchmarks.strip():
            # Use first benchmark ticker as the name
            benchmark_name = benchmarks.split(",")[0].strip().upper()

        return create_equity_chart(df, log_scale=log_scale, benchmark_name=benchmark_name)

    @app.callback(
        Output("graph-drawdown", "figure"),
        Input("store-results", "data"),
        prevent_initial_call=True,
    )
    def update_drawdown_chart(results: dict | None) -> dict:
        """Update the drawdown chart."""
        if not results:
            raise PreventUpdate

        drawdown_data = results.get("drawdown", {})
        data_points = drawdown_data.get("data", [])

        if not data_points:
            raise PreventUpdate

        # Convert to Series
        series = pd.Series(
            [p["value"] for p in data_points],
            index=pd.to_datetime([p["date"] for p in data_points]),
        )

        return create_drawdown_chart(series)

    @app.callback(
        Output("graph-heatmap", "figure"),
        Input("store-results", "data"),
        prevent_initial_call=True,
    )
    def update_heatmap(results: dict | None) -> dict:
        """Update the monthly returns heatmap."""
        if not results:
            raise PreventUpdate

        heatmap_data = results.get("monthly_heatmap", {})

        if not heatmap_data.get("years"):
            raise PreventUpdate

        # Create a simple namespace object for the chart function
        class HeatmapData:
            def __init__(self, data: dict):
                self.years = data.get("years", [])
                self.months = data.get("months", [
                    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
                    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
                ])
                self.returns = data.get("returns", [])

        return create_monthly_heatmap(HeatmapData(heatmap_data))


def _validate_inputs(
    strategy: str | None,
    start_date: str | None,
    end_date: str | None,
    initial_capital: float | None,
    benchmarks: str | None,
) -> str | None:
    """
    Validate form inputs.

    Args:
        strategy: Strategy description text.
        start_date: Backtest start date.
        end_date: Backtest end date.
        initial_capital: Initial capital amount.
        benchmarks: Benchmark tickers string.

    Returns:
        Error message string if validation fails, None otherwise.
    """
    if not strategy or len(strategy.strip()) < VALIDATION["MIN_STRATEGY_LENGTH"]:
        return f"Please enter a strategy description (at least {VALIDATION['MIN_STRATEGY_LENGTH']} characters)."

    if not start_date or not end_date:
        return "Please select both start and end dates."

    if not initial_capital or initial_capital < VALIDATION["MIN_CAPITAL"]:
        return f"Initial capital must be at least ${VALIDATION['MIN_CAPITAL']:,}."

    if not benchmarks or not benchmarks.strip():
        return "Please enter at least one benchmark ticker."

    return None


def _register_toggle_callbacks(app: dash.Dash) -> None:
    """Register callbacks for collapsible section toggles."""

    @app.callback(
        [
            Output("collapse-code-viewer", "is_open"),
            Output("btn-toggle-code", "children"),
        ],
        Input("btn-toggle-code", "n_clicks"),
        State("collapse-code-viewer", "is_open"),
        prevent_initial_call=True,
    )
    def toggle_code_viewer(n_clicks: int, is_open: bool) -> tuple:
        """Toggle the code viewer collapse section."""
        if not n_clicks:
            raise PreventUpdate

        new_state = not is_open
        icon_class = "fas fa-chevron-up" if new_state else "fas fa-chevron-down"
        return new_state, html.I(className=icon_class)

    @app.callback(
        [
            Output("collapse-trade-summary", "is_open"),
            Output("btn-toggle-trades", "children"),
        ],
        Input("btn-toggle-trades", "n_clicks"),
        State("collapse-trade-summary", "is_open"),
        prevent_initial_call=True,
    )
    def toggle_trade_summary(n_clicks: int, is_open: bool) -> tuple:
        """Toggle the trade summary collapse section."""
        if not n_clicks:
            raise PreventUpdate

        new_state = not is_open
        icon_class = "fas fa-chevron-up" if new_state else "fas fa-chevron-down"
        return new_state, html.I(className=icon_class)


def _register_validation_callbacks(app: dash.Dash) -> None:
    """Register callbacks for real-time input validation."""

    @app.callback(
        [
            Output("input-capital", "invalid"),
            Output("input-capital", "valid"),
        ],
        Input("input-capital", "value"),
        prevent_initial_call=True,
    )
    def validate_capital(value: float | None) -> tuple[bool, bool]:
        """Validate initial capital input."""
        if value is None:
            return False, False
        is_valid = value >= VALIDATION["MIN_CAPITAL"]
        return not is_valid, is_valid

    @app.callback(
        Output("div-validation-alert", "children"),
        [
            Input("textarea-strategy", "value"),
            Input("datepicker-range", "start_date"),
            Input("datepicker-range", "end_date"),
            Input("input-capital", "value"),
            Input("input-benchmarks", "value"),
        ],
        prevent_initial_call=True,
    )
    def show_validation_summary(
        strategy: str | None,
        start_date: str | None,
        end_date: str | None,
        capital: float | None,
        benchmarks: str | None,
    ) -> html.Div | None:
        """Show validation warnings for incomplete fields."""
        warnings = []

        if not strategy or len(strategy.strip()) < VALIDATION["MIN_STRATEGY_LENGTH"]:
            warnings.append(f"Strategy needs at least {VALIDATION['MIN_STRATEGY_LENGTH']} characters")

        if not start_date or not end_date:
            warnings.append("Select date range")

        if capital is None or capital < VALIDATION["MIN_CAPITAL"]:
            warnings.append(f"Capital must be ≥ ${VALIDATION['MIN_CAPITAL']:,}")

        if not benchmarks or not benchmarks.strip():
            warnings.append("Enter benchmark ticker(s)")

        if warnings:
            return dbc.Alert(
                [
                    html.I(className="fas fa-exclamation-triangle me-2"),
                    html.Small(" · ".join(warnings)),
                ],
                color="warning",
                className="mb-0 py-2",
            )

        return None
