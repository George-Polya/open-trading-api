"""
API v1 package.

Exports the main API router that aggregates all v1 endpoints.
"""

from fastapi import APIRouter

from app.api.v1.endpoints import backtest

# Create the main v1 router
api_router = APIRouter()

# Include all endpoint routers
api_router.include_router(backtest.router)

__all__ = ["api_router"]
