"""
Fallback Data Provider implementation.

Provides automatic failover mechanism for data providers.
When the primary provider fails, automatically tries fallback providers in order.
"""

import asyncio
import logging
from datetime import date
from typing import TypeVar

from app.core.config import DataConfig, Settings
from app.core.config import DataProvider as DataProviderEnum
from app.providers.data.base import (
    CurrentPrice,
    DataProvider,
    DataProviderError,
    DataUnavailableError,
    DateRange,
    Exchange,
    PriceData,
    RateLimitError,
    TickerInfo,
    TickerNotFoundError,
)
from app.providers.data.factory import DataProviderFactory, LRUCache

logger = logging.getLogger(__name__)

T = TypeVar("T")


class FallbackDataProvider(DataProvider):
    """
    Data provider with automatic fallback support.

    Wraps multiple providers and automatically switches to fallback
    providers when the primary fails. Supports retry logic with
    exponential backoff.

    The fallback mechanism handles:
    - DataProviderError: Transient errors, tries fallback
    - RateLimitError: Rate limiting, tries fallback after delay
    - DataUnavailableError: Data unavailable, tries fallback
    - TickerNotFoundError: NOT handled - propagates immediately

    Example:
        settings = get_settings()
        fallback_provider = await FallbackDataProvider.from_settings(settings)

        # Will automatically try fallback providers if primary fails
        prices = await fallback_provider.get_daily_prices(
            "AAPL",
            date(2024, 1, 1),
            date(2024, 3, 31)
        )
    """

    # Errors that should NOT trigger fallback (permanent failures)
    NON_FALLBACK_ERRORS = (TickerNotFoundError,)

    def __init__(
        self,
        providers: list[DataProvider],
        retry_attempts: int = 3,
        retry_delay: float = 1.0,
        retry_backoff: float = 2.0,
    ):
        """
        Initialize the fallback provider.

        Args:
            providers: List of providers in priority order (primary first)
            retry_attempts: Number of retry attempts per provider
            retry_delay: Initial delay between retries in seconds
            retry_backoff: Multiplier for exponential backoff
        """
        if not providers:
            raise ValueError("At least one provider must be provided")

        self._providers = providers
        self._retry_attempts = retry_attempts
        self._retry_delay = retry_delay
        self._retry_backoff = retry_backoff
        self._last_successful_provider: DataProvider | None = None

    @property
    def provider_name(self) -> str:
        """Get the provider name."""
        return "fallback"

    @property
    def primary_provider(self) -> DataProvider:
        """Get the primary (first) provider."""
        return self._providers[0]

    @property
    def providers(self) -> list[DataProvider]:
        """Get all providers."""
        return self._providers.copy()

    @property
    def last_successful_provider(self) -> DataProvider | None:
        """Get the last provider that successfully returned data."""
        return self._last_successful_provider

    async def _execute_with_fallback(
        self,
        method_name: str,
        *args,
        **kwargs,
    ):
        """
        Execute a method with fallback support.

        Tries each provider in order. For each provider:
        1. Attempts the call with retry logic
        2. If all retries fail, moves to next provider
        3. If all providers fail, raises the last error

        Args:
            method_name: Name of the method to call
            *args: Positional arguments for the method
            **kwargs: Keyword arguments for the method

        Returns:
            Result from the first successful provider

        Raises:
            DataProviderError: If all providers fail
            TickerNotFoundError: If ticker is not found (no fallback)
        """
        last_error: Exception | None = None
        errors_by_provider: dict[str, str] = {}

        for provider in self._providers:
            provider_name = provider.provider_name
            method = getattr(provider, method_name, None)

            if method is None:
                logger.warning(
                    f"Provider {provider_name} does not have method {method_name}"
                )
                continue

            # Try with retries
            for attempt in range(self._retry_attempts):
                try:
                    result = await method(*args, **kwargs)
                    self._last_successful_provider = provider

                    if attempt > 0 or provider != self._providers[0]:
                        logger.info(
                            f"Successfully retrieved data from {provider_name} "
                            f"(attempt {attempt + 1})"
                        )

                    return result

                except self.NON_FALLBACK_ERRORS as e:
                    # These errors should not trigger fallback
                    logger.debug(
                        f"Non-fallback error from {provider_name}: {e}"
                    )
                    raise

                except RateLimitError as e:
                    last_error = e
                    wait_time = e.retry_after or (
                        self._retry_delay * (self._retry_backoff**attempt)
                    )
                    logger.warning(
                        f"Rate limit hit on {provider_name}, "
                        f"waiting {wait_time:.1f}s before retry"
                    )
                    if attempt < self._retry_attempts - 1:
                        await asyncio.sleep(wait_time)
                    else:
                        errors_by_provider[provider_name] = str(e)
                        break

                except (DataProviderError, DataUnavailableError) as e:
                    last_error = e
                    logger.warning(
                        f"Error from {provider_name} (attempt {attempt + 1}): {e}"
                    )

                    if attempt < self._retry_attempts - 1:
                        delay = self._retry_delay * (self._retry_backoff**attempt)
                        await asyncio.sleep(delay)
                    else:
                        errors_by_provider[provider_name] = str(e)
                        break

                except Exception as e:
                    last_error = e
                    logger.error(
                        f"Unexpected error from {provider_name}: {e}",
                        exc_info=True,
                    )
                    errors_by_provider[provider_name] = str(e)
                    break

        # All providers failed
        error_summary = "; ".join(
            f"{p}: {e}" for p, e in errors_by_provider.items()
        )
        raise DataProviderError(
            f"All providers failed for {method_name}. Errors: {error_summary}",
            provider=self.provider_name,
        )

    async def get_daily_prices(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
        exchange: Exchange | None = None,
    ) -> list[PriceData]:
        """Get daily prices with fallback support."""
        return await self._execute_with_fallback(
            "get_daily_prices",
            ticker,
            start_date,
            end_date,
            exchange,
        )

    async def get_current_price(
        self,
        ticker: str,
        exchange: Exchange | None = None,
    ) -> CurrentPrice:
        """Get current price with fallback support."""
        return await self._execute_with_fallback(
            "get_current_price",
            ticker,
            exchange,
        )

    async def get_ticker_info(
        self,
        ticker: str,
        exchange: Exchange | None = None,
    ) -> TickerInfo:
        """Get ticker info with fallback support."""
        return await self._execute_with_fallback(
            "get_ticker_info",
            ticker,
            exchange,
        )

    async def get_available_date_range(
        self,
        ticker: str,
        exchange: Exchange | None = None,
    ) -> DateRange:
        """Get available date range with fallback support."""
        return await self._execute_with_fallback(
            "get_available_date_range",
            ticker,
            exchange,
        )

    def detect_exchange(self, ticker: str) -> Exchange:
        """Detect exchange using primary provider."""
        return self._providers[0].detect_exchange(ticker)

    async def health_check(self) -> bool:
        """
        Check if at least one provider is healthy.

        Returns:
            True if at least one provider is healthy
        """
        for provider in self._providers:
            try:
                if await provider.health_check():
                    return True
            except Exception:
                continue
        return False

    async def close(self) -> None:
        """Close all providers."""
        for provider in self._providers:
            try:
                await provider.close()
            except Exception as e:
                logger.warning(
                    f"Error closing provider {provider.provider_name}: {e}"
                )

    @classmethod
    async def from_settings(
        cls,
        settings: Settings,
        cache: LRUCache | None = None,
    ) -> "FallbackDataProvider":
        """
        Create a FallbackDataProvider from settings.

        Creates and initializes all configured providers.

        Args:
            settings: Application settings
            cache: Optional shared cache for providers

        Returns:
            Configured FallbackDataProvider instance
        """
        factory = DataProviderFactory(settings, cache=cache)
        providers = await factory.get_all_providers(
            use_cache=settings.data.enable_caching
        )

        if not providers:
            raise DataProviderError(
                "No providers could be created from settings",
                provider="fallback",
            )

        return cls(
            providers=providers,
            retry_attempts=settings.data.retry_attempts,
            retry_delay=settings.data.retry_delay_seconds,
        )

    @classmethod
    async def from_providers(
        cls,
        provider_types: list[DataProviderEnum],
        settings: Settings,
        cache: LRUCache | None = None,
    ) -> "FallbackDataProvider":
        """
        Create a FallbackDataProvider from specific provider types.

        Args:
            provider_types: List of provider types in priority order
            settings: Application settings
            cache: Optional shared cache for providers

        Returns:
            Configured FallbackDataProvider instance
        """
        factory = DataProviderFactory(settings, cache=cache)
        providers = []

        for pt in provider_types:
            try:
                provider = await factory.get_provider(
                    pt, use_cache=settings.data.enable_caching
                )
                providers.append(provider)
            except Exception as e:
                logger.warning(f"Failed to create provider {pt.value}: {e}")

        if not providers:
            raise DataProviderError(
                f"No providers could be created from {provider_types}",
                provider="fallback",
            )

        return cls(
            providers=providers,
            retry_attempts=settings.data.retry_attempts,
            retry_delay=settings.data.retry_delay_seconds,
        )


# Convenience function
async def get_resilient_data_provider(
    settings: Settings | None = None,
) -> FallbackDataProvider:
    """
    Get a data provider with automatic fallback support.

    Convenience function that creates a FallbackDataProvider
    with all configured providers.

    Args:
        settings: Application settings (loads from config if None)

    Returns:
        Configured FallbackDataProvider instance
    """
    if settings is None:
        from app.core.config import get_settings

        settings = get_settings()

    return await FallbackDataProvider.from_settings(settings)
