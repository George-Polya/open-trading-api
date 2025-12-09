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
    create_job_status_badge,
    create_metrics_row,
)

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
            State("select-llm-provider", "value"),
            State("input-llm-model", "value"),
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
        llm_provider: str,
        llm_model: str | None,
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
                    "amount": float(contribution_amount),
                },
                "fees": {
                    "trading_fee_percent": float(trading_fee),
                    "slippage_percent": float(slippage),
                },
                "dividend_reinvestment": dividend_reinvest,
                "llm_settings": {
                    "provider": llm_provider,
                    "model": llm_model if llm_model else None,
                },
            },
        }

        try:
            # Call generate API
            response = requests.post(
                f"{API_BASE_URL}/backtest/generate",
                json=payload,
                timeout=120,  # 2 minute timeout for code generation
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
                    {"code": code, "model_info": model_info},  # store
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
            State("datepicker-range", "start_date"),
            State("datepicker-range", "end_date"),
            State("input-capital", "value"),
            State("input-benchmarks", "value"),
        ],
        prevent_initial_call=True,
    )
    def execute_backtest(
        n_clicks: int,
        generated_code_data: dict | None,
        start_date: str,
        end_date: str,
        initial_capital: float,
        benchmarks: str,
    ) -> tuple:
        """Handle backtest execution button click."""
        if not n_clicks or not generated_code_data:
            raise PreventUpdate

        code = generated_code_data.get("code", "")
        if not code:
            return (
                no_update,
                no_update,
                True,  # Keep polling disabled
                dbc.Alert("No code to execute.", color="warning"),
            )

        benchmark_list = [b.strip().upper() for b in benchmarks.split(",") if b.strip()]

        payload = {
            "code": code,
            "params": {
                "start_date": start_date,
                "end_date": end_date,
                "initial_capital": float(initial_capital),
                "benchmarks": benchmark_list,
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
                    return (
                        current_status,
                        no_update,
                        True,
                        dbc.Alert(
                            "Completed but failed to fetch results.",
                            color="warning",
                        ),
                    )

            elif current_status == "failed":
                return (
                    current_status,
                    no_update,
                    True,  # Stop polling
                    dbc.Alert(
                        [
                            html.I(className="fas fa-times-circle me-2"),
                            "Backtest execution failed.",
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
            Output("div-metrics-row", "children"),
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
                no_update,
                create_job_status_badge(status or "pending"),
            )

        # Extract metrics
        metrics = results.get("metrics", {})

        return (
            {"display": "none"},  # Hide no-results placeholder
            {"display": "block"},  # Show results content
            create_metrics_row(metrics),  # Metrics row
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
        prevent_initial_call=True,
    )
    def update_equity_chart(results: dict | None, log_scale: bool) -> dict:
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

        return create_equity_chart(df, log_scale=log_scale)

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
    if not strategy or len(strategy.strip()) < 10:
        return "Please enter a strategy description (at least 10 characters)."

    if not start_date or not end_date:
        return "Please select both start and end dates."

    if not initial_capital or initial_capital <= 0:
        return "Initial capital must be a positive number."

    if not benchmarks or not benchmarks.strip():
        return "Please enter at least one benchmark ticker."

    return None
