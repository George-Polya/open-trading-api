"""
Tests for KISDataProvider implementation.

Tests:
- Exchange detection
- Data normalization
- API call wrappers
- Error handling
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from app.core.config import KISConfig
from app.providers.data.base import (
    DataProviderError,
    Exchange,
    InvalidDateRangeError,
    TickerNotFoundError,
)
from app.providers.data.kis import KISDataProvider


class TestKISDataProviderBasic:
    """Basic tests for KISDataProvider."""

    @pytest.fixture
    def mock_config(self) -> KISConfig:
        """Create mock KIS configuration."""
        return KISConfig(
            my_app="prod_app_key",
            my_sec="prod_app_secret",
            paper_app="paper_app_key",
            paper_sec="paper_app_secret",
            my_htsid="testuser",
            my_acct_stock="12345678",
            my_paper_stock="11111111",
            my_prod="01",
            prod="https://openapi.koreainvestment.com:9443",
            vps="https://openapivts.koreainvestment.com:29443",
        )

    @pytest.fixture
    def provider(self, mock_config: KISConfig) -> KISDataProvider:
        """Create KIS data provider with mock config."""
        return KISDataProvider(
            config=mock_config,
            is_paper=False,
            product_code="01",
        )

    def test_provider_name(self, provider: KISDataProvider) -> None:
        """Test provider name."""
        assert provider.provider_name == "kis"

    def test_detect_exchange_korean_stock(self, provider: KISDataProvider) -> None:
        """Test exchange detection for Korean stocks."""
        assert provider.detect_exchange("005930") == Exchange.KRX
        assert provider.detect_exchange("000660") == Exchange.KRX
        assert provider.detect_exchange("035720") == Exchange.KRX
        assert provider.detect_exchange("373220") == Exchange.KRX

    def test_detect_exchange_us_stock(self, provider: KISDataProvider) -> None:
        """Test exchange detection for US stocks."""
        assert provider.detect_exchange("AAPL") == Exchange.NASDAQ
        assert provider.detect_exchange("TSLA") == Exchange.NASDAQ
        assert provider.detect_exchange("MSFT") == Exchange.NASDAQ
        assert provider.detect_exchange("GOOGL") == Exchange.NASDAQ

    def test_is_domestic(self, provider: KISDataProvider) -> None:
        """Test domestic exchange detection."""
        assert provider._is_domestic(Exchange.KRX) is True
        assert provider._is_domestic(Exchange.KRX_KOSPI) is True
        assert provider._is_domestic(Exchange.KRX_KOSDAQ) is True
        assert provider._is_domestic(Exchange.NASDAQ) is False
        assert provider._is_domestic(Exchange.NYSE) is False

    def test_parse_decimal(self, provider: KISDataProvider) -> None:
        """Test decimal parsing."""
        assert provider._parse_decimal("100.50") == Decimal("100.50")
        assert provider._parse_decimal("1,000,000") == Decimal("1000000")
        assert provider._parse_decimal("") == Decimal("0")
        assert provider._parse_decimal(None) == Decimal("0")
        assert provider._parse_decimal("invalid", Decimal("99")) == Decimal("99")

    def test_parse_int(self, provider: KISDataProvider) -> None:
        """Test integer parsing."""
        assert provider._parse_int("1000") == 1000
        assert provider._parse_int("1,000,000") == 1000000
        assert provider._parse_int("") == 0
        assert provider._parse_int(None) == 0
        assert provider._parse_int("invalid", 99) == 99

    def test_parse_date(self, provider: KISDataProvider) -> None:
        """Test date parsing."""
        assert provider._parse_date("20240115") == date(2024, 1, 15)
        assert provider._parse_date("20231231") == date(2023, 12, 31)

    def test_get_currency(self, provider: KISDataProvider) -> None:
        """Test currency mapping."""
        assert provider._get_currency(Exchange.KRX) == "KRW"
        assert provider._get_currency(Exchange.NASDAQ) == "USD"
        assert provider._get_currency(Exchange.NYSE) == "USD"
        assert provider._get_currency(Exchange.HKEX) == "HKD"
        assert provider._get_currency(Exchange.TSE) == "JPY"


class TestKISDataProviderNormalization:
    """Tests for data normalization."""

    @pytest.fixture
    def provider(self) -> KISDataProvider:
        """Create provider with minimal config."""
        config = KISConfig(
            my_app="test",
            my_sec="test",
            my_acct_stock="12345678",
        )
        return KISDataProvider(config=config)

    def test_normalize_domestic_prices(self, provider: KISDataProvider) -> None:
        """Test normalization of domestic stock price data."""
        df = pd.DataFrame([
            {
                "stck_bsop_date": "20240115",
                "stck_oprc": "75000",
                "stck_hgpr": "76000",
                "stck_lwpr": "74500",
                "stck_clpr": "75500",
                "acml_vol": "5000000",
                "acml_tr_pbmn": "377500000000",
                "prdy_vrss": "500",
                "prdy_vrss_sign": "2",
            },
            {
                "stck_bsop_date": "20240116",
                "stck_oprc": "75500",
                "stck_hgpr": "77000",
                "stck_lwpr": "75000",
                "stck_clpr": "76500",
                "acml_vol": "6000000",
                "acml_tr_pbmn": "459000000000",
                "prdy_vrss": "1000",
                "prdy_vrss_sign": "2",
            },
        ])

        prices = provider._normalize_domestic_prices(df)

        assert len(prices) == 2

        # Check first price
        p1 = prices[0]
        assert p1.date == date(2024, 1, 15)
        assert p1.open == Decimal("75000")
        assert p1.high == Decimal("76000")
        assert p1.low == Decimal("74500")
        assert p1.close == Decimal("75500")
        assert p1.volume == 5000000

        # Check second price
        p2 = prices[1]
        assert p2.date == date(2024, 1, 16)
        assert p2.close == Decimal("76500")
        assert p2.volume == 6000000

    def test_normalize_overseas_prices(self, provider: KISDataProvider) -> None:
        """Test normalization of overseas stock price data."""
        df = pd.DataFrame([
            {
                "xymd": "20240115",
                "open": "185.50",
                "high": "188.00",
                "low": "185.00",
                "clos": "187.50",
                "tvol": "50000000",
                "tamt": "9375000000",
            },
            {
                "xymd": "20240116",
                "open": "187.50",
                "high": "190.00",
                "low": "186.00",
                "clos": "189.00",
                "tvol": "60000000",
                "tamt": "11340000000",
            },
        ])

        prices = provider._normalize_overseas_prices(df)

        assert len(prices) == 2

        # Check first price
        p1 = prices[0]
        assert p1.date == date(2024, 1, 15)
        assert p1.open == Decimal("185.50")
        assert p1.high == Decimal("188.00")
        assert p1.low == Decimal("185.00")
        assert p1.close == Decimal("187.50")
        assert p1.volume == 50000000

    def test_normalize_empty_dataframe(self, provider: KISDataProvider) -> None:
        """Test normalization of empty DataFrame."""
        df = pd.DataFrame()
        assert provider._normalize_domestic_prices(df) == []
        assert provider._normalize_overseas_prices(df) == []


class TestKISDataProviderAsync:
    """Async tests for KISDataProvider API calls."""

    @pytest.fixture
    def mock_config(self) -> KISConfig:
        """Create mock KIS configuration."""
        return KISConfig(
            my_app="test_app",
            my_sec="test_secret",
            my_acct_stock="12345678",
            prod="https://openapi.koreainvestment.com:9443",
        )

    @pytest.fixture
    def provider(self, mock_config: KISConfig) -> KISDataProvider:
        """Create provider with mock config."""
        return KISDataProvider(config=mock_config)

    @pytest.mark.asyncio
    async def test_get_daily_prices_invalid_date_range(
        self, provider: KISDataProvider
    ) -> None:
        """Test get_daily_prices with invalid date range."""
        with pytest.raises(InvalidDateRangeError, match="Start date after end date"):
            await provider.get_daily_prices(
                ticker="005930",
                start_date=date(2024, 12, 31),
                end_date=date(2024, 1, 1),
            )

    @pytest.mark.asyncio
    async def test_get_daily_prices_domestic_success(
        self, provider: KISDataProvider
    ) -> None:
        """Test successful domestic price data retrieval."""
        mock_response_data = {
            "rt_cd": "0",
            "msg_cd": "MCA00000",
            "msg1": "정상처리",
            "output1": {
                "stck_prdy_clpr": "75000",
            },
            "output2": [
                {
                    "stck_bsop_date": "20240115",
                    "stck_oprc": "75000",
                    "stck_hgpr": "76000",
                    "stck_lwpr": "74500",
                    "stck_clpr": "75500",
                    "acml_vol": "5000000",
                },
            ],
            "tr_cont": "D",
        }

        # Mock the auth manager
        provider._auth_manager._token = MagicMock()
        provider._auth_manager._token.is_valid = True
        provider._auth_manager._token.access_token = "test_token"
        provider._auth_manager._environment = MagicMock()
        provider._auth_manager._environment.app_key = "test_key"
        provider._auth_manager._environment.app_secret = "test_secret"
        provider._auth_manager._environment.base_url = "https://test.com"

        mock_http_client = AsyncMock()
        mock_http_response = MagicMock()
        mock_http_response.status_code = 200
        mock_http_response.json.return_value = mock_response_data
        mock_http_client.get = AsyncMock(return_value=mock_http_response)
        provider._http_client = mock_http_client

        prices = await provider.get_daily_prices(
            ticker="005930",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        )

        assert len(prices) == 1
        assert prices[0].date == date(2024, 1, 15)
        assert prices[0].close == Decimal("75500")

    @pytest.mark.asyncio
    async def test_get_daily_prices_overseas_success(
        self, provider: KISDataProvider
    ) -> None:
        """Test successful overseas price data retrieval."""
        mock_response_data = {
            "rt_cd": "0",
            "msg_cd": "MCA00000",
            "msg1": "정상처리",
            "output1": {},
            "output2": [
                {
                    "xymd": "20240115",
                    "open": "185.50",
                    "high": "188.00",
                    "low": "185.00",
                    "clos": "187.50",
                    "tvol": "50000000",
                },
            ],
            "tr_cont": "D",
        }

        # Mock the auth manager
        provider._auth_manager._token = MagicMock()
        provider._auth_manager._token.is_valid = True
        provider._auth_manager._token.access_token = "test_token"
        provider._auth_manager._environment = MagicMock()
        provider._auth_manager._environment.app_key = "test_key"
        provider._auth_manager._environment.app_secret = "test_secret"
        provider._auth_manager._environment.base_url = "https://test.com"

        mock_http_client = AsyncMock()
        mock_http_response = MagicMock()
        mock_http_response.status_code = 200
        mock_http_response.json.return_value = mock_response_data
        mock_http_client.get = AsyncMock(return_value=mock_http_response)
        provider._http_client = mock_http_client

        prices = await provider.get_daily_prices(
            ticker="AAPL",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            exchange=Exchange.NASDAQ,
        )

        assert len(prices) == 1
        assert prices[0].date == date(2024, 1, 15)
        assert prices[0].close == Decimal("187.50")

    @pytest.mark.asyncio
    async def test_get_current_price_domestic(self, provider: KISDataProvider) -> None:
        """Test current price retrieval for domestic stocks."""
        mock_response_data = {
            "rt_cd": "0",
            "msg_cd": "MCA00000",
            "msg1": "정상처리",
            "output": {
                "stck_prpr": "75500",
                "prdy_vrss": "500",
                "prdy_ctrt": "0.67",
                "acml_vol": "5000000",
                "stck_hgpr": "76000",
                "stck_lwpr": "74500",
                "stck_oprc": "75000",
                "stck_prdy_clpr": "75000",
                "stck_sdpr": "52500",
                "stck_mxpr": "97500",
            },
        }

        # Mock the auth manager and http client
        provider._auth_manager._token = MagicMock()
        provider._auth_manager._token.is_valid = True
        provider._auth_manager._token.access_token = "test_token"
        provider._auth_manager._environment = MagicMock()
        provider._auth_manager._environment.app_key = "test_key"
        provider._auth_manager._environment.app_secret = "test_secret"
        provider._auth_manager._environment.base_url = "https://test.com"

        mock_http_client = AsyncMock()
        mock_http_response = MagicMock()
        mock_http_response.status_code = 200
        mock_http_response.json.return_value = mock_response_data
        mock_http_client.get = AsyncMock(return_value=mock_http_response)
        provider._http_client = mock_http_client

        price = await provider.get_current_price("005930")

        assert price.symbol == "005930"
        assert price.price == Decimal("75500")
        assert price.change == Decimal("500")
        assert price.change_percent == Decimal("0.67")
        assert price.volume == 5000000

    @pytest.mark.asyncio
    async def test_get_current_price_ticker_not_found(
        self, provider: KISDataProvider
    ) -> None:
        """Test current price retrieval when ticker not found."""
        mock_response_data = {
            "rt_cd": "0",
            "msg_cd": "MCA00000",
            "msg1": "정상처리",
            "output": {},  # Empty output
        }

        # Mock setup
        provider._auth_manager._token = MagicMock()
        provider._auth_manager._token.is_valid = True
        provider._auth_manager._token.access_token = "test_token"
        provider._auth_manager._environment = MagicMock()
        provider._auth_manager._environment.app_key = "test_key"
        provider._auth_manager._environment.app_secret = "test_secret"
        provider._auth_manager._environment.base_url = "https://test.com"

        mock_http_client = AsyncMock()
        mock_http_response = MagicMock()
        mock_http_response.status_code = 200
        mock_http_response.json.return_value = mock_response_data
        mock_http_client.get = AsyncMock(return_value=mock_http_response)
        provider._http_client = mock_http_client

        with pytest.raises(TickerNotFoundError):
            await provider.get_current_price("INVALID")

    @pytest.mark.asyncio
    async def test_make_request_api_error(self, provider: KISDataProvider) -> None:
        """Test API error handling."""
        mock_response_data = {
            "rt_cd": "1",
            "msg_cd": "MGERR001",
            "msg1": "API 오류 발생",
        }

        # Mock setup
        provider._auth_manager._token = MagicMock()
        provider._auth_manager._token.is_valid = True
        provider._auth_manager._token.access_token = "test_token"
        provider._auth_manager._environment = MagicMock()
        provider._auth_manager._environment.app_key = "test_key"
        provider._auth_manager._environment.app_secret = "test_secret"
        provider._auth_manager._environment.base_url = "https://test.com"

        mock_http_client = AsyncMock()
        mock_http_response = MagicMock()
        mock_http_response.status_code = 200
        mock_http_response.json.return_value = mock_response_data
        mock_http_client.get = AsyncMock(return_value=mock_http_response)
        provider._http_client = mock_http_client

        with pytest.raises(DataProviderError, match="API 오류 발생"):
            await provider._make_request(
                "/test/api",
                "TEST001",
                {"param": "value"},
            )

    @pytest.mark.asyncio
    async def test_get_available_date_range_domestic(
        self, provider: KISDataProvider
    ) -> None:
        """Test available date range for domestic stocks."""
        date_range = await provider.get_available_date_range("005930")

        assert date_range.ticker == "005930"
        assert date_range.start_date == date(2005, 1, 1)
        assert date_range.end_date == date.today()

    @pytest.mark.asyncio
    async def test_get_available_date_range_overseas(
        self, provider: KISDataProvider
    ) -> None:
        """Test available date range for overseas stocks."""
        date_range = await provider.get_available_date_range("AAPL")

        assert date_range.ticker == "AAPL"
        assert date_range.start_date == date(2015, 1, 1)
        assert date_range.end_date == date.today()

    @pytest.mark.asyncio
    async def test_health_check_success(self, provider: KISDataProvider) -> None:
        """Test health check when authenticated."""
        # Mock authenticated state
        provider._auth_manager._token = MagicMock()
        provider._auth_manager._token.is_valid = True

        result = await provider.health_check()
        assert result is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self, provider: KISDataProvider) -> None:
        """Test health check when authentication fails."""
        # Mock authentication to fail
        provider._auth_manager.authenticate = AsyncMock(
            side_effect=Exception("Auth failed")
        )

        result = await provider.health_check()
        assert result is False

    @pytest.mark.asyncio
    async def test_close(self, provider: KISDataProvider) -> None:
        """Test provider cleanup."""
        mock_http_client = AsyncMock()
        mock_http_client.aclose = AsyncMock()
        provider._http_client = mock_http_client
        provider._owns_client = True

        await provider.close()

        mock_http_client.aclose.assert_called_once()
        assert provider._http_client is None
