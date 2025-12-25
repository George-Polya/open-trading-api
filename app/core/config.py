"""
Configuration loader for the backtesting service.

Loads configuration from config.yaml and environment variables using pydantic-settings.
Supports llm/data/execution sections as described in PRD.
"""

from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMProvider(str, Enum):
    """Supported LLM providers."""

    OPENROUTER = "openrouter"
    LANGCHAIN = "langchain"
    ANTHROPIC = "anthropic"
    OPENAI = "openai"


class DataProvider(str, Enum):
    """Supported data providers."""

    KIS = "kis"
    YFINANCE = "yfinance"
    MOCK = "mock"


class ExecutionProvider(str, Enum):
    """Supported code execution providers."""

    DOCKER = "docker"
    LOCAL = "local"


class LLMConfig(BaseModel):
    """
    LLM provider configuration.

    Note: API keys should NOT be stored here.
    Use environment variables (OPENROUTER_API_KEY, ANTHROPIC_API_KEY, OPENAI_API_KEY).
    """

    provider: LLMProvider = Field(
        default=LLMProvider.OPENROUTER,
        description="LLM provider to use",
    )
    model: str = Field(
        default="anthropic/claude-3.5-sonnet",
        description="Model identifier",
    )
    site_url: Optional[str] = Field(
        default=None,
        description="Site URL for OpenRouter HTTP-Referer header",
    )
    site_name: Optional[str] = Field(
        default=None,
        description="Site name for OpenRouter X-Title header",
    )
    temperature: float = Field(
        default=0.2,
        ge=0.0,
        le=2.0,
        description="Temperature for generation",
    )
    max_tokens: int = Field(
        default=8000,
        gt=0,
        description="Maximum tokens to generate",
    )
    max_context_tokens: int = Field(
        default=128000,
        gt=0,
        description="Maximum context tokens the model supports",
    )
    # Reasoning/Thinking model support
    reasoning_enabled: bool = Field(
        default=False,
        description="Enable reasoning mode for thinking models (o1, deepseek-r1, kimi-k2-thinking, etc.)",
    )
    reasoning_max_tokens: Optional[int] = Field(
        default=None,
        description="Max tokens for reasoning. If None, uses max_tokens value.",
    )
    # Web search support (OpenRouter only)
    # See: https://openrouter.ai/announcements/introducing-web-search-via-the-api
    web_search_enabled: bool = Field(
        default=False,
        description="Enable web search for real-time information retrieval (OpenRouter only)",
    )
    web_search_max_results: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Maximum number of web search results to fetch (1-10)",
    )
    web_search_prompt: Optional[str] = Field(
        default=None,
        description="Custom prompt for integrating web search results into the response",
    )


class KISConfig(BaseModel):
    """
    KIS API configuration loaded from kis_devlp.yaml.

    Matches the existing kis_devlp.yaml format used throughout the project.
    """

    # 실전투자 credentials
    my_app: str = Field(default="", description="실전투자 앱키")
    my_sec: str = Field(default="", description="실전투자 앱키 시크릿")

    # 모의투자 credentials
    paper_app: str = Field(default="", description="모의투자 앱키")
    paper_sec: str = Field(default="", description="모의투자 앱키 시크릿")

    # Account info
    my_htsid: str = Field(default="", description="HTS ID")
    my_acct_stock: str = Field(default="", description="증권계좌 8자리")
    my_acct_future: str = Field(default="", description="선물옵션계좌 8자리")
    my_paper_stock: str = Field(default="", description="모의투자 증권계좌 8자리")
    my_paper_future: str = Field(default="", description="모의투자 선물옵션계좌 8자리")
    my_prod: str = Field(default="01", description="계좌번호 뒤 2자리")

    # Domain URLs
    prod: str = Field(
        default="https://openapi.koreainvestment.com:9443",
        description="실전투자 서비스 URL",
    )
    vps: str = Field(
        default="https://openapivts.koreainvestment.com:29443",
        description="모의투자 서비스 URL",
    )
    ops: str = Field(
        default="ws://ops.koreainvestment.com:21000",
        description="실전투자 웹소켓 URL",
    )
    vops: str = Field(
        default="ws://ops.koreainvestment.com:31000",
        description="모의투자 웹소켓 URL",
    )

    my_token: str = Field(default="", description="인증 토큰")
    my_agent: str = Field(default="", description="User-Agent")

    @classmethod
    def from_yaml(cls, config_path: Path | str) -> "KISConfig":
        """Load KIS config from kis_devlp.yaml file."""
        config_path = Path(config_path)
        if config_path.exists():
            with open(config_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            return cls(**data)
        return cls()


class DataConfig(BaseModel):
    """
    Data provider configuration.

    Supports primary provider selection with fallback chain for resilience.
    When the primary provider fails, the system automatically tries fallback
    providers in order.

    Example config.yaml:
        data:
          provider: kis
          is_paper: true  # Use paper trading mode for KIS
          fallback_providers:
            - yfinance
            - mock
          cache_ttl_seconds: 300
          enable_caching: true
          retry_attempts: 3
          retry_delay_seconds: 1.0
    """

    provider: DataProvider = Field(
        default=DataProvider.KIS,
        description="Primary data provider to use",
    )
    is_paper: bool = Field(
        default=False,
        description="Use paper trading mode for KIS API (모의투자)",
    )
    fallback_providers: list[DataProvider] = Field(
        default_factory=list,
        description="Fallback providers in order of preference",
    )
    cache_ttl_seconds: int = Field(
        default=300,
        ge=0,
        description="Cache TTL in seconds for data provider responses",
    )
    enable_caching: bool = Field(
        default=True,
        description="Enable caching of data provider responses",
    )
    retry_attempts: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Number of retry attempts before falling back",
    )
    retry_delay_seconds: float = Field(
        default=1.0,
        ge=0.0,
        le=30.0,
        description="Delay between retry attempts in seconds",
    )
    kis_config_path: str = Field(
        default="kis_devlp.yaml",
        description="Path to KIS configuration file (kis_devlp.yaml)",
    )
    _kis_config: KISConfig | None = None

    @field_validator("fallback_providers")
    @classmethod
    def validate_fallback_providers(
        cls, v: list[DataProvider], info
    ) -> list[DataProvider]:
        """
        Validate fallback providers don't include the primary provider.
        """
        # Note: We can't access 'provider' field here directly in Pydantic v2
        # The validation will be done at Settings level
        # Remove duplicates while preserving order
        seen = set()
        unique = []
        for p in v:
            if p not in seen:
                seen.add(p)
                unique.append(p)
        return unique

    def get_all_providers(self) -> list[DataProvider]:
        """
        Get list of all providers (primary + fallbacks) in order.

        Returns:
            List of DataProvider enums starting with primary.
        """
        providers = [self.provider]
        for fb in self.fallback_providers:
            if fb not in providers:
                providers.append(fb)
        return providers

    def get_kis_config(self, base_path: Path | None = None) -> KISConfig:
        """
        Load and cache KIS configuration from kis_devlp.yaml.

        Args:
            base_path: Base path to resolve kis_config_path. Defaults to cwd.

        Returns:
            KISConfig loaded from kis_devlp.yaml.
        """
        if self._kis_config is None:
            if base_path is None:
                base_path = Path.cwd()
            kis_path = base_path / self.kis_config_path
            if not kis_path.exists():
                # Try project root
                kis_path = Path(__file__).parent.parent.parent / self.kis_config_path
            self._kis_config = KISConfig.from_yaml(kis_path)
        return self._kis_config


class ExecutionConfig(BaseModel):
    """Code execution configuration."""

    provider: ExecutionProvider = Field(
        default=ExecutionProvider.DOCKER,
        description="Code execution provider to use",
    )
    fallback_to_local: bool = Field(
        default=True,
        description="Fallback to local execution if Docker fails",
    )
    docker_image: str = Field(
        default="backtest-runner:latest",
        description="Docker image for backtest execution (must have pandas, backtesting, etc.)",
    )
    docker_socket_url: Optional[str] = Field(
        default=None,
        description="Docker socket URL (e.g., 'unix:///var/run/docker.sock'). "
                    "If None, uses aiodocker default. "
                    "For macOS Docker Desktop, try 'unix://$HOME/.docker/run/docker.sock'",
    )
    timeout: int = Field(
        default=300,
        gt=0,
        le=600,
        description="Execution timeout in seconds",
    )
    memory_limit: str = Field(
        default="2g",
        description="Memory limit for execution (Docker format)",
    )
    allowed_modules: list[str] = Field(
        default_factory=lambda: ["pandas", "numpy"],
        description="Allowed Python modules for execution",
    )


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables and config.yaml.

    Priority (highest to lowest):
    1. Environment variables (from .env file or system)
    2. config.yaml file
    3. Default values

    Secrets (loaded from .env only - NEVER commit to git):
        LLM API Keys:
        - OPENROUTER_API_KEY: OpenRouter API key
        - ANTHROPIC_API_KEY: Anthropic Claude API key
        - OPENAI_API_KEY: OpenAI API key

        KIS API Credentials:
        - KIS_APP_KEY: 실전투자 앱키
        - KIS_APP_SECRET: 실전투자 앱키 시크릿
        - KIS_PAPER_APP_KEY: 모의투자 앱키
        - KIS_PAPER_APP_SECRET: 모의투자 앱키 시크릿
        - KIS_ACCOUNT_STOCK: 증권계좌 8자리
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="",
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="ignore",
    )

    # Application settings
    app_name: str = Field(
        default="Natural Language Backtesting Service",
        description="Application name",
    )
    app_version: str = Field(
        default="0.1.0",
        description="Application version",
    )
    debug: bool = Field(
        default=False,
        description="Debug mode",
        alias="APP_DEBUG",
    )

    # LLM API Keys (from .env)
    openrouter_api_key: str = Field(
        default="",
        description="OpenRouter API key",
    )
    anthropic_api_key: str = Field(
        default="",
        description="Anthropic API key",
    )
    openai_api_key: str = Field(
        default="",
        description="OpenAI API key",
    )

    # KIS API Credentials (from .env) - 민감 정보
    kis_app_key: str = Field(
        default="",
        description="KIS 실전투자 앱키",
    )
    kis_app_secret: str = Field(
        default="",
        description="KIS 실전투자 앱키 시크릿",
    )
    kis_paper_app_key: str = Field(
        default="",
        description="KIS 모의투자 앱키",
    )
    kis_paper_app_secret: str = Field(
        default="",
        description="KIS 모의투자 앱키 시크릿",
    )
    kis_hts_id: str = Field(
        default="",
        description="KIS HTS ID",
    )
    kis_account_stock: str = Field(
        default="",
        description="KIS 증권계좌 8자리",
    )
    kis_account_future: str = Field(
        default="",
        description="KIS 선물옵션계좌 8자리",
    )
    kis_paper_account_stock: str = Field(
        default="",
        description="KIS 모의투자 증권계좌 8자리",
    )
    kis_paper_account_future: str = Field(
        default="",
        description="KIS 모의투자 선물옵션계좌 8자리",
    )

    # Configuration sections (from config.yaml)
    llm: LLMConfig = Field(
        default_factory=LLMConfig,
        description="LLM provider configuration",
    )
    data: DataConfig = Field(
        default_factory=DataConfig,
        description="Data provider configuration",
    )
    execution: ExecutionConfig = Field(
        default_factory=ExecutionConfig,
        description="Code execution configuration",
    )

    def get_llm_api_key(self) -> str:
        """
        Get the appropriate API key based on the configured LLM provider.

        Returns:
            API key for the current LLM provider.

        Raises:
            ValueError: If no API key is configured for the provider.
        """
        provider = self.llm.provider
        key_map = {
            LLMProvider.OPENROUTER: self.openrouter_api_key,
            LLMProvider.LANGCHAIN: self.openrouter_api_key,  # LangChain uses OpenRouter
            LLMProvider.ANTHROPIC: self.anthropic_api_key,
            LLMProvider.OPENAI: self.openai_api_key,
        }
        api_key = key_map.get(provider, "")
        if not api_key:
            raise ValueError(
                f"No API key configured for provider '{provider.value}'. "
                f"Set the {provider.value.upper()}_API_KEY environment variable."
            )
        return api_key

    def get_kis_config(self) -> KISConfig:
        """
        Get KIS configuration with environment variables taking priority.

        Priority:
        1. Environment variables (.env)
        2. kis_devlp.yaml file (fallback)

        Returns:
            KISConfig with credentials from env vars or yaml file.
        """
        # 환경변수에 값이 있으면 사용
        if self.kis_app_key:
            return KISConfig(
                my_app=self.kis_app_key,
                my_sec=self.kis_app_secret,
                paper_app=self.kis_paper_app_key,
                paper_sec=self.kis_paper_app_secret,
                my_htsid=self.kis_hts_id,
                my_acct_stock=self.kis_account_stock,
                my_acct_future=self.kis_account_future,
                my_paper_stock=self.kis_paper_account_stock,
                my_paper_future=self.kis_paper_account_future,
            )

        # 환경변수가 없으면 kis_devlp.yaml에서 로드
        return self.data.get_kis_config()

    @classmethod
    def from_yaml(cls, config_path: Path | str | None = None) -> "Settings":
        """
        Load settings from a YAML configuration file.

        Args:
            config_path: Path to config.yaml file. If None, looks for config.yaml
                        in the current directory and project root.

        Returns:
            Settings instance with values from YAML merged with env vars.
        """
        config_data: dict = {}

        if config_path is None:
            # Look for config.yaml in common locations
            search_paths = [
                Path.cwd() / "config.yaml",
                Path(__file__).parent.parent.parent / "config.yaml",
            ]
            for path in search_paths:
                if path.exists():
                    config_path = path
                    break

        if config_path is not None:
            config_path = Path(config_path)
            if config_path.exists():
                with open(config_path, encoding="utf-8") as f:
                    config_data = yaml.safe_load(f) or {}

        return cls(**config_data)


@lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance.

    Uses lru_cache to ensure settings are only loaded once.
    Call get_settings.cache_clear() to reload settings.

    Returns:
        Cached Settings instance.
    """
    return Settings.from_yaml()
