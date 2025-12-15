"""
Data Provider Factory.

Creates and configures data provider instances based on application settings.
Includes caching layer to reduce API calls and improve performance.
"""

import asyncio
import hashlib
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import date
from functools import wraps
from typing import Any, Callable, TypeVar

from app.core.config import DataProvider as DataProviderEnum
from app.core.config import Settings
from app.providers.data.base import (
    CurrentPrice,
    DataProvider,
    DataProviderError,
    Exchange,
    PriceData,
    TickerInfo,
)
from app.providers.data.kis import KISDataProvider
from app.providers.data.mock import MockDataProvider
from app.providers.data.yfinance import YFinanceDataProvider

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Type alias for provider factory functions
ProviderFactory = Callable[[Settings], DataProvider]


@dataclass
class CacheEntry:
    """Represents a cached value with expiration."""

    value: Any
    expires_at: float
    created_at: float = field(default_factory=time.time)

    def is_expired(self) -> bool:
        """Check if the cache entry has expired."""
        return time.time() > self.expires_at


class LRUCache:
    """
    Least Recently Used (LRU) cache with TTL support.

    Thread-safe cache implementation with automatic expiration.
    """

    def __init__(self, max_size: int = 1000, default_ttl: int = 300):
        """
        Initialize the LRU cache.

        Args:
            max_size: Maximum number of entries to store
            default_ttl: Default TTL in seconds
        """
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._lock = asyncio.Lock()

    def _make_key(self, *args: Any, **kwargs: Any) -> str:
        """Create a cache key from arguments."""
        key_data = str(args) + str(sorted(kwargs.items()))
        return hashlib.md5(key_data.encode(), usedforsecurity=False).hexdigest()

    async def get(self, key: str) -> tuple[bool, Any]:
        """
        Get a value from the cache.

        Args:
            key: Cache key

        Returns:
            Tuple of (found, value)
        """
        async with self._lock:
            if key not in self._cache:
                return False, None

            entry = self._cache[key]
            if entry.is_expired():
                del self._cache[key]
                return False, None

            # Move to end (most recently used)
            self._cache.move_to_end(key)
            return True, entry.value

    async def set(
        self,
        key: str,
        value: Any,
        ttl: int | None = None,
    ) -> None:
        """
        Set a value in the cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl: TTL in seconds (uses default if None)
        """
        ttl = ttl if ttl is not None else self._default_ttl
        expires_at = time.time() + ttl

        async with self._lock:
            # If key exists, update and move to end
            if key in self._cache:
                self._cache[key] = CacheEntry(value=value, expires_at=expires_at)
                self._cache.move_to_end(key)
            else:
                # Evict oldest if at capacity
                while len(self._cache) >= self._max_size:
                    self._cache.popitem(last=False)

                self._cache[key] = CacheEntry(value=value, expires_at=expires_at)

    async def delete(self, key: str) -> bool:
        """
        Delete a value from the cache.

        Args:
            key: Cache key

        Returns:
            True if key was deleted, False if not found
        """
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    async def clear(self) -> None:
        """Clear all entries from the cache."""
        async with self._lock:
            self._cache.clear()

    async def cleanup_expired(self) -> int:
        """
        Remove all expired entries.

        Returns:
            Number of entries removed
        """
        async with self._lock:
            expired_keys = [
                key for key, entry in self._cache.items() if entry.is_expired()
            ]
            for key in expired_keys:
                del self._cache[key]
            return len(expired_keys)

    @property
    def size(self) -> int:
        """Get current cache size."""
        return len(self._cache)


class CachedDataProvider(DataProvider):
    """
    Wrapper that adds caching to any DataProvider.

    Caches responses from get_daily_prices, get_current_price, and
    get_ticker_info methods to reduce API calls.
    """

    def __init__(
        self,
        provider: DataProvider,
        cache: LRUCache,
        cache_ttl: int = 300,
    ):
        """
        Initialize the cached provider.

        Args:
            provider: Underlying data provider
            cache: LRU cache instance
            cache_ttl: TTL for cached entries in seconds
        """
        self._provider = provider
        self._cache = cache
        self._cache_ttl = cache_ttl

    @property
    def provider_name(self) -> str:
        """Get the provider name."""
        return f"cached_{self._provider.provider_name}"

    @property
    def underlying_provider(self) -> DataProvider:
        """Get the underlying provider."""
        return self._provider

    def _make_cache_key(self, method: str, *args: Any, **kwargs: Any) -> str:
        """Create a cache key for a method call."""
        key_parts = [self._provider.provider_name, method]
        key_parts.extend(str(arg) for arg in args)
        key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
        return hashlib.md5(":".join(key_parts).encode(), usedforsecurity=False).hexdigest()

    async def get_daily_prices(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
        exchange: Exchange | None = None,
    ) -> list[PriceData]:
        """Get daily prices with caching."""
        cache_key = self._make_cache_key(
            "get_daily_prices",
            ticker,
            start_date.isoformat(),
            end_date.isoformat(),
            exchange.value if exchange else None,
        )

        found, cached_value = await self._cache.get(cache_key)
        if found:
            logger.debug(f"Cache hit for daily prices: {ticker}")
            return cached_value

        logger.debug(f"Cache miss for daily prices: {ticker}")
        result = await self._provider.get_daily_prices(
            ticker, start_date, end_date, exchange
        )
        await self._cache.set(cache_key, result, self._cache_ttl)
        return result

    async def get_current_price(
        self,
        ticker: str,
        exchange: Exchange | None = None,
    ) -> CurrentPrice:
        """Get current price with shorter cache TTL."""
        # Current price has shorter TTL (30 seconds)
        current_price_ttl = min(30, self._cache_ttl)

        cache_key = self._make_cache_key(
            "get_current_price",
            ticker,
            exchange.value if exchange else None,
        )

        found, cached_value = await self._cache.get(cache_key)
        if found:
            logger.debug(f"Cache hit for current price: {ticker}")
            return cached_value

        logger.debug(f"Cache miss for current price: {ticker}")
        result = await self._provider.get_current_price(ticker, exchange)
        await self._cache.set(cache_key, result, current_price_ttl)
        return result

    async def get_ticker_info(
        self,
        ticker: str,
        exchange: Exchange | None = None,
    ) -> TickerInfo:
        """Get ticker info with caching (longer TTL for static data)."""
        # Ticker info rarely changes, use longer TTL (1 hour)
        ticker_info_ttl = max(3600, self._cache_ttl)

        cache_key = self._make_cache_key(
            "get_ticker_info",
            ticker,
            exchange.value if exchange else None,
        )

        found, cached_value = await self._cache.get(cache_key)
        if found:
            logger.debug(f"Cache hit for ticker info: {ticker}")
            return cached_value

        logger.debug(f"Cache miss for ticker info: {ticker}")
        result = await self._provider.get_ticker_info(ticker, exchange)
        await self._cache.set(cache_key, result, ticker_info_ttl)
        return result

    async def get_available_date_range(
        self,
        ticker: str,
        exchange: Exchange | None = None,
    ):
        """Get available date range with caching."""
        cache_key = self._make_cache_key(
            "get_available_date_range",
            ticker,
            exchange.value if exchange else None,
        )

        found, cached_value = await self._cache.get(cache_key)
        if found:
            return cached_value

        result = await self._provider.get_available_date_range(ticker, exchange)
        await self._cache.set(cache_key, result, self._cache_ttl)
        return result

    async def health_check(self) -> bool:
        """Check provider health."""
        return await self._provider.health_check()

    async def close(self) -> None:
        """Close the underlying provider."""
        await self._provider.close()

    def detect_exchange(self, ticker: str) -> Exchange:
        """Detect exchange using underlying provider."""
        return self._provider.detect_exchange(ticker)


# Registry of provider factories
_PROVIDER_REGISTRY: dict[DataProviderEnum, ProviderFactory] = {}


def _create_kis_provider(settings: Settings) -> DataProvider:
    """Create KIS data provider."""
    kis_config = settings.get_kis_config()
    is_paper = settings.data.is_paper
    logger.info(f"Creating KIS provider with is_paper={is_paper}")
    return KISDataProvider(
        config=kis_config,
        is_paper=is_paper,
    )


def _create_yfinance_provider(settings: Settings) -> DataProvider:
    """Create YFinance data provider."""
    return YFinanceDataProvider()


def _create_mock_provider(settings: Settings) -> DataProvider:
    """Create Mock data provider."""
    return MockDataProvider()


# Initialize registry
_PROVIDER_REGISTRY = {
    DataProviderEnum.KIS: _create_kis_provider,
    DataProviderEnum.YFINANCE: _create_yfinance_provider,
    DataProviderEnum.MOCK: _create_mock_provider,
}


class DataProviderFactory:
    """
    Factory for creating data provider instances.

    Uses the configured provider setting to instantiate the appropriate
    adapter class. Supports caching and extensibility through a registry pattern.

    Example:
        # Create factory with settings
        factory = DataProviderFactory(settings)

        # Get cached provider
        provider = await factory.get_provider()

        # Get specific provider type
        yf_provider = await factory.get_provider(DataProviderEnum.YFINANCE)

        # Clean up
        await factory.close_all()
    """

    def __init__(
        self,
        settings: Settings,
        cache: LRUCache | None = None,
    ):
        """
        Initialize the factory.

        Args:
            settings: Application settings
            cache: Optional shared cache instance
        """
        self._settings = settings
        self._cache = cache or LRUCache(
            max_size=1000,
            default_ttl=settings.data.cache_ttl_seconds,
        )
        self._providers: dict[DataProviderEnum, DataProvider] = {}
        self._initialized: dict[DataProviderEnum, bool] = {}

    @staticmethod
    def create_provider(
        provider_type: DataProviderEnum,
        settings: Settings,
    ) -> DataProvider:
        """
        Create a data provider based on type.

        Args:
            provider_type: Provider type enum
            settings: Application settings

        Returns:
            Configured DataProvider instance

        Raises:
            ValueError: If the provider type is not supported
            DataProviderError: If provider creation fails
        """
        factory_func = _PROVIDER_REGISTRY.get(provider_type)
        if factory_func is None:
            supported = [p.value for p in _PROVIDER_REGISTRY.keys()]
            raise ValueError(
                f"Unsupported data provider: '{provider_type.value}'. "
                f"Supported providers: {supported}"
            )

        try:
            return factory_func(settings)
        except Exception as e:
            raise DataProviderError(
                f"Failed to create data provider '{provider_type.value}': {e}",
                provider=provider_type.value,
            ) from e

    async def get_provider(
        self,
        provider_type: DataProviderEnum | None = None,
        use_cache: bool | None = None,
    ) -> DataProvider:
        """
        Get a data provider instance.

        Creates and initializes the provider if not already cached.
        Wraps with caching layer if enabled.

        Args:
            provider_type: Provider type (uses settings default if None)
            use_cache: Whether to use caching (uses settings if None)

        Returns:
            Configured and initialized DataProvider
        """
        if provider_type is None:
            provider_type = self._settings.data.provider

        if use_cache is None:
            use_cache = self._settings.data.enable_caching

        # Check if we already have this provider
        if provider_type not in self._providers:
            provider = self.create_provider(provider_type, self._settings)
            self._providers[provider_type] = provider
            self._initialized[provider_type] = False

        provider = self._providers[provider_type]

        # Initialize if needed
        if not self._initialized.get(provider_type, False):
            if hasattr(provider, "initialize"):
                await provider.initialize()
            self._initialized[provider_type] = True

        # Wrap with cache if enabled and not already wrapped
        if use_cache and not isinstance(provider, CachedDataProvider):
            cached_provider = CachedDataProvider(
                provider=provider,
                cache=self._cache,
                cache_ttl=self._settings.data.cache_ttl_seconds,
            )
            return cached_provider

        return provider

    async def get_all_providers(
        self,
        use_cache: bool | None = None,
    ) -> list[DataProvider]:
        """
        Get all configured providers (primary + fallbacks).

        Args:
            use_cache: Whether to use caching

        Returns:
            List of DataProvider instances
        """
        provider_types = self._settings.data.get_all_providers()
        providers = []

        for pt in provider_types:
            try:
                provider = await self.get_provider(pt, use_cache)
                providers.append(provider)
            except Exception as e:
                logger.warning(f"Failed to create provider {pt.value}: {e}")

        return providers

    async def close_all(self) -> None:
        """Close all created providers."""
        for provider_type, provider in self._providers.items():
            try:
                await provider.close()
            except Exception as e:
                logger.warning(f"Error closing provider {provider_type.value}: {e}")

        self._providers.clear()
        self._initialized.clear()
        await self._cache.clear()

    async def clear_cache(self) -> None:
        """Clear the provider cache."""
        await self._cache.clear()

    @staticmethod
    def register(
        provider_type: DataProviderEnum,
        factory_func: ProviderFactory,
    ) -> None:
        """
        Register a new provider factory.

        Args:
            provider_type: Provider enum value to register
            factory_func: Factory function that creates the provider
        """
        _PROVIDER_REGISTRY[provider_type] = factory_func

    @staticmethod
    def unregister(provider_type: DataProviderEnum) -> bool:
        """
        Unregister a provider factory.

        Args:
            provider_type: Provider enum value to unregister

        Returns:
            True if provider was unregistered, False if not found
        """
        if provider_type in _PROVIDER_REGISTRY:
            del _PROVIDER_REGISTRY[provider_type]
            return True
        return False

    @staticmethod
    def get_supported_providers() -> list[str]:
        """
        Get list of supported provider names.

        Returns:
            List of provider name strings
        """
        return [p.value for p in _PROVIDER_REGISTRY.keys()]

    @staticmethod
    def is_provider_supported(provider_type: DataProviderEnum) -> bool:
        """
        Check if a provider is supported.

        Args:
            provider_type: Provider enum value to check

        Returns:
            True if provider is supported
        """
        return provider_type in _PROVIDER_REGISTRY


# Convenience function for simple use cases
async def get_data_provider(settings: Settings | None = None) -> DataProvider:
    """
    Get the default data provider based on settings.

    Convenience function for simple use cases.

    Args:
        settings: Application settings (loads from config if None)

    Returns:
        Configured DataProvider instance
    """
    if settings is None:
        from app.core.config import get_settings

        settings = get_settings()

    factory = DataProviderFactory(settings)
    return await factory.get_provider()
