"""
Mock Data Provider implementation.

Provides deterministic synthetic price data for testing and offline development.
Generates consistent data based on seed values for reproducible test scenarios.
"""

import hashlib
import logging
import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from app.providers.data.base import (
    CurrentPrice,
    DataProvider,
    DataProviderError,
    DateRange,
    Exchange,
    InvalidDateRangeError,
    PriceData,
    TickerInfo,
    TickerNotFoundError,
)

logger = logging.getLogger(__name__)


@dataclass
class MockDataConfig:
    """
    Configuration for mock data generation.

    Allows customizing the synthetic data generation behavior.

    Attributes:
        seed: Base seed for reproducible random generation
        base_price: Starting price for generated data
        volatility: Daily price volatility (0.0 to 1.0)
        trend: Daily trend factor (-1.0 to 1.0, positive = upward)
        volume_base: Base daily volume
        volume_variance: Volume variance factor
        include_weekends: Whether to include weekend dates
    """

    seed: int = 42
    base_price: Decimal = Decimal("100.00")
    volatility: float = 0.02  # 2% daily volatility
    trend: float = 0.0005  # 0.05% daily upward trend
    volume_base: int = 1_000_000
    volume_variance: float = 0.3
    include_weekends: bool = False


# Predefined mock tickers with different characteristics
MOCK_TICKERS: dict[str, MockDataConfig] = {
    # Korean stocks (6-digit codes)
    "005930": MockDataConfig(
        seed=1, base_price=Decimal("70000"), volatility=0.015, trend=0.001
    ),  # Samsung-like
    "000660": MockDataConfig(
        seed=2, base_price=Decimal("150000"), volatility=0.025, trend=0.0015
    ),  # SK Hynix-like
    "035420": MockDataConfig(
        seed=3, base_price=Decimal("300000"), volatility=0.02, trend=0.0008
    ),  # NAVER-like
    # US stocks
    "AAPL": MockDataConfig(
        seed=10, base_price=Decimal("180"), volatility=0.018, trend=0.0012
    ),
    "MSFT": MockDataConfig(
        seed=11, base_price=Decimal("400"), volatility=0.015, trend=0.001
    ),
    "GOOGL": MockDataConfig(
        seed=12, base_price=Decimal("140"), volatility=0.02, trend=0.0008
    ),
    "AMZN": MockDataConfig(
        seed=13, base_price=Decimal("175"), volatility=0.022, trend=0.0015
    ),
    "TSLA": MockDataConfig(
        seed=14, base_price=Decimal("250"), volatility=0.04, trend=0.002
    ),  # High volatility
    # ETFs
    "SPY": MockDataConfig(
        seed=20, base_price=Decimal("450"), volatility=0.01, trend=0.0005
    ),  # S&P 500
    "QQQ": MockDataConfig(
        seed=21, base_price=Decimal("380"), volatility=0.012, trend=0.0008
    ),  # NASDAQ
}

# Mock ticker info
MOCK_TICKER_INFO: dict[str, dict[str, Any]] = {
    "005930": {
        "name": "삼성전자",
        "exchange": Exchange.KRX,
        "currency": "KRW",
        "security_type": "stock",
        "sector": "Technology",
    },
    "000660": {
        "name": "SK하이닉스",
        "exchange": Exchange.KRX,
        "currency": "KRW",
        "security_type": "stock",
        "sector": "Technology",
    },
    "035420": {
        "name": "NAVER",
        "exchange": Exchange.KRX,
        "currency": "KRW",
        "security_type": "stock",
        "sector": "Communication Services",
    },
    "AAPL": {
        "name": "Apple Inc.",
        "exchange": Exchange.NASDAQ,
        "currency": "USD",
        "security_type": "stock",
        "sector": "Technology",
    },
    "MSFT": {
        "name": "Microsoft Corporation",
        "exchange": Exchange.NASDAQ,
        "currency": "USD",
        "security_type": "stock",
        "sector": "Technology",
    },
    "GOOGL": {
        "name": "Alphabet Inc.",
        "exchange": Exchange.NASDAQ,
        "currency": "USD",
        "security_type": "stock",
        "sector": "Communication Services",
    },
    "AMZN": {
        "name": "Amazon.com Inc.",
        "exchange": Exchange.NASDAQ,
        "currency": "USD",
        "security_type": "stock",
        "sector": "Consumer Discretionary",
    },
    "TSLA": {
        "name": "Tesla Inc.",
        "exchange": Exchange.NASDAQ,
        "currency": "USD",
        "security_type": "stock",
        "sector": "Consumer Discretionary",
    },
    "SPY": {
        "name": "SPDR S&P 500 ETF Trust",
        "exchange": Exchange.NYSE,
        "currency": "USD",
        "security_type": "etf",
        "sector": None,
    },
    "QQQ": {
        "name": "Invesco QQQ Trust",
        "exchange": Exchange.NASDAQ,
        "currency": "USD",
        "security_type": "etf",
        "sector": None,
    },
}


class MockDataProvider(DataProvider):
    """
    Mock data provider for testing and offline development.

    Generates deterministic synthetic price data using configurable
    algorithms (sine wave, linear trend, random walk with seed).

    Features:
    - Reproducible data: Same inputs produce same outputs
    - Configurable: Adjust volatility, trend, volume patterns
    - Predefined tickers: Common stocks with realistic characteristics
    - Custom tickers: Any ticker generates data based on ticker hash

    Example:
        provider = MockDataProvider()

        # Using predefined ticker
        prices = await provider.get_daily_prices(
            "AAPL",
            date(2024, 1, 1),
            date(2024, 3, 31)
        )

        # Using custom ticker (generates based on hash)
        custom_prices = await provider.get_daily_prices(
            "CUSTOM123",
            date(2024, 1, 1),
            date(2024, 3, 31)
        )

        # Using custom config
        config = MockDataConfig(base_price=Decimal("50"), volatility=0.05)
        provider = MockDataProvider(default_config=config)
    """

    def __init__(
        self,
        default_config: MockDataConfig | None = None,
        simulate_errors: bool = False,
        error_rate: float = 0.0,
    ) -> None:
        """
        Initialize the Mock data provider.

        Args:
            default_config: Default configuration for unknown tickers
            simulate_errors: Whether to randomly simulate errors
            error_rate: Error rate (0.0 to 1.0) when simulate_errors is True
        """
        self._default_config = default_config or MockDataConfig()
        self._simulate_errors = simulate_errors
        self._error_rate = error_rate
        self._initialized = False

    @property
    def provider_name(self) -> str:
        """Get the provider name."""
        return "mock"

    async def initialize(self) -> None:
        """Initialize the provider."""
        self._initialized = True
        logger.info("Mock data provider initialized")

    async def close(self) -> None:
        """Clean up provider resources."""
        self._initialized = False

    def _get_config(self, ticker: str) -> MockDataConfig:
        """
        Get configuration for a ticker.

        Returns predefined config if available, otherwise creates
        a deterministic config based on ticker hash.

        Args:
            ticker: Ticker symbol

        Returns:
            MockDataConfig for the ticker
        """
        if ticker in MOCK_TICKERS:
            return MOCK_TICKERS[ticker]

        # Generate deterministic config from ticker hash
        ticker_hash = int(hashlib.md5(ticker.encode(), usedforsecurity=False).hexdigest(), 16)
        seed = ticker_hash % 10000

        # Derive base price from hash (between 10 and 1000)
        base_price = Decimal(str(10 + (ticker_hash % 990)))

        # Derive volatility (0.01 to 0.05)
        volatility = 0.01 + (ticker_hash % 400) / 10000

        # Derive trend (-0.001 to 0.002)
        trend = -0.001 + (ticker_hash % 300) / 100000

        return MockDataConfig(
            seed=seed,
            base_price=base_price,
            volatility=volatility,
            trend=trend,
        )

    def _should_simulate_error(self, ticker: str) -> bool:
        """Check if we should simulate an error for this request."""
        if not self._simulate_errors or self._error_rate <= 0:
            return False

        # Deterministic "random" based on ticker
        ticker_hash = int(hashlib.md5(ticker.encode(), usedforsecurity=False).hexdigest(), 16)
        return (ticker_hash % 100) < (self._error_rate * 100)

    def _generate_deterministic_value(
        self,
        seed: int,
        day_offset: int,
        component: str = "price",
    ) -> float:
        """
        Generate a deterministic pseudo-random value.

        Uses a simple but deterministic algorithm based on seed and offset.

        Args:
            seed: Base seed value
            day_offset: Day offset from base date
            component: Component name for additional variation

        Returns:
            Pseudo-random value between 0 and 1
        """
        # Create a unique value for this seed/day/component combination
        combined = f"{seed}_{day_offset}_{component}"
        hash_val = int(hashlib.md5(combined.encode(), usedforsecurity=False).hexdigest(), 16)
        return (hash_val % 10000) / 10000

    def _generate_price(
        self,
        config: MockDataConfig,
        day_offset: int,
        prev_close: Decimal | None = None,
    ) -> tuple[Decimal, Decimal, Decimal, Decimal]:
        """
        Generate OHLC prices for a single day.

        Combines:
        - Trend component (linear drift)
        - Cyclical component (sine wave for seasonality)
        - Random component (deterministic pseudo-random noise)

        Args:
            config: Mock data configuration
            day_offset: Days from the start date
            prev_close: Previous day's close price

        Returns:
            Tuple of (open, high, low, close) prices
        """
        seed = config.seed

        # Start from base price or previous close
        base = prev_close if prev_close is not None else config.base_price

        # Trend component
        trend_factor = 1 + config.trend * day_offset

        # Cyclical component (30-day cycle)
        cycle_factor = 1 + 0.01 * math.sin(2 * math.pi * day_offset / 30)

        # Random component
        random_val = self._generate_deterministic_value(seed, day_offset, "noise")
        noise_factor = 1 + config.volatility * (random_val - 0.5) * 2

        # Calculate close price
        close_float = float(base) * trend_factor * cycle_factor * noise_factor
        close = Decimal(str(round(close_float, 2)))

        # Generate intraday range
        high_random = self._generate_deterministic_value(seed, day_offset, "high")
        low_random = self._generate_deterministic_value(seed, day_offset, "low")

        # High is 0-2% above max(open, close)
        # Low is 0-2% below min(open, close)
        open_price = prev_close if prev_close is not None else close
        max_price = max(open_price, close)
        min_price = min(open_price, close)

        high = max_price * Decimal(str(1 + 0.02 * high_random))
        low = min_price * Decimal(str(1 - 0.02 * low_random))

        # Ensure proper OHLC relationship
        high = max(high, open_price, close)
        low = min(low, open_price, close)

        return (
            Decimal(str(round(float(open_price), 2))),
            Decimal(str(round(float(high), 2))),
            Decimal(str(round(float(low), 2))),
            Decimal(str(round(float(close), 2))),
        )

    def _generate_volume(
        self,
        config: MockDataConfig,
        day_offset: int,
    ) -> int:
        """
        Generate trading volume for a single day.

        Args:
            config: Mock data configuration
            day_offset: Days from the start date

        Returns:
            Trading volume
        """
        seed = config.seed
        random_val = self._generate_deterministic_value(seed, day_offset, "volume")

        # Volume varies around base with configured variance
        variance_factor = 1 + config.volume_variance * (random_val - 0.5) * 2

        # Add day-of-week pattern (higher on Monday/Friday)
        dow = day_offset % 5
        dow_factor = 1.1 if dow in (0, 4) else 1.0

        volume = int(config.volume_base * variance_factor * dow_factor)
        return max(volume, 1000)  # Minimum volume

    def _is_trading_day(self, check_date: date, include_weekends: bool = False) -> bool:
        """Check if a date is a trading day."""
        if include_weekends:
            return True
        # Weekday: 0=Monday, 6=Sunday
        return check_date.weekday() < 5

    async def get_daily_prices(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
        exchange: Exchange | None = None,
    ) -> list[PriceData]:
        """
        Get daily OHLCV price data for a ticker.

        Generates deterministic synthetic data based on the ticker
        and date range.

        Args:
            ticker: Ticker symbol
            start_date: Start date for historical data
            end_date: End date for historical data
            exchange: Exchange hint (optional, ignored for mock)

        Returns:
            List of PriceData records sorted by date ascending

        Raises:
            DataProviderError: If error simulation is triggered
            InvalidDateRangeError: If date range is invalid
        """
        if start_date > end_date:
            raise InvalidDateRangeError(
                start_date, end_date, "Start date after end date", self.provider_name
            )

        if self._should_simulate_error(ticker):
            raise DataProviderError(
                f"Simulated error for ticker {ticker}",
                provider=self.provider_name,
            )

        config = self._get_config(ticker)
        prices = []

        # Reference date for consistent day offsets
        reference_date = date(2020, 1, 1)
        current_date = start_date
        prev_close: Decimal | None = None

        # Generate initial prev_close based on days before start_date
        if start_date > reference_date:
            pre_offset = (start_date - reference_date).days - 1
            _, _, _, prev_close = self._generate_price(config, pre_offset, config.base_price)

        while current_date <= end_date:
            if self._is_trading_day(current_date, config.include_weekends):
                day_offset = (current_date - reference_date).days
                open_p, high_p, low_p, close_p = self._generate_price(
                    config, day_offset, prev_close
                )
                volume = self._generate_volume(config, day_offset)

                prices.append(
                    PriceData(
                        date=current_date,
                        open=open_p,
                        high=high_p,
                        low=low_p,
                        close=close_p,
                        volume=volume,
                        adjusted_close=close_p,  # No dividends in mock data
                    )
                )

                prev_close = close_p

            current_date += timedelta(days=1)

        return prices

    async def get_current_price(
        self,
        ticker: str,
        exchange: Exchange | None = None,
    ) -> CurrentPrice:
        """
        Get the current/latest price for a ticker.

        Returns synthetic current price data based on today's date.

        Args:
            ticker: Ticker symbol
            exchange: Exchange hint (optional, ignored for mock)

        Returns:
            CurrentPrice with latest price information
        """
        if self._should_simulate_error(ticker):
            raise DataProviderError(
                f"Simulated error for ticker {ticker}",
                provider=self.provider_name,
            )

        config = self._get_config(ticker)
        reference_date = date(2020, 1, 1)
        today = date.today()

        # Get today's and yesterday's prices
        today_offset = (today - reference_date).days
        yesterday_offset = today_offset - 1

        # Calculate previous close
        _, _, _, prev_close = self._generate_price(config, yesterday_offset, config.base_price)

        # Calculate current prices
        open_p, high_p, low_p, close_p = self._generate_price(
            config, today_offset, prev_close
        )
        volume = self._generate_volume(config, today_offset)

        change = close_p - prev_close
        change_percent = (
            (change / prev_close * 100) if prev_close != Decimal("0") else Decimal("0")
        )

        return CurrentPrice(
            symbol=ticker,
            price=close_p,
            change=change,
            change_percent=change_percent,
            volume=volume,
            timestamp=datetime.now(timezone.utc),
            bid=close_p * Decimal("0.999"),  # Simulated bid slightly below
            ask=close_p * Decimal("1.001"),  # Simulated ask slightly above
            extra={
                "open": open_p,
                "high": high_p,
                "low": low_p,
                "prev_close": prev_close,
            },
        )

    async def get_ticker_info(
        self,
        ticker: str,
        exchange: Exchange | None = None,
    ) -> TickerInfo:
        """
        Get metadata about a ticker.

        Returns predefined info for known tickers, or generates
        basic info for unknown tickers.

        Args:
            ticker: Ticker symbol
            exchange: Exchange hint (optional)

        Returns:
            TickerInfo with ticker metadata
        """
        if self._should_simulate_error(ticker):
            raise DataProviderError(
                f"Simulated error for ticker {ticker}",
                provider=self.provider_name,
            )

        # Check for predefined ticker info
        if ticker in MOCK_TICKER_INFO:
            info = MOCK_TICKER_INFO[ticker]
            config = self._get_config(ticker)

            # Calculate approximate market cap
            current = await self.get_current_price(ticker, exchange)
            # Assume 1 billion shares outstanding for mock purposes
            market_cap = current.price * Decimal("1000000000")

            return TickerInfo(
                symbol=ticker,
                name=info["name"],
                exchange=info["exchange"],
                currency=info["currency"],
                security_type=info["security_type"],
                sector=info.get("sector"),
                market_cap=market_cap,
                extra={"mock": True},
            )

        # Generate info for unknown ticker
        detected_exchange = exchange or self.detect_exchange(ticker)
        currency_map = {
            Exchange.KRX: "KRW",
            Exchange.KRX_KOSPI: "KRW",
            Exchange.KRX_KOSDAQ: "KRW",
            Exchange.HKEX: "HKD",
            Exchange.TSE: "JPY",
            Exchange.SSE: "CNY",
            Exchange.SZSE: "CNY",
        }
        currency = currency_map.get(detected_exchange, "USD")

        return TickerInfo(
            symbol=ticker,
            name=f"Mock Company {ticker}",
            exchange=detected_exchange,
            currency=currency,
            security_type="stock",
            extra={"mock": True, "generated": True},
        )

    async def get_available_date_range(
        self,
        ticker: str,
        exchange: Exchange | None = None,
    ) -> DateRange:
        """
        Get the available date range for historical data.

        Mock provider supports data from 2010 to today.

        Args:
            ticker: Ticker symbol
            exchange: Exchange hint (optional)

        Returns:
            DateRange indicating available historical data range
        """
        # Mock data is available from 2010 onwards
        return DateRange(
            start_date=date(2010, 1, 1),
            end_date=date.today(),
            ticker=ticker,
        )

    async def health_check(self) -> bool:
        """
        Check if the Mock provider is healthy.

        Always returns True for mock provider.

        Returns:
            True (always healthy)
        """
        return True

    @classmethod
    def with_error_simulation(
        cls,
        error_rate: float = 0.1,
        default_config: MockDataConfig | None = None,
    ) -> "MockDataProvider":
        """
        Create a MockDataProvider with error simulation enabled.

        Useful for testing error handling and fallback mechanisms.

        Args:
            error_rate: Rate of simulated errors (0.0 to 1.0)
            default_config: Default configuration for unknown tickers

        Returns:
            MockDataProvider with error simulation
        """
        return cls(
            default_config=default_config,
            simulate_errors=True,
            error_rate=error_rate,
        )
