"""
Tests for LLM provider factory.

Tests:
- Factory creates correct adapter based on settings
- Factory raises error for unsupported providers
- Factory registration/unregistration
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.core.config import LLMConfig, LLMProvider as LLMProviderEnum, Settings
from app.providers.llm.base import LLMProvider, LLMProviderError
from app.providers.llm.factory import LLMProviderFactory
from app.providers.llm.openrouter import OpenRouterAdapter


@pytest.fixture
def mock_http_client() -> httpx.AsyncClient:
    """Create a mock HTTP client."""
    return MagicMock(spec=httpx.AsyncClient)


@pytest.fixture
def openrouter_settings() -> Settings:
    """Create settings configured for OpenRouter."""
    settings = MagicMock(spec=Settings)
    settings.llm = LLMConfig(
        provider=LLMProviderEnum.OPENROUTER,
        model="anthropic/claude-3.5-sonnet",
        temperature=0.2,
        max_tokens=8000,
    )
    settings.get_llm_api_key.return_value = "sk-or-v1-test-key"
    return settings


class TestLLMProviderFactory:
    """Tests for LLMProviderFactory."""

    def test_create_openrouter_adapter(
        self,
        openrouter_settings: Settings,
        mock_http_client: httpx.AsyncClient,
    ) -> None:
        """Test factory creates OpenRouterAdapter for OpenRouter provider."""
        provider = LLMProviderFactory.create(openrouter_settings, mock_http_client)

        assert isinstance(provider, OpenRouterAdapter)
        assert provider.provider_name == "openrouter"

    def test_create_raises_for_unsupported_provider(
        self,
        mock_http_client: httpx.AsyncClient,
    ) -> None:
        """Test factory raises ValueError for unsupported provider."""
        settings = MagicMock(spec=Settings)
        settings.llm = LLMConfig(provider=LLMProviderEnum.ANTHROPIC)
        settings.get_llm_api_key.return_value = "test-key"

        with pytest.raises(ValueError, match="Unsupported LLM provider"):
            LLMProviderFactory.create(settings, mock_http_client)

    def test_create_raises_llm_provider_error_on_failure(
        self,
        mock_http_client: httpx.AsyncClient,
    ) -> None:
        """Test factory wraps creation errors in LLMProviderError."""
        settings = MagicMock(spec=Settings)
        settings.llm = LLMConfig(provider=LLMProviderEnum.OPENROUTER)
        # Empty API key will raise ValueError in OpenRouterAdapter
        settings.get_llm_api_key.return_value = ""

        with pytest.raises(LLMProviderError, match="Failed to create LLM provider"):
            LLMProviderFactory.create(settings, mock_http_client)

    def test_get_supported_providers(self) -> None:
        """Test getting list of supported providers."""
        providers = LLMProviderFactory.get_supported_providers()

        assert "openrouter" in providers
        assert isinstance(providers, list)

    def test_is_provider_supported(self) -> None:
        """Test checking if provider is supported."""
        assert LLMProviderFactory.is_provider_supported(LLMProviderEnum.OPENROUTER)
        # Anthropic and OpenAI not yet implemented
        assert not LLMProviderFactory.is_provider_supported(LLMProviderEnum.ANTHROPIC)
        assert not LLMProviderFactory.is_provider_supported(LLMProviderEnum.OPENAI)

    def test_register_custom_provider(
        self,
        mock_http_client: httpx.AsyncClient,
    ) -> None:
        """Test registering a custom provider factory."""

        class MockProvider(LLMProvider):
            async def generate(self, prompt, config=None, system_prompt=None):
                pass

            def get_model_info(self):
                pass

            @property
            def provider_name(self):
                return "mock"

        def mock_factory(settings, client):
            return MockProvider()

        # Register
        LLMProviderFactory.register(LLMProviderEnum.ANTHROPIC, mock_factory)

        try:
            assert LLMProviderFactory.is_provider_supported(LLMProviderEnum.ANTHROPIC)

            settings = MagicMock(spec=Settings)
            settings.llm = LLMConfig(provider=LLMProviderEnum.ANTHROPIC)
            settings.get_llm_api_key.return_value = "test"

            provider = LLMProviderFactory.create(settings, mock_http_client)
            assert isinstance(provider, MockProvider)
        finally:
            # Clean up
            LLMProviderFactory.unregister(LLMProviderEnum.ANTHROPIC)

    def test_unregister_provider(self) -> None:
        """Test unregistering a provider."""

        def mock_factory(settings, client):
            return MagicMock()

        LLMProviderFactory.register(LLMProviderEnum.ANTHROPIC, mock_factory)
        assert LLMProviderFactory.is_provider_supported(LLMProviderEnum.ANTHROPIC)

        result = LLMProviderFactory.unregister(LLMProviderEnum.ANTHROPIC)
        assert result is True
        assert not LLMProviderFactory.is_provider_supported(LLMProviderEnum.ANTHROPIC)

    def test_unregister_nonexistent_provider(self) -> None:
        """Test unregistering a provider that doesn't exist returns False."""
        # Make sure it's not registered
        LLMProviderFactory.unregister(LLMProviderEnum.ANTHROPIC)

        result = LLMProviderFactory.unregister(LLMProviderEnum.ANTHROPIC)
        assert result is False
