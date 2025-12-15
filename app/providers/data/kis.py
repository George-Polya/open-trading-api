"""
KIS (Korea Investment & Securities) Data Provider implementation.

Provides market data from KIS OpenAPI with async support.
Wraps synchronous KIS API calls using asyncio.to_thread for non-blocking execution.
"""

import asyncio
import logging
import time
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from functools import partial
from typing import Any

import httpx
import pandas as pd

from app.core.config import KISConfig
from app.providers.data.base import (
    CurrentPrice,
    DataProvider,
    DataUnavailableError,
    DataProviderError,
    DateRange,
    Exchange,
    InvalidDateRangeError,
    PriceData,
    RateLimitError,
    TickerInfo,
    TickerNotFoundError,
)
from app.providers.data.kis_auth import AuthenticationError, KISAuthManager

logger = logging.getLogger(__name__)


class KISDataProvider(DataProvider):
    """
    KIS OpenAPI data provider implementation.

    Provides async access to KIS market data including:
    - Daily OHLCV price data (domestic and overseas)
    - Current/real-time prices
    - Ticker information

    Uses asyncio.to_thread for non-blocking HTTP requests.

    Example:
        config = KISConfig.from_yaml("kis_devlp.yaml")
        provider = KISDataProvider(config)
        await provider.initialize()

        prices = await provider.get_daily_prices(
            "005930",  # Samsung Electronics
            date(2024, 1, 1),
            date(2024, 3, 31)
        )
    """

    # Column mappings for domestic stocks (국내주식)
    DOMESTIC_PRICE_COLUMNS = {
        "stck_bsop_date": "date",  # 주식 영업 일자
        "stck_oprc": "open",  # 시가
        "stck_hgpr": "high",  # 고가
        "stck_lwpr": "low",  # 저가
        "stck_clpr": "close",  # 종가
        "acml_vol": "volume",  # 누적 거래량
        "acml_tr_pbmn": "turnover",  # 누적 거래대금
        "prdy_vrss": "change",  # 전일 대비
        "prdy_vrss_sign": "change_sign",  # 전일 대비 부호
    }

    # Column mappings for overseas stocks (해외주식)
    OVERSEAS_PRICE_COLUMNS = {
        "xymd": "date",  # 일자
        "open": "open",  # 시가
        "high": "high",  # 고가
        "low": "low",  # 저가
        "clos": "close",  # 종가
        "tvol": "volume",  # 거래량
        "tamt": "turnover",  # 거래대금
    }

    # Exchange code mappings for overseas markets
    OVERSEAS_EXCHANGE_CODES = {
        Exchange.NYSE: "NYS",
        Exchange.NASDAQ: "NAS",
        Exchange.AMEX: "AMS",
        Exchange.HKEX: "HKS",
        Exchange.TSE: "TSE",
        Exchange.SSE: "SHS",
        Exchange.SZSE: "SZS",
    }

    # Reverse mapping
    EXCHANGE_CODE_TO_ENUM = {v: k for k, v in OVERSEAS_EXCHANGE_CODES.items()}

    def __init__(
        self,
        config: KISConfig,
        is_paper: bool = False,
        product_code: str = "01",
        http_client: httpx.AsyncClient | None = None,
    ):
        """
        Initialize the KIS data provider.

        Args:
            config: KIS configuration with credentials
            is_paper: Whether to use paper trading mode
            product_code: Account product code
            http_client: Optional shared HTTP client
        """
        self._config = config
        self._is_paper = is_paper
        self._auth_manager = KISAuthManager(
            config=config,
            is_paper=is_paper,
            product_code=product_code,
        )
        self._http_client = http_client
        self._owns_client = False
        self._request_lock = asyncio.Lock()
        self._last_request_at = 0.0
        self._min_request_interval_seconds = 0.25

    @property
    def provider_name(self) -> str:
        """Get the provider name."""
        return "kis"

    async def initialize(self) -> None:
        """
        Initialize the provider and authenticate.

        Should be called before making any data requests.
        """
        await self._auth_manager.authenticate()
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(60.0),
                limits=httpx.Limits(max_connections=50, max_keepalive_connections=10),
            )
            self._owns_client = True

    async def close(self) -> None:
        """Clean up provider resources."""
        if self._owns_client and self._http_client:
            await self._http_client.aclose()
            self._http_client = None
        await self._auth_manager.close()

    def detect_exchange(self, ticker: str) -> Exchange:
        """
        Detect the exchange for a given ticker symbol.

        Korean stock codes are 6 digits.
        US stock symbols are typically alphabetic.

        Args:
            ticker: Ticker symbol

        Returns:
            Detected Exchange enum value
        """
        # Korean stock codes are 6 digits
        if ticker.isdigit() and len(ticker) == 6:
            return Exchange.KRX

        # For alphabetic symbols, default to NASDAQ
        # More sophisticated detection could use prefix patterns
        return Exchange.NASDAQ

    def _is_domestic(self, exchange: Exchange) -> bool:
        """Check if the exchange is a Korean domestic exchange."""
        return exchange in (Exchange.KRX, Exchange.KRX_KOSPI, Exchange.KRX_KOSDAQ)

    async def _ensure_authenticated(self) -> None:
        """Ensure authentication is valid."""
        if not self._auth_manager.is_authenticated:
            await self._auth_manager.authenticate()

    async def _make_request(
        self,
        api_url: str,
        tr_id: str,
        params: dict[str, Any],
        tr_cont: str = "",
    ) -> dict[str, Any]:
        """
        Make an authenticated API request to KIS.

        Args:
            api_url: API endpoint path
            tr_id: Transaction ID
            params: Query parameters
            tr_cont: Transaction continuation flag

        Returns:
            JSON response data

        Raises:
            DataProviderError: If the request fails
        """
        await self._ensure_authenticated()

        if self._http_client is None:
            await self.initialize()

        env = self._auth_manager.environment
        url = f"{env.base_url}{api_url}"
        headers = self._auth_manager.get_tr_headers(tr_id, tr_cont)

        def _is_rate_limit(msg_cd: str | None, msg1: str | None) -> bool:
            return (msg_cd == "EGW00201") or ("초당 거래건수" in (msg1 or ""))

        async def _throttle() -> None:
            async with self._request_lock:
                now = time.monotonic()
                wait = self._min_request_interval_seconds - (now - self._last_request_at)
                if wait > 0:
                    await asyncio.sleep(wait)
                self._last_request_at = time.monotonic()

        last_error: Exception | None = None
        for attempt in range(1, 4):
            try:
                await _throttle()
                response = await self._http_client.get(url, params=params, headers=headers)

                data: dict[str, Any] | None = None
                if response.headers.get("content-type", "").startswith("application/json"):
                    try:
                        data = response.json()
                    except Exception:
                        data = None

                if response.status_code != 200:
                    msg_cd = (data or {}).get("msg_cd") if data else None
                    msg1 = (data or {}).get("msg1") if data else None
                    if _is_rate_limit(msg_cd, msg1):
                        retry_after = 0.8 * attempt
                        last_error = RateLimitError(
                            f"KIS rate limit exceeded: {msg1 or 'unknown'}",
                            provider=self.provider_name,
                            retry_after=retry_after,
                        )
                        await asyncio.sleep(retry_after)
                        continue
                    raise DataUnavailableError(
                        f"KIS API HTTP {response.status_code}: {response.text}",
                        provider=self.provider_name,
                    )

                if data is None:
                    data = response.json()

                # Check KIS-specific error codes
                if data.get("rt_cd") != "0":
                    error_msg = data.get("msg1", "Unknown error")
                    error_code = data.get("msg_cd", "")
                    if _is_rate_limit(error_code, error_msg):
                        retry_after = 0.8 * attempt
                        last_error = RateLimitError(
                            f"KIS rate limit exceeded: {error_msg}",
                            provider=self.provider_name,
                            retry_after=retry_after,
                        )
                        await asyncio.sleep(retry_after)
                        continue
                    raise DataProviderError(
                        f"KIS API error [{error_code}]: {error_msg}",
                        provider=self.provider_name,
                    )

                return data

            except httpx.RequestError as e:
                last_error = DataUnavailableError(
                    f"Network error: {str(e)}",
                    provider=self.provider_name,
                )
                await asyncio.sleep(0.4 * attempt)
                continue

        if last_error is not None:
            raise last_error
        raise DataProviderError("KIS API request failed after retries", provider=self.provider_name)

    def _parse_decimal(self, value: Any, default: Decimal = Decimal("0")) -> Decimal:
        """Safely parse a value to Decimal."""
        if value is None or value == "":
            return default
        try:
            return Decimal(str(value).replace(",", ""))
        except (InvalidOperation, ValueError):
            return default

    def _parse_int(self, value: Any, default: int = 0) -> int:
        """Safely parse a value to int."""
        if value is None or value == "":
            return default
        try:
            return int(str(value).replace(",", ""))
        except (ValueError, TypeError):
            return default

    def _parse_date(self, value: str, fmt: str = "%Y%m%d") -> date:
        """Parse a date string to date object."""
        return datetime.strptime(value, fmt).date()

    def _normalize_domestic_prices(
        self,
        df: pd.DataFrame,
    ) -> list[PriceData]:
        """
        Normalize domestic stock price data to PriceData format.

        Args:
            df: DataFrame with KIS domestic stock columns

        Returns:
            List of PriceData records
        """
        if df.empty:
            return []

        prices = []
        for _, row in df.iterrows():
            try:
                date_str = str(row.get("stck_bsop_date", ""))
                if not date_str or len(date_str) != 8:
                    continue

                price_data = PriceData(
                    date=self._parse_date(date_str),
                    open=self._parse_decimal(row.get("stck_oprc")),
                    high=self._parse_decimal(row.get("stck_hgpr")),
                    low=self._parse_decimal(row.get("stck_lwpr")),
                    close=self._parse_decimal(row.get("stck_clpr")),
                    volume=self._parse_int(row.get("acml_vol")),
                    extra={
                        "turnover": self._parse_decimal(row.get("acml_tr_pbmn")),
                        "change": self._parse_decimal(row.get("prdy_vrss")),
                        "change_sign": row.get("prdy_vrss_sign", ""),
                    },
                )
                prices.append(price_data)
            except Exception as e:
                logger.warning(f"Failed to parse price row: {e}")
                continue

        return prices

    def _normalize_overseas_prices(
        self,
        df: pd.DataFrame,
    ) -> list[PriceData]:
        """
        Normalize overseas stock price data to PriceData format.

        Args:
            df: DataFrame with KIS overseas stock columns

        Returns:
            List of PriceData records
        """
        if df.empty:
            return []

        prices = []
        for _, row in df.iterrows():
            try:
                # Handle different date formats
                date_str = str(row.get("xymd", row.get("stck_bsop_date", "")))
                if not date_str or len(date_str) != 8:
                    continue

                price_data = PriceData(
                    date=self._parse_date(date_str),
                    open=self._parse_decimal(row.get("open", row.get("stck_oprc"))),
                    high=self._parse_decimal(row.get("high", row.get("stck_hgpr"))),
                    low=self._parse_decimal(row.get("low", row.get("stck_lwpr"))),
                    close=self._parse_decimal(row.get("clos", row.get("stck_clpr"))),
                    volume=self._parse_int(row.get("tvol", row.get("acml_vol"))),
                    extra={
                        "turnover": self._parse_decimal(row.get("tamt", row.get("acml_tr_pbmn"))),
                    },
                )
                prices.append(price_data)
            except Exception as e:
                logger.warning(f"Failed to parse overseas price row: {e}")
                continue

        return prices

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

        if exchange is None:
            exchange = self.detect_exchange(ticker)

        if self._is_domestic(exchange):
            return await self._get_domestic_daily_prices(ticker, start_date, end_date)
        else:
            return await self._get_overseas_daily_prices(
                ticker, start_date, end_date, exchange
            )

    async def _get_domestic_daily_prices(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
    ) -> list[PriceData]:
        """
        Get daily prices for domestic (Korean) stocks.

        Uses the 국내주식기간별시세 API.
        """
        api_url = "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
        tr_id = "FHKST03010100"

        params = {
            "FID_COND_MRKT_DIV_CODE": "J",  # J=KRX
            "FID_INPUT_ISCD": ticker,
            "FID_INPUT_DATE_1": start_date.strftime("%Y%m%d"),
            "FID_INPUT_DATE_2": end_date.strftime("%Y%m%d"),
            "FID_PERIOD_DIV_CODE": "D",  # D=Daily
            "FID_ORG_ADJ_PRC": "0",  # 0=수정주가, 1=원주가
        }

        all_prices = []
        tr_cont = ""

        # Handle pagination (max 100 records per request)
        while True:
            data = await self._make_request(api_url, tr_id, params, tr_cont)

            # Process output2 (price data array)
            output2 = data.get("output2", [])
            if output2:
                df = pd.DataFrame(output2)
                prices = self._normalize_domestic_prices(df)
                all_prices.extend(prices)

            # Check for more data
            tr_cont_header = data.get("tr_cont", "")
            if tr_cont_header not in ("F", "M"):
                break

            tr_cont = "N"

            # Rate limiting
            await asyncio.sleep(0.1)

        # Sort by date ascending
        all_prices.sort(key=lambda p: p.date)
        return all_prices

    async def _get_overseas_daily_prices(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
        exchange: Exchange,
    ) -> list[PriceData]:
        """
        Get daily prices for overseas stocks.

        Uses the 해외주식기간별시세 API.
        For US stocks, tries multiple exchanges (NAS, NYS, AMS) if initial attempt fails.
        """
        api_url = "/uapi/overseas-price/v1/quotations/dailyprice"
        tr_id = "HHDFS76240000"

        # For US stocks, try multiple exchanges if data not found
        # Order: NASDAQ (most stocks), NYSE Arca/AMEX (most ETFs like SPY, QLD), NYSE
        us_exchanges = ["NAS", "AMS", "NYS"]  # NASDAQ, AMEX/NYSE Arca, NYSE
        excd = self.OVERSEAS_EXCHANGE_CODES.get(exchange, "NAS")

        # Build list of exchange codes to try
        if excd in us_exchanges:
            # Try the detected exchange first, then others
            exchanges_to_try = [excd] + [e for e in us_exchanges if e != excd]
        else:
            exchanges_to_try = [excd]

        for try_excd in exchanges_to_try:
            prices = await self._fetch_overseas_prices(
                api_url, tr_id, ticker, start_date, end_date, try_excd
            )
            if prices:
                logger.info(f"Found data for {ticker} on exchange {try_excd}")
                return prices
            logger.debug(f"No data for {ticker} on exchange {try_excd}, trying next...")

        logger.warning(f"No data found for {ticker} on any US exchange")
        return []

    async def _fetch_overseas_prices(
        self,
        api_url: str,
        tr_id: str,
        ticker: str,
        start_date: date,
        end_date: date,
        excd: str,
    ) -> list[PriceData]:
        """
        Fetch overseas stock prices from a specific exchange.

        Args:
            api_url: API endpoint
            tr_id: Transaction ID
            ticker: Stock symbol
            start_date: Start date
            end_date: End date
            excd: Exchange code (NAS, NYS, AMS, etc.)

        Returns:
            List of PriceData if found, empty list otherwise
        """
        params = {
            "AUTH": "",
            "EXCD": excd,
            "SYMB": ticker,
            "GUBN": "0",  # 0=일, 1=주, 2=월
            "BYMD": end_date.strftime("%Y%m%d"),
            "MODP": "1",  # 수정주가 반영
        }

        all_prices = []
        tr_cont = ""
        max_iterations = 20  # Safety limit

        for _ in range(max_iterations):
            try:
                data = await self._make_request(api_url, tr_id, params, tr_cont)
            except (RateLimitError, DataUnavailableError) as e:
                # Transient errors should not be misreported as "ticker not found".
                logger.warning(f"Transient API error for {ticker} on {excd}: {e}")
                raise
            except DataProviderError as e:
                # Treat other errors as exchange-specific failures and try next exchange.
                logger.info(f"API error for {ticker} on {excd}: {e}")
                return []

            # Log raw response for debugging
            output1 = data.get("output1", {})
            logger.info(
                f"KIS API response for {ticker}@{excd}: "
                f"rt_cd={data.get('rt_cd')}, msg_cd={data.get('msg_cd')}, msg1={data.get('msg1')}, "
                f"output1={output1 if isinstance(output1, dict) else type(output1).__name__}"
            )

            # Process output2 (price data array)
            output2 = data.get("output2", [])
            logger.info(f"KIS API returned {len(output2)} records for {ticker}@{excd}")
            if output2:
                df = pd.DataFrame(output2)
                prices = self._normalize_overseas_prices(df)

                # Filter by date range
                for p in prices:
                    if start_date <= p.date <= end_date:
                        all_prices.append(p)
                    elif p.date < start_date:
                        # Data is sorted descending, stop if before start_date
                        break

            # Check for more data
            tr_cont_header = data.get("tr_cont", "")
            if tr_cont_header not in ("F", "M"):
                break

            # Check if we've gone past start_date
            if output2:
                last_date_str = output2[-1].get("xymd", "")
                if last_date_str:
                    last_date = self._parse_date(last_date_str)
                    if last_date < start_date:
                        break

            tr_cont = "N"
            await asyncio.sleep(0.1)

        # Sort by date ascending
        all_prices.sort(key=lambda p: p.date)
        return all_prices

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
        if exchange is None:
            exchange = self.detect_exchange(ticker)

        if self._is_domestic(exchange):
            return await self._get_domestic_current_price(ticker)
        else:
            return await self._get_overseas_current_price(ticker, exchange)

    async def _get_domestic_current_price(self, ticker: str) -> CurrentPrice:
        """Get current price for domestic stocks."""
        api_url = "/uapi/domestic-stock/v1/quotations/inquire-price"
        tr_id = "FHKST01010100"

        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": ticker,
        }

        data = await self._make_request(api_url, tr_id, params)
        output = data.get("output", {})

        if not output:
            raise TickerNotFoundError(ticker, self.provider_name)

        return CurrentPrice(
            symbol=ticker,
            price=self._parse_decimal(output.get("stck_prpr")),
            change=self._parse_decimal(output.get("prdy_vrss")),
            change_percent=self._parse_decimal(output.get("prdy_ctrt")),
            volume=self._parse_int(output.get("acml_vol")),
            timestamp=datetime.now(),
            bid=self._parse_decimal(output.get("stck_sdpr")),  # 하한가를 bid로 사용
            ask=self._parse_decimal(output.get("stck_mxpr")),  # 상한가를 ask로 사용
            extra={
                "high": self._parse_decimal(output.get("stck_hgpr")),
                "low": self._parse_decimal(output.get("stck_lwpr")),
                "open": self._parse_decimal(output.get("stck_oprc")),
                "prev_close": self._parse_decimal(output.get("stck_prdy_clpr")),
                "market_cap": self._parse_decimal(output.get("hts_avls")),
            },
        )

    async def _get_overseas_current_price(
        self,
        ticker: str,
        exchange: Exchange,
    ) -> CurrentPrice:
        """Get current price for overseas stocks."""
        api_url = "/uapi/overseas-price/v1/quotations/price"
        tr_id = "HHDFS00000300"

        excd = self.OVERSEAS_EXCHANGE_CODES.get(exchange, "NAS")

        params = {
            "AUTH": "",
            "EXCD": excd,
            "SYMB": ticker,
        }

        data = await self._make_request(api_url, tr_id, params)
        output = data.get("output", {})

        if not output:
            raise TickerNotFoundError(ticker, self.provider_name)

        return CurrentPrice(
            symbol=ticker,
            price=self._parse_decimal(output.get("last")),
            change=self._parse_decimal(output.get("diff")),
            change_percent=self._parse_decimal(output.get("rate")),
            volume=self._parse_int(output.get("tvol")),
            timestamp=datetime.now(),
            bid=self._parse_decimal(output.get("pbid")),
            ask=self._parse_decimal(output.get("pask")),
            extra={
                "high": self._parse_decimal(output.get("high")),
                "low": self._parse_decimal(output.get("low")),
                "open": self._parse_decimal(output.get("open")),
                "prev_close": self._parse_decimal(output.get("base")),
            },
        )

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
        if exchange is None:
            exchange = self.detect_exchange(ticker)

        if self._is_domestic(exchange):
            return await self._get_domestic_ticker_info(ticker)
        else:
            return await self._get_overseas_ticker_info(ticker, exchange)

    async def _get_domestic_ticker_info(self, ticker: str) -> TickerInfo:
        """Get ticker info for domestic stocks."""
        # Use search info API
        api_url = "/uapi/domestic-stock/v1/quotations/search-info"
        tr_id = "CTPF1604R"

        params = {
            "PDNO": ticker,
            "PRDT_TYPE_CD": "300",  # 300=주식
        }

        data = await self._make_request(api_url, tr_id, params)
        output = data.get("output", {})

        if not output:
            raise TickerNotFoundError(ticker, self.provider_name)

        return TickerInfo(
            symbol=ticker,
            name=output.get("prdt_name", ""),
            exchange=Exchange.KRX,
            currency="KRW",
            security_type=self._map_security_type(output.get("prdt_type_cd", "")),
            sector=output.get("std_idst_clsf_cd_name"),
            extra={
                "listed_date": output.get("lstg_dt"),
                "face_value": self._parse_decimal(output.get("papr")),
            },
        )

    async def _get_overseas_ticker_info(
        self,
        ticker: str,
        exchange: Exchange,
    ) -> TickerInfo:
        """Get ticker info for overseas stocks."""
        # Use price API to get basic info
        current_price = await self._get_overseas_current_price(ticker, exchange)

        return TickerInfo(
            symbol=ticker,
            name=ticker,  # Name not available from price API
            exchange=exchange,
            currency=self._get_currency(exchange),
            security_type="stock",
        )

    def _map_security_type(self, type_code: str) -> str:
        """Map KIS security type code to standard type."""
        type_map = {
            "300": "stock",
            "301": "preferred",
            "302": "etf",
            "303": "etn",
            "304": "warrant",
            "305": "elw",
        }
        return type_map.get(type_code, "stock")

    def _get_currency(self, exchange: Exchange) -> str:
        """Get the currency for an exchange."""
        currency_map = {
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
        return currency_map.get(exchange, "USD")

    async def get_available_date_range(
        self,
        ticker: str,
        exchange: Exchange | None = None,
    ) -> DateRange:
        """
        Get the available date range for historical data.

        For KIS, we estimate based on typical data availability:
        - Domestic: ~20 years of history
        - Overseas: ~10 years of history

        Args:
            ticker: Ticker symbol
            exchange: Exchange hint (optional)

        Returns:
            DateRange indicating available historical data range
        """
        if exchange is None:
            exchange = self.detect_exchange(ticker)

        today = date.today()

        if self._is_domestic(exchange):
            # Domestic stocks typically have ~20 years of data
            start_date = date(2005, 1, 1)
        else:
            # Overseas stocks typically have ~10 years
            start_date = date(2015, 1, 1)

        return DateRange(
            start_date=start_date,
            end_date=today,
            ticker=ticker,
        )

    async def health_check(self) -> bool:
        """
        Check if the KIS provider is healthy.

        Attempts to authenticate and make a simple API call.

        Returns:
            True if healthy, False otherwise
        """
        try:
            await self._ensure_authenticated()
            return True
        except Exception as e:
            logger.warning(f"KIS health check failed: {e}")
            return False
