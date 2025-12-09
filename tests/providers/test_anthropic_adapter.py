"""
Tests for Native Anthropic (Claude) LLM adapter.

Tests:
- Adapter initialization and configuration
- Request building
- Response parsing
- Error handling
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from anthropic import (
    APIConnectionError,
    APIStatusError,
    RateLimitError as AnthropicRateLimitError,
    AuthenticationError as AnthropicAuthenticationError,
    NotFoundError as AnthropicNotFoundError,
)

from app.core.config import LLMConfig, LLMProvider as LLMProviderEnum
from app.providers.llm.base import (
    AuthenticationError,
    GenerationConfig,
    LLMProviderError,
    ModelNotFoundError,
    RateLimitError,
)
from app.providers.llm.anthropic_adapter import AnthropicAdapter


@pytest.fixture
def llm_config() -> LLMConfig:
    """Create a test LLM config."""
    return LLMConfig(
        provider=LLMProviderEnum.ANTHROPIC,
        model="claude-3-5-sonnet-20241022",
        temperature=0.2,
        max_tokens=8000,
    )


@pytest.fixture
def llm_config_with_prefix() -> LLMConfig:
    """Create a test LLM config with provider prefix."""
    return LLMConfig(
        provider=LLMProviderEnum.ANTHROPIC,
        model="anthropic/claude-3.5-sonnet",
        temperature=0.2,
        max_tokens=8000,
    )


@pytest.fixture
def adapter(llm_config: LLMConfig) -> AnthropicAdapter:
    """Create an Anthropic adapter for testing."""
    return AnthropicAdapter(
        api_key="sk-ant-test-key",
        llm_config=llm_config,
    )


class TestAnthropicAdapterInit:
    """Tests for AnthropicAdapter initialization."""

    def test_init_success(self, llm_config: LLMConfig) -> None:
        """Test successful adapter initialization."""
        adapter = AnthropicAdapter(
            api_key="sk-ant-test-key",
            llm_config=llm_config,
        )
        assert adapter.provider_name == "anthropic"

    def test_init_empty_api_key_raises(self, llm_config: LLMConfig) -> None:
        """Test that empty API key raises ValueError."""
        with pytest.raises(ValueError, match="Anthropic API key is required"):
            AnthropicAdapter(
                api_key="",
                llm_config=llm_config,
            )

    def test_init_creates_async_anthropic_client(self, llm_config: LLMConfig) -> None:
        """Test that adapter creates AsyncAnthropic client."""
        adapter = AnthropicAdapter(
            api_key="sk-ant-test-key",
            llm_config=llm_config,
        )
        assert adapter._client is not None

    def test_init_strips_provider_prefix(self, llm_config_with_prefix: LLMConfig) -> None:
        """Test that adapter strips provider prefix from model ID."""
        adapter = AnthropicAdapter(
            api_key="sk-ant-test-key",
            llm_config=llm_config_with_prefix,
        )
        assert adapter._get_model_id() == "claude-3.5-sonnet"


class TestModelInfo:
    """Tests for model info retrieval."""

    def test_get_model_info(self, adapter: AnthropicAdapter) -> None:
        """Test getting model info."""
        info = adapter.get_model_info()

        assert info.model_id == "claude-3-5-sonnet-20241022"
        assert info.provider == "anthropic"
        assert info.max_output_tokens == 8000
        assert info.cost_per_1k_input == Decimal("0.003")
        assert info.cost_per_1k_output == Decimal("0.015")

    def test_get_model_info_unknown_model(self, llm_config: LLMConfig) -> None:
        """Test getting model info for unknown model uses default costs."""
        llm_config.model = "unknown-model"
        adapter = AnthropicAdapter(
            api_key="test-key",
            llm_config=llm_config,
        )
        info = adapter.get_model_info()

        assert info.model_id == "unknown-model"
        assert info.cost_per_1k_input == Decimal("0")
        assert info.cost_per_1k_output == Decimal("0")


class TestGenerate:
    """Tests for generate method."""

    @pytest.mark.asyncio
    async def test_generate_success(self, llm_config: LLMConfig) -> None:
        """Test successful generation."""
        adapter = AnthropicAdapter(
            api_key="test-key",
            llm_config=llm_config,
        )

        # Mock the Anthropic client's messages.create method
        mock_text_block = MagicMock()
        mock_text_block.type = "text"
        mock_text_block.text = "Generated text"

        mock_response = MagicMock()
        mock_response.content = [mock_text_block]
        mock_response.stop_reason = "end_turn"
        mock_response.usage = MagicMock(
            input_tokens=10,
            output_tokens=5,
        )
        mock_response.id = "msg-123"
        mock_response.model = "claude-3-5-sonnet-20241022"
        mock_response.type = "message"

        with patch.object(
            adapter._client.messages,
            "create",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await adapter.generate("Test prompt")

        assert result.content == "Generated text"
        assert result.finish_reason == "stop"
        assert result.usage["prompt_tokens"] == 10
        assert result.usage["completion_tokens"] == 5
        assert result.usage["total_tokens"] == 15

    @pytest.mark.asyncio
    async def test_generate_with_system_prompt(self, llm_config: LLMConfig) -> None:
        """Test generation with system prompt."""
        adapter = AnthropicAdapter(
            api_key="test-key",
            llm_config=llm_config,
        )

        mock_text_block = MagicMock()
        mock_text_block.type = "text"
        mock_text_block.text = "Response"

        mock_response = MagicMock()
        mock_response.content = [mock_text_block]
        mock_response.stop_reason = "end_turn"
        mock_response.usage = MagicMock(input_tokens=10, output_tokens=5)
        mock_response.id = "test"
        mock_response.model = "test"
        mock_response.type = "message"

        with patch.object(
            adapter._client.messages,
            "create",
            new_callable=AsyncMock,
            return_value=mock_response,
        ) as mock_create:
            await adapter.generate("Test", system_prompt="Be helpful")

        # Verify system prompt was passed
        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["system"] == "Be helpful"

    @pytest.mark.asyncio
    async def test_generate_with_custom_config(self, llm_config: LLMConfig) -> None:
        """Test generation with custom config."""
        adapter = AnthropicAdapter(
            api_key="test-key",
            llm_config=llm_config,
        )

        mock_text_block = MagicMock()
        mock_text_block.type = "text"
        mock_text_block.text = "Response"

        mock_response = MagicMock()
        mock_response.content = [mock_text_block]
        mock_response.stop_reason = "end_turn"
        mock_response.usage = MagicMock(input_tokens=10, output_tokens=5)
        mock_response.id = "test"
        mock_response.model = "test"
        mock_response.type = "message"

        with patch.object(
            adapter._client.messages,
            "create",
            new_callable=AsyncMock,
            return_value=mock_response,
        ) as mock_create:
            custom_config = GenerationConfig(
                temperature=0.9,
                max_tokens=100,
                top_p=0.8,
                top_k=40,
            )
            await adapter.generate("Test", config=custom_config)

        call_kwargs = mock_create.call_args.kwargs
        # Anthropic caps temperature at 1.0
        assert call_kwargs["temperature"] == 0.9
        assert call_kwargs["max_tokens"] == 100
        assert call_kwargs["top_p"] == 0.8
        assert call_kwargs["top_k"] == 40

    @pytest.mark.asyncio
    async def test_generate_with_stop_sequences(self, llm_config: LLMConfig) -> None:
        """Test generation with stop sequences."""
        adapter = AnthropicAdapter(
            api_key="test-key",
            llm_config=llm_config,
        )

        mock_text_block = MagicMock()
        mock_text_block.type = "text"
        mock_text_block.text = "Response"

        mock_response = MagicMock()
        mock_response.content = [mock_text_block]
        mock_response.stop_reason = "stop_sequence"
        mock_response.usage = MagicMock(input_tokens=10, output_tokens=5)
        mock_response.id = "test"
        mock_response.model = "test"
        mock_response.type = "message"

        with patch.object(
            adapter._client.messages,
            "create",
            new_callable=AsyncMock,
            return_value=mock_response,
        ) as mock_create:
            config = GenerationConfig(stop_sequences=["END", "STOP"])
            await adapter.generate("Test", config=config)

        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["stop_sequences"] == ["END", "STOP"]

    @pytest.mark.asyncio
    async def test_generate_max_tokens_finish_reason(self, llm_config: LLMConfig) -> None:
        """Test that max_tokens stop reason is converted to 'length'."""
        adapter = AnthropicAdapter(
            api_key="test-key",
            llm_config=llm_config,
        )

        mock_text_block = MagicMock()
        mock_text_block.type = "text"
        mock_text_block.text = "Truncated response"

        mock_response = MagicMock()
        mock_response.content = [mock_text_block]
        mock_response.stop_reason = "max_tokens"
        mock_response.usage = MagicMock(input_tokens=10, output_tokens=100)
        mock_response.id = "test"
        mock_response.model = "test"
        mock_response.type = "message"

        with patch.object(
            adapter._client.messages,
            "create",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await adapter.generate("Test")

        assert result.finish_reason == "length"

    @pytest.mark.asyncio
    async def test_generate_rate_limit_error(self, llm_config: LLMConfig) -> None:
        """Test rate limit error handling."""
        adapter = AnthropicAdapter(
            api_key="test-key",
            llm_config=llm_config,
        )

        mock_response = MagicMock()
        mock_response.status_code = 429
        error = AnthropicRateLimitError(
            message="Rate limited",
            response=mock_response,
            body={"error": {"message": "Rate limited"}},
        )

        with patch.object(
            adapter._client.messages,
            "create",
            new_callable=AsyncMock,
            side_effect=error,
        ):
            with pytest.raises(RateLimitError, match="Rate limit exceeded"):
                await adapter.generate("Test")

    @pytest.mark.asyncio
    async def test_generate_authentication_error(self, llm_config: LLMConfig) -> None:
        """Test authentication error handling."""
        adapter = AnthropicAdapter(
            api_key="test-key",
            llm_config=llm_config,
        )

        mock_response = MagicMock()
        mock_response.status_code = 401
        error = AnthropicAuthenticationError(
            message="Invalid API key",
            response=mock_response,
            body={"error": {"message": "Invalid API key"}},
        )

        with patch.object(
            adapter._client.messages,
            "create",
            new_callable=AsyncMock,
            side_effect=error,
        ):
            with pytest.raises(AuthenticationError, match="Authentication failed"):
                await adapter.generate("Test")

    @pytest.mark.asyncio
    async def test_generate_model_not_found_error(self, llm_config: LLMConfig) -> None:
        """Test model not found error handling."""
        adapter = AnthropicAdapter(
            api_key="test-key",
            llm_config=llm_config,
        )

        mock_response = MagicMock()
        mock_response.status_code = 404
        error = AnthropicNotFoundError(
            message="Model not found",
            response=mock_response,
            body={"error": {"message": "Model not found"}},
        )

        with patch.object(
            adapter._client.messages,
            "create",
            new_callable=AsyncMock,
            side_effect=error,
        ):
            with pytest.raises(ModelNotFoundError):
                await adapter.generate("Test")

    @pytest.mark.asyncio
    async def test_generate_connection_error(self, llm_config: LLMConfig) -> None:
        """Test connection error handling."""
        adapter = AnthropicAdapter(
            api_key="test-key",
            llm_config=llm_config,
        )

        error = APIConnectionError(request=MagicMock())

        with patch.object(
            adapter._client.messages,
            "create",
            new_callable=AsyncMock,
            side_effect=error,
        ):
            with pytest.raises(LLMProviderError, match="Connection failed"):
                await adapter.generate("Test")

    @pytest.mark.asyncio
    async def test_generate_generic_api_error(self, llm_config: LLMConfig) -> None:
        """Test generic API error handling."""
        adapter = AnthropicAdapter(
            api_key="test-key",
            llm_config=llm_config,
        )

        mock_response = MagicMock()
        mock_response.status_code = 500
        error = APIStatusError(
            message="Internal server error",
            response=mock_response,
            body={"error": {"message": "Internal server error"}},
        )

        with patch.object(
            adapter._client.messages,
            "create",
            new_callable=AsyncMock,
            side_effect=error,
        ):
            with pytest.raises(LLMProviderError, match="API error"):
                await adapter.generate("Test")


class TestHealthCheck:
    """Tests for health check functionality."""

    @pytest.mark.asyncio
    async def test_health_check_success(self, llm_config: LLMConfig) -> None:
        """Test successful health check."""
        adapter = AnthropicAdapter(
            api_key="test-key",
            llm_config=llm_config,
        )

        mock_text_block = MagicMock()
        mock_text_block.type = "text"
        mock_text_block.text = "test"

        mock_response = MagicMock()
        mock_response.content = [mock_text_block]
        mock_response.stop_reason = "end_turn"
        mock_response.usage = MagicMock(input_tokens=1, output_tokens=1)
        mock_response.id = "test"
        mock_response.model = "test"
        mock_response.type = "message"

        with patch.object(
            adapter._client.messages,
            "create",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await adapter.health_check()

        assert result is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self, llm_config: LLMConfig) -> None:
        """Test failed health check returns False."""
        adapter = AnthropicAdapter(
            api_key="test-key",
            llm_config=llm_config,
        )

        with patch.object(
            adapter._client.messages,
            "create",
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
        adapter = AnthropicAdapter(
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


class TestFromSettings:
    """Tests for from_settings factory method."""

    def test_from_settings_creates_adapter(self) -> None:
        """Test from_settings creates adapter from settings."""
        mock_settings = MagicMock()
        mock_settings.llm = LLMConfig(
            provider=LLMProviderEnum.ANTHROPIC,
            model="claude-3-5-sonnet-20241022",
        )
        mock_settings.get_llm_api_key.return_value = "sk-ant-test-key"

        adapter = AnthropicAdapter.from_settings(mock_settings)

        assert isinstance(adapter, AnthropicAdapter)
        assert adapter.provider_name == "anthropic"
