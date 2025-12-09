"""
Tests for KIS Authentication Manager.

Tests:
- Token management (caching, expiration)
- Environment setup (prod/paper)
- Header generation
"""

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import KISConfig
from app.providers.data.kis_auth import (
    AuthenticationError,
    KISAuthManager,
    KISEnvironment,
    KISToken,
)


class TestKISToken:
    """Tests for KISToken dataclass."""

    def test_token_creation(self) -> None:
        """Test basic token creation."""
        expires = datetime.now() + timedelta(hours=24)
        token = KISToken(
            access_token="test_token_123",
            expires_at=expires,
            token_type="Bearer",
        )
        assert token.access_token == "test_token_123"
        assert token.expires_at == expires
        assert token.token_type == "Bearer"

    def test_token_is_valid(self) -> None:
        """Test token validity check."""
        # Valid token (expires in 2 hours)
        valid_token = KISToken(
            access_token="valid",
            expires_at=datetime.now() + timedelta(hours=2),
        )
        assert valid_token.is_valid is True
        assert valid_token.is_expired is False

    def test_token_is_expired(self) -> None:
        """Test expired token detection."""
        # Expired token
        expired_token = KISToken(
            access_token="expired",
            expires_at=datetime.now() - timedelta(hours=1),
        )
        assert expired_token.is_expired is True
        assert expired_token.is_valid is False

    def test_token_expiring_soon(self) -> None:
        """Test token expiring within 1 hour (should be considered expired)."""
        # Token expiring in 30 minutes
        soon_expired = KISToken(
            access_token="soon",
            expires_at=datetime.now() + timedelta(minutes=30),
        )
        assert soon_expired.is_expired is True  # Within 1 hour buffer
        assert soon_expired.is_valid is False

    def test_empty_token_is_invalid(self) -> None:
        """Test that empty token is invalid."""
        token = KISToken(
            access_token="",
            expires_at=datetime.now() + timedelta(hours=24),
        )
        assert token.is_valid is False


class TestKISEnvironment:
    """Tests for KISEnvironment dataclass."""

    def test_environment_creation(self) -> None:
        """Test environment configuration."""
        env = KISEnvironment(
            app_key="app123",
            app_secret="secret456",
            account_number="12345678",
            account_product_code="01",
            hts_id="testuser",
            base_url="https://openapi.koreainvestment.com:9443",
            websocket_url="ws://ops.koreainvestment.com:21000",
            is_paper=False,
        )
        assert env.app_key == "app123"
        assert env.account_number == "12345678"
        assert env.is_paper is False

    def test_full_account(self) -> None:
        """Test full account number generation."""
        env = KISEnvironment(
            app_key="app123",
            app_secret="secret456",
            account_number="12345678",
            account_product_code="01",
            hts_id="testuser",
            base_url="https://test.com",
            websocket_url="ws://test.com",
        )
        assert env.full_account == "12345678-01"


class TestKISAuthManager:
    """Tests for KISAuthManager."""

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
            my_acct_future="87654321",
            my_paper_stock="11111111",
            my_paper_future="22222222",
            my_prod="01",
            prod="https://openapi.koreainvestment.com:9443",
            vps="https://openapivts.koreainvestment.com:29443",
        )

    @pytest.fixture
    def auth_manager(self, mock_config: KISConfig, tmp_path: Path) -> KISAuthManager:
        """Create auth manager with mock config."""
        return KISAuthManager(
            config=mock_config,
            is_paper=False,
            product_code="01",
            token_cache_path=tmp_path / "test_token",
        )

    def test_auth_manager_creation(self, auth_manager: KISAuthManager) -> None:
        """Test auth manager initialization."""
        assert auth_manager.is_authenticated is False
        assert auth_manager.environment is not None

    def test_environment_setup_production(self, auth_manager: KISAuthManager) -> None:
        """Test production environment setup."""
        env = auth_manager.environment
        assert env.app_key == "prod_app_key"
        assert env.app_secret == "prod_app_secret"
        assert env.account_number == "12345678"
        assert env.is_paper is False
        assert "openapi.koreainvestment.com" in env.base_url

    def test_environment_setup_paper(self, mock_config: KISConfig, tmp_path: Path) -> None:
        """Test paper trading environment setup."""
        auth_manager = KISAuthManager(
            config=mock_config,
            is_paper=True,
            product_code="01",
            token_cache_path=tmp_path / "test_token",
        )
        env = auth_manager.environment
        assert env.app_key == "paper_app_key"
        assert env.app_secret == "paper_app_secret"
        assert env.account_number == "11111111"
        assert env.is_paper is True
        assert "openapivts.koreainvestment.com" in env.base_url

    def test_get_auth_headers_without_auth(self, auth_manager: KISAuthManager) -> None:
        """Test getting headers without authentication raises error."""
        with pytest.raises(AuthenticationError, match="Not authenticated"):
            auth_manager.get_auth_headers()

    @pytest.mark.asyncio
    async def test_authenticate_success(self, auth_manager: KISAuthManager) -> None:
        """Test successful authentication."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "test_access_token_123",
            "token_type": "Bearer",
            "access_token_token_expired": (datetime.now() + timedelta(hours=24)).strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
        }

        with patch("app.providers.data.kis_auth.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_client.return_value.__aexit__.return_value = None

            token = await auth_manager.authenticate(force=True)

            assert token.access_token == "test_access_token_123"
            assert auth_manager.is_authenticated is True

    @pytest.mark.asyncio
    async def test_authenticate_failure(self, auth_manager: KISAuthManager) -> None:
        """Test authentication failure."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"

        with patch("app.providers.data.kis_auth.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_client.return_value.__aexit__.return_value = None

            with pytest.raises(AuthenticationError, match="KIS authentication failed"):
                await auth_manager.authenticate(force=True)

    def test_get_tr_headers_paper_trading(
        self, mock_config: KISConfig, tmp_path: Path
    ) -> None:
        """Test TR headers modification for paper trading."""
        auth_manager = KISAuthManager(
            config=mock_config,
            is_paper=True,
            product_code="01",
            token_cache_path=tmp_path / "test_token",
        )

        # Set up a valid token manually
        auth_manager._token = KISToken(
            access_token="test_token",
            expires_at=datetime.now() + timedelta(hours=24),
        )

        headers = auth_manager.get_tr_headers("TTTC0802U")

        # TR ID should be changed for paper trading
        assert headers["tr_id"] == "VTTC0802U"  # T -> V

    def test_get_tr_headers_production(self, auth_manager: KISAuthManager) -> None:
        """Test TR headers for production."""
        # Set up a valid token manually
        auth_manager._token = KISToken(
            access_token="test_token",
            expires_at=datetime.now() + timedelta(hours=24),
        )

        headers = auth_manager.get_tr_headers("TTTC0802U")

        # TR ID should remain unchanged for production
        assert headers["tr_id"] == "TTTC0802U"

    @pytest.mark.asyncio
    async def test_ensure_authenticated_when_not_authenticated(
        self, auth_manager: KISAuthManager
    ) -> None:
        """Test ensure_authenticated calls authenticate when needed."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "test_token",
            "token_type": "Bearer",
            "access_token_token_expired": (datetime.now() + timedelta(hours=24)).strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
        }

        with patch("app.providers.data.kis_auth.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_client.return_value.__aexit__.return_value = None

            await auth_manager.ensure_authenticated()
            assert auth_manager.is_authenticated is True

    @pytest.mark.asyncio
    async def test_ensure_authenticated_skips_when_already_authenticated(
        self, auth_manager: KISAuthManager
    ) -> None:
        """Test ensure_authenticated skips auth when already valid."""
        # Set up a valid token manually
        auth_manager._token = KISToken(
            access_token="existing_token",
            expires_at=datetime.now() + timedelta(hours=24),
        )

        # Should not make any HTTP calls
        await auth_manager.ensure_authenticated()
        assert auth_manager._token.access_token == "existing_token"
