"""
LLM Provider Factory.

Creates and configures LLM provider instances based on application settings.
Follows the Factory Method pattern for provider creation.
"""

from typing import Callable

from app.core.config import LLMProvider as LLMProviderEnum
from app.core.config import Settings
from app.providers.llm.base import LLMProvider, LLMProviderError
from app.providers.llm.anthropic_adapter import AnthropicAdapter
from app.providers.llm.langchain_adapter import LangChainAdapter
from app.providers.llm.openai_adapter import OpenAIAdapter
from app.providers.llm.openrouter import OpenRouterAdapter

# Type alias for provider factory functions
ProviderFactory = Callable[[Settings], LLMProvider]

# Registry of provider factories
# Maps provider enum to factory function for extensibility
_PROVIDER_REGISTRY: dict[LLMProviderEnum, ProviderFactory] = {
    LLMProviderEnum.OPENROUTER: lambda settings: OpenRouterAdapter.from_settings(settings),
    LLMProviderEnum.LANGCHAIN: lambda settings: LangChainAdapter.from_settings(settings),
    LLMProviderEnum.ANTHROPIC: lambda settings: AnthropicAdapter.from_settings(settings),
    LLMProviderEnum.OPENAI: lambda settings: OpenAIAdapter.from_settings(settings),
}


class LLMProviderFactory:
    """
    Factory for creating LLM provider instances.

    Uses the configured provider setting to instantiate the appropriate
    adapter class. Supports extensibility through a registry pattern.

    Example:
        provider = LLMProviderFactory.create(settings)
        result = await provider.generate("Hello, world!")

    To register a new provider:
        LLMProviderFactory.register(LLMProviderEnum.CUSTOM, my_factory_func)
    """

    @staticmethod
    def create(settings: Settings) -> LLMProvider:
        """
        Create an LLM provider based on settings.

        Args:
            settings: Application settings containing LLM configuration

        Returns:
            Configured LLMProvider instance

        Raises:
            ValueError: If the configured provider is not supported
            LLMProviderError: If provider creation fails
        """
        provider_type = settings.llm.provider

        factory_func = _PROVIDER_REGISTRY.get(provider_type)
        if factory_func is None:
            supported = [p.value for p in _PROVIDER_REGISTRY.keys()]
            raise ValueError(
                f"Unsupported LLM provider: '{provider_type.value}'. "
                f"Supported providers: {supported}"
            )

        try:
            return factory_func(settings)
        except Exception as e:
            raise LLMProviderError(
                f"Failed to create LLM provider '{provider_type.value}': {e}",
                provider=provider_type.value,
            ) from e

    @staticmethod
    def register(
        provider_type: LLMProviderEnum,
        factory_func: ProviderFactory,
    ) -> None:
        """
        Register a new provider factory.

        Allows extending the factory with custom provider implementations.

        Args:
            provider_type: Provider enum value to register
            factory_func: Factory function that creates the provider

        Example:
            def create_custom(settings):
                return CustomAdapter(...)

            LLMProviderFactory.register(LLMProviderEnum.CUSTOM, create_custom)
        """
        _PROVIDER_REGISTRY[provider_type] = factory_func

    @staticmethod
    def unregister(provider_type: LLMProviderEnum) -> bool:
        """
        Unregister a provider factory.

        Args:
            provider_type: Provider enum value to unregister

        Returns:
            True if provider was unregistered, False if not found
        """
        if provider_type in _PROVIDER_REGISTRY:
            del _PROVIDER_REGISTRY[provider_type]
            return True
        return False

    @staticmethod
    def get_supported_providers() -> list[str]:
        """
        Get list of supported provider names.

        Returns:
            List of provider name strings
        """
        return [p.value for p in _PROVIDER_REGISTRY.keys()]

    @staticmethod
    def is_provider_supported(provider_type: LLMProviderEnum) -> bool:
        """
        Check if a provider is supported.

        Args:
            provider_type: Provider enum value to check

        Returns:
            True if provider is supported
        """
        return provider_type in _PROVIDER_REGISTRY
