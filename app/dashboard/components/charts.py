"""
Performance Visualization Charts (Plotly).

Provides chart creation functions for equity curves, drawdowns,
asset allocation, and monthly returns heatmaps.

Uses centralized constants from app.dashboard.constants for consistency.
"""

from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from app.dashboard.constants import CHART_LAYOUT_DEFAULTS, COLORS

# Local reference to layout defaults for backward compatibility
LAYOUT_DEFAULTS = CHART_LAYOUT_DEFAULTS


# Range selector buttons for equity chart
RANGE_SELECTOR_BUTTONS = [
    dict(count=1, label="1M", step="month", stepmode="backward"),
    dict(count=3, label="3M", step="month", stepmode="backward"),
    dict(count=6, label="6M", step="month", stepmode="backward"),
    dict(count=1, label="1Y", step="year", stepmode="backward"),
    dict(count=2, label="2Y", step="year", stepmode="backward"),
    dict(step="all", label="All"),
]


def create_equity_chart(
    df: pd.DataFrame,
    log_scale: bool = False,
    include_benchmark: bool = True,
    benchmark_name: str = "Benchmark",
) -> go.Figure:
    """
    Create an equity curve line chart.

    Args:
        df: DataFrame with columns ['date', 'strategy'] and optionally ['benchmark'].
            - date: Date index or column
            - strategy: Strategy equity values
            - benchmark: Optional benchmark equity values
        log_scale: Whether to use log scale on y-axis.
        include_benchmark: Whether to include benchmark if available.
        benchmark_name: Name to display for benchmark in legend (e.g., "SPY").

    Returns:
        Plotly Figure object for the equity curve.
    """
    fig = go.Figure()

    # Handle both Series and DataFrame inputs
    if isinstance(df, pd.Series):
        dates = df.index
        strategy_values = df.values
        benchmark_values = None
    else:
        dates = df.index if "date" not in df.columns else df["date"]
        strategy_values = df["strategy"] if "strategy" in df.columns else df.iloc[:, 0]
        benchmark_values = (
            df["benchmark"]
            if include_benchmark and "benchmark" in df.columns
            else None
        )

    # Strategy line
    fig.add_trace(
        go.Scatter(
            x=dates,
            y=strategy_values,
            name="Strategy",
            mode="lines",
            line={"color": COLORS["primary"], "width": 2},
            hovertemplate="%{x}<br>Strategy: $%{y:,.0f}<extra></extra>",
        )
    )

    # Benchmark line (if available)
    if benchmark_values is not None:
        fig.add_trace(
            go.Scatter(
                x=dates,
                y=benchmark_values,
                name=benchmark_name,
                mode="lines",
                line={"color": COLORS["benchmark"], "width": 1.5, "dash": "dash"},
                hovertemplate=f"%{{x}}<br>{benchmark_name}: $%{{y:,.0f}}<extra></extra>",
            )
        )

    # Update layout with range selector and interactivity
    fig.update_layout(
        **LAYOUT_DEFAULTS,
        title={"text": "Portfolio Value", "x": 0.5, "xanchor": "center"},
        xaxis={
            "title": "Date",
            "showgrid": True,
            "gridcolor": "#e9ecef",
            "rangeselector": {
                "buttons": RANGE_SELECTOR_BUTTONS,
                "bgcolor": "white",
                "activecolor": COLORS["primary"],
                "font": {"size": 11},
            },
            "rangeslider": {"visible": False},  # Optional: enable for range slider
        },
        yaxis={
            "title": "Portfolio Value ($)",
            "showgrid": True,
            "gridcolor": "#e9ecef",
            "type": "log" if log_scale else "linear",
            "tickformat": "$,.0f",
        },
        dragmode="zoom",  # Enable zoom by default
    )

    return fig


def create_drawdown_chart(df: pd.DataFrame | pd.Series) -> go.Figure:
    """
    Create a drawdown area chart.

    Args:
        df: DataFrame or Series with drawdown values (as negative percentages).

    Returns:
        Plotly Figure object for the drawdown chart.
    """
    fig = go.Figure()

    # Handle both Series and DataFrame inputs
    if isinstance(df, pd.Series):
        dates = df.index
        values = df.values
    else:
        dates = df.index if "date" not in df.columns else df["date"]
        values = df["drawdown"] if "drawdown" in df.columns else df.iloc[:, 0]

    # Drawdown area
    fig.add_trace(
        go.Scatter(
            x=dates,
            y=values,
            name="Drawdown",
            mode="lines",
            fill="tozeroy",
            line={"color": COLORS["danger"], "width": 1},
            fillcolor="rgba(220, 53, 69, 0.3)",
            hovertemplate="%{x}<br>Drawdown: %{y:.2f}%<extra></extra>",
        )
    )

    # Add max drawdown annotation
    min_idx = np.argmin(values)
    min_value = values[min_idx]
    min_date = dates[min_idx] if hasattr(dates, "__getitem__") else dates

    fig.add_annotation(
        x=min_date,
        y=min_value,
        text=f"Max DD: {min_value:.1f}%",
        showarrow=True,
        arrowhead=2,
        arrowsize=1,
        arrowwidth=1,
        arrowcolor=COLORS["danger"],
        ax=30,
        ay=-30,
        font={"color": COLORS["danger"], "size": 10},
    )

    # Update layout
    fig.update_layout(
        **LAYOUT_DEFAULTS,
        title={"text": "Drawdown", "x": 0.5, "xanchor": "center"},
        xaxis={"title": "Date", "showgrid": True, "gridcolor": "#e9ecef"},
        yaxis={
            "title": "Drawdown (%)",
            "showgrid": True,
            "gridcolor": "#e9ecef",
            "tickformat": ".1f",
            "ticksuffix": "%",
        },
        showlegend=False,
    )

    return fig


def create_asset_allocation_chart(df: pd.DataFrame) -> go.Figure:
    """
    Create a stacked area chart for asset allocation over time.

    Args:
        df: DataFrame with date index and columns for each asset's allocation
            (values should be percentages summing to 100).

    Returns:
        Plotly Figure object for the asset allocation chart.
    """
    fig = go.Figure()

    # Generate colors for assets
    colors = [
        COLORS["primary"],
        COLORS["success"],
        COLORS["warning"],
        COLORS["info"],
        COLORS["danger"],
        COLORS["secondary"],
        "#9b59b6",  # purple
        "#1abc9c",  # teal
        "#e67e22",  # orange
        "#34495e",  # dark blue-grey
    ]

    # Add traces for each asset
    for i, col in enumerate(df.columns):
        color = colors[i % len(colors)]
        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df[col],
                name=col,
                mode="lines",
                stackgroup="one",
                line={"width": 0.5, "color": color},
                fillcolor=color,
                hovertemplate=f"%{{x}}<br>{col}: %{{y:.1f}}%<extra></extra>",
            )
        )

    # Update layout (override legend from defaults)
    layout_config = {k: v for k, v in LAYOUT_DEFAULTS.items() if k != "legend"}
    fig.update_layout(
        **layout_config,
        title={"text": "Asset Allocation", "x": 0.5, "xanchor": "center"},
        xaxis={"title": "Date", "showgrid": True, "gridcolor": "#e9ecef"},
        yaxis={
            "title": "Allocation (%)",
            "showgrid": True,
            "gridcolor": "#e9ecef",
            "range": [0, 100],
            "tickformat": ".0f",
            "ticksuffix": "%",
        },
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "center",
            "x": 0.5,
        },
    )

    return fig


def create_monthly_heatmap(df: pd.DataFrame) -> go.Figure:
    """
    Create a monthly returns heatmap.

    Args:
        df: DataFrame with years as index and months (1-12) as columns,
            or MonthlyHeatmapData-like structure with years, months, returns.

    Returns:
        Plotly Figure object for the monthly returns heatmap.
    """
    # Handle different input formats
    if hasattr(df, "years") and hasattr(df, "returns"):
        # MonthlyHeatmapData-like object
        years = df.years
        months = getattr(df, "months", [
            "Jan", "Feb", "Mar", "Apr", "May", "Jun",
            "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
        ])
        z_values = df.returns
    else:
        # DataFrame format
        years = list(df.index)
        months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        z_values = df.values.tolist()

    # Create heatmap
    fig = go.Figure(
        data=go.Heatmap(
            z=z_values,
            x=months,
            y=years,
            colorscale=[
                [0.0, COLORS["danger"]],
                [0.5, COLORS["light"]],
                [1.0, COLORS["success"]],
            ],
            zmid=0,  # Center color scale at 0
            text=[[f"{v:.1f}%" if v is not None else "" for v in row] for row in z_values],
            texttemplate="%{text}",
            textfont={"size": 10},
            hovertemplate=(
                "Year: %{y}<br>"
                "Month: %{x}<br>"
                "Return: %{z:.2f}%<extra></extra>"
            ),
            colorbar={
                "title": "Return (%)",
                "tickformat": ".1f",
                "ticksuffix": "%",
            },
        )
    )

    # Update layout
    fig.update_layout(
        **LAYOUT_DEFAULTS,
        title={"text": "Monthly Returns", "x": 0.5, "xanchor": "center"},
        xaxis={"title": "", "side": "top", "tickangle": 0},
        yaxis={"title": "", "autorange": "reversed"},
    )

    return fig


def create_performance_summary_chart(metrics: dict[str, Any]) -> go.Figure:
    """
    Create a summary chart showing key performance metrics.

    Args:
        metrics: Dictionary containing performance metrics
            (total_return, cagr, max_drawdown, sharpe_ratio, etc.)

    Returns:
        Plotly Figure object with performance summary.
    """
    # Define metrics to display
    metric_configs = [
        ("Total Return", metrics.get("total_return", 0), "%", True),
        ("CAGR", metrics.get("cagr", 0), "%", True),
        ("Max Drawdown", -abs(metrics.get("max_drawdown", 0)), "%", True),
        ("Sharpe Ratio", metrics.get("sharpe_ratio", 0), "", False),
        ("Sortino Ratio", metrics.get("sortino_ratio", 0), "", False),
        ("Calmar Ratio", metrics.get("calmar_ratio", 0), "", False),
    ]

    names = [m[0] for m in metric_configs]
    values = [m[1] for m in metric_configs]
    colors_list = [
        COLORS["success"] if v > 0 else COLORS["danger"]
        for v in values
    ]

    # Create bar chart
    fig = go.Figure(
        data=go.Bar(
            x=names,
            y=values,
            marker_color=colors_list,
            text=[f"{v:.2f}{m[2]}" for v, m in zip(values, metric_configs)],
            textposition="outside",
            hovertemplate="%{x}: %{y:.2f}<extra></extra>",
        )
    )

    # Update layout
    fig.update_layout(
        **LAYOUT_DEFAULTS,
        title={"text": "Performance Summary", "x": 0.5, "xanchor": "center"},
        xaxis={"title": ""},
        yaxis={"title": "Value", "showgrid": True, "gridcolor": "#e9ecef"},
        showlegend=False,
    )

    return fig


def create_combined_chart(
    equity_df: pd.DataFrame,
    drawdown_df: pd.DataFrame | pd.Series,
    log_scale: bool = False,
) -> go.Figure:
    """
    Create a combined chart with equity curve and drawdown as subplots.

    Args:
        equity_df: Equity curve data.
        drawdown_df: Drawdown data.
        log_scale: Whether to use log scale for equity.

    Returns:
        Plotly Figure with subplots.
    """
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        row_heights=[0.7, 0.3],
        subplot_titles=("Portfolio Value", "Drawdown"),
    )

    # Equity curve
    if isinstance(equity_df, pd.Series):
        dates = equity_df.index
        strategy_values = equity_df.values
    else:
        dates = equity_df.index
        strategy_values = (
            equity_df["strategy"]
            if "strategy" in equity_df.columns
            else equity_df.iloc[:, 0]
        )

    fig.add_trace(
        go.Scatter(
            x=dates,
            y=strategy_values,
            name="Strategy",
            mode="lines",
            line={"color": COLORS["primary"], "width": 2},
        ),
        row=1,
        col=1,
    )

    # Drawdown
    if isinstance(drawdown_df, pd.Series):
        dd_dates = drawdown_df.index
        dd_values = drawdown_df.values
    else:
        dd_dates = drawdown_df.index
        dd_values = (
            drawdown_df["drawdown"]
            if "drawdown" in drawdown_df.columns
            else drawdown_df.iloc[:, 0]
        )

    fig.add_trace(
        go.Scatter(
            x=dd_dates,
            y=dd_values,
            name="Drawdown",
            mode="lines",
            fill="tozeroy",
            line={"color": COLORS["danger"], "width": 1},
            fillcolor="rgba(220, 53, 69, 0.3)",
        ),
        row=2,
        col=1,
    )

    # Update layout
    fig.update_layout(
        **LAYOUT_DEFAULTS,
        height=500,
        showlegend=False,
    )

    fig.update_yaxes(
        title_text="Value ($)",
        type="log" if log_scale else "linear",
        row=1,
        col=1,
    )
    fig.update_yaxes(
        title_text="DD (%)",
        tickformat=".1f",
        ticksuffix="%",
        row=2,
        col=1,
    )
    fig.update_xaxes(title_text="Date", row=2, col=1)

    return fig
