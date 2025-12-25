"""
FastAPI Application Entry Point.

Natural Language Backtesting Service with AI-Generated Code.
"""

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from starlette.middleware.wsgi import WSGIMiddleware

from app.core.config import Settings
from app.core.container import Container, get_container, get_settings_dep

logger = logging.getLogger(__name__)


class HealthResponse(BaseModel):
    """Health check response model."""

    status: str
    app_name: str
    app_version: str
    timestamp: str
    debug: bool
    llm_provider: str
    data_provider: str
    execution_provider: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan context manager.

    Handles startup and shutdown events:
    - Startup: Initialize container, pre-load settings, create HTTP client
    - Shutdown: Close HTTP client and release resources
    """
    # Startup
    container = get_container()
    await container.startup()

    yield

    # Shutdown
    await container.shutdown()


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application instance.
    """
    settings = get_container().settings

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "AI-powered natural language backtesting service. "
            "Describe your investment strategy in natural language, "
            "and AI will generate Python code to backtest it."
        ),
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        lifespan=lifespan,
    )

    # Configure CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.debug else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routes
    register_routes(app)

    return app


def mount_dashboard(app: FastAPI) -> None:
    """
    Mount the Dash dashboard application onto FastAPI.

    The dashboard is available at /dashboard/ and provides
    a web-based UI for the backtest service.

    Args:
        app: FastAPI application instance.
    """
    try:
        from app.dashboard.app import create_dash_app

        # Redirect /dashboard -> /dashboard/ using middleware (runs before routing)
        @app.middleware("http")
        async def redirect_dashboard_middleware(request, call_next):
            if request.url.path == "/dashboard":
                return RedirectResponse(url="/dashboard/", status_code=301)
            return await call_next(request)

        # Create Dash app with correct path prefix
        dash_app = create_dash_app(requests_pathname_prefix="/dashboard/")

        # Mount Dash app via WSGI middleware
        app.mount("/dashboard", WSGIMiddleware(dash_app.server))

        logger.info("Dashboard mounted at /dashboard/")

    except ImportError as e:
        logger.warning(
            f"Dashboard dependencies not installed: {e}. "
            "Install dash and dash-bootstrap-components to enable the dashboard."
        )
    except Exception as e:
        logger.exception(f"Failed to mount dashboard: {e}")


def register_routes(app: FastAPI) -> None:
    """
    Register all application routes.

    Args:
        app: FastAPI application instance.
    """
    # Import and register API v1 router
    from app.api.v1 import api_router

    app.include_router(
        api_router,
        prefix="/api/v1",
        tags=["API v1"],
    )

    # Mount Dash dashboard
    mount_dashboard(app)

    @app.get(
        "/health",
        response_model=HealthResponse,
        tags=["Health"],
        summary="Health Check",
        description="Check if the service is running and return configuration metadata.",
    )
    async def health_check(
        settings: Settings = Depends(get_settings_dep),
    ) -> HealthResponse:
        """
        Health check endpoint for readiness probes.

        Returns service status and configuration metadata.
        """
        return HealthResponse(
            status="healthy",
            app_name=settings.app_name,
            app_version=settings.app_version,
            timestamp=datetime.now(timezone.utc).isoformat(),
            debug=settings.debug,
            llm_provider=settings.llm.provider.value,
            data_provider=settings.data.provider.value,
            execution_provider=settings.execution.provider.value,
        )

    @app.get(
        "/",
        tags=["Root"],
        summary="Root",
        description="Root endpoint returning service information.",
    )
    async def root(
        settings: Settings = Depends(get_settings_dep),
    ) -> dict[str, Any]:
        """
        Root endpoint.

        Returns basic service information.
        """
        return {
            "service": settings.app_name,
            "version": settings.app_version,
            "docs": "/docs" if settings.debug else None,
            "health": "/health",
            "dashboard": "/dashboard/",
        }


# Create the application instance
app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
