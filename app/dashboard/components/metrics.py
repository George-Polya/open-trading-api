"""
Metrics Display and Results Dashboard Components.

Provides components for displaying performance metrics and assembling
the complete results dashboard with charts and metric cards.
"""

from typing import Any

import dash_bootstrap_components as dbc
from dash import dcc, html


def create_metric_card(
    title: str,
    value: str,
    icon: str = "fas fa-chart-line",
    color: str = "primary",
    subtitle: str | None = None,
) -> dbc.Card:
    """
    Create a metric card component.

    Args:
        title: Metric name (e.g., "CAGR").
        value: Formatted metric value (e.g., "12.5%").
        icon: Font Awesome icon class.
        color: Bootstrap color name (primary, success, danger, etc.).
        subtitle: Optional subtitle or description.

    Returns:
        Dash Bootstrap Card component.
    """
    return dbc.Card(
        dbc.CardBody(
            [
                dbc.Row(
                    [
                        dbc.Col(
                            html.Div(
                                html.I(className=f"{icon} fa-2x text-{color}"),
                                className="d-flex align-items-center justify-content-center h-100",
                            ),
                            width=3,
                        ),
                        dbc.Col(
                            [
                                html.H6(
                                    title,
                                    className="text-muted mb-0 small",
                                ),
                                html.H4(
                                    value,
                                    className=f"mb-0 text-{color}",
                                ),
                                html.Small(
                                    subtitle,
                                    className="text-muted",
                                ) if subtitle else None,
                            ],
                            width=9,
                        ),
                    ],
                    className="align-items-center",
                ),
            ],
            className="py-2",
        ),
        className="shadow-sm h-100",
    )


def create_metrics_row(metrics: dict[str, Any] | None = None) -> dbc.Row:
    """
    Create a row of metric cards.

    Args:
        metrics: Dictionary of performance metrics.
            Expected keys: total_return, cagr, max_drawdown,
            sharpe_ratio, sortino_ratio, calmar_ratio.

    Returns:
        Dash Bootstrap Row with metric cards.
    """
    if metrics is None:
        metrics = {}

    # Define metric configurations
    metric_configs = [
        {
            "id": "metric-total-return",
            "title": "Total Return",
            "key": "total_return",
            "format": "{:.2f}%",
            "icon": "fas fa-percentage",
            "positive_color": "success",
            "negative_color": "danger",
        },
        {
            "id": "metric-cagr",
            "title": "CAGR",
            "key": "cagr",
            "format": "{:.2f}%",
            "icon": "fas fa-chart-line",
            "positive_color": "success",
            "negative_color": "danger",
        },
        {
            "id": "metric-mdd",
            "title": "Max Drawdown",
            "key": "max_drawdown",
            "format": "-{:.2f}%",
            "icon": "fas fa-arrow-down",
            "positive_color": "danger",  # Always show as danger
            "negative_color": "danger",
        },
        {
            "id": "metric-sharpe",
            "title": "Sharpe Ratio",
            "key": "sharpe_ratio",
            "format": "{:.2f}",
            "icon": "fas fa-balance-scale",
            "positive_color": "success",
            "negative_color": "danger",
        },
        {
            "id": "metric-sortino",
            "title": "Sortino Ratio",
            "key": "sortino_ratio",
            "format": "{:.2f}",
            "icon": "fas fa-shield-alt",
            "positive_color": "success",
            "negative_color": "danger",
        },
        {
            "id": "metric-calmar",
            "title": "Calmar Ratio",
            "key": "calmar_ratio",
            "format": "{:.2f}",
            "icon": "fas fa-star",
            "positive_color": "success",
            "negative_color": "danger",
        },
    ]

    cards = []
    for config in metric_configs:
        value = metrics.get(config["key"], 0.0)
        formatted_value = config["format"].format(abs(value) if config["key"] == "max_drawdown" else value)

        # Determine color based on value
        if config["key"] == "max_drawdown":
            color = config["positive_color"]
        else:
            color = config["positive_color"] if value >= 0 else config["negative_color"]

        cards.append(
            dbc.Col(
                html.Div(
                    id=config["id"],
                    children=create_metric_card(
                        title=config["title"],
                        value=formatted_value,
                        icon=config["icon"],
                        color=color,
                    ),
                ),
                xs=6,
                sm=4,
                md=4,
                lg=2,
                className="mb-2",
            )
        )

    return dbc.Row(cards, className="g-2")


def create_results_dashboard() -> dbc.Card:
    """
    Create the complete results dashboard component.

    Contains:
    - Metrics row with performance KPIs
    - Equity curve chart
    - Drawdown chart
    - Monthly returns heatmap

    Returns:
        Dash Bootstrap Card containing the full results dashboard.
    """
    return dbc.Card(
        [
            dbc.CardHeader(
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                html.I(className="fas fa-chart-bar me-2"),
                                "Backtest Results",
                            ],
                            width="auto",
                        ),
                        dbc.Col(
                            html.Div(
                                id="div-job-status-badge",
                            ),
                            width="auto",
                            className="ms-auto",
                        ),
                    ],
                    className="align-items-center",
                ),
                className="fw-bold",
            ),
            dbc.CardBody(
                [
                    # No results placeholder
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.I(
                                        className="fas fa-chart-pie fa-4x text-muted mb-3"
                                    ),
                                    html.P(
                                        "No backtest results yet",
                                        className="text-muted mb-1",
                                    ),
                                    html.Small(
                                        "Generate and execute a backtest to see results here.",
                                        className="text-muted",
                                    ),
                                ],
                                className="text-center py-5",
                            ),
                        ],
                        id="div-no-results",
                    ),
                    # Results content (hidden by default)
                    html.Div(
                        [
                            # Metrics row
                            html.Div(
                                id="div-metrics-row",
                                className="mb-4",
                            ),
                            # Chart tabs
                            dbc.Tabs(
                                [
                                    dbc.Tab(
                                        dcc.Loading(
                                            dcc.Graph(
                                                id="graph-equity",
                                                config={
                                                    "displayModeBar": True,
                                                    "displaylogo": False,
                                                    "modeBarButtonsToRemove": [
                                                        "select2d",
                                                        "lasso2d",
                                                    ],
                                                },
                                                style={"height": "350px"},
                                            ),
                                            type="circle",
                                        ),
                                        label="Equity Curve",
                                        tab_id="tab-equity",
                                    ),
                                    dbc.Tab(
                                        dcc.Loading(
                                            dcc.Graph(
                                                id="graph-drawdown",
                                                config={
                                                    "displayModeBar": True,
                                                    "displaylogo": False,
                                                },
                                                style={"height": "350px"},
                                            ),
                                            type="circle",
                                        ),
                                        label="Drawdown",
                                        tab_id="tab-drawdown",
                                    ),
                                    dbc.Tab(
                                        dcc.Loading(
                                            dcc.Graph(
                                                id="graph-heatmap",
                                                config={
                                                    "displayModeBar": True,
                                                    "displaylogo": False,
                                                },
                                                style={"height": "350px"},
                                            ),
                                            type="circle",
                                        ),
                                        label="Monthly Returns",
                                        tab_id="tab-heatmap",
                                    ),
                                ],
                                id="tabs-charts",
                                active_tab="tab-equity",
                                className="mb-3",
                            ),
                            # Log scale toggle
                            dbc.Row(
                                [
                                    dbc.Col(
                                        dbc.Switch(
                                            id="switch-log-scale",
                                            label="Log Scale",
                                            value=True,
                                            className="small",
                                        ),
                                        width="auto",
                                    ),
                                ],
                                className="justify-content-end",
                            ),
                        ],
                        id="div-results-content",
                        style={"display": "none"},
                    ),
                ]
            ),
        ],
        className="shadow-sm h-100",
    )


def create_job_status_badge(status: str) -> dbc.Badge:
    """
    Create a badge showing the current job status.

    Args:
        status: Job status string (pending, running, completed, failed).

    Returns:
        Dash Bootstrap Badge component.
    """
    status_configs = {
        "pending": {"color": "warning", "icon": "fas fa-clock"},
        "running": {"color": "info", "icon": "fas fa-spinner fa-spin"},
        "completed": {"color": "success", "icon": "fas fa-check"},
        "failed": {"color": "danger", "icon": "fas fa-times"},
    }

    config = status_configs.get(status.lower(), {"color": "secondary", "icon": "fas fa-question"})

    return dbc.Badge(
        [
            html.I(className=f"{config['icon']} me-1"),
            status.capitalize(),
        ],
        color=config["color"],
        className="ms-2",
    )


def create_trade_summary_table(trades: list[dict[str, Any]]) -> dbc.Table:
    """
    Create a summary table of trades.

    Args:
        trades: List of trade dictionaries with keys like
            date, symbol, action, quantity, price, profit.

    Returns:
        Dash Bootstrap Table component.
    """
    if not trades:
        return html.Div(
            html.P("No trades executed.", className="text-muted text-center"),
        )

    # Create table header
    header = html.Thead(
        html.Tr(
            [
                html.Th("Date"),
                html.Th("Symbol"),
                html.Th("Action"),
                html.Th("Qty", className="text-end"),
                html.Th("Price", className="text-end"),
                html.Th("P/L", className="text-end"),
            ]
        )
    )

    # Create table body
    rows = []
    for trade in trades[:50]:  # Limit to 50 trades for performance
        profit = trade.get("profit", 0)
        profit_color = "text-success" if profit >= 0 else "text-danger"

        rows.append(
            html.Tr(
                [
                    html.Td(trade.get("date", "N/A")),
                    html.Td(trade.get("symbol", "N/A")),
                    html.Td(
                        dbc.Badge(
                            trade.get("action", "N/A").upper(),
                            color="success" if trade.get("action", "").lower() == "buy" else "danger",
                        )
                    ),
                    html.Td(f"{trade.get('quantity', 0):,.0f}", className="text-end"),
                    html.Td(f"${trade.get('price', 0):,.2f}", className="text-end"),
                    html.Td(
                        f"${profit:+,.2f}",
                        className=f"text-end {profit_color}",
                    ),
                ]
            )
        )

    body = html.Tbody(rows)

    return dbc.Table(
        [header, body],
        bordered=True,
        hover=True,
        responsive=True,
        size="sm",
        className="small",
    )
