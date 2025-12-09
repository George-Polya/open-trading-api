"""
Input and Configuration Components.

Provides UI components for strategy input and backtest configuration.
Components mirror the BacktestParams model from app/models/backtest.py.
"""

from datetime import date, timedelta

import dash_bootstrap_components as dbc
from dash import dcc, html

from app.models.backtest import ContributionFrequency


def create_strategy_input_card() -> dbc.Card:
    """
    Create the Strategy Input Card component.

    Provides a textarea for natural language strategy description
    with helpful placeholder text and character counter.

    Returns:
        Dash Bootstrap Card component for strategy input.
    """
    return dbc.Card(
        [
            dbc.CardHeader(
                [
                    html.I(className="fas fa-lightbulb me-2"),
                    "Strategy Description",
                ],
                className="fw-bold",
            ),
            dbc.CardBody(
                [
                    dbc.Label(
                        "Describe your investment strategy in natural language:",
                        html_for="textarea-strategy",
                        className="small text-muted mb-2",
                    ),
                    dbc.Textarea(
                        id="textarea-strategy",
                        placeholder=(
                            "Example: Create a momentum strategy that invests in the "
                            "top 3 performing stocks from AAPL, MSFT, GOOGL, AMZN, "
                            "META based on 6-month returns. Rebalance monthly with "
                            "equal weighting among selected stocks."
                        ),
                        rows=6,
                        className="mb-2",
                        style={"resize": "vertical"},
                    ),
                    html.Div(
                        [
                            html.Small(
                                id="text-strategy-counter",
                                className="text-muted",
                                children="0 / 10,000 characters",
                            ),
                        ],
                        className="d-flex justify-content-end",
                    ),
                    dbc.FormText(
                        [
                            html.I(className="fas fa-info-circle me-1"),
                            "Tip: Be specific about tickers, rebalancing frequency, "
                            "and allocation rules for better code generation.",
                        ],
                        color="secondary",
                    ),
                ]
            ),
        ],
        className="shadow-sm h-100",
    )


def create_backtest_config_card() -> dbc.Card:
    """
    Create the Backtest Configuration Card component.

    Provides form inputs for all backtest parameters matching
    the BacktestParams model.

    Returns:
        Dash Bootstrap Card component for backtest configuration.
    """
    # Default dates
    default_end = date.today()
    default_start = default_end - timedelta(days=365 * 3)  # 3 years

    return dbc.Card(
        [
            dbc.CardHeader(
                [
                    html.I(className="fas fa-cog me-2"),
                    "Backtest Configuration",
                ],
                className="fw-bold",
            ),
            dbc.CardBody(
                [
                    # Date Range
                    dbc.Row(
                        [
                            dbc.Col(
                                [
                                    dbc.Label(
                                        "Date Range",
                                        className="small fw-bold",
                                    ),
                                    dcc.DatePickerRange(
                                        id="datepicker-range",
                                        min_date_allowed=date(2015, 1, 1),
                                        max_date_allowed=default_end,
                                        start_date=default_start,
                                        end_date=default_end,
                                        display_format="YYYY-MM-DD",
                                        className="w-100",
                                    ),
                                ],
                                width=12,
                                className="mb-3",
                            ),
                        ]
                    ),
                    # Initial Capital
                    dbc.Row(
                        [
                            dbc.Col(
                                [
                                    dbc.Label(
                                        "Initial Capital ($)",
                                        html_for="input-capital",
                                        className="small fw-bold",
                                    ),
                                    dbc.InputGroup(
                                        [
                                            dbc.InputGroupText("$"),
                                            dbc.Input(
                                                id="input-capital",
                                                type="number",
                                                value=100000,
                                                min=1000,
                                                step=1000,
                                            ),
                                        ],
                                        size="sm",
                                    ),
                                ],
                                width=6,
                                className="mb-3",
                            ),
                            dbc.Col(
                                [
                                    dbc.Label(
                                        "Benchmark Tickers",
                                        html_for="input-benchmarks",
                                        className="small fw-bold",
                                    ),
                                    dbc.Input(
                                        id="input-benchmarks",
                                        type="text",
                                        value="SPY",
                                        placeholder="SPY, QQQ",
                                        size="sm",
                                    ),
                                    dbc.FormText(
                                        "Comma-separated",
                                        className="small",
                                    ),
                                ],
                                width=6,
                                className="mb-3",
                            ),
                        ]
                    ),
                    # Contribution Settings (Collapsible)
                    dbc.Accordion(
                        [
                            dbc.AccordionItem(
                                _create_contribution_settings(),
                                title="Periodic Contributions",
                            ),
                            dbc.AccordionItem(
                                _create_fee_settings(),
                                title="Fees & Slippage",
                            ),
                            dbc.AccordionItem(
                                _create_llm_settings(),
                                title="LLM Settings",
                            ),
                        ],
                        start_collapsed=True,
                        className="mb-3",
                    ),
                    # Dividend Reinvestment
                    dbc.Checkbox(
                        id="checkbox-dividend",
                        label="Reinvest Dividends",
                        value=True,
                        className="small",
                    ),
                ]
            ),
        ],
        className="shadow-sm",
    )


def _create_contribution_settings() -> html.Div:
    """Create contribution settings form fields."""
    return html.Div(
        [
            dbc.Row(
                [
                    dbc.Col(
                        [
                            dbc.Label(
                                "Frequency",
                                html_for="select-contribution-freq",
                                className="small",
                            ),
                            dbc.Select(
                                id="select-contribution-freq",
                                options=[
                                    {"label": "Monthly", "value": ContributionFrequency.MONTHLY.value},
                                    {"label": "Quarterly", "value": ContributionFrequency.QUARTERLY.value},
                                    {"label": "Semi-Annual", "value": ContributionFrequency.SEMIANNUAL.value},
                                    {"label": "Annual", "value": ContributionFrequency.ANNUAL.value},
                                ],
                                value=ContributionFrequency.MONTHLY.value,
                                size="sm",
                            ),
                        ],
                        width=6,
                    ),
                    dbc.Col(
                        [
                            dbc.Label(
                                "Amount ($)",
                                html_for="input-contribution-amount",
                                className="small",
                            ),
                            dbc.InputGroup(
                                [
                                    dbc.InputGroupText("$"),
                                    dbc.Input(
                                        id="input-contribution-amount",
                                        type="number",
                                        value=0,
                                        min=0,
                                        step=100,
                                    ),
                                ],
                                size="sm",
                            ),
                        ],
                        width=6,
                    ),
                ]
            ),
            dbc.FormText(
                "Set amount to 0 to disable periodic contributions.",
                className="small text-muted",
            ),
        ]
    )


def _create_fee_settings() -> html.Div:
    """Create fee settings form fields."""
    return html.Div(
        [
            dbc.Row(
                [
                    dbc.Col(
                        [
                            dbc.Label(
                                "Trading Fee (%)",
                                html_for="input-trading-fee",
                                className="small",
                            ),
                            dbc.InputGroup(
                                [
                                    dbc.Input(
                                        id="input-trading-fee",
                                        type="number",
                                        value=0.1,
                                        min=0,
                                        max=10,
                                        step=0.01,
                                    ),
                                    dbc.InputGroupText("%"),
                                ],
                                size="sm",
                            ),
                        ],
                        width=6,
                    ),
                    dbc.Col(
                        [
                            dbc.Label(
                                "Slippage (%)",
                                html_for="input-slippage",
                                className="small",
                            ),
                            dbc.InputGroup(
                                [
                                    dbc.Input(
                                        id="input-slippage",
                                        type="number",
                                        value=0.05,
                                        min=0,
                                        max=10,
                                        step=0.01,
                                    ),
                                    dbc.InputGroupText("%"),
                                ],
                                size="sm",
                            ),
                        ],
                        width=6,
                    ),
                ]
            ),
        ]
    )


def _create_llm_settings() -> html.Div:
    """Create LLM settings form fields."""
    return html.Div(
        [
            dbc.Row(
                [
                    dbc.Col(
                        [
                            dbc.Label(
                                "Provider",
                                html_for="select-llm-provider",
                                className="small",
                            ),
                            dbc.Select(
                                id="select-llm-provider",
                                options=[
                                    {"label": "OpenRouter", "value": "openrouter"},
                                    {"label": "Anthropic", "value": "anthropic"},
                                    {"label": "OpenAI", "value": "openai"},
                                ],
                                value="openrouter",
                                size="sm",
                            ),
                        ],
                        width=6,
                    ),
                    dbc.Col(
                        [
                            dbc.Label(
                                "Model (optional)",
                                html_for="input-llm-model",
                                className="small",
                            ),
                            dbc.Input(
                                id="input-llm-model",
                                type="text",
                                placeholder="Use default",
                                size="sm",
                            ),
                        ],
                        width=6,
                    ),
                ]
            ),
            dbc.FormText(
                "Leave model blank to use the provider's default model.",
                className="small text-muted",
            ),
        ]
    )
