"""
LangChain LLM Provider Adapter.

Implements the LLMProvider interface using LangChain's ChatOpenAI with OpenRouter.
Provides an alternative integration path for those already using LangChain ecosystem.

API Documentation: https://openrouter.ai/docs
LangChain Documentation: https://python.langchain.com/docs/integrations/chat/openai
"""

from decimal import Decimal
from typing import Any

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

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

# Default model costs (per 1k tokens, in USD)
DEFAULT_MODEL_COSTS: dict[str, tuple[Decimal, Decimal]] = {
    "anthropic/claude-3.5-sonnet": (Decimal("0.003"), Decimal("0.015")),
    "anthropic/claude-sonnet-4": (Decimal("0.003"), Decimal("0.015")),
    "anthropic/claude-3-opus": (Decimal("0.015"), Decimal("0.075")),
    "anthropic/claude-3-haiku": (Decimal("0.00025"), Decimal("0.00125")),
    "openai/gpt-4o": (Decimal("0.005"), Decimal("0.015")),
    "openai/gpt-4o-mini": (Decimal("0.00015"), Decimal("0.0006")),
    "moonshotai/kimi-k2-thinking": (Decimal("0.0006"), Decimal("0.002")),
}


class LangChainAdapter(LLMProvider):
    """
    LangChain-based LLM Provider implementation using OpenRouter.

    Uses LangChain's ChatOpenAI with base_url set to OpenRouter for unified
    access to models from multiple providers (Anthropic, OpenAI, etc.).

    This adapter is useful when you want to leverage LangChain's ecosystem
    (chains, agents, memory, etc.) while using OpenRouter as the backend.

    Attributes:
        _client: LangChain ChatOpenAI client configured for OpenRouter
        _llm_config: LLM configuration from settings
        _model_info: Cached model metadata

    Example:
        adapter = LangChainAdapter(
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
        Initialize the LangChain adapter.

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

        # Initialize LangChain ChatOpenAI with OpenRouter base URL
        self._client = ChatOpenAI(
            api_key=api_key,
            base_url=OPENROUTER_BASE_URL,
            model=llm_config.model,
            temperature=llm_config.temperature,
            max_tokens=llm_config.max_tokens,
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
            provider="langchain",
            display_name=model_id.split("/")[-1] if "/" in model_id else model_id,
            max_context_tokens=128000,
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
    ) -> list[SystemMessage | HumanMessage]:
        """
        Build LangChain messages list for the API request.

        Args:
            prompt: User prompt/message
            system_prompt: Optional system prompt

        Returns:
            List of LangChain message objects
        """
        messages: list[SystemMessage | HumanMessage] = []

        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))

        messages.append(HumanMessage(content=prompt))

        return messages

    async def generate(
        self,
        prompt: str,
        config: GenerationConfig | None = None,
        system_prompt: str | None = None,
    ) -> GenerationResult:
        """
        Generate text using LangChain ChatOpenAI with OpenRouter.

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

        try:
            # Create a bound client with custom config if different from defaults
            client = self._client
            if (
                config.temperature != self._llm_config.temperature
                or config.max_tokens != self._llm_config.max_tokens
            ):
                # Create new client with updated parameters
                client = self._client.bind(
                    temperature=config.temperature,
                    max_tokens=config.max_tokens,
                )

            # Apply additional parameters if set
            invoke_kwargs: dict[str, Any] = {}
            if config.stop_sequences:
                invoke_kwargs["stop"] = config.stop_sequences

            # Make API call using LangChain
            response = await client.ainvoke(messages, **invoke_kwargs)

            # Extract content
            content = str(response.content) if response.content else ""

            # Extract usage statistics from response metadata
            usage_dict: dict[str, int] = {}
            if hasattr(response, "response_metadata"):
                token_usage = response.response_metadata.get("token_usage", {})
                if token_usage:
                    usage_dict = {
                        "prompt_tokens": token_usage.get("prompt_tokens", 0),
                        "completion_tokens": token_usage.get("completion_tokens", 0),
                        "total_tokens": token_usage.get("total_tokens", 0),
                    }

            # Extract finish reason
            finish_reason = "stop"
            if hasattr(response, "response_metadata"):
                finish_reason = response.response_metadata.get("finish_reason", "stop")

            # Build raw response for debugging
            raw_response: dict[str, Any] = {}
            if hasattr(response, "response_metadata"):
                raw_response = dict(response.response_metadata)
            if hasattr(response, "id"):
                raw_response["id"] = response.id

            return GenerationResult(
                content=content,
                model_info=self._model_info,
                usage=usage_dict,
                finish_reason=finish_reason,
                raw_response=raw_response,
            )

        except Exception as e:
            error_msg = str(e).lower()

            # Handle rate limit errors
            if "rate limit" in error_msg or "429" in str(e):
                raise RateLimitError(
                    f"Rate limit exceeded: {e}",
                    provider="langchain",
                    retry_after=None,
                ) from e

            # Handle authentication errors
            if "401" in str(e) or "403" in str(e) or "unauthorized" in error_msg:
                raise AuthenticationError(
                    f"Authentication failed: {e}",
                    provider="langchain",
                ) from e

            # Handle model not found errors
            if "404" in str(e) or "model not found" in error_msg:
                raise ModelNotFoundError(
                    f"Model not found: {e}",
                    provider="langchain",
                ) from e

            # Generic error
            raise LLMProviderError(
                f"LangChain generation failed: {e}",
                provider="langchain",
            ) from e

    def get_model_info(self) -> ModelInfo:
        """Get metadata about the configured model."""
        return self._model_info

    @property
    def provider_name(self) -> str:
        """Get the provider name."""
        return "langchain"

    async def health_check(self) -> bool:
        """
        Check if the LangChain/OpenRouter connection is working.

        Makes a lightweight request to verify connectivity and authentication.

        Returns:
            True if API is accessible, False otherwise
        """
        try:
            # Simple test message
            messages = [HumanMessage(content="test")]
            await self._client.ainvoke(messages, max_tokens=5)
            return True
        except Exception:
            return False

    async def close(self) -> None:
        """
        Close the LangChain client.

        LangChain's ChatOpenAI doesn't require explicit cleanup,
        but this method is provided for interface consistency.
        """
        # LangChain ChatOpenAI doesn't have an explicit close method
        pass

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
    ) -> "LangChainAdapter":
        """
        Create adapter from application settings.

        Convenience factory method for creating the adapter with proper
        configuration from the global settings object.

        Args:
            settings: Application settings

        Returns:
            Configured LangChainAdapter instance

        Raises:
            ValueError: If OpenRouter API key is not configured
        """
        api_key = settings.get_llm_api_key()
        return cls(
            api_key=api_key,
            llm_config=settings.llm,
        )
