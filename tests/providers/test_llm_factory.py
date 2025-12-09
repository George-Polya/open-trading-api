"""
Tests for LLM provider factory.

Tests:
- Factory creates correct adapter based on settings
- Factory raises error for unsupported providers
- Factory registration/unregistration
"""

from unittest.mock import MagicMock, patch

import pytest

from app.core.config import LLMConfig, LLMProvider as LLMProviderEnum, Settings
from app.providers.llm.base import LLMProvider, LLMProviderError
from app.providers.llm.anthropic_adapter import AnthropicAdapter
from app.providers.llm.factory import LLMProviderFactory
from app.providers.llm.langchain_adapter import LangChainAdapter
from app.providers.llm.openai_adapter import OpenAIAdapter
from app.providers.llm.openrouter import OpenRouterAdapter


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


@pytest.fixture
def langchain_settings() -> Settings:
    """Create settings configured for LangChain."""
    settings = MagicMock(spec=Settings)
    settings.llm = LLMConfig(
        provider=LLMProviderEnum.LANGCHAIN,
        model="anthropic/claude-3.5-sonnet",
        temperature=0.2,
        max_tokens=8000,
    )
    settings.get_llm_api_key.return_value = "sk-or-v1-test-key"
    return settings


@pytest.fixture
def anthropic_settings() -> Settings:
    """Create settings configured for Anthropic."""
    settings = MagicMock(spec=Settings)
    settings.llm = LLMConfig(
        provider=LLMProviderEnum.ANTHROPIC,
        model="claude-3-5-sonnet-20241022",
        temperature=0.2,
        max_tokens=8000,
    )
    settings.get_llm_api_key.return_value = "sk-ant-test-key"
    return settings


@pytest.fixture
def openai_settings() -> Settings:
    """Create settings configured for OpenAI."""
    settings = MagicMock(spec=Settings)
    settings.llm = LLMConfig(
        provider=LLMProviderEnum.OPENAI,
        model="gpt-4o",
        temperature=0.2,
        max_tokens=8000,
    )
    settings.get_llm_api_key.return_value = "sk-test-key"
    return settings


class TestLLMProviderFactory:
    """Tests for LLMProviderFactory."""

    def test_create_openrouter_adapter(
        self,
        openrouter_settings: Settings,
    ) -> None:
        """Test factory creates OpenRouterAdapter for OpenRouter provider."""
        provider = LLMProviderFactory.create(openrouter_settings)

        assert isinstance(provider, OpenRouterAdapter)
        assert provider.provider_name == "openrouter"

    def test_create_langchain_adapter(
        self,
        langchain_settings: Settings,
    ) -> None:
        """Test factory creates LangChainAdapter for LangChain provider."""
        provider = LLMProviderFactory.create(langchain_settings)

        assert isinstance(provider, LangChainAdapter)
        assert provider.provider_name == "langchain"

    def test_create_anthropic_adapter(
        self,
        anthropic_settings: Settings,
    ) -> None:
        """Test factory creates AnthropicAdapter for Anthropic provider."""
        provider = LLMProviderFactory.create(anthropic_settings)

        assert isinstance(provider, AnthropicAdapter)
        assert provider.provider_name == "anthropic"

    def test_create_openai_adapter(
        self,
        openai_settings: Settings,
    ) -> None:
        """Test factory creates OpenAIAdapter for OpenAI provider."""
        provider = LLMProviderFactory.create(openai_settings)

        assert isinstance(provider, OpenAIAdapter)
        assert provider.provider_name == "openai"

    def test_create_raises_llm_provider_error_on_failure(self) -> None:
        """Test factory wraps creation errors in LLMProviderError."""
        settings = MagicMock(spec=Settings)
        settings.llm = LLMConfig(provider=LLMProviderEnum.OPENROUTER)
        # Empty API key will raise ValueError in OpenRouterAdapter
        settings.get_llm_api_key.return_value = ""

        with pytest.raises(LLMProviderError, match="Failed to create LLM provider"):
            LLMProviderFactory.create(settings)

    def test_get_supported_providers(self) -> None:
        """Test getting list of supported providers."""
        providers = LLMProviderFactory.get_supported_providers()

        assert "openrouter" in providers
        assert "langchain" in providers
        assert "anthropic" in providers
        assert "openai" in providers
        assert isinstance(providers, list)

    def test_is_provider_supported(self) -> None:
        """Test checking if provider is supported."""
        assert LLMProviderFactory.is_provider_supported(LLMProviderEnum.OPENROUTER)
        assert LLMProviderFactory.is_provider_supported(LLMProviderEnum.LANGCHAIN)
        assert LLMProviderFactory.is_provider_supported(LLMProviderEnum.ANTHROPIC)
        assert LLMProviderFactory.is_provider_supported(LLMProviderEnum.OPENAI)

    def test_register_custom_provider_override(self) -> None:
        """Test registering a custom provider factory can override existing."""
        from app.providers.llm.factory import _PROVIDER_REGISTRY

        # Save original factory
        original_factory = _PROVIDER_REGISTRY.get(LLMProviderEnum.ANTHROPIC)

        class MockProvider(LLMProvider):
            async def generate(self, prompt, config=None, system_prompt=None):
                pass

            def get_model_info(self):
                pass

            @property
            def provider_name(self):
                return "mock"

        def mock_factory(settings):
            return MockProvider()

        try:
            # Override with mock
            LLMProviderFactory.register(LLMProviderEnum.ANTHROPIC, mock_factory)

            settings = MagicMock(spec=Settings)
            settings.llm = LLMConfig(provider=LLMProviderEnum.ANTHROPIC)
            settings.get_llm_api_key.return_value = "test"

            provider = LLMProviderFactory.create(settings)
            assert isinstance(provider, MockProvider)
        finally:
            # Restore original
            if original_factory:
                LLMProviderFactory.register(LLMProviderEnum.ANTHROPIC, original_factory)

    def test_unregister_and_reregister_provider(self) -> None:
        """Test unregistering and re-registering a provider."""
        from app.providers.llm.factory import _PROVIDER_REGISTRY

        # Save original factory
        original_factory = _PROVIDER_REGISTRY.get(LLMProviderEnum.ANTHROPIC)

        try:
            # Unregister
            result = LLMProviderFactory.unregister(LLMProviderEnum.ANTHROPIC)
            assert result is True
            assert not LLMProviderFactory.is_provider_supported(LLMProviderEnum.ANTHROPIC)

            # Re-unregister should return False
            result = LLMProviderFactory.unregister(LLMProviderEnum.ANTHROPIC)
            assert result is False
        finally:
            # Restore original
            if original_factory:
                LLMProviderFactory.register(LLMProviderEnum.ANTHROPIC, original_factory)
