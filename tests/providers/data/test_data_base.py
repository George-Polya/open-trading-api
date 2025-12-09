"""
Tests for DataProvider base abstractions.

Tests:
- PriceData, TickerInfo, DateRange, CurrentPrice dataclass validation
- Exchange enum values
- DataProvider abstract class enforcement
- Exception classes
"""

from dataclasses import FrozenInstanceError
from datetime import date, datetime
from decimal import Decimal

import pytest

from app.providers.data.base import (
    AuthenticationError,
    CurrentPrice,
    DataProvider,
    DataProviderError,
    DateRange,
    Exchange,
    InvalidDateRangeError,
    PriceData,
    RateLimitError,
    TickerInfo,
    TickerNotFoundError,
)


class TestExchange:
    """Tests for Exchange enum."""

    def test_korean_exchanges(self) -> None:
        """Test Korean exchange values."""
        assert Exchange.KRX.value == "KRX"
        assert Exchange.KRX_KOSPI.value == "KRX_KOSPI"
        assert Exchange.KRX_KOSDAQ.value == "KRX_KOSDAQ"

    def test_us_exchanges(self) -> None:
        """Test US exchange values."""
        assert Exchange.NYSE.value == "NYSE"
        assert Exchange.NASDAQ.value == "NAS"
        assert Exchange.AMEX.value == "AMS"

    def test_asian_exchanges(self) -> None:
        """Test Asian exchange values."""
        assert Exchange.HKEX.value == "HKS"
        assert Exchange.TSE.value == "TSE"
        assert Exchange.SSE.value == "SHS"
        assert Exchange.SZSE.value == "SZS"


class TestPriceData:
    """Tests for PriceData dataclass."""

    def test_price_data_creation(self) -> None:
        """Test basic PriceData creation."""
        price = PriceData(
            date=date(2024, 1, 15),
            open=Decimal("100.00"),
            high=Decimal("105.00"),
            low=Decimal("99.00"),
            close=Decimal("103.00"),
            volume=1000000,
        )
        assert price.date == date(2024, 1, 15)
        assert price.open == Decimal("100.00")
        assert price.high == Decimal("105.00")
        assert price.low == Decimal("99.00")
        assert price.close == Decimal("103.00")
        assert price.volume == 1000000
        assert price.adjusted_close is None

    def test_price_data_with_adjusted_close(self) -> None:
        """Test PriceData with adjusted close price."""
        price = PriceData(
            date=date(2024, 1, 15),
            open=Decimal("100.00"),
            high=Decimal("105.00"),
            low=Decimal("99.00"),
            close=Decimal("103.00"),
            volume=1000000,
            adjusted_close=Decimal("102.50"),
        )
        assert price.adjusted_close == Decimal("102.50")

    def test_price_data_with_extra(self) -> None:
        """Test PriceData with extra fields."""
        price = PriceData(
            date=date(2024, 1, 15),
            open=Decimal("100.00"),
            high=Decimal("105.00"),
            low=Decimal("99.00"),
            close=Decimal("103.00"),
            volume=1000000,
            extra={"turnover": Decimal("103000000"), "change_sign": "2"},
        )
        assert price.extra["turnover"] == Decimal("103000000")
        assert price.extra["change_sign"] == "2"

    def test_price_data_is_frozen(self) -> None:
        """Test that PriceData is immutable."""
        price = PriceData(
            date=date(2024, 1, 15),
            open=Decimal("100.00"),
            high=Decimal("105.00"),
            low=Decimal("99.00"),
            close=Decimal("103.00"),
            volume=1000000,
        )
        with pytest.raises(FrozenInstanceError):
            price.close = Decimal("104.00")  # type: ignore

    def test_price_data_validation_high_less_than_low(self) -> None:
        """Test validation when high < low."""
        with pytest.raises(ValueError, match="High .* cannot be less than low"):
            PriceData(
                date=date(2024, 1, 15),
                open=Decimal("100.00"),
                high=Decimal("98.00"),  # Invalid: high < low
                low=Decimal("99.00"),
                close=Decimal("103.00"),
                volume=1000000,
            )

    def test_price_data_validation_negative_price(self) -> None:
        """Test validation for negative prices."""
        with pytest.raises(ValueError, match="Prices cannot be negative"):
            PriceData(
                date=date(2024, 1, 15),
                open=Decimal("-100.00"),
                high=Decimal("105.00"),
                low=Decimal("99.00"),
                close=Decimal("103.00"),
                volume=1000000,
            )

    def test_price_data_validation_negative_volume(self) -> None:
        """Test validation for negative volume."""
        with pytest.raises(ValueError, match="Volume cannot be negative"):
            PriceData(
                date=date(2024, 1, 15),
                open=Decimal("100.00"),
                high=Decimal("105.00"),
                low=Decimal("99.00"),
                close=Decimal("103.00"),
                volume=-1000,
            )


class TestTickerInfo:
    """Tests for TickerInfo dataclass."""

    def test_ticker_info_creation(self) -> None:
        """Test basic TickerInfo creation."""
        info = TickerInfo(
            symbol="005930",
            name="삼성전자",
            exchange=Exchange.KRX,
        )
        assert info.symbol == "005930"
        assert info.name == "삼성전자"
        assert info.exchange == Exchange.KRX
        assert info.currency == "KRW"  # Default
        assert info.security_type == "stock"  # Default

    def test_ticker_info_with_all_fields(self) -> None:
        """Test TickerInfo with all fields."""
        info = TickerInfo(
            symbol="AAPL",
            name="Apple Inc.",
            exchange=Exchange.NASDAQ,
            currency="USD",
            security_type="stock",
            sector="Technology",
            market_cap=Decimal("3000000000000"),
            extra={"isin": "US0378331005"},
        )
        assert info.currency == "USD"
        assert info.sector == "Technology"
        assert info.market_cap == Decimal("3000000000000")
        assert info.extra["isin"] == "US0378331005"

    def test_ticker_info_is_frozen(self) -> None:
        """Test that TickerInfo is immutable."""
        info = TickerInfo(
            symbol="005930",
            name="삼성전자",
            exchange=Exchange.KRX,
        )
        with pytest.raises(FrozenInstanceError):
            info.symbol = "000660"  # type: ignore


class TestDateRange:
    """Tests for DateRange dataclass."""

    def test_date_range_creation(self) -> None:
        """Test basic DateRange creation."""
        dr = DateRange(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            ticker="005930",
        )
        assert dr.start_date == date(2024, 1, 1)
        assert dr.end_date == date(2024, 12, 31)
        assert dr.ticker == "005930"

    def test_date_range_validation_start_after_end(self) -> None:
        """Test validation when start_date > end_date."""
        with pytest.raises(ValueError, match="Start date .* cannot be after end date"):
            DateRange(
                start_date=date(2024, 12, 31),
                end_date=date(2024, 1, 1),
                ticker="005930",
            )

    def test_date_range_contains(self) -> None:
        """Test DateRange.contains method."""
        dr = DateRange(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            ticker="005930",
        )
        assert dr.contains(date(2024, 6, 15)) is True
        assert dr.contains(date(2024, 1, 1)) is True  # Inclusive start
        assert dr.contains(date(2024, 12, 31)) is True  # Inclusive end
        assert dr.contains(date(2023, 12, 31)) is False
        assert dr.contains(date(2025, 1, 1)) is False

    def test_date_range_days(self) -> None:
        """Test DateRange.days property."""
        dr = DateRange(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            ticker="005930",
        )
        assert dr.days == 30


class TestCurrentPrice:
    """Tests for CurrentPrice dataclass."""

    def test_current_price_creation(self) -> None:
        """Test basic CurrentPrice creation."""
        now = datetime.now()
        price = CurrentPrice(
            symbol="005930",
            price=Decimal("75000"),
            change=Decimal("1000"),
            change_percent=Decimal("1.35"),
            volume=5000000,
            timestamp=now,
        )
        assert price.symbol == "005930"
        assert price.price == Decimal("75000")
        assert price.change == Decimal("1000")
        assert price.change_percent == Decimal("1.35")
        assert price.volume == 5000000
        assert price.timestamp == now
        assert price.bid is None
        assert price.ask is None

    def test_current_price_with_bid_ask(self) -> None:
        """Test CurrentPrice with bid/ask."""
        price = CurrentPrice(
            symbol="AAPL",
            price=Decimal("185.50"),
            change=Decimal("2.30"),
            change_percent=Decimal("1.26"),
            volume=50000000,
            timestamp=datetime.now(),
            bid=Decimal("185.45"),
            ask=Decimal("185.55"),
        )
        assert price.bid == Decimal("185.45")
        assert price.ask == Decimal("185.55")


class TestDataProviderAbstract:
    """Tests for DataProvider abstract base class."""

    def test_cannot_instantiate_abstract_class(self) -> None:
        """Test that DataProvider cannot be instantiated directly."""
        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            DataProvider()  # type: ignore

    def test_subclass_must_implement_all_abstract_methods(self) -> None:
        """Test that incomplete subclass raises TypeError."""

        class IncompleteProvider(DataProvider):
            async def get_daily_prices(self, ticker, start_date, end_date, exchange=None):
                return []

            @property
            def provider_name(self) -> str:
                return "test"

        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            IncompleteProvider()  # type: ignore

    def test_complete_subclass_can_be_instantiated(self) -> None:
        """Test that complete subclass can be instantiated."""

        class CompleteProvider(DataProvider):
            async def get_daily_prices(self, ticker, start_date, end_date, exchange=None):
                return []

            async def get_current_price(self, ticker, exchange=None):
                return CurrentPrice(
                    symbol=ticker,
                    price=Decimal("100"),
                    change=Decimal("0"),
                    change_percent=Decimal("0"),
                    volume=0,
                    timestamp=datetime.now(),
                )

            async def get_ticker_info(self, ticker, exchange=None):
                return TickerInfo(
                    symbol=ticker,
                    name=ticker,
                    exchange=Exchange.KRX,
                )

            async def get_available_date_range(self, ticker, exchange=None):
                return DateRange(
                    start_date=date(2020, 1, 1),
                    end_date=date.today(),
                    ticker=ticker,
                )

            @property
            def provider_name(self) -> str:
                return "test"

        provider = CompleteProvider()
        assert provider.provider_name == "test"

    def test_detect_exchange_korean_stock(self) -> None:
        """Test exchange detection for Korean stocks."""

        class TestProvider(DataProvider):
            async def get_daily_prices(self, ticker, start_date, end_date, exchange=None):
                return []

            async def get_current_price(self, ticker, exchange=None):
                return CurrentPrice(
                    symbol=ticker,
                    price=Decimal("100"),
                    change=Decimal("0"),
                    change_percent=Decimal("0"),
                    volume=0,
                    timestamp=datetime.now(),
                )

            async def get_ticker_info(self, ticker, exchange=None):
                return TickerInfo(symbol=ticker, name=ticker, exchange=Exchange.KRX)

            async def get_available_date_range(self, ticker, exchange=None):
                return DateRange(
                    start_date=date(2020, 1, 1),
                    end_date=date.today(),
                    ticker=ticker,
                )

            @property
            def provider_name(self) -> str:
                return "test"

        provider = TestProvider()
        # Korean stock codes are 6 digits
        assert provider.detect_exchange("005930") == Exchange.KRX
        assert provider.detect_exchange("000660") == Exchange.KRX
        assert provider.detect_exchange("035720") == Exchange.KRX

    def test_detect_exchange_us_stock(self) -> None:
        """Test exchange detection for US stocks."""

        class TestProvider(DataProvider):
            async def get_daily_prices(self, ticker, start_date, end_date, exchange=None):
                return []

            async def get_current_price(self, ticker, exchange=None):
                return CurrentPrice(
                    symbol=ticker,
                    price=Decimal("100"),
                    change=Decimal("0"),
                    change_percent=Decimal("0"),
                    volume=0,
                    timestamp=datetime.now(),
                )

            async def get_ticker_info(self, ticker, exchange=None):
                return TickerInfo(symbol=ticker, name=ticker, exchange=Exchange.NASDAQ)

            async def get_available_date_range(self, ticker, exchange=None):
                return DateRange(
                    start_date=date(2020, 1, 1),
                    end_date=date.today(),
                    ticker=ticker,
                )

            @property
            def provider_name(self) -> str:
                return "test"

        provider = TestProvider()
        # US symbols default to NASDAQ
        assert provider.detect_exchange("AAPL") == Exchange.NASDAQ
        assert provider.detect_exchange("TSLA") == Exchange.NASDAQ
        assert provider.detect_exchange("MSFT") == Exchange.NASDAQ


class TestExceptions:
    """Tests for data provider exception classes."""

    def test_data_provider_error(self) -> None:
        """Test DataProviderError."""
        error = DataProviderError("Something went wrong", provider="kis")
        assert str(error) == "Something went wrong"
        assert error.provider == "kis"

    def test_ticker_not_found_error(self) -> None:
        """Test TickerNotFoundError."""
        error = TickerNotFoundError("INVALID", provider="kis")
        assert "INVALID" in str(error)
        assert error.ticker == "INVALID"
        assert error.provider == "kis"
        assert isinstance(error, DataProviderError)

    def test_authentication_error(self) -> None:
        """Test AuthenticationError."""
        error = AuthenticationError("Invalid API key", provider="kis")
        assert "Invalid API key" in str(error)
        assert isinstance(error, DataProviderError)

    def test_rate_limit_error(self) -> None:
        """Test RateLimitError."""
        error = RateLimitError(
            "Rate limited",
            provider="kis",
            retry_after=60.0,
        )
        assert error.retry_after == 60.0
        assert error.provider == "kis"
        assert isinstance(error, DataProviderError)

    def test_invalid_date_range_error(self) -> None:
        """Test InvalidDateRangeError."""
        error = InvalidDateRangeError(
            start_date=date(2024, 12, 31),
            end_date=date(2024, 1, 1),
            reason="Start date after end date",
            provider="kis",
        )
        assert "2024-12-31" in str(error)
        assert "2024-01-01" in str(error)
        assert "Start date after end date" in str(error)
        assert error.start_date == date(2024, 12, 31)
        assert error.end_date == date(2024, 1, 1)
        assert isinstance(error, DataProviderError)
