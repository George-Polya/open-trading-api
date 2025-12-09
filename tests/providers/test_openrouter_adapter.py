"""
Tests for OpenRouter LLM adapter using OpenAI SDK.

Tests:
- Adapter initialization and configuration
- Request building
- Response parsing
- Error handling
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from openai import APIConnectionError, APIStatusError, RateLimitError as OpenAIRateLimitError

from app.core.config import LLMConfig, LLMProvider as LLMProviderEnum
from app.providers.llm.base import (
    AuthenticationError,
    GenerationConfig,
    LLMProviderError,
    ModelNotFoundError,
    RateLimitError,
)
from app.providers.llm.openrouter import OpenRouterAdapter


@pytest.fixture
def llm_config() -> LLMConfig:
    """Create a test LLM config."""
    return LLMConfig(
        provider=LLMProviderEnum.OPENROUTER,
        model="anthropic/claude-3.5-sonnet",
        site_url="https://test.com",
        site_name="Test App",
        temperature=0.2,
        max_tokens=8000,
    )


@pytest.fixture
def adapter(llm_config: LLMConfig) -> OpenRouterAdapter:
    """Create an OpenRouter adapter for testing."""
    return OpenRouterAdapter(
        api_key="sk-or-v1-test-key",
        llm_config=llm_config,
    )


class TestOpenRouterAdapterInit:
    """Tests for OpenRouterAdapter initialization."""

    def test_init_success(self, llm_config: LLMConfig) -> None:
        """Test successful adapter initialization."""
        adapter = OpenRouterAdapter(
            api_key="sk-or-v1-test-key",
            llm_config=llm_config,
        )
        assert adapter.provider_name == "openrouter"

    def test_init_empty_api_key_raises(self, llm_config: LLMConfig) -> None:
        """Test that empty API key raises ValueError."""
        with pytest.raises(ValueError, match="OpenRouter API key is required"):
            OpenRouterAdapter(
                api_key="",
                llm_config=llm_config,
            )

    def test_init_creates_async_openai_client(self, llm_config: LLMConfig) -> None:
        """Test that adapter creates AsyncOpenAI client."""
        adapter = OpenRouterAdapter(
            api_key="sk-or-v1-test-key",
            llm_config=llm_config,
        )
        # Client should be created
        assert adapter._client is not None
        assert adapter._client.base_url.host == "openrouter.ai"


class TestModelInfo:
    """Tests for model info retrieval."""

    def test_get_model_info(self, adapter: OpenRouterAdapter) -> None:
        """Test getting model info."""
        info = adapter.get_model_info()

        assert info.model_id == "anthropic/claude-3.5-sonnet"
        assert info.provider == "openrouter"
        assert info.display_name == "claude-3.5-sonnet"
        assert info.max_output_tokens == 8000
        assert info.cost_per_1k_input == Decimal("0.003")
        assert info.cost_per_1k_output == Decimal("0.015")


class TestMessageBuilding:
    """Tests for message building."""

    def test_build_messages_basic(self, adapter: OpenRouterAdapter) -> None:
        """Test basic message building."""
        messages = adapter._build_messages("Hello")

        assert messages == [{"role": "user", "content": "Hello"}]

    def test_build_messages_with_system_prompt(
        self, adapter: OpenRouterAdapter
    ) -> None:
        """Test message building with system prompt."""
        messages = adapter._build_messages("Hello", system_prompt="Be helpful")

        assert messages[0] == {"role": "system", "content": "Be helpful"}
        assert messages[1] == {"role": "user", "content": "Hello"}


class TestExtraBody:
    """Tests for extra_body building."""

    def test_build_extra_body_empty(self, adapter: OpenRouterAdapter) -> None:
        """Test extra_body is None when no extra params."""
        config = GenerationConfig()
        extra = adapter._build_extra_body(config)

        assert extra is None

    def test_build_extra_body_with_extras(self, adapter: OpenRouterAdapter) -> None:
        """Test extra_body includes config.extra."""
        config = GenerationConfig(extra={"reasoning": {"enabled": True}})
        extra = adapter._build_extra_body(config)

        assert extra == {"reasoning": {"enabled": True}}


class TestGenerate:
    """Tests for generate method."""

    @pytest.mark.asyncio
    async def test_generate_success(self, llm_config: LLMConfig) -> None:
        """Test successful generation."""
        adapter = OpenRouterAdapter(
            api_key="test-key",
            llm_config=llm_config,
        )

        # Mock the OpenAI client's chat.completions.create method
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(content="Generated text"),
                finish_reason="stop",
            )
        ]
        mock_response.usage = MagicMock(
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        )
        mock_response.id = "chatcmpl-123"
        mock_response.model = "anthropic/claude-3.5-sonnet"
        mock_response.created = 1234567890

        with patch.object(
            adapter._client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await adapter.generate("Test prompt")

        assert result.content == "Generated text"
        assert result.finish_reason == "stop"
        assert result.usage["prompt_tokens"] == 10
        assert result.usage["completion_tokens"] == 5

    @pytest.mark.asyncio
    async def test_generate_with_custom_config(self, llm_config: LLMConfig) -> None:
        """Test generation with custom config."""
        adapter = OpenRouterAdapter(
            api_key="test-key",
            llm_config=llm_config,
        )

        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content="Response"), finish_reason="stop")
        ]
        mock_response.usage = None
        mock_response.id = "test"
        mock_response.model = "test"
        mock_response.created = 0

        with patch.object(
            adapter._client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=mock_response,
        ) as mock_create:
            custom_config = GenerationConfig(temperature=0.9, max_tokens=100)
            await adapter.generate("Test", config=custom_config)

        # Verify the call was made with custom parameters
        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["temperature"] == 0.9
        assert call_kwargs["max_tokens"] == 100

    @pytest.mark.asyncio
    async def test_generate_with_extra_body(self, llm_config: LLMConfig) -> None:
        """Test generation with extra_body for reasoning models."""
        adapter = OpenRouterAdapter(
            api_key="test-key",
            llm_config=llm_config,
        )

        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content="Response"), finish_reason="stop")
        ]
        mock_response.usage = None
        mock_response.id = "test"
        mock_response.model = "test"
        mock_response.created = 0

        with patch.object(
            adapter._client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=mock_response,
        ) as mock_create:
            config = GenerationConfig(extra={"reasoning": {"enabled": True}})
            await adapter.generate("Test", config=config)

        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["extra_body"] == {"reasoning": {"enabled": True}}

    @pytest.mark.asyncio
    async def test_generate_rate_limit_error(self, llm_config: LLMConfig) -> None:
        """Test rate limit error handling."""
        adapter = OpenRouterAdapter(
            api_key="test-key",
            llm_config=llm_config,
        )

        mock_response = MagicMock()
        mock_response.status_code = 429
        error = OpenAIRateLimitError(
            message="Rate limited",
            response=mock_response,
            body={"error": {"message": "Rate limited"}},
        )

        with patch.object(
            adapter._client.chat.completions,
            "create",
            new_callable=AsyncMock,
            side_effect=error,
        ):
            with pytest.raises(RateLimitError, match="Rate limit exceeded"):
                await adapter.generate("Test")

    @pytest.mark.asyncio
    async def test_generate_authentication_error(self, llm_config: LLMConfig) -> None:
        """Test authentication error handling."""
        adapter = OpenRouterAdapter(
            api_key="test-key",
            llm_config=llm_config,
        )

        mock_response = MagicMock()
        mock_response.status_code = 401
        error = APIStatusError(
            message="Invalid API key",
            response=mock_response,
            body={"error": {"message": "Invalid API key"}},
        )

        with patch.object(
            adapter._client.chat.completions,
            "create",
            new_callable=AsyncMock,
            side_effect=error,
        ):
            with pytest.raises(AuthenticationError, match="Authentication failed"):
                await adapter.generate("Test")

    @pytest.mark.asyncio
    async def test_generate_model_not_found_error(self, llm_config: LLMConfig) -> None:
        """Test model not found error handling."""
        adapter = OpenRouterAdapter(
            api_key="test-key",
            llm_config=llm_config,
        )

        mock_response = MagicMock()
        mock_response.status_code = 404
        error = APIStatusError(
            message="Model not found",
            response=mock_response,
            body={"error": {"message": "Model not found"}},
        )

        with patch.object(
            adapter._client.chat.completions,
            "create",
            new_callable=AsyncMock,
            side_effect=error,
        ):
            with pytest.raises(ModelNotFoundError):
                await adapter.generate("Test")

    @pytest.mark.asyncio
    async def test_generate_connection_error(self, llm_config: LLMConfig) -> None:
        """Test connection error handling."""
        adapter = OpenRouterAdapter(
            api_key="test-key",
            llm_config=llm_config,
        )

        error = APIConnectionError(request=MagicMock())

        with patch.object(
            adapter._client.chat.completions,
            "create",
            new_callable=AsyncMock,
            side_effect=error,
        ):
            with pytest.raises(LLMProviderError, match="Connection failed"):
                await adapter.generate("Test")


class TestHealthCheck:
    """Tests for health check functionality."""

    @pytest.mark.asyncio
    async def test_health_check_success(self, llm_config: LLMConfig) -> None:
        """Test successful health check."""
        adapter = OpenRouterAdapter(
            api_key="test-key",
            llm_config=llm_config,
        )

        with patch.object(
            adapter._client.models,
            "list",
            new_callable=AsyncMock,
            return_value=MagicMock(),
        ):
            result = await adapter.health_check()

        assert result is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self, llm_config: LLMConfig) -> None:
        """Test failed health check returns False."""
        adapter = OpenRouterAdapter(
            api_key="test-key",
            llm_config=llm_config,
        )

        with patch.object(
            adapter._client.models,
            "list",
            new_callable=AsyncMock,
            side_effect=Exception("Connection failed"),
        ):
            result = await adapter.health_check()

        assert result is False


class TestClose:
    """Tests for close functionality."""

    @pytest.mark.asyncio
    async def test_close_calls_client_close(self, llm_config: LLMConfig) -> None:
        """Test that close calls the client's close method."""
        adapter = OpenRouterAdapter(
            api_key="test-key",
            llm_config=llm_config,
        )

        with patch.object(
            adapter._client,
            "close",
            new_callable=AsyncMock,
        ) as mock_close:
            await adapter.close()

        mock_close.assert_called_once()
