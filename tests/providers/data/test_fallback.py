"""
Tests for FallbackDataProvider.

Verifies automatic failover mechanism between data providers.
"""

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import DataConfig, DataProvider as DataProviderEnum, Settings
from app.providers.data.fallback import FallbackDataProvider, get_resilient_data_provider
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
from app.providers.data.mock import MockDataProvider


class TestFallbackDataProviderInit:
    """Tests for FallbackDataProvider initialization."""

    def test_requires_at_least_one_provider(self):
        """Test that at least one provider is required."""
        with pytest.raises(ValueError) as exc_info:
            FallbackDataProvider(providers=[])

        assert "at least one provider" in str(exc_info.value).lower()

    def test_stores_providers_in_order(self):
        """Test providers are stored in priority order."""
        provider1 = AsyncMock(spec=DataProvider)
        provider2 = AsyncMock(spec=DataProvider)

        fallback = FallbackDataProvider(providers=[provider1, provider2])

        assert fallback.providers == [provider1, provider2]
        assert fallback.primary_provider == provider1

    def test_provider_name(self):
        """Test provider name is 'fallback'."""
        provider = AsyncMock(spec=DataProvider)
        fallback = FallbackDataProvider(providers=[provider])

        assert fallback.provider_name == "fallback"


class TestFallbackMechanism:
    """Tests for automatic fallback behavior."""

    @pytest.fixture
    def mock_prices(self):
        """Create mock price data."""
        return [
            PriceData(
                date=date(2024, 1, 2),
                open=Decimal("100"),
                high=Decimal("105"),
                low=Decimal("99"),
                close=Decimal("103"),
                volume=1000000,
            )
        ]

    @pytest.fixture
    def primary_provider(self):
        """Create primary provider mock."""
        provider = AsyncMock(spec=DataProvider)
        provider.provider_name = "primary"
        return provider

    @pytest.fixture
    def fallback_provider(self):
        """Create fallback provider mock."""
        provider = AsyncMock(spec=DataProvider)
        provider.provider_name = "fallback_mock"
        return provider

    @pytest.mark.asyncio
    async def test_uses_primary_when_successful(
        self, primary_provider, fallback_provider, mock_prices
    ):
        """Test primary provider is used when successful."""
        primary_provider.get_daily_prices.return_value = mock_prices
        fallback_provider.get_daily_prices.return_value = []

        fallback = FallbackDataProvider(
            providers=[primary_provider, fallback_provider],
            retry_attempts=1,
        )

        result = await fallback.get_daily_prices(
            "AAPL", date(2024, 1, 1), date(2024, 1, 5)
        )

        assert result == mock_prices
        primary_provider.get_daily_prices.assert_called_once()
        fallback_provider.get_daily_prices.assert_not_called()

    @pytest.mark.asyncio
    async def test_fallback_on_provider_error(
        self, primary_provider, fallback_provider, mock_prices
    ):
        """Test falls back to secondary on DataProviderError."""
        primary_provider.get_daily_prices.side_effect = DataProviderError(
            "API down", provider="primary"
        )
        fallback_provider.get_daily_prices.return_value = mock_prices

        fallback = FallbackDataProvider(
            providers=[primary_provider, fallback_provider],
            retry_attempts=1,
            retry_delay=0,
        )

        result = await fallback.get_daily_prices(
            "AAPL", date(2024, 1, 1), date(2024, 1, 5)
        )

        assert result == mock_prices
        assert fallback.last_successful_provider == fallback_provider

    @pytest.mark.asyncio
    async def test_fallback_on_data_unavailable(
        self, primary_provider, fallback_provider, mock_prices
    ):
        """Test falls back on DataUnavailableError."""
        primary_provider.get_daily_prices.side_effect = DataUnavailableError(
            "Data not available", provider="primary"
        )
        fallback_provider.get_daily_prices.return_value = mock_prices

        fallback = FallbackDataProvider(
            providers=[primary_provider, fallback_provider],
            retry_attempts=1,
            retry_delay=0,
        )

        result = await fallback.get_daily_prices(
            "AAPL", date(2024, 1, 1), date(2024, 1, 5)
        )

        assert result == mock_prices

    @pytest.mark.asyncio
    async def test_no_fallback_on_ticker_not_found(
        self, primary_provider, fallback_provider
    ):
        """Test TickerNotFoundError does NOT trigger fallback."""
        primary_provider.get_daily_prices.side_effect = TickerNotFoundError(
            "INVALID", provider="primary"
        )
        fallback_provider.get_daily_prices.return_value = []

        fallback = FallbackDataProvider(
            providers=[primary_provider, fallback_provider],
            retry_attempts=1,
        )

        with pytest.raises(TickerNotFoundError):
            await fallback.get_daily_prices(
                "INVALID", date(2024, 1, 1), date(2024, 1, 5)
            )

        # Fallback should NOT be called for TickerNotFoundError
        fallback_provider.get_daily_prices.assert_not_called()

    @pytest.mark.asyncio
    async def test_retries_before_fallback(
        self, primary_provider, fallback_provider, mock_prices
    ):
        """Test retries primary before falling back."""
        # Primary fails twice, then would succeed on third
        # But we only have 2 retry attempts, so it should fall back
        primary_provider.get_daily_prices.side_effect = DataProviderError(
            "Error", provider="primary"
        )
        fallback_provider.get_daily_prices.return_value = mock_prices

        fallback = FallbackDataProvider(
            providers=[primary_provider, fallback_provider],
            retry_attempts=2,
            retry_delay=0,
        )

        result = await fallback.get_daily_prices(
            "AAPL", date(2024, 1, 1), date(2024, 1, 5)
        )

        assert result == mock_prices
        # Primary should be called retry_attempts times
        assert primary_provider.get_daily_prices.call_count == 2

    @pytest.mark.asyncio
    async def test_all_providers_fail(self, primary_provider, fallback_provider):
        """Test error when all providers fail."""
        primary_provider.get_daily_prices.side_effect = DataProviderError(
            "Primary error", provider="primary"
        )
        fallback_provider.get_daily_prices.side_effect = DataProviderError(
            "Fallback error", provider="fallback_mock"
        )

        fallback = FallbackDataProvider(
            providers=[primary_provider, fallback_provider],
            retry_attempts=1,
            retry_delay=0,
        )

        with pytest.raises(DataProviderError) as exc_info:
            await fallback.get_daily_prices(
                "AAPL", date(2024, 1, 1), date(2024, 1, 5)
            )

        assert "All providers failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_rate_limit_triggers_fallback(
        self, primary_provider, fallback_provider, mock_prices
    ):
        """Test RateLimitError triggers fallback."""
        primary_provider.get_daily_prices.side_effect = RateLimitError(
            "Rate limit exceeded", provider="primary", retry_after=60
        )
        fallback_provider.get_daily_prices.return_value = mock_prices

        fallback = FallbackDataProvider(
            providers=[primary_provider, fallback_provider],
            retry_attempts=1,
            retry_delay=0,
        )

        result = await fallback.get_daily_prices(
            "AAPL", date(2024, 1, 1), date(2024, 1, 5)
        )

        assert result == mock_prices


class TestFallbackMethods:
    """Tests for all DataProvider methods with fallback."""

    @pytest.fixture
    def primary_provider(self):
        """Create primary provider mock."""
        provider = AsyncMock(spec=DataProvider)
        provider.provider_name = "primary"
        return provider

    @pytest.fixture
    def fallback_provider(self):
        """Create fallback provider mock."""
        provider = AsyncMock(spec=DataProvider)
        provider.provider_name = "fallback_mock"
        return provider

    @pytest.mark.asyncio
    async def test_get_current_price_fallback(
        self, primary_provider, fallback_provider
    ):
        """Test get_current_price uses fallback."""
        primary_provider.get_current_price.side_effect = DataProviderError(
            "Error", provider="primary"
        )
        mock_price = CurrentPrice(
            symbol="AAPL",
            price=Decimal("150"),
            change=Decimal("2"),
            change_percent=Decimal("1.5"),
            volume=1000000,
            timestamp=date.today(),
        )
        fallback_provider.get_current_price.return_value = mock_price

        fallback = FallbackDataProvider(
            providers=[primary_provider, fallback_provider],
            retry_attempts=1,
            retry_delay=0,
        )

        result = await fallback.get_current_price("AAPL")

        assert result == mock_price

    @pytest.mark.asyncio
    async def test_get_ticker_info_fallback(
        self, primary_provider, fallback_provider
    ):
        """Test get_ticker_info uses fallback."""
        primary_provider.get_ticker_info.side_effect = DataProviderError(
            "Error", provider="primary"
        )
        mock_info = TickerInfo(
            symbol="AAPL",
            name="Apple Inc.",
            exchange=Exchange.NASDAQ,
            currency="USD",
        )
        fallback_provider.get_ticker_info.return_value = mock_info

        fallback = FallbackDataProvider(
            providers=[primary_provider, fallback_provider],
            retry_attempts=1,
            retry_delay=0,
        )

        result = await fallback.get_ticker_info("AAPL")

        assert result == mock_info

    @pytest.mark.asyncio
    async def test_get_available_date_range_fallback(
        self, primary_provider, fallback_provider
    ):
        """Test get_available_date_range uses fallback."""
        primary_provider.get_available_date_range.side_effect = DataProviderError(
            "Error", provider="primary"
        )
        mock_range = DateRange(
            start_date=date(2020, 1, 1),
            end_date=date(2024, 1, 1),
            ticker="AAPL",
        )
        fallback_provider.get_available_date_range.return_value = mock_range

        fallback = FallbackDataProvider(
            providers=[primary_provider, fallback_provider],
            retry_attempts=1,
            retry_delay=0,
        )

        result = await fallback.get_available_date_range("AAPL")

        assert result == mock_range


class TestFallbackHealthCheck:
    """Tests for health check with fallback."""

    @pytest.mark.asyncio
    async def test_health_check_true_if_any_healthy(self):
        """Test health check returns True if any provider is healthy."""
        unhealthy = AsyncMock(spec=DataProvider)
        unhealthy.health_check.return_value = False

        healthy = AsyncMock(spec=DataProvider)
        healthy.health_check.return_value = True

        fallback = FallbackDataProvider(providers=[unhealthy, healthy])

        result = await fallback.health_check()

        assert result is True

    @pytest.mark.asyncio
    async def test_health_check_false_if_all_unhealthy(self):
        """Test health check returns False if all providers unhealthy."""
        provider1 = AsyncMock(spec=DataProvider)
        provider1.health_check.return_value = False

        provider2 = AsyncMock(spec=DataProvider)
        provider2.health_check.return_value = False

        fallback = FallbackDataProvider(providers=[provider1, provider2])

        result = await fallback.health_check()

        assert result is False


class TestFallbackClose:
    """Tests for closing fallback provider."""

    @pytest.mark.asyncio
    async def test_close_closes_all_providers(self):
        """Test close() closes all providers."""
        provider1 = AsyncMock(spec=DataProvider)
        provider2 = AsyncMock(spec=DataProvider)

        fallback = FallbackDataProvider(providers=[provider1, provider2])
        await fallback.close()

        provider1.close.assert_called_once()
        provider2.close.assert_called_once()


class TestFallbackExchangeDetection:
    """Tests for exchange detection."""

    def test_detect_exchange_uses_primary(self):
        """Test exchange detection uses primary provider."""
        primary = MagicMock(spec=DataProvider)
        primary.detect_exchange.return_value = Exchange.NYSE

        secondary = MagicMock(spec=DataProvider)
        secondary.detect_exchange.return_value = Exchange.NASDAQ

        fallback = FallbackDataProvider(providers=[primary, secondary])

        result = fallback.detect_exchange("AAPL")

        assert result == Exchange.NYSE
        primary.detect_exchange.assert_called_once_with("AAPL")


class TestFallbackFromSettings:
    """Tests for creating FallbackDataProvider from settings."""

    @pytest.fixture
    def mock_settings(self):
        """Create mock settings."""
        settings = MagicMock(spec=Settings)
        settings.data = DataConfig(
            provider=DataProviderEnum.MOCK,
            fallback_providers=[DataProviderEnum.YFINANCE],
            enable_caching=False,
            retry_attempts=2,
            retry_delay_seconds=0.1,
        )
        return settings

    @pytest.mark.asyncio
    async def test_from_settings_creates_providers(self, mock_settings):
        """Test from_settings creates configured providers."""
        fallback = await FallbackDataProvider.from_settings(mock_settings)

        assert len(fallback.providers) == 2
        assert isinstance(fallback.primary_provider, MockDataProvider)

    @pytest.mark.asyncio
    async def test_from_providers_specific_types(self, mock_settings):
        """Test from_providers with specific provider types."""
        fallback = await FallbackDataProvider.from_providers(
            provider_types=[DataProviderEnum.MOCK],
            settings=mock_settings,
        )

        assert len(fallback.providers) == 1
        assert isinstance(fallback.primary_provider, MockDataProvider)


class TestGetResilientDataProvider:
    """Tests for get_resilient_data_provider convenience function."""

    @pytest.mark.asyncio
    async def test_get_resilient_data_provider_with_settings(self):
        """Test getting resilient provider with explicit settings."""
        settings = MagicMock(spec=Settings)
        settings.data = DataConfig(
            provider=DataProviderEnum.MOCK,
            fallback_providers=[],
            enable_caching=False,
            retry_attempts=1,
            retry_delay_seconds=0,
        )

        provider = await get_resilient_data_provider(settings)

        assert isinstance(provider, FallbackDataProvider)
        assert isinstance(provider.primary_provider, MockDataProvider)


class TestIntegrationWithMockProvider:
    """Integration tests using actual MockDataProvider."""

    @pytest.mark.asyncio
    async def test_full_fallback_flow(self):
        """Test complete fallback flow with real mock providers."""
        # Create two mock providers - first one simulates errors
        error_provider = MockDataProvider.with_error_simulation(error_rate=1.0)
        working_provider = MockDataProvider()

        fallback = FallbackDataProvider(
            providers=[error_provider, working_provider],
            retry_attempts=1,
            retry_delay=0,
        )

        # Should fall back to working_provider
        prices = await fallback.get_daily_prices(
            "AAPL", date(2024, 1, 1), date(2024, 1, 10)
        )

        assert len(prices) > 0
        assert fallback.last_successful_provider == working_provider

    @pytest.mark.asyncio
    async def test_deterministic_with_fallback(self):
        """Test data remains deterministic through fallback."""
        provider1 = MockDataProvider()
        provider2 = MockDataProvider()

        fallback = FallbackDataProvider(providers=[provider1, provider2])

        prices1 = await fallback.get_daily_prices(
            "AAPL", date(2024, 1, 1), date(2024, 1, 5)
        )
        prices2 = await fallback.get_daily_prices(
            "AAPL", date(2024, 1, 1), date(2024, 1, 5)
        )

        # Results should be deterministic
        assert len(prices1) == len(prices2)
        for p1, p2 in zip(prices1, prices2):
            assert p1.close == p2.close
