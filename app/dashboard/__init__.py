"""
Dash Dashboard Module.

Provides a Python Dash-based frontend for the backtest service.
"""

from app.dashboard.app import create_dash_app, dash_app

__all__ = ["create_dash_app", "dash_app"]
