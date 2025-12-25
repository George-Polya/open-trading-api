"""
Metrics Display and Results Dashboard Components.

Provides components for displaying performance metrics and assembling
the complete results dashboard with charts and metric cards.

Redesigned with:
- Primary/Secondary metric hierarchy
- Benchmark comparison display
- Inline trade summary
"""

from typing import Any

import dash_bootstrap_components as dbc
from dash import dcc, html

from app.dashboard.constants import (
    CHART_CONFIG,
    COLORS,
    HEIGHTS,
    PRIMARY_METRICS,
    SECONDARY_METRICS,
    STATUS_BADGES,
    DEFAULT_STATUS_BADGE,
)


def create_metric_card(
    title: str,
    value: str,
    icon: str = "fas fa-chart-line",
    color: str = "primary",
    subtitle: str | None = None,
    size: str = "normal",
) -> dbc.Card:
    """
    Create a metric card component.

    Args:
        title: Metric name (e.g., "CAGR").
        value: Formatted metric value (e.g., "12.5%").
        icon: Font Awesome icon class.
        color: Bootstrap color name (primary, success, danger, etc.).
        subtitle: Optional subtitle or description.
        size: Card size ('normal' or 'large').

    Returns:
        Dash Bootstrap Card component.
    """
    is_large = size == "large"
    value_class = "h3" if is_large else "h4"
    icon_size = "fa-3x" if is_large else "fa-2x"
    padding = "py-3" if is_large else "py-2"

    return dbc.Card(
        dbc.CardBody(
            [
                dbc.Row(
                    [
                        dbc.Col(
                            html.Div(
                                html.I(className=f"{icon} {icon_size} text-{color}"),
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
                                html.Div(
                                    value,
                                    className=f"{value_class} mb-0 text-{color}",
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
            className=padding,
        ),
        className="shadow-sm h-100",
    )


def create_metric_card_with_comparison(
    title: str,
    value: float,
    benchmark_value: float | None,
    format_str: str,
    icon: str,
    always_negative_color: bool = False,
) -> dbc.Card:
    """
    Create a metric card with benchmark comparison.

    Args:
        title: Metric name.
        value: Strategy metric value.
        benchmark_value: Benchmark metric value for comparison.
        format_str: Format string for the value (e.g., "{:.2f}%").
        icon: Font Awesome icon class.
        always_negative_color: If True, always show in danger color.

    Returns:
        Dash Bootstrap Card with comparison subtitle.
    """
    # Format the main value
    is_mdd = "drawdown" in title.lower()
    display_value = abs(value) if is_mdd else value
    formatted_value = format_str.format(display_value)
    if is_mdd:
        formatted_value = f"-{formatted_value}"

    # Determine color
    if always_negative_color:
        color = "danger"
    else:
        color = "success" if value >= 0 else "danger"

    # Create comparison subtitle
    subtitle = None
    if benchmark_value is not None:
        delta = value - benchmark_value
        delta_str = f"{delta:+.2f}%"
        if delta >= 0:
            subtitle = html.Span(
                [
                    html.I(className="fas fa-arrow-up me-1"),
                    f"vs BM: {delta_str}",
                ],
                className="text-success",
            )
        else:
            subtitle = html.Span(
                [
                    html.I(className="fas fa-arrow-down me-1"),
                    f"vs BM: {delta_str}",
                ],
                className="text-danger",
            )

    return dbc.Card(
        dbc.CardBody(
            [
                dbc.Row(
                    [
                        dbc.Col(
                            html.Div(
                                html.I(className=f"{icon} fa-3x text-{color}"),
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
                                html.Div(
                                    formatted_value,
                                    className=f"h3 mb-0 text-{color} fw-bold",
                                ),
                                html.Small(
                                    subtitle,
                                    className="d-block mt-1",
                                ) if subtitle else None,
                            ],
                            width=9,
                        ),
                    ],
                    className="align-items-center",
                ),
            ],
            className="py-3",
            style={"backgroundColor": COLORS["metric_primary_bg"]},
        ),
        className="shadow-sm h-100 border-0",
    )


def create_secondary_metric_card(
    title: str,
    value: float,
    format_str: str,
    icon: str,
) -> dbc.Card:
    """
    Create a smaller, subdued metric card for secondary metrics.

    Args:
        title: Metric name.
        value: Metric value.
        format_str: Format string for the value.
        icon: Font Awesome icon class.

    Returns:
        Dash Bootstrap Card with subdued styling.
    """
    formatted_value = format_str.format(value)
    color = "success" if value >= 0 else "danger"

    return dbc.Card(
        dbc.CardBody(
            [
                dbc.Row(
                    [
                        dbc.Col(
                            html.I(className=f"{icon} fa-lg text-{color}"),
                            width="auto",
                        ),
                        dbc.Col(
                            [
                                html.Small(title, className="text-muted d-block"),
                                html.Span(formatted_value, className=f"fw-bold text-{color}"),
                            ],
                        ),
                    ],
                    className="align-items-center g-2",
                ),
            ],
            className="py-2 px-3",
            style={"backgroundColor": COLORS["metric_secondary_bg"]},
        ),
        className="shadow-sm h-100 border-0",
    )


def create_metrics_row(
    metrics: dict[str, Any] | None = None,
    benchmark_metrics: dict[str, Any] | None = None,
) -> html.Div:
    """
    Create a hierarchical metrics display.

    Primary metrics (larger, with benchmark comparison):
    - Total Return
    - CAGR
    - Max Drawdown

    Secondary metrics (smaller, subdued):
    - Sharpe Ratio
    - Sortino Ratio
    - Calmar Ratio

    Args:
        metrics: Dictionary of strategy performance metrics.
        benchmark_metrics: Dictionary of benchmark metrics for comparison.

    Returns:
        html.Div containing both primary and secondary metric rows.
    """
    if metrics is None:
        metrics = {}
    if benchmark_metrics is None:
        benchmark_metrics = {}

    return html.Div(
        [
            _create_primary_metrics_row(metrics, benchmark_metrics),
            html.Div(className="mb-3"),
            _create_secondary_metrics_row(metrics),
        ]
    )


def _create_primary_metrics_row(
    metrics: dict[str, Any],
    benchmark_metrics: dict[str, Any],
) -> dbc.Row:
    """Create the primary metrics row with larger cards and benchmark comparison."""
    cards = []

    for config in PRIMARY_METRICS:
        value = metrics.get(config["key"], 0.0)
        benchmark_value = benchmark_metrics.get(config["key"]) if (config.get("show_benchmark") and benchmark_metrics) else None

        cards.append(
            dbc.Col(
                html.Div(
                    id=f"metric-{config['key'].replace('_', '-')}",
                    children=create_metric_card_with_comparison(
                        title=config["title"],
                        value=value,
                        benchmark_value=benchmark_value,
                        format_str=config["format"],
                        icon=config["icon"],
                        always_negative_color=config.get("always_negative_color", False),
                    ),
                ),
                xs=12,
                sm=4,
                className="mb-2",
            )
        )

    return dbc.Row(cards, className="g-2")


def _create_secondary_metrics_row(metrics: dict[str, Any]) -> dbc.Row:
    """Create the secondary metrics row with smaller, subdued cards."""
    cards = []

    for config in SECONDARY_METRICS:
        value = metrics.get(config["key"], 0.0)

        cards.append(
            dbc.Col(
                html.Div(
                    id=f"metric-{config['key'].replace('_', '-')}",
                    children=create_secondary_metric_card(
                        title=config["title"],
                        value=value,
                        format_str=config["format"],
                        icon=config["icon"],
                    ),
                ),
                xs=6,
                sm=4,
                className="mb-2",
            )
        )

    return dbc.Row(cards, className="g-2")


def create_results_dashboard() -> dbc.Card:
    """
    Create the complete results dashboard component.

    Contains:
    - Primary metrics row (Total Return, CAGR, Max Drawdown with benchmark comparison)
    - Secondary metrics row (Sharpe, Sortino, Calmar)
    - Chart tabs (Equity, Drawdown, Monthly Returns)
    - Inline trade summary (last 10 trades)

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
                            # Primary Metrics row
                            html.Div(
                                id="div-primary-metrics",
                                className="mb-3",
                            ),
                            # Secondary Metrics row
                            html.Div(
                                id="div-secondary-metrics",
                                className="mb-4",
                            ),
                            # Chart tabs
                            dbc.Tabs(
                                [
                                    dbc.Tab(
                                        dcc.Loading(
                                            dcc.Graph(
                                                id="graph-equity",
                                                config=CHART_CONFIG,
                                                style={"height": HEIGHTS["CHART_DEFAULT"]},
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
                                                config=CHART_CONFIG,
                                                style={"height": HEIGHTS["CHART_DEFAULT"]},
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
                                                config=CHART_CONFIG,
                                                style={"height": HEIGHTS["CHART_DEFAULT"]},
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
                            # Chart controls row
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
                                className="justify-content-end mb-4",
                            ),
                            # Inline Trade Summary
                            html.Div(
                                [
                                    dbc.Row(
                                        [
                                            dbc.Col(
                                                html.H6(
                                                    [
                                                        html.I(className="fas fa-exchange-alt me-2"),
                                                        "Recent Trades",
                                                    ],
                                                    className="mb-0",
                                                ),
                                                width="auto",
                                            ),
                                            dbc.Col(
                                                dbc.Button(
                                                    html.I(className="fas fa-chevron-down"),
                                                    id="btn-toggle-trades",
                                                    color="link",
                                                    size="sm",
                                                    className="p-0",
                                                ),
                                                width="auto",
                                                className="ms-auto",
                                            ),
                                        ],
                                        className="align-items-center mb-2",
                                    ),
                                    dbc.Collapse(
                                        html.Div(
                                            id="div-trade-summary-inline",
                                            style={
                                                "maxHeight": HEIGHTS["TRADE_TABLE_MAX"],
                                                "overflow": "auto",
                                            },
                                        ),
                                        id="collapse-trade-summary",
                                        is_open=True,
                                    ),
                                ],
                                className="border-top pt-3",
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
    config = STATUS_BADGES.get(status.lower(), DEFAULT_STATUS_BADGE)

    return dbc.Badge(
        [
            html.I(className=f"{config['icon']} me-1"),
            status.capitalize(),
        ],
        color=config["color"],
        className="ms-2",
    )


def create_trade_summary_table(
    trades: list[dict[str, Any]],
    limit: int | None = None,
) -> dbc.Table | html.Div:
    """
    Create a summary table of trades.

    Args:
        trades: List of trade dictionaries with keys like
            date, symbol, action, quantity, price, profit.
        limit: Maximum number of trades to display. Defaults to 10 for inline view.

    Returns:
        Dash Bootstrap Table component or empty message.
    """
    if not trades:
        return html.Div(
            html.P("No trades executed.", className="text-muted text-center"),
        )

    display_limit = limit or int(HEIGHTS["TRADE_TABLE_INLINE_ROWS"])
    display_trades = trades[:display_limit]

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
    for trade in display_trades:
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

    # Add "View All" footer if there are more trades
    footer = None
    if len(trades) > display_limit:
        remaining = len(trades) - display_limit
        footer = html.Tfoot(
            html.Tr(
                html.Td(
                    html.Small(f"+ {remaining} more trades", className="text-muted"),
                    colSpan=6,
                    className="text-center",
                )
            )
        )

    table_children = [header, body]
    if footer:
        table_children.append(footer)

    return dbc.Table(
        table_children,
        bordered=True,
        hover=True,
        responsive=True,
        size="sm",
        className="small mb-0",
    )
