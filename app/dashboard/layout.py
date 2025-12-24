"""
Dashboard Layout Definition.

Defines the main layout structure for the Dash application,
combining all UI components into a cohesive interface.
"""

import dash_bootstrap_components as dbc
from dash import dcc, html


def create_layout() -> dbc.Container:
    """
    Create the main dashboard layout.

    The layout is organized as follows:
    1. Header with title
    2. Strategy Input Section (left column)
    3. Configuration Section (left column)
    4. Code Viewer Section (center)
    5. Results Section (right column)

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
            # Interval component for polling
            dcc.Interval(
                id="interval-polling",
                interval=2000,  # 2 seconds
                n_intervals=0,
                disabled=True,
            ),
            # Header
            _create_header(),
            html.Hr(className="my-2"),
            # Main content area
            dbc.Row(
                [
                    # Left column: Strategy Input and Configuration
                    dbc.Col(
                        [
                            _create_strategy_section(),
                            html.Div(className="my-3"),
                            _create_config_section(),
                            html.Div(className="my-3"),
                            _create_action_buttons(),
                        ],
                        md=4,
                        className="pe-md-4",
                    ),
                    # Center column: Code Viewer
                    dbc.Col(
                        [
                            _create_code_viewer_section(),
                        ],
                        md=4,
                        className="px-md-2",
                    ),
                    # Right column: Results Dashboard
                    dbc.Col(
                        [
                            _create_results_section(),
                        ],
                        md=4,
                        className="ps-md-4",
                    ),
                ],
                className="g-4",
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


def _create_strategy_section() -> dbc.Card:
    """
    Create the strategy input section.

    This is a placeholder that will be replaced with StrategyInputCard
    from components/inputs.py
    """
    from app.dashboard.components.inputs import create_strategy_input_card

    return create_strategy_input_card()


def _create_config_section() -> dbc.Card:
    """
    Create the backtest configuration section.

    This is a placeholder that will be replaced with BacktestConfigCard
    from components/inputs.py
    """
    from app.dashboard.components.inputs import create_backtest_config_card

    return create_backtest_config_card()


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
                                disabled=False,  # Enable by default for custom code
                            ),
                            width=6,
                        ),
                    ],
                    className="g-2",
                ),
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

    Uses CodeViewerCard from components/code_view.py
    """
    from app.dashboard.components.code_view import create_code_viewer_card

    return create_code_viewer_card()


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
