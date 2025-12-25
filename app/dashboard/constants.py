"""
Dashboard Constants Module.

Centralizes all styling constants, magic numbers, and configuration values
used across dashboard components for maintainability and consistency.
"""

from typing import Any

# =============================================================================
# LAYOUT CONSTANTS
# =============================================================================

LAYOUT = {
    # Column widths (Bootstrap 12-column grid)
    "CONFIG_COLUMN_WIDTH_LG": 3,  # 25% on large screens
    "CONFIG_COLUMN_WIDTH_MD": 4,  # 33% on medium screens
    "RESULTS_COLUMN_WIDTH_LG": 9,  # 75% on large screens
    "RESULTS_COLUMN_WIDTH_MD": 8,  # 67% on medium screens
    # Polling
    "POLLING_INTERVAL_MS": 2000,
    # Grid gaps
    "ROW_GAP": 4,  # Bootstrap g-4
    "COLUMN_GAP": 3,  # Bootstrap spacing
}

# =============================================================================
# COMPONENT HEIGHTS
# =============================================================================

HEIGHTS = {
    # Code viewer
    "CODE_VIEWER_MIN": "350px",
    "CODE_VIEWER_MAX": "500px",
    "CODE_TEXTAREA_ROWS": 6,
    # Charts
    "CHART_DEFAULT": "350px",
    "CHART_COMPACT": "280px",
    "CHART_COMBINED_MAIN": "250px",
    "CHART_COMBINED_SUB": "150px",
    # Trade table
    "TRADE_TABLE_MAX": "300px",
    "TRADE_TABLE_INLINE_ROWS": 10,
    # Strategy textarea
    "STRATEGY_TEXTAREA_ROWS": 6,
}

# =============================================================================
# COLORS (Bootstrap + Custom)
# =============================================================================

COLORS = {
    # Bootstrap theme colors
    "primary": "#0d6efd",
    "success": "#198754",
    "danger": "#dc3545",
    "warning": "#ffc107",
    "info": "#0dcaf0",
    "secondary": "#6c757d",
    "light": "#f8f9fa",
    "dark": "#212529",
    # Chart-specific
    "benchmark": "#6c757d",
    "positive": "#198754",
    "negative": "#dc3545",
    # Metric card backgrounds
    "metric_primary_bg": "rgba(13, 110, 253, 0.08)",
    "metric_secondary_bg": "rgba(108, 117, 125, 0.04)",
    # Code viewer
    "code_bg_dark": "#1e1e1e",
    "code_bg_light": "#f8f9fa",
}

# =============================================================================
# VALIDATION CONSTANTS
# =============================================================================

VALIDATION = {
    # Strategy
    "MIN_STRATEGY_LENGTH": 10,
    "MAX_STRATEGY_LENGTH": 10000,
    # Capital
    "MIN_CAPITAL": 1000,
    "CAPITAL_STEP": 1000,
    "DEFAULT_CAPITAL": 100000,
    # Dates
    "MIN_DATE_YEAR": 2001,
    "DEFAULT_LOOKBACK_YEARS": 3,
    # Contribution
    "MIN_CONTRIBUTION": 0,
    "CONTRIBUTION_STEP": 100,
    "DEFAULT_CONTRIBUTION": 0,
    # Fees
    "MIN_FEE": 0,
    "MAX_FEE": 10,
    "FEE_STEP": 0.01,
    "DEFAULT_TRADING_FEE": 0.1,
    "DEFAULT_SLIPPAGE": 0.05,
    # API timeouts
    "API_TIMEOUT_GENERATE": 300,
    "API_TIMEOUT_EXECUTE": 30,
    "API_TIMEOUT_STATUS": 10,
}

# =============================================================================
# METRIC CONFIGURATION
# =============================================================================

# Primary metrics (emphasized, shown larger)
PRIMARY_METRICS = [
    {
        "key": "total_return",
        "title": "Total Return",
        "icon": "fas fa-percentage",
        "format": "{:.2f}%",
        "show_benchmark": True,
    },
    {
        "key": "cagr",
        "title": "CAGR",
        "icon": "fas fa-chart-line",
        "format": "{:.2f}%",
        "show_benchmark": True,
    },
    {
        "key": "max_drawdown",
        "title": "Max Drawdown",
        "icon": "fas fa-arrow-down",
        "format": "{:.2f}%",
        "always_negative_color": True,
        "show_benchmark": True,
    },
]

# Secondary metrics (subdued, shown smaller)
SECONDARY_METRICS = [
    {
        "key": "sharpe_ratio",
        "title": "Sharpe Ratio",
        "icon": "fas fa-balance-scale",
        "format": "{:.2f}",
        "show_benchmark": False,
    },
    {
        "key": "sortino_ratio",
        "title": "Sortino Ratio",
        "icon": "fas fa-shield-alt",
        "format": "{:.2f}",
        "show_benchmark": False,
    },
    {
        "key": "calmar_ratio",
        "title": "Calmar Ratio",
        "icon": "fas fa-star",
        "format": "{:.2f}",
        "show_benchmark": False,
    },
]

# =============================================================================
# CHART LAYOUT DEFAULTS
# =============================================================================

CHART_LAYOUT_DEFAULTS: dict[str, Any] = {
    "paper_bgcolor": "rgba(0,0,0,0)",
    "plot_bgcolor": "rgba(0,0,0,0)",
    "font": {"family": "system-ui, -apple-system, sans-serif", "size": 12},
    "margin": {"l": 50, "r": 20, "t": 40, "b": 40},
    "hovermode": "x unified",
    "legend": {
        "orientation": "h",
        "yanchor": "bottom",
        "y": 1.02,
        "xanchor": "right",
        "x": 1,
    },
}

# Chart config for interactivity
CHART_CONFIG: dict[str, Any] = {
    "displayModeBar": True,
    "displaylogo": False,
    "modeBarButtonsToRemove": ["select2d", "lasso2d"],
    "scrollZoom": True,
    "responsive": True,
}

# =============================================================================
# LLM PROVIDER OPTIONS
# =============================================================================

LLM_PROVIDERS = [
    {"label": "OpenRouter", "value": "openrouter"},
    {"label": "Anthropic", "value": "anthropic"},
    {"label": "OpenAI", "value": "openai"},
]

DEFAULT_LLM_PROVIDER = "openrouter"

# =============================================================================
# CONTRIBUTION FREQUENCY OPTIONS
# =============================================================================

CONTRIBUTION_FREQUENCIES = [
    {"label": "Monthly", "value": "monthly"},
    {"label": "Quarterly", "value": "quarterly"},
    {"label": "Semi-Annual", "value": "semiannual"},
    {"label": "Annual", "value": "annual"},
]

DEFAULT_CONTRIBUTION_FREQUENCY = "monthly"

# =============================================================================
# STATUS BADGE CONFIGURATION
# =============================================================================

STATUS_BADGES = {
    "pending": {"color": "warning", "icon": "fas fa-clock"},
    "running": {"color": "info", "icon": "fas fa-spinner fa-spin"},
    "completed": {"color": "success", "icon": "fas fa-check"},
    "failed": {"color": "danger", "icon": "fas fa-times"},
}

DEFAULT_STATUS_BADGE = {"color": "secondary", "icon": "fas fa-question"}
