"""
Dashboard Layout Definition.

Defines the main layout structure for the Dash application,
combining all UI components into a cohesive interface.

Layout Structure (2-column):
- Left Column (30%): Quick Config, Advanced Config (accordion), Action Buttons
- Right Column (70%): Code Viewer (collapsible), Results Dashboard
"""

import dash_bootstrap_components as dbc
from dash import dcc, html

from app.dashboard.constants import LAYOUT


def create_layout() -> dbc.Container:
    """
    Create the main dashboard layout.

    The layout is organized as a 2-column design:
    - Left (30%): Configuration and actions
    - Right (70%): Code viewer and results

    Returns:
        Dashboard layout as a Bootstrap Container.
    """
    return dbc.Container(
        [
            # Data stores for state management
            dcc.Store(id="store-generated-code", storage_type="memory"),
            dcc.Store(id="store-job-id", storage_type="memory"),
            dcc.Store(id="store-job-status", storage_type="memory"),
            dcc.Store(id="store-results", storage_type="memory"),
            dcc.Store(id="store-benchmark-metrics", storage_type="memory"),
            # Interval component for polling
            dcc.Interval(
                id="interval-polling",
                interval=LAYOUT["POLLING_INTERVAL_MS"],
                n_intervals=0,
                disabled=True,
            ),
            # Header
            _create_header(),
            html.Hr(className="my-2"),
            # Main content area - 2 column layout
            dbc.Row(
                [
                    # Left column: Configuration (30%)
                    dbc.Col(
                        [
                            _create_quick_config_section(),
                            html.Div(className="my-3"),
                            _create_advanced_config_section(),
                            html.Div(className="my-3"),
                            _create_action_buttons(),
                        ],
                        xs=12,
                        md=LAYOUT["CONFIG_COLUMN_WIDTH_MD"],
                        lg=LAYOUT["CONFIG_COLUMN_WIDTH_LG"],
                        className="mb-4 mb-lg-0",
                    ),
                    # Right column: Code + Results (70%)
                    dbc.Col(
                        [
                            _create_code_viewer_section(),
                            html.Div(className="my-3"),
                            _create_results_section(),
                        ],
                        xs=12,
                        md=LAYOUT["RESULTS_COLUMN_WIDTH_MD"],
                        lg=LAYOUT["RESULTS_COLUMN_WIDTH_LG"],
                    ),
                ],
                className=f"g-{LAYOUT['ROW_GAP']}",
            ),
            # Footer
            html.Hr(className="mt-5"),
            _create_footer(),
        ],
        fluid=True,
        className="py-3",
    )


def _create_header() -> dbc.Row:
    """Create the header section."""
    return dbc.Row(
        [
            dbc.Col(
                [
                    html.H2(
                        [
                            html.I(className="fas fa-chart-line me-2"),
                            "Backtest Dashboard",
                        ],
                        className="mb-1",
                    ),
                    html.P(
                        "AI-Powered Investment Strategy Backtesting",
                        className="text-muted mb-0",
                    ),
                ],
                width="auto",
            ),
            dbc.Col(
                dbc.Badge(
                    "v1.0.0",
                    color="secondary",
                    className="ms-auto",
                ),
                width="auto",
                className="d-flex align-items-center",
            ),
        ],
        className="align-items-center",
    )


def _create_quick_config_section() -> dbc.Card:
    """
    Create the Quick Configuration section.

    Contains essential settings visible at a glance:
    - LLM Settings (moved to top for visibility)
    - Date Range
    - Initial Capital
    - Benchmark Tickers
    """
    from app.dashboard.components.inputs import create_quick_config_card

    return create_quick_config_card()


def _create_advanced_config_section() -> dbc.Accordion:
    """
    Create the Advanced Configuration section.

    Contains collapsible accordion with:
    - Strategy Description
    - Periodic Contributions
    - Fees & Slippage
    """
    from app.dashboard.components.inputs import create_advanced_config_accordion

    return create_advanced_config_accordion()


def _create_action_buttons() -> dbc.Card:
    """Create the action buttons section."""
    return dbc.Card(
        dbc.CardBody(
            [
                dbc.Row(
                    [
                        dbc.Col(
                            dbc.Button(
                                [
                                    html.I(className="fas fa-code me-2", id="icon-generate"),
                                    html.Span("Generate Code", id="text-generate"),
                                ],
                                id="btn-generate",
                                color="primary",
                                className="w-100",
                            ),
                            width=6,
                        ),
                        dbc.Col(
                            dbc.Button(
                                [
                                    html.I(className="fas fa-play me-2", id="icon-execute"),
                                    html.Span("Execute Backtest", id="text-execute"),
                                ],
                                id="btn-execute",
                                color="success",
                                className="w-100",
                                disabled=False,
                            ),
                            width=6,
                        ),
                    ],
                    className="g-2",
                ),
                # Validation alert container
                html.Div(id="div-validation-alert", className="mt-2"),
                # Loading indicator for status messages
                dcc.Loading(
                    id="loading-status",
                    type="default",
                    children=html.Div(
                        id="div-status-message",
                        className="mt-3",
                    ),
                ),
            ]
        ),
        className="shadow-sm",
    )


def _create_code_viewer_section() -> dbc.Card:
    """
    Create the code viewer section.

    Uses CodeViewerCard from components/code_view.py.
    Collapsible on mobile for better UX.
    """
    from app.dashboard.components.code_view import create_code_viewer_card

    return dbc.Card(
        [
            dbc.CardHeader(
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                html.I(className="fas fa-code me-2"),
                                "Generated Code",
                            ],
                            width="auto",
                        ),
                        dbc.Col(
                            dbc.Button(
                                html.I(className="fas fa-chevron-down"),
                                id="btn-toggle-code",
                                color="link",
                                size="sm",
                                className="p-0",
                            ),
                            width="auto",
                            className="ms-auto",
                        ),
                    ],
                    className="align-items-center",
                ),
                className="fw-bold",
            ),
            dbc.Collapse(
                dbc.CardBody(
                    create_code_viewer_card(),
                    className="p-2",
                ),
                id="collapse-code-viewer",
                is_open=True,
            ),
        ],
        className="shadow-sm",
    )


def _create_results_section() -> dbc.Card:
    """
    Create the results dashboard section.

    Uses ResultsDashboard from components/metrics.py
    """
    from app.dashboard.components.metrics import create_results_dashboard

    return create_results_dashboard()


def _create_footer() -> dbc.Row:
    """Create the footer section."""
    return dbc.Row(
        dbc.Col(
            html.P(
                [
                    html.I(className="fas fa-info-circle me-2"),
                    "Built with ",
                    html.A(
                        "Dash",
                        href="https://plotly.com/dash/",
                        target="_blank",
                        className="text-decoration-none",
                    ),
                    " and ",
                    html.A(
                        "FastAPI",
                        href="https://fastapi.tiangolo.com/",
                        target="_blank",
                        className="text-decoration-none",
                    ),
                ],
                className="text-center text-muted small mb-0",
            ),
            width=12,
        )
    )
