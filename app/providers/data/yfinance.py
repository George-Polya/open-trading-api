"""
YFinance Data Provider implementation.

Provides market data from Yahoo Finance as a fallback/alternative to KIS API.
Uses asyncio.to_thread for non-blocking execution since yfinance is synchronous.
Now supports local CSV cache for faster data retrieval.
"""

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf
from pandas import DataFrame

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

# Cache directory for price data
CACHE_DIR = Path(__file__).parent.parent.parent.parent / "stocks_info" / "price_cache"


class YFinanceDataProvider(DataProvider):
    """
    Yahoo Finance data provider implementation.

    Provides async access to Yahoo Finance market data including:
    - Daily OHLCV price data for global markets
    - Current/real-time prices
    - Ticker information

    Uses asyncio.to_thread for non-blocking HTTP requests since
    yfinance is a synchronous library.

    Example:
        provider = YFinanceDataProvider()

        prices = await provider.get_daily_prices(
            "AAPL",
            date(2024, 1, 1),
            date(2024, 3, 31)
        )
    """

    # Exchange mapping for Korean stocks (add .KS or .KQ suffix)
    KOREAN_EXCHANGE_SUFFIX = {
        Exchange.KRX: ".KS",  # KOSPI
        Exchange.KRX_KOSPI: ".KS",
        Exchange.KRX_KOSDAQ: ".KQ",
    }

    # Exchange to currency mapping
    EXCHANGE_CURRENCY_MAP = {
        Exchange.KRX: "KRW",
        Exchange.KRX_KOSPI: "KRW",
        Exchange.KRX_KOSDAQ: "KRW",
        Exchange.NYSE: "USD",
        Exchange.NASDAQ: "USD",
        Exchange.AMEX: "USD",
        Exchange.HKEX: "HKD",
        Exchange.TSE: "JPY",
        Exchange.SSE: "CNY",
        Exchange.SZSE: "CNY",
    }

    def __init__(self) -> None:
        """Initialize the YFinance data provider."""
        self._initialized = False

    @property
    def provider_name(self) -> str:
        """Get the provider name."""
        return "yfinance"

    async def initialize(self) -> None:
        """
        Initialize the provider.

        YFinance doesn't require explicit initialization,
        but we track state for consistency with other providers.
        """
        self._initialized = True
        logger.info("YFinance data provider initialized")

    async def close(self) -> None:
        """Clean up provider resources."""
        self._initialized = False

    def _format_ticker(self, ticker: str, exchange: Exchange | None = None) -> str:
        """
        Format ticker symbol for yfinance.

        Adds exchange suffix for Korean stocks.

        Args:
            ticker: Original ticker symbol
            exchange: Exchange hint

        Returns:
            Formatted ticker for yfinance
        """
        if exchange is None:
            exchange = self.detect_exchange(ticker)

        suffix = self.KOREAN_EXCHANGE_SUFFIX.get(exchange, "")
        return f"{ticker}{suffix}"

    def _parse_decimal(self, value: Any, default: Decimal = Decimal("0")) -> Decimal:
        """Safely parse a value to Decimal."""
        if value is None or (hasattr(value, "__len__") and len(value) == 0):
            return default
        try:
            # Handle numpy/pandas numeric types
            float_val = float(value)
            if float_val != float_val:  # Check for NaN
                return default
            return Decimal(str(float_val))
        except (InvalidOperation, ValueError, TypeError):
            return default

    def _parse_int(self, value: Any, default: int = 0) -> int:
        """Safely parse a value to int."""
        if value is None:
            return default
        try:
            float_val = float(value)
            if float_val != float_val:  # Check for NaN
                return default
            return int(float_val)
        except (ValueError, TypeError):
            return default

    def _normalize_prices(self, df: DataFrame, ticker: str) -> list[PriceData]:
        """
        Normalize yfinance DataFrame to PriceData format.

        Args:
            df: DataFrame from yfinance with OHLCV data
            ticker: Ticker symbol for logging

        Returns:
            List of PriceData records
        """
        if df.empty:
            return []

        prices = []
        for idx, row in df.iterrows():
            try:
                # Convert index to date (UTC aware)
                if hasattr(idx, "date"):
                    price_date = idx.date()
                else:
                    price_date = idx

                # Parse OHLCV values
                open_price = self._parse_decimal(row.get("Open"))
                high_price = self._parse_decimal(row.get("High"))
                low_price = self._parse_decimal(row.get("Low"))
                close_price = self._parse_decimal(row.get("Close"))
                volume = self._parse_int(row.get("Volume"))
                # Try "Adj Close" first, fall back to "Close" (yfinance newer versions)
                adj_close = self._parse_decimal(row.get("Adj Close"))
                if adj_close == Decimal("0"):
                    adj_close = close_price  # Use Close as adjusted close

                # Skip if essential data is missing
                if close_price == Decimal("0"):
                    continue

                # Ensure high >= low (data quality check)
                if high_price < low_price:
                    high_price, low_price = low_price, high_price

                price_data = PriceData(
                    date=price_date,
                    open=open_price,
                    high=high_price,
                    low=low_price,
                    close=close_price,
                    volume=volume,
                    adjusted_close=adj_close if adj_close != Decimal("0") else None,
                )
                prices.append(price_data)
            except Exception as e:
                logger.warning(f"Failed to parse price row for {ticker}: {e}")
                continue

        return prices

    def _load_cache_for_year(self, ticker: str, year: int) -> DataFrame | None:
        """
        Load cached data for a specific year.
        
        Args:
            ticker: Ticker symbol (e.g., "SPY", "QQQ")
            year: Year to load
            
        Returns:
            DataFrame with OHLCV data or None if not cached
        """
        ticker_dir = CACHE_DIR / ticker.upper()
        cache_file = ticker_dir / f"{year}.csv"
        
        if cache_file.exists():
            try:
                df = pd.read_csv(cache_file, header=[0, 1], index_col=0)
                # Parse datetime index and remove timezone info to avoid comparison issues
                df.index = pd.to_datetime(df.index, utc=True).tz_localize(None)
                # MultiIndex 컬럼을 단일 레벨로 변환
                df.columns = df.columns.get_level_values(0)
                
                # Remove "Price" column if it exists (artifact from index name in CSV)
                if "Price" in df.columns:
                    df = df.drop(columns=["Price"])
                
                # Rename columns to match yfinance history() format
                # yf.download() returns: Close, High, Low, Open, Volume
                # yf.Ticker.history() returns: Open, High, Low, Close, Adj Close, Volume
                column_mapping = {
                    "Close": "Close",
                    "High": "High", 
                    "Low": "Low",
                    "Open": "Open",
                    "Volume": "Volume",
                }
                df = df.rename(columns=column_mapping)
                
                # If no "Adj Close", create it from "Close" (yf.download with auto_adjust=True)
                if "Adj Close" not in df.columns and "Close" in df.columns:
                    df["Adj Close"] = df["Close"]
                
                logger.debug(f"Loaded from cache: {ticker.upper()}/{year}.csv with columns {list(df.columns)}")
                return df
            except Exception as e:
                logger.warning(f"Failed to load cache {cache_file}: {e}")
        return None

    def _save_cache_for_year(self, df: DataFrame, ticker: str, year: int) -> None:
        """
        Save data to cache for a specific year.
        
        Args:
            df: DataFrame with OHLCV data
            ticker: Ticker symbol
            year: Year to save
        """
        if df.empty:
            return
        
        ticker_dir = CACHE_DIR / ticker.upper()
        ticker_dir.mkdir(parents=True, exist_ok=True)
        cache_file = ticker_dir / f"{year}.csv"
        
        try:
            df.to_csv(cache_file)
            logger.debug(f"Saved to cache: {ticker.upper()}/{year}.csv")
        except Exception as e:
            logger.warning(f"Failed to save cache {cache_file}: {e}")

    def _fetch_history_sync(
        self,
        yf_ticker: str,
        start_date: date,
        end_date: date,
    ) -> DataFrame:
        """
        Synchronously fetch historical data, using cache when available.
        
        Checks local CSV cache first for each year in the date range.
        Only downloads from yfinance for years not in cache.

        Args:
            yf_ticker: Formatted ticker for yfinance
            start_date: Start date
            end_date: End date

        Returns:
            DataFrame with OHLCV data
        """
        # Extract base ticker (remove exchange suffix like .KS, .KQ)
        base_ticker = yf_ticker.split('.')[0]
        
        all_data = []
        years_to_download = []
        
        # Check cache for each year in range
        for year in range(start_date.year, end_date.year + 1):
            cached_df = self._load_cache_for_year(base_ticker, year)
            if cached_df is not None:
                all_data.append(cached_df)
                logger.info(f"Cache hit: {base_ticker}_{year}")
            else:
                years_to_download.append(year)
        
        # Download missing years from yfinance
        if years_to_download:
            logger.info(f"Downloading from yfinance: {base_ticker} years {years_to_download}")
            ticker_obj = yf.Ticker(yf_ticker)
            
            for year in years_to_download:
                year_start = f"{year}-01-01"
                year_end = f"{year}-12-31"
                
                # For current year, use today as end date
                if year == datetime.now().year:
                    year_end = datetime.now().strftime("%Y-%m-%d")
                
                try:
                    df = ticker_obj.history(
                        start=year_start,
                        end=year_end,
                        auto_adjust=False,
                    )
                    
                    if not df.empty:
                        # Save to cache
                        self._save_cache_for_year(df, base_ticker, year)
                        all_data.append(df)
                except Exception as e:
                    logger.warning(f"Failed to download {base_ticker} {year}: {e}")
        
        if not all_data:
            return DataFrame()
        
        # Combine all data
        combined_df = pd.concat(all_data)
        combined_df = combined_df.sort_index()
        combined_df = combined_df[~combined_df.index.duplicated(keep='last')]
        
        # Remove timezone info from index to avoid tz-naive vs tz-aware comparison issues
        if combined_df.index.tz is not None:
            combined_df.index = combined_df.index.tz_localize(None)
        
        # Filter to requested date range
        start_ts = pd.Timestamp(start_date)
        end_ts = pd.Timestamp(end_date)
        combined_df = combined_df[
            (combined_df.index >= start_ts) &
            (combined_df.index <= end_ts)
        ]
        
        return combined_df

    def _fetch_info_sync(self, yf_ticker: str) -> dict[str, Any]:
        """
        Synchronously fetch ticker info from yfinance.

        Args:
            yf_ticker: Formatted ticker for yfinance

        Returns:
            Dictionary with ticker info
        """
        ticker_obj = yf.Ticker(yf_ticker)
        return ticker_obj.info

    def _fetch_fast_info_sync(self, yf_ticker: str) -> tuple[dict[str, Any], dict[str, Any]]:
        """
        Synchronously fetch fast info and basic info from yfinance.

        Args:
            yf_ticker: Formatted ticker for yfinance

        Returns:
            Tuple of (fast_info dict, basic_info dict)
        """
        ticker_obj = yf.Ticker(yf_ticker)
        fast_info = {}
        basic_info = {}

        # Get fast_info (lightweight)
        try:
            fi = ticker_obj.fast_info
            fast_info = {
                "last_price": getattr(fi, "last_price", None),
                "previous_close": getattr(fi, "previous_close", None),
                "open": getattr(fi, "open", None),
                "day_high": getattr(fi, "day_high", None),
                "day_low": getattr(fi, "day_low", None),
                "last_volume": getattr(fi, "last_volume", None),
                "market_cap": getattr(fi, "market_cap", None),
            }
        except Exception as e:
            logger.debug(f"Failed to get fast_info for {yf_ticker}: {e}")

        # Get basic info
        try:
            basic_info = ticker_obj.basic_info or {}
        except Exception:
            pass

        return fast_info, basic_info

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
        if start_date > end_date:
            raise InvalidDateRangeError(
                start_date, end_date, "Start date after end date", self.provider_name
            )

        yf_ticker = self._format_ticker(ticker, exchange)

        try:
            df = await asyncio.to_thread(
                self._fetch_history_sync,
                yf_ticker,
                start_date,
                end_date,
            )

            if df.empty:
                # Try without suffix for non-Korean stocks
                if exchange and exchange not in self.KOREAN_EXCHANGE_SUFFIX:
                    raise TickerNotFoundError(ticker, self.provider_name)
                # For Korean stocks, try alternate exchange
                if exchange == Exchange.KRX_KOSPI:
                    yf_ticker = f"{ticker}.KQ"
                elif exchange == Exchange.KRX_KOSDAQ:
                    yf_ticker = f"{ticker}.KS"
                else:
                    raise TickerNotFoundError(ticker, self.provider_name)

                df = await asyncio.to_thread(
                    self._fetch_history_sync,
                    yf_ticker,
                    start_date,
                    end_date,
                )
                if df.empty:
                    raise TickerNotFoundError(ticker, self.provider_name)

            prices = self._normalize_prices(df, ticker)
            prices.sort(key=lambda p: p.date)
            return prices

        except TickerNotFoundError:
            raise
        except Exception as e:
            logger.error(f"YFinance error fetching {ticker}: {e}")
            raise DataProviderError(
                f"Failed to fetch data for {ticker}: {e}",
                provider=self.provider_name,
            ) from e

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
        yf_ticker = self._format_ticker(ticker, exchange)

        try:
            fast_info, basic_info = await asyncio.to_thread(
                self._fetch_fast_info_sync,
                yf_ticker,
            )

            # Get price from fast_info or fall back to history
            price = fast_info.get("last_price")
            prev_close = fast_info.get("previous_close")

            if price is None:
                # Fall back to most recent history
                yesterday = date.today() - timedelta(days=7)
                df = await asyncio.to_thread(
                    self._fetch_history_sync,
                    yf_ticker,
                    yesterday,
                    date.today(),
                )
                if df.empty:
                    raise TickerNotFoundError(ticker, self.provider_name)

                last_row = df.iloc[-1]
                price = last_row.get("Close")
                prev_close = df.iloc[-2].get("Close") if len(df) > 1 else None

            price_decimal = self._parse_decimal(price)
            prev_close_decimal = self._parse_decimal(prev_close)

            change = price_decimal - prev_close_decimal if prev_close_decimal else Decimal("0")
            change_percent = (
                (change / prev_close_decimal * 100)
                if prev_close_decimal and prev_close_decimal != Decimal("0")
                else Decimal("0")
            )

            return CurrentPrice(
                symbol=ticker,
                price=price_decimal,
                change=change,
                change_percent=change_percent,
                volume=self._parse_int(fast_info.get("last_volume", 0)),
                timestamp=datetime.now(timezone.utc),
                extra={
                    "open": self._parse_decimal(fast_info.get("open")),
                    "high": self._parse_decimal(fast_info.get("day_high")),
                    "low": self._parse_decimal(fast_info.get("day_low")),
                    "prev_close": prev_close_decimal,
                    "market_cap": self._parse_decimal(fast_info.get("market_cap")),
                },
            )

        except TickerNotFoundError:
            raise
        except Exception as e:
            logger.error(f"YFinance error getting current price for {ticker}: {e}")
            raise DataProviderError(
                f"Failed to get current price for {ticker}: {e}",
                provider=self.provider_name,
            ) from e

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
        yf_ticker = self._format_ticker(ticker, exchange)
        detected_exchange = exchange or self.detect_exchange(ticker)

        try:
            info = await asyncio.to_thread(self._fetch_info_sync, yf_ticker)

            if not info or info.get("regularMarketPrice") is None:
                # Some tickers only have minimal info
                fast_info, _ = await asyncio.to_thread(
                    self._fetch_fast_info_sync,
                    yf_ticker,
                )
                if not fast_info.get("last_price"):
                    raise TickerNotFoundError(ticker, self.provider_name)

            # Determine security type
            quote_type = info.get("quoteType", "EQUITY").upper()
            security_type_map = {
                "EQUITY": "stock",
                "ETF": "etf",
                "MUTUALFUND": "fund",
                "INDEX": "index",
                "CURRENCY": "currency",
                "CRYPTOCURRENCY": "crypto",
            }
            security_type = security_type_map.get(quote_type, "stock")

            # Get currency
            currency = info.get("currency") or self.EXCHANGE_CURRENCY_MAP.get(
                detected_exchange, "USD"
            )

            return TickerInfo(
                symbol=ticker,
                name=info.get("longName") or info.get("shortName") or ticker,
                exchange=detected_exchange,
                currency=currency,
                security_type=security_type,
                sector=info.get("sector"),
                market_cap=self._parse_decimal(info.get("marketCap")),
                extra={
                    "industry": info.get("industry"),
                    "website": info.get("website"),
                    "country": info.get("country"),
                    "employees": info.get("fullTimeEmployees"),
                    "description": info.get("longBusinessSummary"),
                },
            )

        except TickerNotFoundError:
            raise
        except Exception as e:
            logger.error(f"YFinance error getting ticker info for {ticker}: {e}")
            raise DataProviderError(
                f"Failed to get ticker info for {ticker}: {e}",
                provider=self.provider_name,
            ) from e

    async def get_available_date_range(
        self,
        ticker: str,
        exchange: Exchange | None = None,
    ) -> DateRange:
        """
        Get the available date range for historical data.

        YFinance typically provides data back to the IPO date
        or start of available data.

        Args:
            ticker: Ticker symbol
            exchange: Exchange hint (optional)

        Returns:
            DateRange indicating available historical data range
        """
        yf_ticker = self._format_ticker(ticker, exchange)

        try:
            # Get max available history to determine range
            ticker_obj = yf.Ticker(yf_ticker)

            def get_history_range():
                df = ticker_obj.history(period="max")
                if df.empty:
                    return None, None
                return df.index[0].date(), df.index[-1].date()

            start_date, end_date = await asyncio.to_thread(get_history_range)

            if start_date is None:
                raise TickerNotFoundError(ticker, self.provider_name)

            return DateRange(
                start_date=start_date,
                end_date=end_date,
                ticker=ticker,
            )

        except TickerNotFoundError:
            raise
        except Exception as e:
            logger.error(f"YFinance error getting date range for {ticker}: {e}")
            raise DataProviderError(
                f"Failed to get date range for {ticker}: {e}",
                provider=self.provider_name,
            ) from e

    async def health_check(self) -> bool:
        """
        Check if the YFinance provider is healthy.

        Tests connectivity by fetching a known ticker.

        Returns:
            True if healthy, False otherwise
        """
        try:
            # Test with a commonly available ticker
            df = await asyncio.to_thread(
                self._fetch_history_sync,
                "AAPL",
                date.today() - timedelta(days=7),
                date.today(),
            )
            return not df.empty
        except Exception as e:
            logger.warning(f"YFinance health check failed: {e}")
            return False
