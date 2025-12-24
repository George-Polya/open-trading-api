"""
Code Viewer Component.

Provides a component for displaying and inspecting generated backtest code
with syntax highlighting and user code input functionality.
"""

import dash_bootstrap_components as dbc
from dash import dcc, html


def create_code_viewer_card() -> dbc.Card:
    """
    Create the Code Viewer Card component.

    Displays generated Python code with syntax highlighting,
    model information, and allows user to input custom code.

    Returns:
        Dash Bootstrap Card component for code viewing.
    """
    return dbc.Card(
        [
            dbc.CardHeader(
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                html.I(className="fas fa-code me-2"),
                                "Backtest Code",
                            ],
                            width="auto",
                        ),
                        dbc.Col(
                            dbc.Button(
                                [
                                    html.I(className="fas fa-copy me-1"),
                                    "Copy",
                                ],
                                id="btn-copy-code",
                                color="outline-secondary",
                                size="sm",
                                disabled=True,
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
                    # Model info badge (hidden by default)
                    html.Div(
                        id="div-model-info",
                        className="mb-2",
                        style={"display": "none"},
                    ),
                    # Strategy summary
                    html.Div(
                        id="div-strategy-summary",
                        className="mb-3",
                        style={"display": "none"},
                    ),
                    # Tabs for Generated Code vs User Code
                    dbc.Tabs(
                        [
                            dbc.Tab(
                                label="Generated Code",
                                tab_id="tab-generated",
                                children=[
                                    html.Div(
                                        dcc.Markdown(
                                            id="markdown-code",
                                            children="*No code generated yet. Enter a strategy and click 'Generate Code'.*",
                                            className="code-viewer",
                                            style={
                                                "backgroundColor": "#f8f9fa",
                                                "padding": "1rem",
                                                "borderRadius": "0.375rem",
                                                "minHeight": "350px",
                                                "maxHeight": "500px",
                                                "overflow": "auto",
                                                "fontFamily": "monospace",
                                                "fontSize": "0.875rem",
                                            },
                                        ),
                                        className="mt-3",
                                    ),
                                ],
                            ),
                            dbc.Tab(
                                label="Custom Code",
                                tab_id="tab-custom",
                                children=[
                                    html.Div(
                                        [
                                            dbc.Label(
                                                "Enter your Python backtest code:",
                                                className="small text-muted",
                                            ),
                                            dbc.Textarea(
                                                id="textarea-custom-code",
                                                placeholder='''# Example backtest code
def run_backtest(params):
    """
    Run backtest with the given parameters.
    
    Args:
        params: Dictionary with start_date, end_date, tickers, initial_capital, etc.
    
    Returns:
        Dictionary with backtest results.
    """
    import pandas as pd
    
    # Load data using the injected load_data function
    data = load_data(
        params.get("tickers", ["SPY"]),
        params.get("start_date", "2020-01-01"),
        params.get("end_date", "2020-12-31")
    )
    
    # Your strategy logic here
    result = {
        "total_return": 0.15,
        "sharpe_ratio": 1.2,
        "max_drawdown": -0.10,
    }
    
    return result
''',
                                                style={
                                                    "minHeight": "350px",
                                                    "maxHeight": "500px",
                                                    "fontFamily": "monospace",
                                                    "fontSize": "0.875rem",
                                                    "backgroundColor": "#1e1e1e",
                                                    "color": "#d4d4d4",
                                                },
                                                className="form-control",
                                            ),
                                            dbc.FormText(
                                                "Enter your custom backtest code. "
                                                "Use the load_data() function to access market data. "
                                                "Define a run_backtest(params) function to return results.",
                                                className="mt-2",
                                            ),
                                        ],
                                        className="mt-3",
                                    ),
                                ],
                            ),
                        ],
                        id="tabs-code",
                        active_tab="tab-generated",
                        className="nav-pills",
                    ),
                    # Generation time info
                    html.Div(
                        id="div-generation-info",
                        className="mt-2 small text-muted",
                        style={"display": "none"},
                    ),
                    # Copy success toast
                    dcc.Store(id="store-copy-trigger", data=0),
                    # Store active tab
                    dcc.Store(id="store-active-code-tab", data="tab-generated"),
                ]
            ),
        ],
        className="shadow-sm h-100",
    )


def create_model_info_badge(provider: str, model_id: str) -> dbc.Badge:
    """
    Create a badge displaying LLM model information.

    Args:
        provider: LLM provider name.
        model_id: Model identifier.

    Returns:
        Dash Bootstrap Badge component.
    """
    # Provider color mapping
    provider_colors = {
        "openrouter": "primary",
        "anthropic": "warning",
        "openai": "success",
    }
    color = provider_colors.get(provider.lower(), "secondary")

    return dbc.Badge(
        [
            html.I(className="fas fa-robot me-1"),
            f"{provider}: {model_id}",
        ],
        color=color,
        className="me-2",
    )


def create_strategy_summary_alert(summary: str) -> dbc.Alert:
    """
    Create an alert displaying the AI-generated strategy summary.

    Args:
        summary: Strategy interpretation summary from the LLM.

    Returns:
        Dash Bootstrap Alert component.
    """
    return dbc.Alert(
        [
            html.Strong(
                [
                    html.I(className="fas fa-brain me-2"),
                    "Strategy Interpretation: ",
                ]
            ),
            html.Span(summary),
        ],
        color="info",
        className="mb-0",
    )


def format_code_for_display(code: str) -> str:
    """
    Format Python code for markdown display with syntax highlighting.

    Args:
        code: Raw Python code string.

    Returns:
        Markdown-formatted code block.
    """
    return f"```python\n{code}\n```"
