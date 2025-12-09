"""
OpenRouter LLM Provider Adapter.

Implements the LLMProvider interface for OpenRouter API.
OpenRouter provides unified access to multiple LLM models from different providers.

API Documentation: https://openrouter.ai/docs
"""

from decimal import Decimal
from typing import Any

import httpx

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

# OpenRouter API endpoint
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

# Default model costs (per 1k tokens, in USD) - can be updated from API
DEFAULT_MODEL_COSTS: dict[str, tuple[Decimal, Decimal]] = {
    "anthropic/claude-3.5-sonnet": (Decimal("0.003"), Decimal("0.015")),
    "anthropic/claude-3-opus": (Decimal("0.015"), Decimal("0.075")),
    "anthropic/claude-3-haiku": (Decimal("0.00025"), Decimal("0.00125")),
    "openai/gpt-4o": (Decimal("0.005"), Decimal("0.015")),
    "openai/gpt-4o-mini": (Decimal("0.00015"), Decimal("0.0006")),
}


class OpenRouterAdapter(LLMProvider):
    """
    OpenRouter LLM Provider implementation.

    Uses OpenRouter's unified API to access models from multiple providers
    (Anthropic, OpenAI, etc.) through a single interface.

    Attributes:
        _http_client: Shared httpx.AsyncClient for making API requests
        _api_key: OpenRouter API key
        _llm_config: LLM configuration from settings
        _model_info: Cached model metadata

    Example:
        adapter = OpenRouterAdapter(
            http_client=client,
            api_key="sk-or-v1-...",
            llm_config=settings.llm,
        )
        result = await adapter.generate("Write a haiku about coding")
    """

    def __init__(
        self,
        http_client: httpx.AsyncClient,
        api_key: str,
        llm_config: LLMConfig,
    ) -> None:
        """
        Initialize the OpenRouter adapter.

        Args:
            http_client: Shared httpx.AsyncClient for API requests
            api_key: OpenRouter API key
            llm_config: LLM configuration containing model and generation params

        Raises:
            ValueError: If api_key is empty
        """
        if not api_key:
            raise ValueError("OpenRouter API key is required")

        self._http_client = http_client
        self._api_key = api_key
        self._llm_config = llm_config
        self._model_info = self._build_model_info()

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
            max_context_tokens=128000,
            max_output_tokens=self._llm_config.max_tokens,
            cost_per_1k_input=costs[0],
            cost_per_1k_output=costs[1],
            supports_system_prompt=True,
            supports_streaming=True,
        )

    def _build_headers(self) -> dict[str, str]:
        """Build HTTP headers for OpenRouter API requests."""
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        # Optional headers for OpenRouter
        if self._llm_config.site_url:
            headers["HTTP-Referer"] = self._llm_config.site_url
        if self._llm_config.site_name:
            headers["X-Title"] = self._llm_config.site_name

        return headers

    def _build_payload(
        self,
        prompt: str,
        config: GenerationConfig,
        system_prompt: str | None = None,
    ) -> dict[str, Any]:
        """
        Build the API request payload.

        Args:
            prompt: User prompt/message
            config: Generation configuration
            system_prompt: Optional system prompt

        Returns:
            API request payload dict
        """
        messages: list[dict[str, str]] = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": prompt})

        payload: dict[str, Any] = {
            "model": self._llm_config.model,
            "messages": messages,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "top_p": config.top_p,
        }

        # Optional parameters
        if config.stop_sequences:
            payload["stop"] = config.stop_sequences

        if config.frequency_penalty != 0.0:
            payload["frequency_penalty"] = config.frequency_penalty

        if config.presence_penalty != 0.0:
            payload["presence_penalty"] = config.presence_penalty

        if config.seed is not None:
            payload["seed"] = config.seed

        if config.top_k > 0:
            payload["top_k"] = config.top_k

        # Provider-specific extra parameters
        if config.extra:
            payload.update(config.extra)

        return payload

    def _parse_response(self, response_data: dict[str, Any]) -> GenerationResult:
        """
        Parse the API response into GenerationResult.

        Args:
            response_data: Raw JSON response from API

        Returns:
            GenerationResult with parsed content and metadata

        Raises:
            LLMProviderError: If response format is unexpected
        """
        try:
            choices = response_data.get("choices", [])
            if not choices:
                raise LLMProviderError(
                    "No choices in response",
                    provider="openrouter",
                )

            message = choices[0].get("message", {})
            content = message.get("content", "")
            finish_reason = choices[0].get("finish_reason", "stop")

            usage = response_data.get("usage", {})
            usage_dict = {
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            }

            return GenerationResult(
                content=content,
                model_info=self._model_info,
                usage=usage_dict,
                finish_reason=finish_reason,
                raw_response=response_data,
            )

        except (KeyError, IndexError, TypeError) as e:
            raise LLMProviderError(
                f"Failed to parse response: {e}",
                provider="openrouter",
            ) from e

    def _handle_error_response(self, response: httpx.Response) -> None:
        """
        Handle error responses from the API.

        Args:
            response: HTTP response object

        Raises:
            AuthenticationError: For 401/403 status codes
            RateLimitError: For 429 status code
            ModelNotFoundError: For model-related 404 errors
            LLMProviderError: For other errors
        """
        status_code = response.status_code

        try:
            error_data = response.json()
            error_message = error_data.get("error", {}).get("message", response.text)
        except Exception:
            error_message = response.text

        if status_code == 401 or status_code == 403:
            raise AuthenticationError(
                f"Authentication failed: {error_message}",
                provider="openrouter",
            )

        if status_code == 429:
            retry_after = response.headers.get("retry-after")
            raise RateLimitError(
                f"Rate limit exceeded: {error_message}",
                provider="openrouter",
                retry_after=float(retry_after) if retry_after else None,
            )

        if status_code == 404:
            raise ModelNotFoundError(
                f"Model not found: {error_message}",
                provider="openrouter",
            )

        raise LLMProviderError(
            f"API error ({status_code}): {error_message}",
            provider="openrouter",
        )

    async def generate(
        self,
        prompt: str,
        config: GenerationConfig | None = None,
        system_prompt: str | None = None,
    ) -> GenerationResult:
        """
        Generate text using OpenRouter API.

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

        headers = self._build_headers()
        payload = self._build_payload(prompt, config, system_prompt)

        try:
            response = await self._http_client.post(
                OPENROUTER_API_URL,
                headers=headers,
                json=payload,
            )

            if response.status_code != 200:
                self._handle_error_response(response)

            response_data = response.json()
            return self._parse_response(response_data)

        except httpx.TimeoutException as e:
            raise LLMProviderError(
                f"Request timed out: {e}",
                provider="openrouter",
            ) from e
        except httpx.RequestError as e:
            raise LLMProviderError(
                f"Request failed: {e}",
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
            # Use a minimal request to check connectivity
            response = await self._http_client.get(
                "https://openrouter.ai/api/v1/models",
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=10.0,
            )
            return response.status_code == 200
        except Exception:
            return False

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        http_client: httpx.AsyncClient,
    ) -> "OpenRouterAdapter":
        """
        Create adapter from application settings.

        Convenience factory method for creating the adapter with proper
        configuration from the global settings object.

        Args:
            settings: Application settings
            http_client: Shared HTTP client

        Returns:
            Configured OpenRouterAdapter instance

        Raises:
            ValueError: If OpenRouter API key is not configured
        """
        api_key = settings.get_llm_api_key()
        return cls(
            http_client=http_client,
            api_key=api_key,
            llm_config=settings.llm,
        )
