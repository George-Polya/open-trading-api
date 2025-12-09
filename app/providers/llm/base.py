"""
LLM Provider base abstractions.

Defines provider-agnostic interfaces following SOLID Dependency Inversion Principle.
All concrete adapters must implement the LLMProvider abstract base class.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class ModelInfo:
    """
    Metadata about an LLM model.

    Provider-agnostic representation of model information for UI display
    and auditing purposes.

    Attributes:
        model_id: Full model identifier (e.g., "anthropic/claude-3.5-sonnet")
        provider: Provider name (e.g., "openrouter", "anthropic", "openai")
        display_name: Human-readable model name
        max_context_tokens: Maximum context window size
        max_output_tokens: Maximum tokens the model can generate
        cost_per_1k_input: Cost per 1000 input tokens (in USD)
        cost_per_1k_output: Cost per 1000 output tokens (in USD)
        supports_system_prompt: Whether the model supports system prompts
        supports_streaming: Whether the model supports streaming responses
        extra: Additional provider-specific metadata
    """

    model_id: str
    provider: str
    display_name: str = ""
    max_context_tokens: int = 128000
    max_output_tokens: int = 8000
    cost_per_1k_input: Decimal = Decimal("0")
    cost_per_1k_output: Decimal = Decimal("0")
    supports_system_prompt: bool = True
    supports_streaming: bool = True
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Set display_name to model_id if not provided."""
        if not self.display_name:
            object.__setattr__(self, "display_name", self.model_id)


@dataclass
class GenerationConfig:
    """
    Configuration for LLM text generation.

    Maps to common generation parameters across different providers.
    Default values align with PRD specifications (temperature=0.2, max_tokens=8000).

    Attributes:
        temperature: Sampling temperature (0.0 = deterministic, 2.0 = creative)
        max_tokens: Maximum number of tokens to generate
        top_p: Nucleus sampling parameter (0.0-1.0)
        top_k: Top-k sampling parameter (0 = disabled)
        stop_sequences: List of strings that stop generation
        frequency_penalty: Penalty for token frequency (0.0-2.0)
        presence_penalty: Penalty for token presence (0.0-2.0)
        seed: Random seed for reproducible outputs (None = random)
        extra: Additional provider-specific parameters
    """

    temperature: float = 0.2
    max_tokens: int = 8000
    top_p: float = 1.0
    top_k: int = 0
    stop_sequences: list[str] = field(default_factory=list)
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    seed: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate configuration parameters."""
        if not 0.0 <= self.temperature <= 2.0:
            raise ValueError(f"temperature must be between 0.0 and 2.0, got {self.temperature}")
        if self.max_tokens <= 0:
            raise ValueError(f"max_tokens must be positive, got {self.max_tokens}")
        if not 0.0 <= self.top_p <= 1.0:
            raise ValueError(f"top_p must be between 0.0 and 1.0, got {self.top_p}")
        if self.top_k < 0:
            raise ValueError(f"top_k must be non-negative, got {self.top_k}")
        if not 0.0 <= self.frequency_penalty <= 2.0:
            raise ValueError(
                f"frequency_penalty must be between 0.0 and 2.0, got {self.frequency_penalty}"
            )
        if not 0.0 <= self.presence_penalty <= 2.0:
            raise ValueError(
                f"presence_penalty must be between 0.0 and 2.0, got {self.presence_penalty}"
            )


@dataclass
class GenerationResult:
    """
    Result of an LLM generation request.

    Attributes:
        content: Generated text content
        model_info: Information about the model used
        usage: Token usage statistics
        finish_reason: Why generation stopped (e.g., "stop", "length", "content_filter")
        raw_response: Raw response from the provider (for debugging)
    """

    content: str
    model_info: ModelInfo
    usage: dict[str, int] = field(default_factory=dict)
    finish_reason: str = "stop"
    raw_response: dict[str, Any] | None = None


class LLMProvider(ABC):
    """
    Abstract base class for LLM providers.

    All concrete LLM adapters (OpenRouter, Anthropic, OpenAI) must implement
    this interface to ensure consistent behavior across providers.

    The interface follows the Dependency Inversion Principle (DIP):
    - High-level modules (code generator, services) depend on this abstraction
    - Low-level modules (adapters) implement this abstraction

    Example:
        class OpenRouterAdapter(LLMProvider):
            async def generate(self, prompt: str, ...) -> GenerationResult:
                # Implementation
                ...

            def get_model_info(self) -> ModelInfo:
                return self._model_info
    """

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        config: GenerationConfig | None = None,
        system_prompt: str | None = None,
    ) -> GenerationResult:
        """
        Generate text from the LLM.

        Args:
            prompt: The user prompt/message to send to the LLM
            config: Generation configuration. If None, uses provider defaults.
            system_prompt: Optional system prompt for models that support it

        Returns:
            GenerationResult containing the generated text and metadata

        Raises:
            LLMProviderError: If generation fails
            RateLimitError: If rate limit is exceeded
            AuthenticationError: If API key is invalid
        """
        ...

    @abstractmethod
    def get_model_info(self) -> ModelInfo:
        """
        Get metadata about the configured model.

        Returns:
            ModelInfo containing model metadata for UI display and auditing
        """
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """
        Get the provider name.

        Returns:
            Provider identifier string (e.g., "openrouter", "anthropic")
        """
        ...

    async def health_check(self) -> bool:
        """
        Check if the provider is healthy and accessible.

        Default implementation returns True. Override for custom health checks.

        Returns:
            True if provider is healthy, False otherwise
        """
        return True

    async def close(self) -> None:
        """
        Clean up provider resources.

        Called during application shutdown. Override if the provider
        holds resources that need cleanup (e.g., HTTP connections).
        """
        pass


class LLMProviderError(Exception):
    """Base exception for LLM provider errors."""

    def __init__(self, message: str, provider: str | None = None):
        self.provider = provider
        super().__init__(message)


class RateLimitError(LLMProviderError):
    """Raised when API rate limit is exceeded."""

    def __init__(
        self,
        message: str,
        provider: str | None = None,
        retry_after: float | None = None,
    ):
        self.retry_after = retry_after
        super().__init__(message, provider)


class AuthenticationError(LLMProviderError):
    """Raised when API authentication fails."""

    pass


class ModelNotFoundError(LLMProviderError):
    """Raised when the requested model is not available."""

    pass
