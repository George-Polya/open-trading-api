"""
Dash Application Initialization.

Creates and configures the Dash application with Bootstrap styling.
Can be mounted onto FastAPI using WSGIMiddleware.
"""

import dash
import dash_bootstrap_components as dbc
from dash import html

# Application constants
APP_TITLE = "Backtest Dashboard"
APP_DESCRIPTION = "AI-Powered Investment Strategy Backtesting"


def create_dash_app(
    requests_pathname_prefix: str = "/dashboard/",
    serve_locally: bool = True,
) -> dash.Dash:
    """
    Create and configure the Dash application.

    Args:
        requests_pathname_prefix: URL prefix for the Dash app (e.g., "/dashboard/").
        serve_locally: Whether to serve assets locally.

    Returns:
        Configured Dash application instance.
    """
    app = dash.Dash(
        __name__,
        external_stylesheets=[
            dbc.themes.BOOTSTRAP,
            dbc.icons.FONT_AWESOME,
        ],
        suppress_callback_exceptions=True,
        requests_pathname_prefix=requests_pathname_prefix,
        serve_locally=serve_locally,
        title=APP_TITLE,
        update_title="Loading...",
        meta_tags=[
            {"name": "viewport", "content": "width=device-width, initial-scale=1"},
            {"name": "description", "content": APP_DESCRIPTION},
        ],
    )

    # Import and set layout (deferred to avoid circular imports)
    from app.dashboard.layout import create_layout

    app.layout = create_layout()

    # Register callbacks (deferred to avoid circular imports)
    from app.dashboard.callbacks import register_callbacks

    register_callbacks(app)

    return app


def create_initial_layout() -> html.Div:
    """
    Create a minimal initial layout for testing.

    Returns:
        Initial HTML layout structure.
    """
    return html.Div(
        [
            dbc.Container(
                [
                    dbc.Row(
                        dbc.Col(
                            html.H1(
                                APP_TITLE,
                                className="text-center my-4",
                            ),
                            width=12,
                        )
                    ),
                    dbc.Row(
                        dbc.Col(
                            html.P(
                                APP_DESCRIPTION,
                                className="lead text-center text-muted",
                            ),
                            width=12,
                        )
                    ),
                    dbc.Row(
                        dbc.Col(
                            dbc.Alert(
                                "Dashboard is loading...",
                                color="info",
                                className="text-center",
                            ),
                            width={"size": 8, "offset": 2},
                        )
                    ),
                ],
                fluid=True,
                className="py-4",
            )
        ]
    )


# Create a default app instance for import
# This is created lazily to avoid import errors during testing
_dash_app: dash.Dash | None = None


def get_dash_app() -> dash.Dash:
    """
    Get or create the singleton Dash application instance.

    Returns:
        The Dash application instance.
    """
    global _dash_app
    if _dash_app is None:
        _dash_app = create_dash_app()
    return _dash_app


# For backward compatibility
dash_app = property(lambda self: get_dash_app())
