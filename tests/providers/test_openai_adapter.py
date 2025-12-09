"""
Tests for Native OpenAI LLM adapter.

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
from app.providers.llm.openai_adapter import OpenAIAdapter


@pytest.fixture
def llm_config() -> LLMConfig:
    """Create a test LLM config."""
    return LLMConfig(
        provider=LLMProviderEnum.OPENAI,
        model="gpt-4o",
        temperature=0.2,
        max_tokens=8000,
    )


@pytest.fixture
def llm_config_with_prefix() -> LLMConfig:
    """Create a test LLM config with provider prefix."""
    return LLMConfig(
        provider=LLMProviderEnum.OPENAI,
        model="openai/gpt-4o",
        temperature=0.2,
        max_tokens=8000,
    )


@pytest.fixture
def adapter(llm_config: LLMConfig) -> OpenAIAdapter:
    """Create an OpenAI adapter for testing."""
    return OpenAIAdapter(
        api_key="sk-test-key",
        llm_config=llm_config,
    )


class TestOpenAIAdapterInit:
    """Tests for OpenAIAdapter initialization."""

    def test_init_success(self, llm_config: LLMConfig) -> None:
        """Test successful adapter initialization."""
        adapter = OpenAIAdapter(
            api_key="sk-test-key",
            llm_config=llm_config,
        )
        assert adapter.provider_name == "openai"

    def test_init_empty_api_key_raises(self, llm_config: LLMConfig) -> None:
        """Test that empty API key raises ValueError."""
        with pytest.raises(ValueError, match="OpenAI API key is required"):
            OpenAIAdapter(
                api_key="",
                llm_config=llm_config,
            )

    def test_init_creates_async_openai_client(self, llm_config: LLMConfig) -> None:
        """Test that adapter creates AsyncOpenAI client."""
        adapter = OpenAIAdapter(
            api_key="sk-test-key",
            llm_config=llm_config,
        )
        # Client should be created with default OpenAI base URL
        assert adapter._client is not None
        # Should NOT have custom base_url (unlike OpenRouter)
        assert adapter._client.base_url.host == "api.openai.com"

    def test_init_strips_provider_prefix(self, llm_config_with_prefix: LLMConfig) -> None:
        """Test that adapter strips provider prefix from model ID."""
        adapter = OpenAIAdapter(
            api_key="sk-test-key",
            llm_config=llm_config_with_prefix,
        )
        assert adapter._get_model_id() == "gpt-4o"


class TestModelInfo:
    """Tests for model info retrieval."""

    def test_get_model_info(self, adapter: OpenAIAdapter) -> None:
        """Test getting model info."""
        info = adapter.get_model_info()

        assert info.model_id == "gpt-4o"
        assert info.provider == "openai"
        assert info.max_output_tokens == 8000
        assert info.cost_per_1k_input == Decimal("0.005")
        assert info.cost_per_1k_output == Decimal("0.015")

    def test_get_model_info_gpt4o_mini(self, llm_config: LLMConfig) -> None:
        """Test getting model info for GPT-4o-mini."""
        llm_config.model = "gpt-4o-mini"
        adapter = OpenAIAdapter(
            api_key="test-key",
            llm_config=llm_config,
        )
        info = adapter.get_model_info()

        assert info.cost_per_1k_input == Decimal("0.00015")
        assert info.cost_per_1k_output == Decimal("0.0006")

    def test_get_model_info_unknown_model(self, llm_config: LLMConfig) -> None:
        """Test getting model info for unknown model uses default costs."""
        llm_config.model = "unknown-model"
        adapter = OpenAIAdapter(
            api_key="test-key",
            llm_config=llm_config,
        )
        info = adapter.get_model_info()

        assert info.model_id == "unknown-model"
        assert info.cost_per_1k_input == Decimal("0")
        assert info.cost_per_1k_output == Decimal("0")


class TestMessageBuilding:
    """Tests for message building."""

    def test_build_messages_basic(self, adapter: OpenAIAdapter) -> None:
        """Test basic message building."""
        messages = adapter._build_messages("Hello")

        assert messages == [{"role": "user", "content": "Hello"}]

    def test_build_messages_with_system_prompt(
        self, adapter: OpenAIAdapter
    ) -> None:
        """Test message building with system prompt."""
        messages = adapter._build_messages("Hello", system_prompt="Be helpful")

        assert messages[0] == {"role": "system", "content": "Be helpful"}
        assert messages[1] == {"role": "user", "content": "Hello"}


class TestGenerate:
    """Tests for generate method."""

    @pytest.mark.asyncio
    async def test_generate_success(self, llm_config: LLMConfig) -> None:
        """Test successful generation."""
        adapter = OpenAIAdapter(
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
        mock_response.model = "gpt-4o"
        mock_response.created = 1234567890
        mock_response.system_fingerprint = "fp_abc123"

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
        assert result.usage["total_tokens"] == 15
        assert result.raw_response["system_fingerprint"] == "fp_abc123"

    @pytest.mark.asyncio
    async def test_generate_with_custom_config(self, llm_config: LLMConfig) -> None:
        """Test generation with custom config."""
        adapter = OpenAIAdapter(
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
            custom_config = GenerationConfig(
                temperature=0.9,
                max_tokens=100,
                frequency_penalty=0.5,
                presence_penalty=0.3,
                seed=42,
            )
            await adapter.generate("Test", config=custom_config)

        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["temperature"] == 0.9
        assert call_kwargs["max_tokens"] == 100
        assert call_kwargs["frequency_penalty"] == 0.5
        assert call_kwargs["presence_penalty"] == 0.3
        assert call_kwargs["seed"] == 42

    @pytest.mark.asyncio
    async def test_generate_with_stop_sequences(self, llm_config: LLMConfig) -> None:
        """Test generation with stop sequences."""
        adapter = OpenAIAdapter(
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
            config = GenerationConfig(stop_sequences=["END", "STOP"])
            await adapter.generate("Test", config=config)

        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["stop"] == ["END", "STOP"]

    @pytest.mark.asyncio
    async def test_generate_rate_limit_error(self, llm_config: LLMConfig) -> None:
        """Test rate limit error handling."""
        adapter = OpenAIAdapter(
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
        adapter = OpenAIAdapter(
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
    async def test_generate_forbidden_error(self, llm_config: LLMConfig) -> None:
        """Test 403 forbidden error handling."""
        adapter = OpenAIAdapter(
            api_key="test-key",
            llm_config=llm_config,
        )

        mock_response = MagicMock()
        mock_response.status_code = 403
        error = APIStatusError(
            message="Forbidden",
            response=mock_response,
            body={"error": {"message": "Forbidden"}},
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
        adapter = OpenAIAdapter(
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
        adapter = OpenAIAdapter(
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

    @pytest.mark.asyncio
    async def test_generate_generic_api_error(self, llm_config: LLMConfig) -> None:
        """Test generic API error handling."""
        adapter = OpenAIAdapter(
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
            adapter._client.chat.completions,
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
        adapter = OpenAIAdapter(
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
        adapter = OpenAIAdapter(
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
        adapter = OpenAIAdapter(
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
            provider=LLMProviderEnum.OPENAI,
            model="gpt-4o",
        )
        mock_settings.get_llm_api_key.return_value = "sk-test-key"

        adapter = OpenAIAdapter.from_settings(mock_settings)

        assert isinstance(adapter, OpenAIAdapter)
        assert adapter.provider_name == "openai"
