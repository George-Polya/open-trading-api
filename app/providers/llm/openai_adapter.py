"""
OpenAI Native LLM Provider Adapter.

Implements the LLMProvider interface using the native OpenAI SDK.
Provides direct access to OpenAI models without going through OpenRouter.

API Documentation: https://platform.openai.com/docs/api-reference
"""

from decimal import Decimal
from typing import Any

from openai import (
    AsyncOpenAI,
    APIConnectionError,
    APIStatusError,
    RateLimitError as OpenAIRateLimitError,
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
    "gpt-4o": (Decimal("0.005"), Decimal("0.015")),
    "gpt-4o-2024-11-20": (Decimal("0.0025"), Decimal("0.01")),
    "gpt-4o-mini": (Decimal("0.00015"), Decimal("0.0006")),
    "gpt-4o-mini-2024-07-18": (Decimal("0.00015"), Decimal("0.0006")),
    "gpt-4-turbo": (Decimal("0.01"), Decimal("0.03")),
    "gpt-4-turbo-preview": (Decimal("0.01"), Decimal("0.03")),
    "gpt-4": (Decimal("0.03"), Decimal("0.06")),
    "gpt-3.5-turbo": (Decimal("0.0005"), Decimal("0.0015")),
    "o1-preview": (Decimal("0.015"), Decimal("0.06")),
    "o1-mini": (Decimal("0.003"), Decimal("0.012")),
}


class OpenAIAdapter(LLMProvider):
    """
    Native OpenAI LLM Provider implementation.

    Uses the official OpenAI Python SDK for direct access to OpenAI models.
    This is distinct from OpenRouterAdapter which uses OpenAI SDK with
    OpenRouter's base URL.

    Attributes:
        _client: AsyncOpenAI client
        _llm_config: LLM configuration from settings
        _model_info: Cached model metadata

    Example:
        adapter = OpenAIAdapter(
            api_key="sk-...",
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
        Initialize the OpenAI adapter.

        Args:
            api_key: OpenAI API key
            llm_config: LLM configuration containing model and generation params

        Raises:
            ValueError: If api_key is empty
        """
        if not api_key:
            raise ValueError("OpenAI API key is required")

        self._api_key = api_key
        self._llm_config = llm_config
        self._model_info = self._build_model_info()

        # Initialize AsyncOpenAI client (no custom base_url - uses default OpenAI API)
        self._client = AsyncOpenAI(api_key=api_key)

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
            provider="openai",
            display_name=model_id,
            max_context_tokens=128000,  # GPT-4o context window
            max_output_tokens=self._llm_config.max_tokens,
            cost_per_1k_input=costs[0],
            cost_per_1k_output=costs[1],
            supports_system_prompt=True,
            supports_streaming=True,
        )

    def _get_model_id(self) -> str:
        """
        Get the model ID for API calls.

        Strips provider prefix if present (e.g., 'openai/gpt-4o'
        becomes 'gpt-4o').
        """
        model_id = self._llm_config.model
        if "/" in model_id:
            return model_id.split("/")[-1]
        return model_id

    def _build_messages(
        self,
        prompt: str,
        system_prompt: str | None = None,
    ) -> list[dict[str, str]]:
        """
        Build messages list for the API request.

        Args:
            prompt: User prompt/message
            system_prompt: Optional system prompt

        Returns:
            List of message dicts
        """
        messages: list[dict[str, str]] = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": prompt})

        return messages

    async def generate(
        self,
        prompt: str,
        config: GenerationConfig | None = None,
        system_prompt: str | None = None,
    ) -> GenerationResult:
        """
        Generate text using OpenAI API.

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

        messages = self._build_messages(prompt, system_prompt)
        model_id = self._get_model_id()

        try:
            # Build request parameters
            request_params: dict[str, Any] = {
                "model": model_id,
                "messages": messages,
                "temperature": config.temperature,
                "max_tokens": config.max_tokens,
                "top_p": config.top_p,
            }

            # Optional parameters
            if config.stop_sequences:
                request_params["stop"] = config.stop_sequences

            if config.frequency_penalty != 0.0:
                request_params["frequency_penalty"] = config.frequency_penalty

            if config.presence_penalty != 0.0:
                request_params["presence_penalty"] = config.presence_penalty

            if config.seed is not None:
                request_params["seed"] = config.seed

            # Make API call using OpenAI SDK
            response = await self._client.chat.completions.create(**request_params)

            # Parse response
            choice = response.choices[0]
            content = choice.message.content or ""
            finish_reason = choice.finish_reason or "stop"

            # Extract usage statistics
            usage_dict: dict[str, int] = {}
            if response.usage:
                usage_dict = {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                }

            # Build raw response for debugging
            raw_response: dict[str, Any] = {
                "id": response.id,
                "model": response.model,
                "created": response.created,
                "system_fingerprint": getattr(response, "system_fingerprint", None),
            }

            return GenerationResult(
                content=content,
                model_info=self._model_info,
                usage=usage_dict,
                finish_reason=finish_reason,
                raw_response=raw_response,
            )

        except OpenAIRateLimitError as e:
            raise RateLimitError(
                f"Rate limit exceeded: {e}",
                provider="openai",
                retry_after=None,
            ) from e
        except APIStatusError as e:
            if e.status_code == 401 or e.status_code == 403:
                raise AuthenticationError(
                    f"Authentication failed: {e.message}",
                    provider="openai",
                ) from e
            if e.status_code == 404:
                raise ModelNotFoundError(
                    f"Model not found: {e.message}",
                    provider="openai",
                ) from e
            raise LLMProviderError(
                f"API error ({e.status_code}): {e.message}",
                provider="openai",
            ) from e
        except APIConnectionError as e:
            raise LLMProviderError(
                f"Connection failed: {e}",
                provider="openai",
            ) from e
        except Exception as e:
            raise LLMProviderError(
                f"Unexpected error: {e}",
                provider="openai",
            ) from e

    def get_model_info(self) -> ModelInfo:
        """Get metadata about the configured model."""
        return self._model_info

    @property
    def provider_name(self) -> str:
        """Get the provider name."""
        return "openai"

    async def health_check(self) -> bool:
        """
        Check if OpenAI API is accessible.

        Makes a lightweight request to verify connectivity and authentication.

        Returns:
            True if API is accessible, False otherwise
        """
        try:
            # Use models endpoint to check connectivity
            await self._client.models.list()
            return True
        except Exception:
            return False

    async def close(self) -> None:
        """Close the OpenAI client."""
        await self._client.close()

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
    ) -> "OpenAIAdapter":
        """
        Create adapter from application settings.

        Convenience factory method for creating the adapter with proper
        configuration from the global settings object.

        Args:
            settings: Application settings

        Returns:
            Configured OpenAIAdapter instance

        Raises:
            ValueError: If OpenAI API key is not configured
        """
        api_key = settings.get_llm_api_key()
        return cls(
            api_key=api_key,
            llm_config=settings.llm,
        )
