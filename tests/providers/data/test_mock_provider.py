"""
Tests for MockDataProvider.

Verifies deterministic data generation and schema compliance.
"""

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.providers.data.mock import (
    MOCK_TICKER_INFO,
    MOCK_TICKERS,
    MockDataConfig,
    MockDataProvider,
)
from app.providers.data.base import (
    CurrentPrice,
    DataProviderError,
    Exchange,
    PriceData,
    TickerInfo,
)


class TestMockDataConfig:
    """Tests for MockDataConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = MockDataConfig()
        assert config.seed == 42
        assert config.base_price == Decimal("100.00")
        assert config.volatility == 0.02
        assert config.trend == 0.0005
        assert config.volume_base == 1_000_000
        assert config.include_weekends is False

    def test_custom_config(self):
        """Test custom configuration."""
        config = MockDataConfig(
            seed=123,
            base_price=Decimal("500"),
            volatility=0.05,
            trend=0.001,
        )
        assert config.seed == 123
        assert config.base_price == Decimal("500")
        assert config.volatility == 0.05
        assert config.trend == 0.001


class TestMockDataProvider:
    """Tests for MockDataProvider."""

    @pytest.fixture
    def provider(self):
        """Create a mock provider."""
        return MockDataProvider()

    @pytest.fixture
    def custom_provider(self):
        """Create a mock provider with custom config."""
        config = MockDataConfig(
            seed=100,
            base_price=Decimal("50"),
            volatility=0.03,
        )
        return MockDataProvider(default_config=config)

    def test_provider_name(self, provider):
        """Test provider name."""
        assert provider.provider_name == "mock"

    @pytest.mark.asyncio
    async def test_initialize(self, provider):
        """Test provider initialization."""
        await provider.initialize()
        assert provider._initialized is True

    @pytest.mark.asyncio
    async def test_close(self, provider):
        """Test provider cleanup."""
        await provider.initialize()
        await provider.close()
        assert provider._initialized is False

    @pytest.mark.asyncio
    async def test_health_check(self, provider):
        """Test health check always returns True."""
        result = await provider.health_check()
        assert result is True


class TestMockDailyPrices:
    """Tests for get_daily_prices method."""

    @pytest.fixture
    def provider(self):
        """Create a mock provider."""
        return MockDataProvider()

    @pytest.mark.asyncio
    async def test_get_daily_prices_basic(self, provider):
        """Test basic daily prices retrieval."""
        start_date = date(2024, 1, 1)
        end_date = date(2024, 1, 31)

        prices = await provider.get_daily_prices("AAPL", start_date, end_date)

        assert len(prices) > 0
        assert all(isinstance(p, PriceData) for p in prices)
        assert all(start_date <= p.date <= end_date for p in prices)

    @pytest.mark.asyncio
    async def test_get_daily_prices_schema(self, provider):
        """Test price data schema compliance."""
        prices = await provider.get_daily_prices(
            "AAPL", date(2024, 1, 1), date(2024, 1, 5)
        )

        for price in prices:
            assert isinstance(price.date, date)
            assert isinstance(price.open, Decimal)
            assert isinstance(price.high, Decimal)
            assert isinstance(price.low, Decimal)
            assert isinstance(price.close, Decimal)
            assert isinstance(price.volume, int)
            assert price.high >= price.low
            assert price.open > 0
            assert price.close > 0
            assert price.volume > 0

    @pytest.mark.asyncio
    async def test_get_daily_prices_deterministic(self, provider):
        """Test that data is deterministic (same inputs = same outputs)."""
        start_date = date(2024, 1, 1)
        end_date = date(2024, 1, 10)

        prices1 = await provider.get_daily_prices("AAPL", start_date, end_date)
        prices2 = await provider.get_daily_prices("AAPL", start_date, end_date)

        assert len(prices1) == len(prices2)
        for p1, p2 in zip(prices1, prices2):
            assert p1.date == p2.date
            assert p1.open == p2.open
            assert p1.high == p2.high
            assert p1.low == p2.low
            assert p1.close == p2.close
            assert p1.volume == p2.volume

    @pytest.mark.asyncio
    async def test_get_daily_prices_different_tickers(self, provider):
        """Test that different tickers produce different data."""
        start_date = date(2024, 1, 1)
        end_date = date(2024, 1, 5)

        prices_aapl = await provider.get_daily_prices("AAPL", start_date, end_date)
        prices_msft = await provider.get_daily_prices("MSFT", start_date, end_date)

        # Prices should be different
        assert prices_aapl[0].close != prices_msft[0].close

    @pytest.mark.asyncio
    async def test_get_daily_prices_predefined_ticker(self, provider):
        """Test predefined tickers use their specific config."""
        # Samsung has specific config in MOCK_TICKERS
        prices = await provider.get_daily_prices(
            "005930", date(2024, 1, 1), date(2024, 1, 5)
        )

        # Should have Korean stock-like prices
        assert all(p.close > Decimal("10000") for p in prices)

    @pytest.mark.asyncio
    async def test_get_daily_prices_unknown_ticker(self, provider):
        """Test unknown tickers generate data from hash."""
        prices = await provider.get_daily_prices(
            "UNKNOWN123", date(2024, 1, 1), date(2024, 1, 5)
        )

        assert len(prices) > 0
        # Should still be deterministic
        prices2 = await provider.get_daily_prices(
            "UNKNOWN123", date(2024, 1, 1), date(2024, 1, 5)
        )
        assert prices[0].close == prices2[0].close

    @pytest.mark.asyncio
    async def test_get_daily_prices_weekends_excluded(self, provider):
        """Test weekends are excluded by default."""
        # January 6-7, 2024 is Saturday-Sunday
        prices = await provider.get_daily_prices(
            "AAPL", date(2024, 1, 1), date(2024, 1, 14)
        )

        dates = [p.date for p in prices]
        for d in dates:
            assert d.weekday() < 5  # 0-4 are Mon-Fri

    @pytest.mark.asyncio
    async def test_get_daily_prices_sorted(self, provider):
        """Test prices are sorted by date ascending."""
        prices = await provider.get_daily_prices(
            "AAPL", date(2024, 1, 1), date(2024, 1, 31)
        )

        dates = [p.date for p in prices]
        assert dates == sorted(dates)


class TestMockCurrentPrice:
    """Tests for get_current_price method."""

    @pytest.fixture
    def provider(self):
        """Create a mock provider."""
        return MockDataProvider()

    @pytest.mark.asyncio
    async def test_get_current_price_basic(self, provider):
        """Test basic current price retrieval."""
        price = await provider.get_current_price("AAPL")

        assert isinstance(price, CurrentPrice)
        assert price.symbol == "AAPL"
        assert price.price > 0
        assert isinstance(price.change, Decimal)
        assert isinstance(price.change_percent, Decimal)
        assert price.volume > 0

    @pytest.mark.asyncio
    async def test_get_current_price_has_timestamp(self, provider):
        """Test current price has UTC timestamp."""
        price = await provider.get_current_price("AAPL")

        assert isinstance(price.timestamp, datetime)
        assert price.timestamp.tzinfo is not None

    @pytest.mark.asyncio
    async def test_get_current_price_has_bid_ask(self, provider):
        """Test current price includes bid/ask."""
        price = await provider.get_current_price("AAPL")

        assert price.bid is not None
        assert price.ask is not None
        assert price.bid < price.ask  # Bid should be less than ask


class TestMockTickerInfo:
    """Tests for get_ticker_info method."""

    @pytest.fixture
    def provider(self):
        """Create a mock provider."""
        return MockDataProvider()

    @pytest.mark.asyncio
    async def test_get_ticker_info_predefined(self, provider):
        """Test ticker info for predefined tickers."""
        info = await provider.get_ticker_info("AAPL")

        assert isinstance(info, TickerInfo)
        assert info.symbol == "AAPL"
        assert info.name == "Apple Inc."
        assert info.exchange == Exchange.NASDAQ
        assert info.currency == "USD"
        assert info.security_type == "stock"
        assert info.sector == "Technology"

    @pytest.mark.asyncio
    async def test_get_ticker_info_korean_stock(self, provider):
        """Test ticker info for Korean predefined tickers."""
        info = await provider.get_ticker_info("005930")

        assert info.symbol == "005930"
        assert info.name == "삼성전자"
        assert info.exchange == Exchange.KRX
        assert info.currency == "KRW"

    @pytest.mark.asyncio
    async def test_get_ticker_info_unknown(self, provider):
        """Test ticker info for unknown tickers."""
        info = await provider.get_ticker_info("UNKNOWN999")

        assert info.symbol == "UNKNOWN999"
        assert "Mock Company" in info.name
        assert info.extra.get("generated") is True


class TestMockDateRange:
    """Tests for get_available_date_range method."""

    @pytest.fixture
    def provider(self):
        """Create a mock provider."""
        return MockDataProvider()

    @pytest.mark.asyncio
    async def test_get_available_date_range(self, provider):
        """Test available date range."""
        date_range = await provider.get_available_date_range("AAPL")

        assert date_range.ticker == "AAPL"
        assert date_range.start_date == date(2010, 1, 1)
        assert date_range.end_date == date.today()


class TestMockErrorSimulation:
    """Tests for error simulation feature."""

    @pytest.mark.asyncio
    async def test_error_simulation_disabled(self):
        """Test no errors when simulation disabled."""
        provider = MockDataProvider(simulate_errors=False)

        # Should not raise
        prices = await provider.get_daily_prices(
            "AAPL", date(2024, 1, 1), date(2024, 1, 5)
        )
        assert len(prices) > 0

    @pytest.mark.asyncio
    async def test_error_simulation_factory_method(self):
        """Test with_error_simulation factory method."""
        provider = MockDataProvider.with_error_simulation(error_rate=1.0)

        assert provider._simulate_errors is True
        assert provider._error_rate == 1.0

    @pytest.mark.asyncio
    async def test_error_simulation_deterministic(self):
        """Test error simulation is deterministic based on ticker."""
        provider = MockDataProvider.with_error_simulation(error_rate=0.5)

        # Same ticker should consistently trigger or not trigger error
        results = []
        for _ in range(5):
            try:
                await provider.get_daily_prices(
                    "TEST_TICKER", date(2024, 1, 1), date(2024, 1, 5)
                )
                results.append(True)
            except DataProviderError:
                results.append(False)

        # All results should be the same (deterministic)
        assert len(set(results)) == 1


class TestMockExchangeDetection:
    """Tests for exchange detection."""

    @pytest.fixture
    def provider(self):
        """Create a mock provider."""
        return MockDataProvider()

    def test_detect_korean_stock(self, provider):
        """Test Korean stock detection."""
        assert provider.detect_exchange("005930") == Exchange.KRX
        assert provider.detect_exchange("000660") == Exchange.KRX

    def test_detect_us_stock(self, provider):
        """Test US stock detection."""
        assert provider.detect_exchange("AAPL") == Exchange.NASDAQ
        assert provider.detect_exchange("MSFT") == Exchange.NASDAQ
