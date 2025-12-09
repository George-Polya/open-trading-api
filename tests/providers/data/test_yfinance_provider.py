"""
Tests for YFinanceDataProvider.

Uses mocking to avoid actual API calls during unit tests.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from app.providers.data.yfinance import YFinanceDataProvider
from app.providers.data.base import (
    CurrentPrice,
    DataProviderError,
    Exchange,
    PriceData,
    TickerInfo,
    TickerNotFoundError,
)


class TestYFinanceDataProvider:
    """Tests for YFinanceDataProvider."""

    @pytest.fixture
    def provider(self):
        """Create a YFinance provider."""
        return YFinanceDataProvider()

    def test_provider_name(self, provider):
        """Test provider name."""
        assert provider.provider_name == "yfinance"

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


class TestYFinanceTickerFormatting:
    """Tests for ticker formatting."""

    @pytest.fixture
    def provider(self):
        """Create a YFinance provider."""
        return YFinanceDataProvider()

    def test_format_us_ticker(self, provider):
        """Test US ticker formatting (no suffix)."""
        assert provider._format_ticker("AAPL", Exchange.NASDAQ) == "AAPL"
        assert provider._format_ticker("MSFT", Exchange.NYSE) == "MSFT"

    def test_format_korean_ticker_kospi(self, provider):
        """Test Korean KOSPI ticker formatting."""
        assert provider._format_ticker("005930", Exchange.KRX_KOSPI) == "005930.KS"
        assert provider._format_ticker("005930", Exchange.KRX) == "005930.KS"

    def test_format_korean_ticker_kosdaq(self, provider):
        """Test Korean KOSDAQ ticker formatting."""
        assert provider._format_ticker("035420", Exchange.KRX_KOSDAQ) == "035420.KQ"


class TestYFinanceDailyPrices:
    """Tests for get_daily_prices method with mocking."""

    @pytest.fixture
    def provider(self):
        """Create a YFinance provider."""
        return YFinanceDataProvider()

    @pytest.fixture
    def mock_history_df(self):
        """Create a mock history DataFrame."""
        dates = pd.date_range("2024-01-02", periods=3, freq="D")
        return pd.DataFrame(
            {
                "Open": [100.0, 101.0, 102.0],
                "High": [105.0, 106.0, 107.0],
                "Low": [99.0, 100.0, 101.0],
                "Close": [103.0, 104.0, 105.0],
                "Volume": [1000000, 1100000, 1200000],
                "Adj Close": [103.0, 104.0, 105.0],
            },
            index=dates,
        )

    @pytest.mark.asyncio
    async def test_get_daily_prices_success(self, provider, mock_history_df):
        """Test successful daily prices retrieval."""
        with patch.object(
            provider, "_fetch_history_sync", return_value=mock_history_df
        ):
            prices = await provider.get_daily_prices(
                "AAPL", date(2024, 1, 1), date(2024, 1, 5)
            )

            assert len(prices) == 3
            assert all(isinstance(p, PriceData) for p in prices)

    @pytest.mark.asyncio
    async def test_get_daily_prices_schema(self, provider, mock_history_df):
        """Test price data schema compliance."""
        with patch.object(
            provider, "_fetch_history_sync", return_value=mock_history_df
        ):
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

    @pytest.mark.asyncio
    async def test_get_daily_prices_sorted(self, provider, mock_history_df):
        """Test prices are sorted by date ascending."""
        with patch.object(
            provider, "_fetch_history_sync", return_value=mock_history_df
        ):
            prices = await provider.get_daily_prices(
                "AAPL", date(2024, 1, 1), date(2024, 1, 5)
            )

            dates = [p.date for p in prices]
            assert dates == sorted(dates)

    @pytest.mark.asyncio
    async def test_get_daily_prices_empty_result(self, provider):
        """Test ticker not found when empty result."""
        empty_df = pd.DataFrame()

        with patch.object(provider, "_fetch_history_sync", return_value=empty_df):
            with pytest.raises(TickerNotFoundError):
                await provider.get_daily_prices(
                    "INVALID", date(2024, 1, 1), date(2024, 1, 5)
                )

    @pytest.mark.asyncio
    async def test_get_daily_prices_invalid_date_range(self, provider):
        """Test invalid date range raises error."""
        from app.providers.data.base import InvalidDateRangeError

        with pytest.raises(InvalidDateRangeError):
            await provider.get_daily_prices(
                "AAPL", date(2024, 1, 31), date(2024, 1, 1)  # End before start
            )


class TestYFinanceCurrentPrice:
    """Tests for get_current_price method with mocking."""

    @pytest.fixture
    def provider(self):
        """Create a YFinance provider."""
        return YFinanceDataProvider()

    @pytest.fixture
    def mock_fast_info(self):
        """Create mock fast info."""
        return {
            "last_price": 150.0,
            "previous_close": 148.0,
            "open": 149.0,
            "day_high": 152.0,
            "day_low": 147.0,
            "last_volume": 5000000,
            "market_cap": 2500000000000.0,
        }

    @pytest.mark.asyncio
    async def test_get_current_price_success(self, provider, mock_fast_info):
        """Test successful current price retrieval."""
        with patch.object(
            provider, "_fetch_fast_info_sync", return_value=(mock_fast_info, {})
        ):
            price = await provider.get_current_price("AAPL")

            assert isinstance(price, CurrentPrice)
            assert price.symbol == "AAPL"
            assert price.price == Decimal("150.0")
            assert price.change == Decimal("2.0")  # 150 - 148

    @pytest.mark.asyncio
    async def test_get_current_price_has_timestamp(self, provider, mock_fast_info):
        """Test current price has UTC timestamp."""
        with patch.object(
            provider, "_fetch_fast_info_sync", return_value=(mock_fast_info, {})
        ):
            price = await provider.get_current_price("AAPL")

            assert isinstance(price.timestamp, datetime)
            assert price.timestamp.tzinfo is not None


class TestYFinanceTickerInfo:
    """Tests for get_ticker_info method with mocking."""

    @pytest.fixture
    def provider(self):
        """Create a YFinance provider."""
        return YFinanceDataProvider()

    @pytest.fixture
    def mock_info(self):
        """Create mock ticker info."""
        return {
            "longName": "Apple Inc.",
            "shortName": "Apple",
            "regularMarketPrice": 150.0,
            "quoteType": "EQUITY",
            "currency": "USD",
            "sector": "Technology",
            "industry": "Consumer Electronics",
            "marketCap": 2500000000000,
            "website": "https://www.apple.com",
            "country": "United States",
        }

    @pytest.mark.asyncio
    async def test_get_ticker_info_success(self, provider, mock_info):
        """Test successful ticker info retrieval."""
        with patch.object(provider, "_fetch_info_sync", return_value=mock_info):
            info = await provider.get_ticker_info("AAPL")

            assert isinstance(info, TickerInfo)
            assert info.symbol == "AAPL"
            assert info.name == "Apple Inc."
            assert info.currency == "USD"
            assert info.security_type == "stock"
            assert info.sector == "Technology"

    @pytest.mark.asyncio
    async def test_get_ticker_info_etf(self, provider):
        """Test ETF ticker info."""
        mock_info = {
            "longName": "SPDR S&P 500 ETF Trust",
            "regularMarketPrice": 450.0,
            "quoteType": "ETF",
            "currency": "USD",
        }

        with patch.object(provider, "_fetch_info_sync", return_value=mock_info):
            info = await provider.get_ticker_info("SPY")

            assert info.security_type == "etf"


class TestYFinanceExchangeDetection:
    """Tests for exchange detection."""

    @pytest.fixture
    def provider(self):
        """Create a YFinance provider."""
        return YFinanceDataProvider()

    def test_detect_korean_stock(self, provider):
        """Test Korean stock detection."""
        assert provider.detect_exchange("005930") == Exchange.KRX

    def test_detect_us_stock(self, provider):
        """Test US stock detection."""
        assert provider.detect_exchange("AAPL") == Exchange.NASDAQ
        assert provider.detect_exchange("MSFT") == Exchange.NASDAQ


class TestYFinanceHealthCheck:
    """Tests for health check."""

    @pytest.fixture
    def provider(self):
        """Create a YFinance provider."""
        return YFinanceDataProvider()

    @pytest.mark.asyncio
    async def test_health_check_success(self, provider):
        """Test successful health check."""
        mock_df = pd.DataFrame({"Close": [100.0]}, index=[pd.Timestamp("2024-01-01")])

        with patch.object(provider, "_fetch_history_sync", return_value=mock_df):
            result = await provider.health_check()
            assert result is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self, provider):
        """Test failed health check."""
        with patch.object(
            provider, "_fetch_history_sync", side_effect=Exception("Network error")
        ):
            result = await provider.health_check()
            assert result is False
