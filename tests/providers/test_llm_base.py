"""
Tests for LLM provider base abstractions.

Tests:
- ModelInfo and GenerationConfig dataclass validation
- LLMProvider abstract class enforcement
- Exception classes
"""

from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

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


class TestModelInfo:
    """Tests for ModelInfo dataclass."""

    def test_model_info_creation(self) -> None:
        """Test basic ModelInfo creation with required fields."""
        info = ModelInfo(
            model_id="anthropic/claude-3.5-sonnet",
            provider="openrouter",
        )
        assert info.model_id == "anthropic/claude-3.5-sonnet"
        assert info.provider == "openrouter"
        assert info.display_name == "anthropic/claude-3.5-sonnet"  # Auto-set

    def test_model_info_with_all_fields(self) -> None:
        """Test ModelInfo creation with all fields."""
        info = ModelInfo(
            model_id="anthropic/claude-3.5-sonnet",
            provider="openrouter",
            display_name="Claude 3.5 Sonnet",
            max_context_tokens=200000,
            max_output_tokens=4096,
            cost_per_1k_input=Decimal("0.003"),
            cost_per_1k_output=Decimal("0.015"),
            supports_system_prompt=True,
            supports_streaming=True,
            extra={"version": "2024-01"},
        )
        assert info.display_name == "Claude 3.5 Sonnet"
        assert info.max_context_tokens == 200000
        assert info.cost_per_1k_input == Decimal("0.003")
        assert info.extra["version"] == "2024-01"

    def test_model_info_is_frozen(self) -> None:
        """Test that ModelInfo is immutable."""
        info = ModelInfo(model_id="test", provider="test")
        with pytest.raises(FrozenInstanceError):
            info.model_id = "changed"  # type: ignore

    def test_model_info_default_display_name(self) -> None:
        """Test that display_name defaults to model_id."""
        info = ModelInfo(model_id="test/model", provider="test")
        assert info.display_name == "test/model"


class TestGenerationConfig:
    """Tests for GenerationConfig dataclass."""

    def test_default_values(self) -> None:
        """Test GenerationConfig default values match PRD specs."""
        config = GenerationConfig()
        assert config.temperature == 0.2
        assert config.max_tokens == 8000
        assert config.top_p == 1.0
        assert config.top_k == 0
        assert config.stop_sequences == []
        assert config.frequency_penalty == 0.0
        assert config.presence_penalty == 0.0
        assert config.seed is None

    def test_custom_values(self) -> None:
        """Test GenerationConfig with custom values."""
        config = GenerationConfig(
            temperature=0.7,
            max_tokens=4000,
            top_p=0.9,
            stop_sequences=["END", "STOP"],
        )
        assert config.temperature == 0.7
        assert config.max_tokens == 4000
        assert config.top_p == 0.9
        assert config.stop_sequences == ["END", "STOP"]

    def test_temperature_validation_low(self) -> None:
        """Test temperature validation for values below 0."""
        with pytest.raises(ValueError, match="temperature must be between"):
            GenerationConfig(temperature=-0.1)

    def test_temperature_validation_high(self) -> None:
        """Test temperature validation for values above 2."""
        with pytest.raises(ValueError, match="temperature must be between"):
            GenerationConfig(temperature=2.1)

    def test_max_tokens_validation(self) -> None:
        """Test max_tokens validation for non-positive values."""
        with pytest.raises(ValueError, match="max_tokens must be positive"):
            GenerationConfig(max_tokens=0)

        with pytest.raises(ValueError, match="max_tokens must be positive"):
            GenerationConfig(max_tokens=-100)

    def test_top_p_validation(self) -> None:
        """Test top_p validation for out of range values."""
        with pytest.raises(ValueError, match="top_p must be between"):
            GenerationConfig(top_p=-0.1)

        with pytest.raises(ValueError, match="top_p must be between"):
            GenerationConfig(top_p=1.1)

    def test_top_k_validation(self) -> None:
        """Test top_k validation for negative values."""
        with pytest.raises(ValueError, match="top_k must be non-negative"):
            GenerationConfig(top_k=-1)

    def test_frequency_penalty_validation(self) -> None:
        """Test frequency_penalty validation."""
        with pytest.raises(ValueError, match="frequency_penalty must be between"):
            GenerationConfig(frequency_penalty=-0.1)

        with pytest.raises(ValueError, match="frequency_penalty must be between"):
            GenerationConfig(frequency_penalty=2.1)

    def test_presence_penalty_validation(self) -> None:
        """Test presence_penalty validation."""
        with pytest.raises(ValueError, match="presence_penalty must be between"):
            GenerationConfig(presence_penalty=-0.1)

        with pytest.raises(ValueError, match="presence_penalty must be between"):
            GenerationConfig(presence_penalty=2.1)


class TestGenerationResult:
    """Tests for GenerationResult dataclass."""

    def test_result_creation(self) -> None:
        """Test GenerationResult creation."""
        model_info = ModelInfo(model_id="test", provider="test")
        result = GenerationResult(
            content="Hello, world!",
            model_info=model_info,
            usage={"prompt_tokens": 10, "completion_tokens": 5},
            finish_reason="stop",
        )
        assert result.content == "Hello, world!"
        assert result.model_info == model_info
        assert result.usage["prompt_tokens"] == 10
        assert result.finish_reason == "stop"


class TestLLMProviderAbstract:
    """Tests for LLMProvider abstract base class."""

    def test_cannot_instantiate_abstract_class(self) -> None:
        """Test that LLMProvider cannot be instantiated directly."""
        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            LLMProvider()  # type: ignore

    def test_subclass_must_implement_generate(self) -> None:
        """Test that subclass without generate raises TypeError."""

        class IncompleteProvider(LLMProvider):
            def get_model_info(self) -> ModelInfo:
                return ModelInfo(model_id="test", provider="test")

            @property
            def provider_name(self) -> str:
                return "test"

        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            IncompleteProvider()  # type: ignore

    def test_subclass_must_implement_get_model_info(self) -> None:
        """Test that subclass without get_model_info raises TypeError."""

        class IncompleteProvider(LLMProvider):
            async def generate(
                self,
                prompt: str,
                config: GenerationConfig | None = None,
                system_prompt: str | None = None,
            ) -> GenerationResult:
                return GenerationResult(
                    content="test",
                    model_info=ModelInfo(model_id="test", provider="test"),
                )

            @property
            def provider_name(self) -> str:
                return "test"

        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            IncompleteProvider()  # type: ignore

    def test_complete_subclass_can_be_instantiated(self) -> None:
        """Test that complete subclass can be instantiated."""

        class CompleteProvider(LLMProvider):
            async def generate(
                self,
                prompt: str,
                config: GenerationConfig | None = None,
                system_prompt: str | None = None,
            ) -> GenerationResult:
                return GenerationResult(
                    content="test",
                    model_info=ModelInfo(model_id="test", provider="test"),
                )

            def get_model_info(self) -> ModelInfo:
                return ModelInfo(model_id="test", provider="test")

            @property
            def provider_name(self) -> str:
                return "test"

        provider = CompleteProvider()
        assert provider.provider_name == "test"


class TestExceptions:
    """Tests for LLM provider exception classes."""

    def test_llm_provider_error(self) -> None:
        """Test LLMProviderError."""
        error = LLMProviderError("Something went wrong", provider="openrouter")
        assert str(error) == "Something went wrong"
        assert error.provider == "openrouter"

    def test_rate_limit_error(self) -> None:
        """Test RateLimitError with retry_after."""
        error = RateLimitError(
            "Rate limited",
            provider="openrouter",
            retry_after=60.0,
        )
        assert error.retry_after == 60.0
        assert error.provider == "openrouter"

    def test_authentication_error(self) -> None:
        """Test AuthenticationError."""
        error = AuthenticationError("Invalid API key", provider="openrouter")
        assert "Invalid API key" in str(error)
        assert isinstance(error, LLMProviderError)

    def test_model_not_found_error(self) -> None:
        """Test ModelNotFoundError."""
        error = ModelNotFoundError("Model not found", provider="openrouter")
        assert "Model not found" in str(error)
        assert isinstance(error, LLMProviderError)
