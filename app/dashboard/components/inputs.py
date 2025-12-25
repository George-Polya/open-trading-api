"""
Input and Configuration Components.

Provides UI components for strategy input and backtest configuration.
Components mirror the BacktestParams model from app/models/backtest.py.

Redesigned Structure:
- Quick Config Card: Date Range, Capital, Contribution, Benchmark (always visible)
- Advanced Config Accordion: Strategy, Fees (collapsible)
"""

from datetime import date, timedelta

import dash_bootstrap_components as dbc
from dash import dcc, html

from app.dashboard.components.input_helpers import (
    create_card_header,
    create_currency_input,
    create_percentage_input,
    create_select_with_label,
    create_text_input_with_label,
)
from app.dashboard.constants import (
    CONTRIBUTION_FREQUENCIES,
    DEFAULT_CONTRIBUTION_FREQUENCY,
    HEIGHTS,
    VALIDATION,
)


def create_quick_config_card() -> dbc.Card:
    """
    Create the Quick Configuration Card component.

    Contains essential settings that should be visible at a glance:
    - Date Range
    - Initial Capital
    - Periodic Contribution (Frequency + Amount)
    - Benchmark Tickers
    - Reinvest Dividends

    Returns:
        Dash Bootstrap Card component for quick configuration.
    """
    default_end = date.today()
    default_start = default_end - timedelta(days=365 * VALIDATION["DEFAULT_LOOKBACK_YEARS"])

    return dbc.Card(
        [
            create_card_header("Quick Config", "fas fa-sliders-h"),
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
                                        min_date_allowed=date(VALIDATION["MIN_DATE_YEAR"], 1, 1),
                                        max_date_allowed=default_end,
                                        start_date=default_start,
                                        end_date=default_end,
                                        display_format="YYYY-MM-DD",
                                        className="w-100",
                                    ),
                                    dbc.FormFeedback(
                                        id="feedback-datepicker-range",
                                        type="invalid",
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
                                create_currency_input(
                                    input_id="input-capital",
                                    label="Initial Capital",
                                    value=VALIDATION["DEFAULT_CAPITAL"],
                                    min_value=VALIDATION["MIN_CAPITAL"],
                                    step=VALIDATION["CAPITAL_STEP"],
                                ),
                                width=12,
                                className="mb-3",
                            ),
                        ]
                    ),
                    # Periodic Contribution
                    html.Div(
                        [
                            html.Label(
                                [
                                    html.I(className="fas fa-calendar-plus me-1"),
                                    "Periodic Contribution",
                                ],
                                className="small fw-bold mb-2",
                            ),
                            dbc.Row(
                                [
                                    dbc.Col(
                                        create_select_with_label(
                                            select_id="select-contribution-freq",
                                            label="Frequency",
                                            options=[
                                                {"label": f["label"], "value": f["value"]}
                                                for f in CONTRIBUTION_FREQUENCIES
                                            ],
                                            value=DEFAULT_CONTRIBUTION_FREQUENCY,
                                        ),
                                        width=6,
                                    ),
                                    dbc.Col(
                                        create_currency_input(
                                            input_id="input-contribution-amount",
                                            label="Amount",
                                            value=VALIDATION["DEFAULT_CONTRIBUTION"],
                                            min_value=VALIDATION["MIN_CONTRIBUTION"],
                                            step=VALIDATION["CONTRIBUTION_STEP"],
                                            label_class="small",
                                            show_validation=False,
                                        ),
                                        width=6,
                                    ),
                                ],
                            ),
                            dbc.FormText(
                                "Set to 0 to disable periodic contributions.",
                                className="small text-muted",
                            ),
                        ],
                        className="mb-3 pb-3 border-bottom",
                    ),
                    # Benchmark Tickers
                    dbc.Row(
                        [
                            dbc.Col(
                                [
                                    create_text_input_with_label(
                                        input_id="input-benchmarks",
                                        label="Benchmark Tickers",
                                        value="SPY",
                                        placeholder="SPY, QQQ",
                                        help_text="Comma-separated",
                                    ),
                                ],
                                width=12,
                                className="mb-3",
                            ),
                        ]
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


def create_advanced_config_accordion() -> dbc.Accordion:
    """
    Create the Advanced Configuration Accordion component.

    Contains collapsible sections for:
    - Strategy Description
    - Fees & Slippage

    Returns:
        Dash Bootstrap Accordion component for advanced configuration.
    """
    return dbc.Accordion(
        [
            dbc.AccordionItem(
                _create_strategy_section(),
                title="Strategy Description",
                item_id="strategy",
            ),
            dbc.AccordionItem(
                _create_fee_settings(),
                title="Fees & Slippage",
                item_id="fees",
            ),
        ],
        start_collapsed=False,
        active_item="strategy",
        className="shadow-sm",
    )


def _create_strategy_section() -> html.Div:
    """Create the strategy input section inside accordion."""
    return html.Div(
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
                rows=HEIGHTS["STRATEGY_TEXTAREA_ROWS"],
                className="mb-2",
                style={"resize": "vertical"},
            ),
            html.Div(
                [
                    html.Small(
                        id="text-strategy-counter",
                        className="text-muted",
                        children=f"0 / {VALIDATION['MAX_STRATEGY_LENGTH']:,} characters",
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
    )


def _create_contribution_settings() -> html.Div:
    """Create contribution settings form fields."""
    return html.Div(
        [
            dbc.Row(
                [
                    dbc.Col(
                        create_select_with_label(
                            select_id="select-contribution-freq",
                            label="Frequency",
                            options=[
                                {"label": f["label"], "value": f["value"]}
                                for f in CONTRIBUTION_FREQUENCIES
                            ],
                            value=DEFAULT_CONTRIBUTION_FREQUENCY,
                        ),
                        width=6,
                    ),
                    dbc.Col(
                        create_currency_input(
                            input_id="input-contribution-amount",
                            label="Amount",
                            value=VALIDATION["DEFAULT_CONTRIBUTION"],
                            min_value=VALIDATION["MIN_CONTRIBUTION"],
                            step=VALIDATION["CONTRIBUTION_STEP"],
                            label_class="small",
                            show_validation=False,
                        ),
                        width=6,
                    ),
                ]
            ),
            dbc.FormText(
                "Set amount to 0 to disable periodic contributions.",
                className="small text-muted mt-2",
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
                        create_percentage_input(
                            input_id="input-trading-fee",
                            label="Trading Fee",
                            value=VALIDATION["DEFAULT_TRADING_FEE"],
                            min_value=VALIDATION["MIN_FEE"],
                            max_value=VALIDATION["MAX_FEE"],
                            step=VALIDATION["FEE_STEP"],
                            show_validation=False,
                        ),
                        width=6,
                    ),
                    dbc.Col(
                        create_percentage_input(
                            input_id="input-slippage",
                            label="Slippage",
                            value=VALIDATION["DEFAULT_SLIPPAGE"],
                            min_value=VALIDATION["MIN_FEE"],
                            max_value=VALIDATION["MAX_FEE"],
                            step=VALIDATION["FEE_STEP"],
                            show_validation=False,
                        ),
                        width=6,
                    ),
                ]
            ),
        ]
    )


# =============================================================================
# Legacy functions for backward compatibility
# =============================================================================


def create_strategy_input_card() -> dbc.Card:
    """
    Create the Strategy Input Card component.

    DEPRECATED: Use create_advanced_config_accordion() instead.
    Kept for backward compatibility.

    Returns:
        Dash Bootstrap Card component for strategy input.
    """
    return dbc.Card(
        [
            create_card_header("Strategy Description", "fas fa-lightbulb"),
            dbc.CardBody(
                [
                    _create_strategy_section(),
                ],
            ),
        ],
        className="shadow-sm h-100",
    )


def create_backtest_config_card() -> dbc.Card:
    """
    Create the Backtest Configuration Card component.

    DEPRECATED: Use create_quick_config_card() and create_advanced_config_accordion() instead.
    Kept for backward compatibility.

    Returns:
        Dash Bootstrap Card component for backtest configuration.
    """
    default_end = date.today()
    default_start = default_end - timedelta(days=365 * VALIDATION["DEFAULT_LOOKBACK_YEARS"])

    return dbc.Card(
        [
            create_card_header("Backtest Configuration", "fas fa-cog"),
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
                                        min_date_allowed=date(VALIDATION["MIN_DATE_YEAR"], 1, 1),
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
                    # Initial Capital and Benchmark
                    dbc.Row(
                        [
                            dbc.Col(
                                create_currency_input(
                                    input_id="input-capital",
                                    label="Initial Capital ($)",
                                    value=VALIDATION["DEFAULT_CAPITAL"],
                                    min_value=VALIDATION["MIN_CAPITAL"],
                                    step=VALIDATION["CAPITAL_STEP"],
                                    show_validation=False,
                                ),
                                width=6,
                                className="mb-3",
                            ),
                            dbc.Col(
                                [
                                    create_text_input_with_label(
                                        input_id="input-benchmarks",
                                        label="Benchmark Tickers",
                                        value="SPY",
                                        placeholder="SPY, QQQ",
                                        help_text="Comma-separated",
                                        show_validation=False,
                                    ),
                                ],
                                width=6,
                                className="mb-3",
                            ),
                        ]
                    ),
                    # Advanced Settings Accordion
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
                                _create_llm_settings_legacy(),
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


def _create_llm_settings_legacy() -> html.Div:
    """Create LLM settings form fields (legacy version for backward compatibility)."""
    return html.Div(
        [
            dbc.Row(
                [
                    dbc.Col(
                        create_select_with_label(
                            select_id="select-llm-provider",
                            label="Provider",
                            options=LLM_PROVIDERS,
                            value=DEFAULT_LLM_PROVIDER,
                        ),
                        width=6,
                    ),
                    dbc.Col(
                        create_text_input_with_label(
                            input_id="input-llm-model",
                            label="Model (optional)",
                            placeholder="Use default",
                            show_validation=False,
                        ),
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
