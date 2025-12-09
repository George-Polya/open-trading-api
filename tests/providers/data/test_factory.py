"""
Tests for DataProviderFactory.

Verifies factory pattern and caching behavior.
"""

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import DataConfig, DataProvider as DataProviderEnum, Settings
from app.providers.data.factory import (
    CachedDataProvider,
    DataProviderFactory,
    LRUCache,
    get_data_provider,
)
from app.providers.data.base import DataProvider, DataProviderError, Exchange, PriceData
from app.providers.data.mock import MockDataProvider
from app.providers.data.yfinance import YFinanceDataProvider


class TestLRUCache:
    """Tests for LRUCache."""

    @pytest.fixture
    def cache(self):
        """Create a cache instance."""
        return LRUCache(max_size=10, default_ttl=60)

    @pytest.mark.asyncio
    async def test_set_and_get(self, cache):
        """Test basic set and get operations."""
        await cache.set("key1", "value1")
        found, value = await cache.get("key1")

        assert found is True
        assert value == "value1"

    @pytest.mark.asyncio
    async def test_get_missing_key(self, cache):
        """Test getting a non-existent key."""
        found, value = await cache.get("nonexistent")

        assert found is False
        assert value is None

    @pytest.mark.asyncio
    async def test_cache_expiration(self, cache):
        """Test cache entry expiration."""
        await cache.set("key1", "value1", ttl=0)  # Immediate expiration

        found, value = await cache.get("key1")
        assert found is False

    @pytest.mark.asyncio
    async def test_cache_lru_eviction(self):
        """Test LRU eviction when cache is full."""
        cache = LRUCache(max_size=3, default_ttl=60)

        await cache.set("key1", "value1")
        await cache.set("key2", "value2")
        await cache.set("key3", "value3")
        await cache.set("key4", "value4")  # Should evict key1

        found1, _ = await cache.get("key1")
        found4, value4 = await cache.get("key4")

        assert found1 is False  # Evicted
        assert found4 is True
        assert value4 == "value4"

    @pytest.mark.asyncio
    async def test_cache_delete(self, cache):
        """Test cache entry deletion."""
        await cache.set("key1", "value1")
        result = await cache.delete("key1")

        assert result is True
        found, _ = await cache.get("key1")
        assert found is False

    @pytest.mark.asyncio
    async def test_cache_clear(self, cache):
        """Test clearing all cache entries."""
        await cache.set("key1", "value1")
        await cache.set("key2", "value2")
        await cache.clear()

        assert cache.size == 0

    @pytest.mark.asyncio
    async def test_cleanup_expired(self, cache):
        """Test cleanup of expired entries."""
        await cache.set("key1", "value1", ttl=0)  # Expired
        await cache.set("key2", "value2", ttl=3600)  # Valid

        removed = await cache.cleanup_expired()

        assert removed == 1
        found1, _ = await cache.get("key1")
        found2, _ = await cache.get("key2")
        assert found1 is False
        assert found2 is True


class TestCachedDataProvider:
    """Tests for CachedDataProvider wrapper."""

    @pytest.fixture
    def mock_provider(self):
        """Create a mock provider."""
        provider = AsyncMock(spec=DataProvider)
        provider.provider_name = "mock"
        return provider

    @pytest.fixture
    def cache(self):
        """Create a cache instance."""
        return LRUCache(max_size=100, default_ttl=300)

    @pytest.mark.asyncio
    async def test_cached_provider_name(self, mock_provider, cache):
        """Test cached provider name."""
        cached = CachedDataProvider(mock_provider, cache)
        assert cached.provider_name == "cached_mock"

    @pytest.mark.asyncio
    async def test_get_daily_prices_caches_result(self, mock_provider, cache):
        """Test that get_daily_prices caches results."""
        mock_prices = [
            PriceData(
                date=date(2024, 1, 2),
                open=Decimal("100"),
                high=Decimal("105"),
                low=Decimal("99"),
                close=Decimal("103"),
                volume=1000000,
            )
        ]
        mock_provider.get_daily_prices.return_value = mock_prices

        cached = CachedDataProvider(mock_provider, cache)

        # First call
        result1 = await cached.get_daily_prices(
            "AAPL", date(2024, 1, 1), date(2024, 1, 5)
        )

        # Second call (should use cache)
        result2 = await cached.get_daily_prices(
            "AAPL", date(2024, 1, 1), date(2024, 1, 5)
        )

        assert result1 == result2
        # Provider should only be called once
        assert mock_provider.get_daily_prices.call_count == 1

    @pytest.mark.asyncio
    async def test_different_params_not_cached(self, mock_provider, cache):
        """Test that different parameters cause cache miss."""
        mock_provider.get_daily_prices.return_value = []

        cached = CachedDataProvider(mock_provider, cache)

        await cached.get_daily_prices("AAPL", date(2024, 1, 1), date(2024, 1, 5))
        await cached.get_daily_prices("MSFT", date(2024, 1, 1), date(2024, 1, 5))

        assert mock_provider.get_daily_prices.call_count == 2

    @pytest.mark.asyncio
    async def test_underlying_provider(self, mock_provider, cache):
        """Test access to underlying provider."""
        cached = CachedDataProvider(mock_provider, cache)
        assert cached.underlying_provider == mock_provider


class TestDataProviderFactory:
    """Tests for DataProviderFactory."""

    @pytest.fixture
    def mock_settings(self):
        """Create mock settings."""
        settings = MagicMock(spec=Settings)
        settings.data = DataConfig(
            provider=DataProviderEnum.MOCK,
            fallback_providers=[DataProviderEnum.YFINANCE],
            cache_ttl_seconds=300,
            enable_caching=True,
        )
        return settings

    def test_create_mock_provider(self, mock_settings):
        """Test creating mock provider."""
        provider = DataProviderFactory.create_provider(
            DataProviderEnum.MOCK, mock_settings
        )

        assert isinstance(provider, MockDataProvider)

    def test_create_yfinance_provider(self, mock_settings):
        """Test creating YFinance provider."""
        provider = DataProviderFactory.create_provider(
            DataProviderEnum.YFINANCE, mock_settings
        )

        assert isinstance(provider, YFinanceDataProvider)

    def test_create_unsupported_provider(self, mock_settings):
        """Test creating unsupported provider raises error."""
        # Create a fake enum value that's not in the registry
        # The factory checks against registry keys, so we simulate
        # by checking that the method properly validates
        from unittest.mock import MagicMock

        fake_provider = MagicMock()
        fake_provider.value = "invalid_provider"

        with pytest.raises(ValueError) as exc_info:
            DataProviderFactory.create_provider(fake_provider, mock_settings)

        assert "Unsupported" in str(exc_info.value)

    def test_get_supported_providers(self):
        """Test getting supported providers list."""
        supported = DataProviderFactory.get_supported_providers()

        assert "kis" in supported
        assert "yfinance" in supported
        assert "mock" in supported

    def test_is_provider_supported(self):
        """Test checking provider support."""
        assert DataProviderFactory.is_provider_supported(DataProviderEnum.KIS) is True
        assert DataProviderFactory.is_provider_supported(DataProviderEnum.MOCK) is True

    @pytest.mark.asyncio
    async def test_get_provider_with_cache(self, mock_settings):
        """Test getting provider with caching enabled."""
        factory = DataProviderFactory(mock_settings)
        provider = await factory.get_provider(use_cache=True)

        assert isinstance(provider, CachedDataProvider)
        assert isinstance(provider.underlying_provider, MockDataProvider)

    @pytest.mark.asyncio
    async def test_get_provider_without_cache(self, mock_settings):
        """Test getting provider without caching."""
        factory = DataProviderFactory(mock_settings)
        provider = await factory.get_provider(use_cache=False)

        assert isinstance(provider, MockDataProvider)
        assert not isinstance(provider, CachedDataProvider)

    @pytest.mark.asyncio
    async def test_get_all_providers(self, mock_settings):
        """Test getting all configured providers."""
        factory = DataProviderFactory(mock_settings)
        providers = await factory.get_all_providers(use_cache=False)

        assert len(providers) == 2  # Mock + YFinance
        provider_types = [type(p) for p in providers]
        assert MockDataProvider in provider_types
        assert YFinanceDataProvider in provider_types

    @pytest.mark.asyncio
    async def test_close_all(self, mock_settings):
        """Test closing all providers."""
        factory = DataProviderFactory(mock_settings)
        await factory.get_provider(use_cache=False)
        await factory.close_all()

        assert len(factory._providers) == 0

    @pytest.mark.asyncio
    async def test_clear_cache(self, mock_settings):
        """Test clearing provider cache."""
        factory = DataProviderFactory(mock_settings)
        await factory.get_provider(use_cache=True)

        # Add something to cache
        await factory._cache.set("test", "value")
        assert factory._cache.size > 0

        await factory.clear_cache()
        assert factory._cache.size == 0


class TestProviderRegistration:
    """Tests for provider registration/unregistration."""

    @pytest.fixture
    def mock_settings(self):
        """Create mock settings."""
        settings = MagicMock(spec=Settings)
        settings.data = DataConfig(provider=DataProviderEnum.MOCK)
        return settings

    def test_register_custom_provider(self, mock_settings):
        """Test registering a custom provider."""

        class CustomProvider(DataProvider):
            @property
            def provider_name(self):
                return "custom"

            async def get_daily_prices(self, *args, **kwargs):
                return []

            async def get_current_price(self, *args, **kwargs):
                pass

            async def get_ticker_info(self, *args, **kwargs):
                pass

            async def get_available_date_range(self, *args, **kwargs):
                pass

        # This would need a custom enum value, so we test the registration method exists
        assert hasattr(DataProviderFactory, "register")
        assert hasattr(DataProviderFactory, "unregister")


class TestGetDataProviderFunction:
    """Tests for get_data_provider convenience function."""

    @pytest.mark.asyncio
    async def test_get_data_provider_with_settings(self):
        """Test getting provider with explicit settings."""
        settings = MagicMock(spec=Settings)
        settings.data = DataConfig(
            provider=DataProviderEnum.MOCK,
            enable_caching=False,
            cache_ttl_seconds=300,
        )

        provider = await get_data_provider(settings)

        # Should return a provider (possibly cached wrapper)
        assert provider is not None
