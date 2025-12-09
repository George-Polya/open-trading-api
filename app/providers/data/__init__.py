"""
Data Provider package.

Provides abstractions and implementations for market data providers.
"""

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
from app.providers.data.kis import KISDataProvider
from app.providers.data.kis_auth import KISAuthManager

__all__ = [
    # Base classes and types
    "DataProvider",
    "PriceData",
    "CurrentPrice",
    "TickerInfo",
    "DateRange",
    "Exchange",
    # Errors
    "DataProviderError",
    "TickerNotFoundError",
    "AuthenticationError",
    "RateLimitError",
    "InvalidDateRangeError",
    # Implementations
    "KISDataProvider",
    "KISAuthManager",
]
