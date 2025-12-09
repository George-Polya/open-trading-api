"""
KIS API Authentication and Session Management.

Provides thread-safe authentication token management for KIS OpenAPI.
Tokens are cached and automatically refreshed when expired.
"""

import asyncio
import json
import logging
import os
import threading
from collections import namedtuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import yaml

from app.core.config import KISConfig

logger = logging.getLogger(__name__)


@dataclass
class KISToken:
    """
    Represents a KIS API access token.

    Attributes:
        access_token: The OAuth access token
        expires_at: Token expiration datetime
        token_type: Token type (usually "Bearer")
    """

    access_token: str
    expires_at: datetime
    token_type: str = "Bearer"

    @property
    def is_expired(self) -> bool:
        """Check if the token is expired or about to expire (within 1 hour)."""
        return datetime.now() >= (self.expires_at - timedelta(hours=1))

    @property
    def is_valid(self) -> bool:
        """Check if the token is valid and not expired."""
        return bool(self.access_token) and not self.is_expired


@dataclass
class KISEnvironment:
    """
    KIS API environment configuration.

    Holds the resolved configuration for API calls including
    app keys, URLs, and account information.
    """

    app_key: str
    app_secret: str
    account_number: str
    account_product_code: str
    hts_id: str
    base_url: str
    websocket_url: str
    is_paper: bool = False

    @property
    def full_account(self) -> str:
        """Get the full account number including product code."""
        return f"{self.account_number}-{self.account_product_code}"


class KISAuthManager:
    """
    Manages KIS API authentication tokens.

    Thread-safe singleton manager that handles:
    - Token acquisition and caching
    - Automatic token refresh
    - Environment switching (prod/paper)

    Usage:
        auth_manager = KISAuthManager(kis_config)
        await auth_manager.ensure_authenticated()
        headers = auth_manager.get_auth_headers()
    """

    # Production and paper trading URLs
    PROD_URL = "https://openapi.koreainvestment.com:9443"
    PAPER_URL = "https://openapivts.koreainvestment.com:29443"
    PROD_WS_URL = "ws://ops.koreainvestment.com:21000"
    PAPER_WS_URL = "ws://ops.koreainvestment.com:31000"

    def __init__(
        self,
        config: KISConfig,
        is_paper: bool = False,
        product_code: str = "01",
        token_cache_path: Path | None = None,
    ):
        """
        Initialize the KIS authentication manager.

        Args:
            config: KIS configuration with app keys and account info
            is_paper: Whether to use paper trading mode
            product_code: Account product code (01=stock, 03=futures)
            token_cache_path: Path to cache tokens (optional)
        """
        self._config = config
        self._is_paper = is_paper
        self._product_code = product_code
        self._token: KISToken | None = None
        self._environment: KISEnvironment | None = None
        self._lock = threading.Lock()
        self._async_lock = asyncio.Lock()

        # Token cache path
        if token_cache_path is None:
            config_root = Path.home() / "KIS" / "config"
            config_root.mkdir(parents=True, exist_ok=True)
            self._token_cache_path = config_root / f"KIS{datetime.today().strftime('%Y%m%d')}"
        else:
            self._token_cache_path = token_cache_path

        # Initialize environment
        self._setup_environment()

    def _setup_environment(self) -> None:
        """Setup the KIS environment based on configuration."""
        if self._is_paper:
            app_key = self._config.paper_app
            app_secret = self._config.paper_sec
            base_url = self._config.vps or self.PAPER_URL
            ws_url = self._config.vops or self.PAPER_WS_URL

            # Account selection for paper trading
            if self._product_code in ("01", "22", "29"):
                account = self._config.my_paper_stock
            else:
                account = self._config.my_paper_future
        else:
            app_key = self._config.my_app
            app_secret = self._config.my_sec
            base_url = self._config.prod or self.PROD_URL
            ws_url = self._config.ops or self.PROD_WS_URL

            # Account selection for production
            if self._product_code in ("01", "22", "29"):
                account = self._config.my_acct_stock
            elif self._product_code in ("03", "08"):
                account = self._config.my_acct_future
            else:
                account = self._config.my_acct_stock

        self._environment = KISEnvironment(
            app_key=app_key,
            app_secret=app_secret,
            account_number=account,
            account_product_code=self._product_code,
            hts_id=self._config.my_htsid,
            base_url=base_url,
            websocket_url=ws_url,
            is_paper=self._is_paper,
        )

    @property
    def environment(self) -> KISEnvironment:
        """Get the current KIS environment configuration."""
        if self._environment is None:
            self._setup_environment()
        return self._environment

    @property
    def is_authenticated(self) -> bool:
        """Check if currently authenticated with a valid token."""
        return self._token is not None and self._token.is_valid

    def _load_cached_token(self) -> KISToken | None:
        """Load token from cache file if exists and valid."""
        try:
            if not self._token_cache_path.exists():
                return None

            with open(self._token_cache_path, encoding="utf-8") as f:
                data = yaml.safe_load(f)

            if not data or "token" not in data or "valid-date" not in data:
                return None

            expires_at = data["valid-date"]
            if isinstance(expires_at, str):
                expires_at = datetime.strptime(expires_at, "%Y-%m-%d %H:%M:%S")

            token = KISToken(
                access_token=data["token"],
                expires_at=expires_at,
            )

            if token.is_valid:
                logger.debug("Loaded valid token from cache")
                return token

            return None
        except Exception as e:
            logger.warning(f"Failed to load cached token: {e}")
            return None

    def _save_token(self, token: str, expires_at: datetime) -> None:
        """Save token to cache file."""
        try:
            self._token_cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._token_cache_path, "w", encoding="utf-8") as f:
                f.write(f"token: {token}\n")
                f.write(f"valid-date: {expires_at.strftime('%Y-%m-%d %H:%M:%S')}\n")
            logger.debug("Token saved to cache")
        except Exception as e:
            logger.warning(f"Failed to save token to cache: {e}")

    async def authenticate(self, force: bool = False) -> KISToken:
        """
        Authenticate with KIS API and obtain an access token.

        Uses cached token if available and valid, unless force=True.

        Args:
            force: Force new token acquisition even if cached token is valid

        Returns:
            KISToken with access credentials

        Raises:
            AuthenticationError: If authentication fails
        """
        async with self._async_lock:
            # Check cached token first
            if not force and self._token and self._token.is_valid:
                return self._token

            # Try loading from file cache
            if not force:
                cached = self._load_cached_token()
                if cached:
                    self._token = cached
                    return self._token

            # Request new token
            logger.info("Requesting new KIS authentication token")

            env = self.environment
            url = f"{env.base_url}/oauth2/tokenP"

            payload = {
                "grant_type": "client_credentials",
                "appkey": env.app_key,
                "appsecret": env.app_secret,
            }

            headers = {
                "Content-Type": "application/json",
                "Accept": "text/plain",
                "charset": "UTF-8",
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=30.0,
                )

                if response.status_code != 200:
                    raise AuthenticationError(
                        f"KIS authentication failed: {response.status_code} - {response.text}"
                    )

                data = response.json()

                if "access_token" not in data:
                    raise AuthenticationError(
                        f"Invalid authentication response: {data}"
                    )

                # Parse expiration time
                expires_str = data.get("access_token_token_expired", "")
                if expires_str:
                    expires_at = datetime.strptime(expires_str, "%Y-%m-%d %H:%M:%S")
                else:
                    # Default to 24 hours if not provided
                    expires_at = datetime.now() + timedelta(hours=24)

                self._token = KISToken(
                    access_token=data["access_token"],
                    expires_at=expires_at,
                    token_type=data.get("token_type", "Bearer"),
                )

                # Cache the token
                self._save_token(self._token.access_token, self._token.expires_at)

                logger.info("KIS authentication successful")
                return self._token

    async def ensure_authenticated(self) -> None:
        """
        Ensure we have a valid authentication token.

        Acquires a new token if necessary.
        """
        if not self.is_authenticated:
            await self.authenticate()

    def get_auth_headers(self) -> dict[str, str]:
        """
        Get HTTP headers with authentication credentials.

        Returns:
            Dictionary of headers for authenticated API requests

        Raises:
            AuthenticationError: If not authenticated
        """
        if not self._token or not self._token.is_valid:
            raise AuthenticationError("Not authenticated. Call authenticate() first.")

        env = self.environment
        return {
            "Content-Type": "application/json",
            "Accept": "text/plain",
            "charset": "UTF-8",
            "authorization": f"Bearer {self._token.access_token}",
            "appkey": env.app_key,
            "appsecret": env.app_secret,
        }

    def get_tr_headers(
        self,
        tr_id: str,
        tr_cont: str = "",
        custtype: str = "P",
    ) -> dict[str, str]:
        """
        Get headers for a specific transaction request.

        Args:
            tr_id: Transaction ID for the API call
            tr_cont: Transaction continuation flag
            custtype: Customer type (P=individual, B=corporation)

        Returns:
            Complete headers dictionary for the API request
        """
        headers = self.get_auth_headers()

        # Adjust TR ID for paper trading
        if self._is_paper and tr_id[0] in ("T", "J", "C"):
            tr_id = "V" + tr_id[1:]

        headers.update({
            "tr_id": tr_id,
            "tr_cont": tr_cont,
            "custtype": custtype,
        })

        return headers

    async def close(self) -> None:
        """
        Clean up authentication resources.

        Currently a no-op as tokens are stateless,
        but kept for interface consistency.
        """
        pass


class AuthenticationError(Exception):
    """Raised when KIS API authentication fails."""

    pass
