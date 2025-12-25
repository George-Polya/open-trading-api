"""
OpenRouter LLM Provider Adapter.

Implements the LLMProvider interface for OpenRouter API using OpenAI SDK.
OpenRouter provides unified access to multiple LLM models from different providers.

API Documentation: https://openrouter.ai/docs
"""

from decimal import Decimal
from typing import Any

from openai import AsyncOpenAI, APIConnectionError, APIStatusError, RateLimitError as OpenAIRateLimitError

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

# OpenRouter API base URL
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Default model costs (per 1k tokens, in USD) - can be updated from API
DEFAULT_MODEL_COSTS: dict[str, tuple[Decimal, Decimal]] = {
    "anthropic/claude-3.5-sonnet": (Decimal("0.003"), Decimal("0.015")),
    "anthropic/claude-sonnet-4": (Decimal("0.003"), Decimal("0.015")),
    "anthropic/claude-3-opus": (Decimal("0.015"), Decimal("0.075")),
    "anthropic/claude-3-haiku": (Decimal("0.00025"), Decimal("0.00125")),
    "openai/gpt-4o": (Decimal("0.005"), Decimal("0.015")),
    "openai/gpt-4o-mini": (Decimal("0.00015"), Decimal("0.0006")),
    "moonshotai/kimi-k2-thinking": (Decimal("0.0006"), Decimal("0.002")),
}


class OpenRouterAdapter(LLMProvider):
    """
    OpenRouter LLM Provider implementation using OpenAI SDK.

    Uses OpenAI Python SDK with base_url set to OpenRouter for unified
    access to models from multiple providers (Anthropic, OpenAI, etc.).

    Attributes:
        _client: AsyncOpenAI client configured for OpenRouter
        _llm_config: LLM configuration from settings
        _model_info: Cached model metadata

    Example:
        adapter = OpenRouterAdapter(
            api_key="sk-or-v1-...",
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
        Initialize the OpenRouter adapter.

        Args:
            api_key: OpenRouter API key
            llm_config: LLM configuration containing model and generation params

        Raises:
            ValueError: If api_key is empty
        """
        if not api_key:
            raise ValueError("OpenRouter API key is required")

        self._api_key = api_key
        self._llm_config = llm_config
        self._model_info = self._build_model_info()

        # Build default headers for OpenRouter
        default_headers: dict[str, str] = {}
        if llm_config.site_url:
            default_headers["HTTP-Referer"] = llm_config.site_url
        if llm_config.site_name:
            default_headers["X-Title"] = llm_config.site_name

        # Initialize AsyncOpenAI client with OpenRouter base URL
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=OPENROUTER_BASE_URL,
            default_headers=default_headers if default_headers else None,
        )

    def _build_model_info(self) -> ModelInfo:
        """Build ModelInfo from configuration."""
        model_id = self._llm_config.model
        costs = DEFAULT_MODEL_COSTS.get(
            model_id, (Decimal("0"), Decimal("0"))
        )

        return ModelInfo(
            model_id=model_id,
            provider="openrouter",
            display_name=model_id.split("/")[-1] if "/" in model_id else model_id,
            max_context_tokens=self._llm_config.max_context_tokens,
            max_output_tokens=self._llm_config.max_tokens,
            cost_per_1k_input=costs[0],
            cost_per_1k_output=costs[1],
            supports_system_prompt=True,
            supports_streaming=True,
        )

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

    def _build_extra_body(self, config: GenerationConfig) -> dict[str, Any] | None:
        """
        Build extra_body for provider-specific parameters.

        Args:
            config: Generation configuration

        Returns:
            Extra body dict or None if no extra parameters
        """
        extra: dict[str, Any] = {}

        # Add any extra parameters from config (excluding internal overrides)
        if config.extra:
            # Extract web_search_enabled override before adding other extras
            web_search_override = config.extra.pop("web_search_enabled", None)
            extra.update(config.extra)
            # Restore to original config.extra (don't mutate input)
            if web_search_override is not None:
                config.extra["web_search_enabled"] = web_search_override

        # For thinking models: enable reasoning in response
        # See: https://openrouter.ai/docs/guides/best-practices/reasoning-tokens
        if self._llm_config.reasoning_enabled:
            reasoning_tokens = (
                self._llm_config.reasoning_max_tokens
                or (config.max_tokens if config else self._llm_config.max_tokens)
            )
            extra["reasoning"] = {
                "enabled": True,
                "max_tokens": reasoning_tokens,
            }

        # Web search plugin support
        # See: https://openrouter.ai/announcements/introducing-web-search-via-the-api
        # Check for dynamic override in config.extra first, then fall back to static config
        web_search_enabled = (
            config.extra.get("web_search_enabled")
            if config.extra and "web_search_enabled" in config.extra
            else self._llm_config.web_search_enabled
        )

        if web_search_enabled:
            web_plugin: dict[str, Any] = {
                "id": "web",
                "max_results": self._llm_config.web_search_max_results,
            }
            if self._llm_config.web_search_prompt:
                web_plugin["search_prompt"] = self._llm_config.web_search_prompt

            # Add to plugins list (merge with existing if any)
            existing_plugins = extra.get("plugins", [])
            existing_plugins.append(web_plugin)
            extra["plugins"] = existing_plugins

        return extra if extra else None

    async def generate(
        self,
        prompt: str,
        config: GenerationConfig | None = None,
        system_prompt: str | None = None,
    ) -> GenerationResult:
        """
        Generate text using OpenRouter API via OpenAI SDK.

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
        extra_body = self._build_extra_body(config)

        try:
            # Build request parameters
            request_params: dict[str, Any] = {
                "model": self._llm_config.model,
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

            if extra_body:
                request_params["extra_body"] = extra_body

            # Make API call using OpenAI SDK
            response = await self._client.chat.completions.create(**request_params)

            choice = response.choices[0]

            # Parse response
            content = choice.message.content or ""
            reasoning_text = ""

            # For thinking models: extract reasoning from various fields
            # OpenRouter uses reasoning_details array
            if hasattr(choice.message, "reasoning_details") and choice.message.reasoning_details:
                details = choice.message.reasoning_details
                reasoning_parts = []
                for detail in details:
                    if hasattr(detail, "text") and detail.text:
                        reasoning_parts.append(detail.text)
                    elif hasattr(detail, "summary") and detail.summary:
                        reasoning_parts.append(detail.summary)
                    elif isinstance(detail, dict):
                        reasoning_parts.append(detail.get("text") or detail.get("summary") or "")
                reasoning_text = "\n".join(reasoning_parts)

            # Legacy: check reasoning field directly
            if not reasoning_text and hasattr(choice.message, "reasoning") and choice.message.reasoning:
                reasoning_text = choice.message.reasoning

            # Check model_extra dict (pydantic models)
            if not reasoning_text and hasattr(choice.message, "model_extra"):
                extras = choice.message.model_extra or {}
                reasoning_text = extras.get("reasoning") or ""
                # Also check reasoning_details in model_extra
                if not reasoning_text and "reasoning_details" in extras:
                    details = extras["reasoning_details"]
                    if isinstance(details, list):
                        reasoning_parts = []
                        for detail in details:
                            if isinstance(detail, dict):
                                reasoning_parts.append(detail.get("text") or detail.get("summary") or "")
                        reasoning_text = "\n".join(reasoning_parts)

            # If content is empty but reasoning exists, use reasoning as content
            # (Some thinking models put everything in reasoning)
            if not content and reasoning_text:
                content = reasoning_text

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
            }

            # Include reasoning_details if present (for thinking models)
            if hasattr(choice.message, "reasoning_details") and choice.message.reasoning_details:
                raw_response["reasoning_details"] = choice.message.reasoning_details

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
                provider="openrouter",
                retry_after=None,
            ) from e
        except APIStatusError as e:
            if e.status_code == 401 or e.status_code == 403:
                raise AuthenticationError(
                    f"Authentication failed: {e.message}",
                    provider="openrouter",
                ) from e
            if e.status_code == 404:
                raise ModelNotFoundError(
                    f"Model not found: {e.message}",
                    provider="openrouter",
                ) from e
            raise LLMProviderError(
                f"API error ({e.status_code}): {e.message}",
                provider="openrouter",
            ) from e
        except APIConnectionError as e:
            raise LLMProviderError(
                f"Connection failed: {e}",
                provider="openrouter",
            ) from e
        except Exception as e:
            raise LLMProviderError(
                f"Unexpected error: {e}",
                provider="openrouter",
            ) from e

    def get_model_info(self) -> ModelInfo:
        """Get metadata about the configured model."""
        return self._model_info

    @property
    def provider_name(self) -> str:
        """Get the provider name."""
        return "openrouter"

    async def health_check(self) -> bool:
        """
        Check if OpenRouter API is accessible.

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
    ) -> "OpenRouterAdapter":
        """
        Create adapter from application settings.

        Convenience factory method for creating the adapter with proper
        configuration from the global settings object.

        Args:
            settings: Application settings

        Returns:
            Configured OpenRouterAdapter instance

        Raises:
            ValueError: If OpenRouter API key is not configured
        """
        api_key = settings.get_llm_api_key()
        return cls(
            api_key=api_key,
            llm_config=settings.llm,
        )
