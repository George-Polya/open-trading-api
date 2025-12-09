"""
Data Provider base abstractions.

Defines provider-agnostic interfaces following SOLID Dependency Inversion Principle.
All concrete data provider adapters must implement the DataProvider abstract base class.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any


class Exchange(str, Enum):
    """Supported exchanges."""

    # Korean exchanges
    KRX = "KRX"  # Korea Exchange (KOSPI, KOSDAQ)
    KRX_KOSPI = "KRX_KOSPI"  # KOSPI
    KRX_KOSDAQ = "KRX_KOSDAQ"  # KOSDAQ

    # US exchanges
    NYSE = "NYSE"  # New York Stock Exchange
    NASDAQ = "NAS"  # NASDAQ
    AMEX = "AMS"  # NYSE American (AMEX)

    # Other exchanges
    HKEX = "HKS"  # Hong Kong Stock Exchange
    TSE = "TSE"  # Tokyo Stock Exchange
    SSE = "SHS"  # Shanghai Stock Exchange
    SZSE = "SZS"  # Shenzhen Stock Exchange


@dataclass(frozen=True)
class PriceData:
    """
    Standardized price data record.

    Represents a single OHLCV (Open, High, Low, Close, Volume) record
    with a normalized schema across all data providers.

    Attributes:
        date: Trading date
        open: Opening price
        high: Highest price during the period
        low: Lowest price during the period
        close: Closing price
        volume: Trading volume
        adjusted_close: Dividend/split adjusted close price (optional)
        extra: Additional provider-specific fields
    """

    date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    adjusted_close: Decimal | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate price data."""
        if self.high < self.low:
            raise ValueError(f"High ({self.high}) cannot be less than low ({self.low})")
        if self.open < 0 or self.close < 0 or self.high < 0 or self.low < 0:
            raise ValueError("Prices cannot be negative")
        if self.volume < 0:
            raise ValueError("Volume cannot be negative")


@dataclass(frozen=True)
class TickerInfo:
    """
    Metadata about a ticker/security.

    Provides normalized ticker information across different exchanges
    and data providers.

    Attributes:
        symbol: Ticker symbol (e.g., "005930" for Samsung, "AAPL" for Apple)
        name: Company/security name
        exchange: Exchange where the security is traded
        currency: Trading currency (e.g., "KRW", "USD")
        security_type: Type of security (e.g., "stock", "etf", "bond")
        sector: Industry sector (optional)
        market_cap: Market capitalization (optional)
        extra: Additional provider-specific metadata
    """

    symbol: str
    name: str
    exchange: Exchange
    currency: str = "KRW"
    security_type: str = "stock"
    sector: str | None = None
    market_cap: Decimal | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DateRange:
    """
    Available date range for historical data.

    Represents the earliest and latest dates for which
    historical data is available for a given ticker.

    Attributes:
        start_date: Earliest available date
        end_date: Latest available date
        ticker: Ticker symbol this range applies to
    """

    start_date: date
    end_date: date
    ticker: str

    def __post_init__(self) -> None:
        """Validate date range."""
        if self.start_date > self.end_date:
            raise ValueError(
                f"Start date ({self.start_date}) cannot be after end date ({self.end_date})"
            )

    def contains(self, check_date: date) -> bool:
        """Check if a date is within this range."""
        return self.start_date <= check_date <= self.end_date

    @property
    def days(self) -> int:
        """Return the number of days in the range."""
        return (self.end_date - self.start_date).days


@dataclass(frozen=True)
class CurrentPrice:
    """
    Current/real-time price information.

    Represents the latest price data for a ticker.

    Attributes:
        symbol: Ticker symbol
        price: Current price
        change: Price change from previous close
        change_percent: Percentage change from previous close
        volume: Current day's trading volume
        timestamp: Timestamp of the price data
        bid: Current bid price (optional)
        ask: Current ask price (optional)
        extra: Additional provider-specific fields
    """

    symbol: str
    price: Decimal
    change: Decimal
    change_percent: Decimal
    volume: int
    timestamp: datetime
    bid: Decimal | None = None
    ask: Decimal | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class DataProvider(ABC):
    """
    Abstract base class for data providers.

    All concrete data provider adapters (KIS, YFinance, etc.) must implement
    this interface to ensure consistent behavior across providers.

    The interface follows the Dependency Inversion Principle (DIP):
    - High-level modules (backtest service) depend on this abstraction
    - Low-level modules (adapters) implement this abstraction

    Example:
        class KISDataProvider(DataProvider):
            async def get_daily_prices(self, ticker, start_date, end_date):
                # Implementation
                ...

            def get_provider_name(self) -> str:
                return "kis"
    """

    @abstractmethod
    async def get_daily_prices(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
        exchange: Exchange | None = None,
    ) -> list[PriceData]:
        """
        Get daily OHLCV price data for a ticker.

        Args:
            ticker: Ticker symbol (e.g., "005930", "AAPL")
            start_date: Start date for historical data
            end_date: End date for historical data
            exchange: Exchange hint (optional, auto-detected if not provided)

        Returns:
            List of PriceData records sorted by date ascending

        Raises:
            DataProviderError: If data retrieval fails
            TickerNotFoundError: If the ticker is not found
        """
        ...

    @abstractmethod
    async def get_current_price(
        self,
        ticker: str,
        exchange: Exchange | None = None,
    ) -> CurrentPrice:
        """
        Get the current/latest price for a ticker.

        Args:
            ticker: Ticker symbol
            exchange: Exchange hint (optional)

        Returns:
            CurrentPrice with latest price information

        Raises:
            DataProviderError: If data retrieval fails
            TickerNotFoundError: If the ticker is not found
        """
        ...

    @abstractmethod
    async def get_ticker_info(
        self,
        ticker: str,
        exchange: Exchange | None = None,
    ) -> TickerInfo:
        """
        Get metadata about a ticker.

        Args:
            ticker: Ticker symbol
            exchange: Exchange hint (optional)

        Returns:
            TickerInfo with ticker metadata

        Raises:
            DataProviderError: If data retrieval fails
            TickerNotFoundError: If the ticker is not found
        """
        ...

    @abstractmethod
    async def get_available_date_range(
        self,
        ticker: str,
        exchange: Exchange | None = None,
    ) -> DateRange:
        """
        Get the available date range for historical data.

        Args:
            ticker: Ticker symbol
            exchange: Exchange hint (optional)

        Returns:
            DateRange indicating available historical data range

        Raises:
            DataProviderError: If data retrieval fails
            TickerNotFoundError: If the ticker is not found
        """
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """
        Get the provider name.

        Returns:
            Provider identifier string (e.g., "kis", "yfinance")
        """
        ...

    def detect_exchange(self, ticker: str) -> Exchange:
        """
        Detect the exchange for a given ticker symbol.

        Default implementation uses symbol format heuristics:
        - 6 digits => KRX (Korean stocks)
        - Otherwise => NASDAQ (US stocks)

        Override in subclasses for more sophisticated detection.

        Args:
            ticker: Ticker symbol

        Returns:
            Detected Exchange enum value
        """
        # Korean stock codes are typically 6 digits
        if ticker.isdigit() and len(ticker) == 6:
            return Exchange.KRX
        # Default to NASDAQ for other symbols
        return Exchange.NASDAQ

    async def health_check(self) -> bool:
        """
        Check if the provider is healthy and accessible.

        Default implementation returns True. Override for custom health checks.

        Returns:
            True if provider is healthy, False otherwise
        """
        return True

    async def close(self) -> None:
        """
        Clean up provider resources.

        Called during application shutdown. Override if the provider
        holds resources that need cleanup (e.g., HTTP connections, auth tokens).
        """
        pass


class DataProviderError(Exception):
    """Base exception for data provider errors."""

    def __init__(self, message: str, provider: str | None = None):
        self.provider = provider
        super().__init__(message)


class TickerNotFoundError(DataProviderError):
    """Raised when a ticker symbol is not found."""

    def __init__(self, ticker: str, provider: str | None = None):
        self.ticker = ticker
        super().__init__(f"Ticker '{ticker}' not found", provider)


class AuthenticationError(DataProviderError):
    """Raised when API authentication fails."""

    pass


class RateLimitError(DataProviderError):
    """Raised when API rate limit is exceeded."""

    def __init__(
        self,
        message: str,
        provider: str | None = None,
        retry_after: float | None = None,
    ):
        self.retry_after = retry_after
        super().__init__(message, provider)


class InvalidDateRangeError(DataProviderError):
    """Raised when the requested date range is invalid."""

    def __init__(
        self,
        start_date: date,
        end_date: date,
        reason: str | None = None,
        provider: str | None = None,
    ):
        self.start_date = start_date
        self.end_date = end_date
        message = f"Invalid date range: {start_date} to {end_date}"
        if reason:
            message += f" - {reason}"
        super().__init__(message, provider)


class DataUnavailableError(DataProviderError):
    """
    Raised when data is temporarily unavailable.

    This error indicates a transient failure that may be resolved
    by retrying or using a fallback provider. It's distinct from
    TickerNotFoundError which indicates the ticker doesn't exist.

    Examples:
        - API service temporarily down
        - Network connectivity issues
        - Rate limit exceeded (but retryable)
        - Data not yet available for the requested date range
    """

    def __init__(
        self,
        message: str,
        provider: str | None = None,
        retryable: bool = True,
    ):
        self.retryable = retryable
        super().__init__(message, provider)
