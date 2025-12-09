"""
Code Viewer Component.

Provides a component for displaying and inspecting generated backtest code
with syntax highlighting and copy functionality.
"""

import dash_bootstrap_components as dbc
from dash import dcc, html


def create_code_viewer_card() -> dbc.Card:
    """
    Create the Code Viewer Card component.

    Displays generated Python code with syntax highlighting,
    model information, and copy functionality.

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
                                "Generated Code",
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
                    # Code display area
                    html.Div(
                        [
                            dcc.Markdown(
                                id="markdown-code",
                                children="*No code generated yet. Enter a strategy and click 'Generate Code'.*",
                                className="code-viewer",
                                style={
                                    "backgroundColor": "#f8f9fa",
                                    "padding": "1rem",
                                    "borderRadius": "0.375rem",
                                    "minHeight": "400px",
                                    "maxHeight": "600px",
                                    "overflow": "auto",
                                    "fontFamily": "monospace",
                                    "fontSize": "0.875rem",
                                },
                            ),
                        ],
                        id="div-code-container",
                    ),
                    # Generation time info
                    html.Div(
                        id="div-generation-info",
                        className="mt-2 small text-muted",
                        style={"display": "none"},
                    ),
                    # Copy success toast
                    dcc.Store(id="store-copy-trigger", data=0),
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
