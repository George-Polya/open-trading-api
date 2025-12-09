"""
Tests for OpenRouter LLM adapter.

Tests:
- Adapter initialization and configuration
- Request payload building
- Response parsing
- Error handling
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

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
def mock_http_client() -> MagicMock:
    """Create a mock HTTP client."""
    return MagicMock(spec=httpx.AsyncClient)


@pytest.fixture
def adapter(llm_config: LLMConfig, mock_http_client: MagicMock) -> OpenRouterAdapter:
    """Create an OpenRouter adapter for testing."""
    return OpenRouterAdapter(
        http_client=mock_http_client,
        api_key="sk-or-v1-test-key",
        llm_config=llm_config,
    )


class TestOpenRouterAdapterInit:
    """Tests for OpenRouterAdapter initialization."""

    def test_init_success(
        self, llm_config: LLMConfig, mock_http_client: MagicMock
    ) -> None:
        """Test successful adapter initialization."""
        adapter = OpenRouterAdapter(
            http_client=mock_http_client,
            api_key="sk-or-v1-test-key",
            llm_config=llm_config,
        )
        assert adapter.provider_name == "openrouter"

    def test_init_empty_api_key_raises(
        self, llm_config: LLMConfig, mock_http_client: MagicMock
    ) -> None:
        """Test that empty API key raises ValueError."""
        with pytest.raises(ValueError, match="OpenRouter API key is required"):
            OpenRouterAdapter(
                http_client=mock_http_client,
                api_key="",
                llm_config=llm_config,
            )


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


class TestPayloadBuilding:
    """Tests for request payload building."""

    def test_build_headers(self, adapter: OpenRouterAdapter) -> None:
        """Test header building with site URL and name."""
        headers = adapter._build_headers()

        assert headers["Authorization"] == "Bearer sk-or-v1-test-key"
        assert headers["Content-Type"] == "application/json"
        assert headers["HTTP-Referer"] == "https://test.com"
        assert headers["X-Title"] == "Test App"

    def test_build_headers_without_optional(
        self, mock_http_client: MagicMock
    ) -> None:
        """Test header building without optional site info."""
        config = LLMConfig(provider=LLMProviderEnum.OPENROUTER)
        adapter = OpenRouterAdapter(
            http_client=mock_http_client,
            api_key="test-key",
            llm_config=config,
        )
        headers = adapter._build_headers()

        assert "HTTP-Referer" not in headers
        assert "X-Title" not in headers

    def test_build_payload_basic(self, adapter: OpenRouterAdapter) -> None:
        """Test basic payload building."""
        config = GenerationConfig()
        payload = adapter._build_payload("Hello", config)

        assert payload["model"] == "anthropic/claude-3.5-sonnet"
        assert payload["messages"] == [{"role": "user", "content": "Hello"}]
        assert payload["temperature"] == 0.2
        assert payload["max_tokens"] == 8000

    def test_build_payload_with_system_prompt(
        self, adapter: OpenRouterAdapter
    ) -> None:
        """Test payload building with system prompt."""
        config = GenerationConfig()
        payload = adapter._build_payload("Hello", config, system_prompt="Be helpful")

        assert payload["messages"][0] == {"role": "system", "content": "Be helpful"}
        assert payload["messages"][1] == {"role": "user", "content": "Hello"}

    def test_build_payload_with_stop_sequences(
        self, adapter: OpenRouterAdapter
    ) -> None:
        """Test payload building with stop sequences."""
        config = GenerationConfig(stop_sequences=["END", "STOP"])
        payload = adapter._build_payload("Hello", config)

        assert payload["stop"] == ["END", "STOP"]

    def test_build_payload_with_penalties(self, adapter: OpenRouterAdapter) -> None:
        """Test payload building with frequency/presence penalties."""
        config = GenerationConfig(frequency_penalty=0.5, presence_penalty=0.3)
        payload = adapter._build_payload("Hello", config)

        assert payload["frequency_penalty"] == 0.5
        assert payload["presence_penalty"] == 0.3


class TestResponseParsing:
    """Tests for API response parsing."""

    def test_parse_success_response(self, adapter: OpenRouterAdapter) -> None:
        """Test parsing successful API response."""
        response_data = {
            "choices": [
                {
                    "message": {"content": "Hello there!"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
            },
        }

        result = adapter._parse_response(response_data)

        assert result.content == "Hello there!"
        assert result.finish_reason == "stop"
        assert result.usage["prompt_tokens"] == 10
        assert result.usage["completion_tokens"] == 5

    def test_parse_empty_choices_raises(self, adapter: OpenRouterAdapter) -> None:
        """Test that empty choices raises error."""
        with pytest.raises(LLMProviderError, match="No choices in response"):
            adapter._parse_response({"choices": []})


class TestErrorHandling:
    """Tests for error response handling."""

    def test_handle_401_authentication_error(
        self, adapter: OpenRouterAdapter
    ) -> None:
        """Test 401 response raises AuthenticationError."""
        response = MagicMock(spec=httpx.Response)
        response.status_code = 401
        response.json.return_value = {"error": {"message": "Invalid key"}}

        with pytest.raises(AuthenticationError, match="Authentication failed"):
            adapter._handle_error_response(response)

    def test_handle_403_authentication_error(
        self, adapter: OpenRouterAdapter
    ) -> None:
        """Test 403 response raises AuthenticationError."""
        response = MagicMock(spec=httpx.Response)
        response.status_code = 403
        response.json.return_value = {"error": {"message": "Forbidden"}}

        with pytest.raises(AuthenticationError):
            adapter._handle_error_response(response)

    def test_handle_429_rate_limit_error(self, adapter: OpenRouterAdapter) -> None:
        """Test 429 response raises RateLimitError."""
        response = MagicMock(spec=httpx.Response)
        response.status_code = 429
        response.headers = {"retry-after": "60"}
        response.json.return_value = {"error": {"message": "Rate limited"}}

        with pytest.raises(RateLimitError) as exc_info:
            adapter._handle_error_response(response)

        assert exc_info.value.retry_after == 60.0

    def test_handle_404_model_not_found(self, adapter: OpenRouterAdapter) -> None:
        """Test 404 response raises ModelNotFoundError."""
        response = MagicMock(spec=httpx.Response)
        response.status_code = 404
        response.json.return_value = {"error": {"message": "Model not found"}}

        with pytest.raises(ModelNotFoundError):
            adapter._handle_error_response(response)

    def test_handle_500_generic_error(self, adapter: OpenRouterAdapter) -> None:
        """Test 500 response raises LLMProviderError."""
        response = MagicMock(spec=httpx.Response)
        response.status_code = 500
        response.text = "Internal Server Error"
        response.json.side_effect = Exception("JSON parse error")

        with pytest.raises(LLMProviderError, match="API error"):
            adapter._handle_error_response(response)


class TestGenerate:
    """Tests for generate method."""

    @pytest.mark.asyncio
    async def test_generate_success(
        self, llm_config: LLMConfig
    ) -> None:
        """Test successful generation."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {"content": "Generated text"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = mock_response

        adapter = OpenRouterAdapter(
            http_client=mock_client,
            api_key="test-key",
            llm_config=llm_config,
        )

        result = await adapter.generate("Test prompt")

        assert result.content == "Generated text"
        assert result.finish_reason == "stop"
        mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_with_custom_config(
        self, llm_config: LLMConfig
    ) -> None:
        """Test generation with custom config."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Response"}, "finish_reason": "stop"}],
            "usage": {},
        }

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = mock_response

        adapter = OpenRouterAdapter(
            http_client=mock_client,
            api_key="test-key",
            llm_config=llm_config,
        )

        custom_config = GenerationConfig(temperature=0.9, max_tokens=100)
        await adapter.generate("Test", config=custom_config)

        call_args = mock_client.post.call_args
        payload = call_args.kwargs["json"]
        assert payload["temperature"] == 0.9
        assert payload["max_tokens"] == 100

    @pytest.mark.asyncio
    async def test_generate_timeout_error(
        self, llm_config: LLMConfig
    ) -> None:
        """Test timeout raises LLMProviderError."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.side_effect = httpx.TimeoutException("Request timed out")

        adapter = OpenRouterAdapter(
            http_client=mock_client,
            api_key="test-key",
            llm_config=llm_config,
        )

        with pytest.raises(LLMProviderError, match="timed out"):
            await adapter.generate("Test")

    @pytest.mark.asyncio
    async def test_generate_request_error(
        self, llm_config: LLMConfig
    ) -> None:
        """Test request error raises LLMProviderError."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.side_effect = httpx.RequestError("Connection failed")

        adapter = OpenRouterAdapter(
            http_client=mock_client,
            api_key="test-key",
            llm_config=llm_config,
        )

        with pytest.raises(LLMProviderError, match="Request failed"):
            await adapter.generate("Test")


class TestHealthCheck:
    """Tests for health check functionality."""

    @pytest.mark.asyncio
    async def test_health_check_success(self, llm_config: LLMConfig) -> None:
        """Test successful health check."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = mock_response

        adapter = OpenRouterAdapter(
            http_client=mock_client,
            api_key="test-key",
            llm_config=llm_config,
        )

        result = await adapter.health_check()

        assert result is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self, llm_config: LLMConfig) -> None:
        """Test failed health check returns False."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.side_effect = Exception("Connection failed")

        adapter = OpenRouterAdapter(
            http_client=mock_client,
            api_key="test-key",
            llm_config=llm_config,
        )

        result = await adapter.health_check()

        assert result is False
