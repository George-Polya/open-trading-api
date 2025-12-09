"""
Dependency Injection Container for the backtesting service.

Provides lazy initialization of shared resources using lru_cache.
Ensures singletons are created once during startup and shared across
FastAPI dependencies.
"""

from functools import lru_cache
from typing import TYPE_CHECKING

import httpx

from app.core.config import Settings, get_settings

if TYPE_CHECKING:
    from app.core.config import Settings


class Container:
    """
    Dependency Injection Container.

    Manages lifecycle of shared resources:
    - Settings (configuration)
    - HTTP Client (httpx.AsyncClient)
    - Future: LLM providers, Data providers, etc.

    Usage:
        container = get_container()
        settings = container.settings
        http_client = container.get_http_client()
    """

    def __init__(self, settings: Settings | None = None):
        """
        Initialize the container.

        Args:
            settings: Optional settings override. If None, loads from config.
        """
        self._settings = settings
        self._http_client: httpx.AsyncClient | None = None

    @property
    def settings(self) -> Settings:
        """
        Get the application settings.

        Returns:
            Cached Settings instance.
        """
        if self._settings is None:
            self._settings = get_settings()
        return self._settings

    def get_http_client(self) -> httpx.AsyncClient:
        """
        Get or create the shared HTTP client.

        The client is lazily initialized on first access.
        Call close_http_client() during shutdown to properly close connections.

        Returns:
            Shared httpx.AsyncClient instance.
        """
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(120.0),
                limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
            )
        return self._http_client

    async def close_http_client(self) -> None:
        """
        Close the HTTP client.

        Should be called during application shutdown to properly release
        resources and close connections.
        """
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    async def startup(self) -> None:
        """
        Initialize resources on application startup.

        Called by FastAPI lifespan context manager.
        """
        # Pre-initialize settings to catch config errors early
        _ = self.settings
        # Pre-initialize HTTP client
        _ = self.get_http_client()

    async def shutdown(self) -> None:
        """
        Clean up resources on application shutdown.

        Called by FastAPI lifespan context manager.
        """
        await self.close_http_client()


# Global container instance using lru_cache for singleton behavior
@lru_cache
def get_container() -> Container:
    """
    Get the cached container instance.

    Uses lru_cache to ensure container is a singleton.
    Call get_container.cache_clear() to reset (useful for testing).

    Returns:
        Cached Container instance.
    """
    return Container()


def clear_container_cache() -> None:
    """
    Clear the container cache.

    Useful for testing to reset the container state.
    Also clears the settings cache.
    """
    get_container.cache_clear()
    get_settings.cache_clear()


# Convenience functions for FastAPI dependencies
def get_settings_dep() -> Settings:
    """
    FastAPI dependency for getting settings.

    Usage:
        @app.get("/")
        async def root(settings: Settings = Depends(get_settings_dep)):
            ...
    """
    return get_container().settings


def get_http_client_dep() -> httpx.AsyncClient:
    """
    FastAPI dependency for getting the HTTP client.

    Usage:
        @app.get("/")
        async def root(client: httpx.AsyncClient = Depends(get_http_client_dep)):
            ...
    """
    return get_container().get_http_client()
