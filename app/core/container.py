"""
Dependency Injection Container for the backtesting service.

Provides lazy initialization of shared resources using lru_cache.
Ensures singletons are created once during startup and shared across
FastAPI dependencies.
"""

from functools import lru_cache
from typing import TYPE_CHECKING

import httpx

from app.core.config import DataProvider as DataProviderEnum
from app.core.config import Settings, get_settings

if TYPE_CHECKING:
    from app.core.config import Settings
    from app.providers.data.base import DataProvider
    from app.providers.llm.base import LLMProvider


class Container:
    """
    Dependency Injection Container.

    Manages lifecycle of shared resources:
    - Settings (configuration)
    - HTTP Client (httpx.AsyncClient)
    - LLM Provider (for code generation)
    - Data Provider (for market data)

    Usage:
        container = get_container()
        settings = container.settings
        http_client = container.get_http_client()
        llm_provider = container.get_llm_provider()
        data_provider = await container.get_data_provider()
    """

    def __init__(self, settings: Settings | None = None):
        """
        Initialize the container.

        Args:
            settings: Optional settings override. If None, loads from config.
        """
        self._settings = settings
        self._http_client: httpx.AsyncClient | None = None
        self._llm_provider: "LLMProvider | None" = None
        self._data_provider: "DataProvider | None" = None

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

    def get_llm_provider(self) -> "LLMProvider":
        """
        Get or create the LLM provider.

        The provider is lazily initialized on first access using the factory.
        Uses settings to determine which provider adapter to create.

        Returns:
            LLMProvider instance (singleton per container)

        Raises:
            ValueError: If the configured provider is not supported
            LLMProviderError: If provider creation fails
        """
        if self._llm_provider is None:
            from app.providers.llm.factory import LLMProviderFactory

            self._llm_provider = LLMProviderFactory.create(settings=self.settings)
        return self._llm_provider

    async def close_llm_provider(self) -> None:
        """
        Close and cleanup the LLM provider.

        Calls the provider's close method if it exists.
        """
        if self._llm_provider is not None:
            await self._llm_provider.close()
            self._llm_provider = None

    async def get_data_provider(self) -> "DataProvider":
        """
        Get or create the data provider.

        The provider is lazily initialized on first access.
        Uses settings to determine which provider to create (KIS, YFinance, etc.).

        Returns:
            DataProvider instance (singleton per container)

        Raises:
            ValueError: If the configured provider is not supported
            DataProviderError: If provider creation fails
        """
        if self._data_provider is None:
            provider_type = self.settings.data.provider

            if provider_type == DataProviderEnum.KIS:
                from app.providers.data.kis import KISDataProvider

                kis_config = self.settings.get_kis_config()
                self._data_provider = KISDataProvider(
                    config=kis_config,
                    is_paper=False,  # Use production by default
                    http_client=self.get_http_client(),
                )
                # Initialize the provider (authenticate)
                await self._data_provider.initialize()

            elif provider_type == DataProviderEnum.MOCK:
                # Mock provider for testing (to be implemented)
                raise NotImplementedError("Mock data provider not yet implemented")

            elif provider_type == DataProviderEnum.YFINANCE:
                # YFinance provider (to be implemented)
                raise NotImplementedError("YFinance data provider not yet implemented")

            else:
                raise ValueError(f"Unsupported data provider: {provider_type}")

        return self._data_provider

    async def close_data_provider(self) -> None:
        """
        Close and cleanup the data provider.

        Calls the provider's close method to release resources.
        """
        if self._data_provider is not None:
            await self._data_provider.close()
            self._data_provider = None

    async def startup(self) -> None:
        """
        Initialize resources on application startup.

        Called by FastAPI lifespan context manager.
        Pre-initializes critical resources and validates configuration.
        """
        # Pre-initialize settings to catch config errors early
        _ = self.settings
        # Pre-initialize HTTP client
        _ = self.get_http_client()
        # Note: LLM provider is lazily initialized on first use
        # to avoid API key validation errors during tests

    async def shutdown(self) -> None:
        """
        Clean up resources on application shutdown.

        Called by FastAPI lifespan context manager.
        """
        await self.close_data_provider()
        await self.close_llm_provider()
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


def get_llm_provider_dep() -> "LLMProvider":
    """
    FastAPI dependency for getting the LLM provider.

    Returns the singleton LLM provider instance from the container.
    The provider type depends on the settings.llm.provider configuration.

    Usage:
        @app.post("/generate")
        async def generate(
            prompt: str,
            llm: LLMProvider = Depends(get_llm_provider_dep)
        ):
            result = await llm.generate(prompt)
            return result

    Returns:
        LLMProvider instance

    Raises:
        ValueError: If the configured provider is not supported
        LLMProviderError: If provider creation fails
    """
    return get_container().get_llm_provider()


async def get_data_provider_dep() -> "DataProvider":
    """
    FastAPI dependency for getting the data provider.

    Returns the singleton data provider instance from the container.
    The provider type depends on the settings.data.provider configuration.

    Usage:
        @app.get("/prices/{ticker}")
        async def get_prices(
            ticker: str,
            data: DataProvider = Depends(get_data_provider_dep)
        ):
            prices = await data.get_daily_prices(ticker, start, end)
            return prices

    Returns:
        DataProvider instance

    Raises:
        ValueError: If the configured provider is not supported
        DataProviderError: If provider creation fails
    """
    return await get_container().get_data_provider()
