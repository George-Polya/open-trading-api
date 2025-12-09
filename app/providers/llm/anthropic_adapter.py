"""
Anthropic (Claude) Native LLM Provider Adapter.

Implements the LLMProvider interface using the native Anthropic SDK.
Provides direct access to Claude models without going through OpenRouter.

API Documentation: https://docs.anthropic.com/en/api
"""

from decimal import Decimal
from typing import Any

from anthropic import (
    AsyncAnthropic,
    APIConnectionError,
    APIStatusError,
    RateLimitError as AnthropicRateLimitError,
    AuthenticationError as AnthropicAuthenticationError,
    NotFoundError as AnthropicNotFoundError,
)

from app.core.config import LLMConfig, Settings
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

# Default model costs (per 1k tokens, in USD)
DEFAULT_MODEL_COSTS: dict[str, tuple[Decimal, Decimal]] = {
    "claude-3-5-sonnet-20241022": (Decimal("0.003"), Decimal("0.015")),
    "claude-sonnet-4-20250514": (Decimal("0.003"), Decimal("0.015")),
    "claude-3-5-sonnet-latest": (Decimal("0.003"), Decimal("0.015")),
    "claude-3-opus-20240229": (Decimal("0.015"), Decimal("0.075")),
    "claude-3-opus-latest": (Decimal("0.015"), Decimal("0.075")),
    "claude-3-haiku-20240307": (Decimal("0.00025"), Decimal("0.00125")),
    "claude-3-5-haiku-20241022": (Decimal("0.001"), Decimal("0.005")),
    "claude-3-5-haiku-latest": (Decimal("0.001"), Decimal("0.005")),
}


class AnthropicAdapter(LLMProvider):
    """
    Native Anthropic (Claude) LLM Provider implementation.

    Uses the official Anthropic Python SDK for direct access to Claude models.
    This is preferable when you want to use Anthropic's API directly without
    going through OpenRouter.

    Attributes:
        _client: AsyncAnthropic client
        _llm_config: LLM configuration from settings
        _model_info: Cached model metadata

    Example:
        adapter = AnthropicAdapter(
            api_key="sk-ant-...",
            llm_config=settings.llm,
        )
        result = await adapter.generate("Write a haiku about coding")
    """

    def __init__(
        self,
        api_key: str,
        llm_config: LLMConfig,
    ) -> None:
        """
        Initialize the Anthropic adapter.

        Args:
            api_key: Anthropic API key
            llm_config: LLM configuration containing model and generation params

        Raises:
            ValueError: If api_key is empty
        """
        if not api_key:
            raise ValueError("Anthropic API key is required")

        self._api_key = api_key
        self._llm_config = llm_config
        self._model_info = self._build_model_info()

        # Initialize AsyncAnthropic client
        self._client = AsyncAnthropic(api_key=api_key)

    def _build_model_info(self) -> ModelInfo:
        """Build ModelInfo from configuration."""
        model_id = self._llm_config.model

        # Handle model ID format (strip provider prefix if present)
        if "/" in model_id:
            model_id = model_id.split("/")[-1]

        costs = DEFAULT_MODEL_COSTS.get(
            model_id, (Decimal("0"), Decimal("0"))
        )

        return ModelInfo(
            model_id=model_id,
            provider="anthropic",
            display_name=model_id,
            max_context_tokens=200000,  # Claude 3.5 context window
            max_output_tokens=self._llm_config.max_tokens,
            cost_per_1k_input=costs[0],
            cost_per_1k_output=costs[1],
            supports_system_prompt=True,
            supports_streaming=True,
        )

    def _get_model_id(self) -> str:
        """
        Get the model ID for API calls.

        Strips provider prefix if present (e.g., 'anthropic/claude-3.5-sonnet'
        becomes 'claude-3.5-sonnet').
        """
        model_id = self._llm_config.model
        if "/" in model_id:
            return model_id.split("/")[-1]
        return model_id

    async def generate(
        self,
        prompt: str,
        config: GenerationConfig | None = None,
        system_prompt: str | None = None,
    ) -> GenerationResult:
        """
        Generate text using Anthropic API.

        Args:
            prompt: The user prompt/message
            config: Generation configuration. Uses settings defaults if None.
            system_prompt: Optional system prompt

        Returns:
            GenerationResult containing the generated text and metadata

        Raises:
            LLMProviderError: If generation fails
            RateLimitError: If rate limit is exceeded
            AuthenticationError: If API key is invalid
        """
        if config is None:
            config = GenerationConfig(
                temperature=self._llm_config.temperature,
                max_tokens=self._llm_config.max_tokens,
            )

        model_id = self._get_model_id()

        try:
            # Build request parameters
            request_params: dict[str, Any] = {
                "model": model_id,
                "max_tokens": config.max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            }

            # Add system prompt if provided
            if system_prompt:
                request_params["system"] = system_prompt

            # Add temperature (Anthropic supports 0.0-1.0)
            request_params["temperature"] = min(config.temperature, 1.0)

            # Optional parameters
            if config.top_p != 1.0:
                request_params["top_p"] = config.top_p

            if config.top_k > 0:
                request_params["top_k"] = config.top_k

            if config.stop_sequences:
                request_params["stop_sequences"] = config.stop_sequences

            # Make API call using Anthropic SDK
            response = await self._client.messages.create(**request_params)

            # Parse response - extract text from content blocks
            content = ""
            for block in response.content:
                if block.type == "text":
                    content += block.text

            # Extract finish reason
            finish_reason = response.stop_reason or "stop"
            if finish_reason == "end_turn":
                finish_reason = "stop"
            elif finish_reason == "max_tokens":
                finish_reason = "length"

            # Extract usage statistics
            usage_dict: dict[str, int] = {}
            if response.usage:
                usage_dict = {
                    "prompt_tokens": response.usage.input_tokens,
                    "completion_tokens": response.usage.output_tokens,
                    "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
                }

            # Build raw response for debugging
            raw_response: dict[str, Any] = {
                "id": response.id,
                "model": response.model,
                "type": response.type,
                "stop_reason": response.stop_reason,
            }

            return GenerationResult(
                content=content,
                model_info=self._model_info,
                usage=usage_dict,
                finish_reason=finish_reason,
                raw_response=raw_response,
            )

        except AnthropicRateLimitError as e:
            raise RateLimitError(
                f"Rate limit exceeded: {e}",
                provider="anthropic",
                retry_after=None,
            ) from e
        except AnthropicAuthenticationError as e:
            raise AuthenticationError(
                f"Authentication failed: {e}",
                provider="anthropic",
            ) from e
        except AnthropicNotFoundError as e:
            raise ModelNotFoundError(
                f"Model not found: {e}",
                provider="anthropic",
            ) from e
        except APIStatusError as e:
            raise LLMProviderError(
                f"API error ({e.status_code}): {e.message}",
                provider="anthropic",
            ) from e
        except APIConnectionError as e:
            raise LLMProviderError(
                f"Connection failed: {e}",
                provider="anthropic",
            ) from e
        except Exception as e:
            raise LLMProviderError(
                f"Unexpected error: {e}",
                provider="anthropic",
            ) from e

    def get_model_info(self) -> ModelInfo:
        """Get metadata about the configured model."""
        return self._model_info

    @property
    def provider_name(self) -> str:
        """Get the provider name."""
        return "anthropic"

    async def health_check(self) -> bool:
        """
        Check if Anthropic API is accessible.

        Makes a lightweight request to verify connectivity and authentication.

        Returns:
            True if API is accessible, False otherwise
        """
        try:
            # Make a minimal request to check connectivity
            await self._client.messages.create(
                model=self._get_model_id(),
                max_tokens=5,
                messages=[{"role": "user", "content": "test"}],
            )
            return True
        except Exception:
            return False

    async def close(self) -> None:
        """Close the Anthropic client."""
        await self._client.close()

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
    ) -> "AnthropicAdapter":
        """
        Create adapter from application settings.

        Convenience factory method for creating the adapter with proper
        configuration from the global settings object.

        Args:
            settings: Application settings

        Returns:
            Configured AnthropicAdapter instance

        Raises:
            ValueError: If Anthropic API key is not configured
        """
        api_key = settings.get_llm_api_key()
        return cls(
            api_key=api_key,
            llm_config=settings.llm,
        )
