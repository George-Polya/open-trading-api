"""
LLM Provider abstraction layer.

Provides provider-agnostic interfaces for LLM operations following SOLID DIP.

Exports:
    - ModelInfo: Metadata about the LLM model
    - GenerationConfig: Configuration for text generation
    - GenerationResult: Result of an LLM generation request
    - LLMProvider: Abstract base class for LLM providers
    - LLMProviderFactory: Factory for creating LLM provider instances
    - OpenRouterAdapter: OpenRouter API adapter (OpenAI SDK)
    - LangChainAdapter: LangChain-based adapter
    - Exceptions: LLMProviderError, RateLimitError, AuthenticationError, ModelNotFoundError
"""

from app.providers.llm.base import (
    AuthenticationError,
    GenerationConfig,
    GenerationResult,
    LLMProvider,
    LLMProviderError,
    ModelInfo,
    ModelNotFoundError,
    RateLimitError,
)
from app.providers.llm.factory import LLMProviderFactory
from app.providers.llm.langchain_adapter import LangChainAdapter
from app.providers.llm.openrouter import OpenRouterAdapter

__all__ = [
    # Core types
    "ModelInfo",
    "GenerationConfig",
    "GenerationResult",
    "LLMProvider",
    # Factory
    "LLMProviderFactory",
    # Adapters
    "OpenRouterAdapter",
    "LangChainAdapter",
    # Exceptions
    "LLMProviderError",
    "RateLimitError",
    "AuthenticationError",
    "ModelNotFoundError",
]
