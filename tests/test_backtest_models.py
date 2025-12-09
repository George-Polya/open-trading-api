"""
Tests for backtest domain models.

Tests cover:
- Model instantiation with valid data
- Validation errors for invalid data
- JSON serialization/deserialization
- Property-based tests for date ordering
"""

from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from app.models import (
    ContributionFrequency,
    ContributionPlan,
    FeeSettings,
    LLMSettings,
    BacktestParams,
    BacktestRequest,
    ModelInfo,
    GeneratedCode,
    GenerationConfig,
)
from app.models.backtest import AVAILABLE_DATA_START, AVAILABLE_DATA_END
from app.core.config import LLMProvider


# =============================================================================
# ContributionFrequency Enum Tests
# =============================================================================


class TestContributionFrequency:
    """Tests for ContributionFrequency enum."""

    def test_enum_values(self) -> None:
        """Test that enum has expected values."""
        assert ContributionFrequency.MONTHLY.value == "monthly"
        assert ContributionFrequency.QUARTERLY.value == "quarterly"
        assert ContributionFrequency.SEMIANNUAL.value == "semiannual"
        assert ContributionFrequency.ANNUAL.value == "annual"

    def test_enum_serialization(self) -> None:
        """Test that enum serializes to string correctly."""
        plan = ContributionPlan(
            frequency=ContributionFrequency.MONTHLY,
            amount=1000.0,
        )
        data = plan.model_dump()
        assert data["frequency"] == "monthly"

    def test_enum_deserialization(self) -> None:
        """Test that enum deserializes from string correctly."""
        plan = ContributionPlan.model_validate({
            "frequency": "quarterly",
            "amount": 500.0,
        })
        assert plan.frequency == ContributionFrequency.QUARTERLY


# =============================================================================
# ContributionPlan Tests
# =============================================================================


class TestContributionPlan:
    """Tests for ContributionPlan model."""

    def test_default_values(self) -> None:
        """Test default values."""
        plan = ContributionPlan()
        assert plan.frequency == ContributionFrequency.MONTHLY
        assert plan.amount == 0.0

    def test_valid_contribution(self) -> None:
        """Test valid contribution plan."""
        plan = ContributionPlan(
            frequency=ContributionFrequency.MONTHLY,
            amount=1000.0,
        )
        assert plan.frequency == ContributionFrequency.MONTHLY
        assert plan.amount == 1000.0

    def test_zero_amount_allowed(self) -> None:
        """Test that zero amount is allowed (no contribution)."""
        plan = ContributionPlan(amount=0.0)
        assert plan.amount == 0.0

    def test_negative_amount_rejected(self) -> None:
        """Test that negative amount raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            ContributionPlan(amount=-100.0)
        assert "Contribution amount cannot be negative" in str(exc_info.value)


# =============================================================================
# FeeSettings Tests
# =============================================================================


class TestFeeSettings:
    """Tests for FeeSettings model."""

    def test_default_values(self) -> None:
        """Test default values match PRD (0.1% fee, 0.05% slippage)."""
        fees = FeeSettings()
        assert fees.trading_fee_percent == 0.1
        assert fees.slippage_percent == 0.05

    def test_custom_fees(self) -> None:
        """Test custom fee values."""
        fees = FeeSettings(trading_fee_percent=0.2, slippage_percent=0.1)
        assert fees.trading_fee_percent == 0.2
        assert fees.slippage_percent == 0.1

    def test_negative_fee_rejected(self) -> None:
        """Test that negative fees raise ValidationError."""
        with pytest.raises(ValidationError):
            FeeSettings(trading_fee_percent=-0.1)

    def test_excessive_fee_rejected(self) -> None:
        """Test that fees > 10% raise ValidationError."""
        with pytest.raises(ValidationError):
            FeeSettings(trading_fee_percent=15.0)


# =============================================================================
# LLMSettings Tests
# =============================================================================


class TestLLMSettings:
    """Tests for LLMSettings model."""

    def test_default_provider(self) -> None:
        """Test default provider is OpenRouter."""
        settings = LLMSettings()
        assert settings.provider == LLMProvider.OPENROUTER
        assert settings.model is None

    def test_custom_provider(self) -> None:
        """Test custom provider and model."""
        settings = LLMSettings(
            provider=LLMProvider.ANTHROPIC,
            model="claude-3-5-sonnet-20241022",
        )
        assert settings.provider == LLMProvider.ANTHROPIC
        assert settings.model == "claude-3-5-sonnet-20241022"


# =============================================================================
# BacktestParams Tests
# =============================================================================


class TestBacktestParams:
    """Tests for BacktestParams model."""

    @pytest.fixture
    def valid_params(self) -> dict:
        """Return valid params dict for testing."""
        return {
            "start_date": date(2020, 1, 1),
            "end_date": date(2024, 1, 1),
            "initial_capital": 10000.0,
            "benchmarks": ["SPY", "QQQ"],
        }

    def test_minimal_valid_params(self, valid_params: dict) -> None:
        """Test minimal valid params."""
        params = BacktestParams(**valid_params)
        assert params.start_date == date(2020, 1, 1)
        assert params.end_date == date(2024, 1, 1)
        assert params.initial_capital == 10000.0
        assert params.benchmarks == ["SPY", "QQQ"]

    def test_full_params(self, valid_params: dict) -> None:
        """Test params with all options specified."""
        valid_params.update({
            "contribution": ContributionPlan(
                frequency=ContributionFrequency.MONTHLY,
                amount=1000.0,
            ),
            "fees": FeeSettings(trading_fee_percent=0.2),
            "dividend_reinvestment": False,
            "llm_settings": LLMSettings(provider=LLMProvider.ANTHROPIC),
        })
        params = BacktestParams(**valid_params)
        assert params.contribution.amount == 1000.0
        assert params.fees.trading_fee_percent == 0.2
        assert params.dividend_reinvestment is False
        assert params.llm_settings.provider == LLMProvider.ANTHROPIC

    def test_default_values(self, valid_params: dict) -> None:
        """Test default values are set correctly."""
        params = BacktestParams(**valid_params)
        assert params.contribution.frequency == ContributionFrequency.MONTHLY
        assert params.contribution.amount == 0.0
        assert params.fees.trading_fee_percent == 0.1
        assert params.fees.slippage_percent == 0.05
        assert params.dividend_reinvestment is True
        assert params.llm_settings.provider == LLMProvider.OPENROUTER

    # Validation Error Tests

    def test_start_after_end_rejected(self) -> None:
        """Test that start_date > end_date raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            BacktestParams(
                start_date=date(2024, 1, 1),
                end_date=date(2020, 1, 1),
                initial_capital=10000.0,
                benchmarks=["SPY"],
            )
        assert "start_date" in str(exc_info.value)
        assert "must be before or equal to" in str(exc_info.value)

    def test_same_start_end_allowed(self) -> None:
        """Test that start_date == end_date is allowed."""
        params = BacktestParams(
            start_date=date(2020, 1, 1),
            end_date=date(2020, 1, 1),
            initial_capital=10000.0,
            benchmarks=["SPY"],
        )
        assert params.start_date == params.end_date

    def test_negative_capital_rejected(self) -> None:
        """Test that negative capital raises ValidationError."""
        with pytest.raises(ValidationError):
            BacktestParams(
                start_date=date(2020, 1, 1),
                end_date=date(2024, 1, 1),
                initial_capital=-1000.0,
                benchmarks=["SPY"],
            )

    def test_zero_capital_rejected(self) -> None:
        """Test that zero capital raises ValidationError."""
        with pytest.raises(ValidationError):
            BacktestParams(
                start_date=date(2020, 1, 1),
                end_date=date(2024, 1, 1),
                initial_capital=0.0,
                benchmarks=["SPY"],
            )

    def test_empty_benchmarks_rejected(self) -> None:
        """Test that empty benchmarks list raises ValidationError."""
        with pytest.raises(ValidationError):
            BacktestParams(
                start_date=date(2020, 1, 1),
                end_date=date(2024, 1, 1),
                initial_capital=10000.0,
                benchmarks=[],
            )

    def test_date_before_available_range_rejected(self) -> None:
        """Test that date before available range raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            BacktestParams(
                start_date=date(2010, 1, 1),
                end_date=date(2024, 1, 1),
                initial_capital=10000.0,
                benchmarks=["SPY"],
            )
        assert "before available data range" in str(exc_info.value)

    def test_date_after_available_range_rejected(self) -> None:
        """Test that date after available range raises ValidationError."""
        future_date = AVAILABLE_DATA_END + timedelta(days=365)
        with pytest.raises(ValidationError) as exc_info:
            BacktestParams(
                start_date=date(2020, 1, 1),
                end_date=future_date,
                initial_capital=10000.0,
                benchmarks=["SPY"],
            )
        assert "after available data range" in str(exc_info.value)

    def test_benchmarks_normalized_to_uppercase(self) -> None:
        """Test that benchmarks are normalized to uppercase."""
        params = BacktestParams(
            start_date=date(2020, 1, 1),
            end_date=date(2024, 1, 1),
            initial_capital=10000.0,
            benchmarks=["spy", "qqq", "  iwm  "],
        )
        assert params.benchmarks == ["SPY", "QQQ", "IWM"]


# =============================================================================
# BacktestRequest Tests
# =============================================================================


class TestBacktestRequest:
    """Tests for BacktestRequest model."""

    @pytest.fixture
    def valid_request(self) -> dict:
        """Return valid request dict for testing."""
        return {
            "strategy": "Buy QLD when S&P500 drops 20% and sell when RSI > 70",
            "params": {
                "start_date": date(2020, 1, 1),
                "end_date": date(2024, 1, 1),
                "initial_capital": 10000.0,
                "benchmarks": ["SPY"],
            },
        }

    def test_valid_request(self, valid_request: dict) -> None:
        """Test valid request."""
        request = BacktestRequest(**valid_request)
        assert "QLD" in request.strategy
        assert request.params.initial_capital == 10000.0

    def test_empty_strategy_rejected(self, valid_request: dict) -> None:
        """Test that empty strategy raises ValidationError."""
        valid_request["strategy"] = ""
        with pytest.raises(ValidationError):
            BacktestRequest(**valid_request)

    def test_whitespace_strategy_rejected(self, valid_request: dict) -> None:
        """Test that whitespace-only strategy raises ValidationError."""
        valid_request["strategy"] = "   \n\t  "
        with pytest.raises(ValidationError):
            BacktestRequest(**valid_request)

    def test_short_strategy_rejected(self, valid_request: dict) -> None:
        """Test that strategy < 10 chars raises ValidationError."""
        valid_request["strategy"] = "Buy SPY"  # 7 chars
        with pytest.raises(ValidationError):
            BacktestRequest(**valid_request)

    def test_strategy_stripped(self, valid_request: dict) -> None:
        """Test that strategy is stripped of leading/trailing whitespace."""
        valid_request["strategy"] = "  " + valid_request["strategy"] + "  "
        request = BacktestRequest(**valid_request)
        assert not request.strategy.startswith(" ")
        assert not request.strategy.endswith(" ")


# =============================================================================
# ModelInfo Tests
# =============================================================================


class TestModelInfo:
    """Tests for ModelInfo model."""

    def test_valid_model_info(self) -> None:
        """Test valid model info."""
        info = ModelInfo(
            provider="openrouter",
            model_id="anthropic/claude-3.5-sonnet",
            max_tokens=8192,
            supports_system_prompt=True,
            cost_per_1k_input=0.003,
            cost_per_1k_output=0.015,
        )
        assert info.provider == "openrouter"
        assert info.model_id == "anthropic/claude-3.5-sonnet"
        assert info.max_tokens == 8192

    def test_default_values(self) -> None:
        """Test default values."""
        info = ModelInfo(provider="test", model_id="test-model")
        assert info.max_tokens == 4096
        assert info.supports_system_prompt is True
        assert info.cost_per_1k_input == 0.0
        assert info.cost_per_1k_output == 0.0


# =============================================================================
# GenerationConfig Tests
# =============================================================================


class TestGenerationConfig:
    """Tests for GenerationConfig model."""

    def test_default_values(self) -> None:
        """Test default values match PRD."""
        config = GenerationConfig()
        assert config.temperature == 0.2
        assert config.max_tokens == 8000
        assert config.top_p == 0.9
        assert config.stop_sequences is None

    def test_custom_config(self) -> None:
        """Test custom config."""
        config = GenerationConfig(
            temperature=0.5,
            max_tokens=4000,
            top_p=0.8,
            stop_sequences=["```", "\n\n"],
        )
        assert config.temperature == 0.5
        assert config.max_tokens == 4000
        assert config.stop_sequences == ["```", "\n\n"]

    def test_temperature_bounds(self) -> None:
        """Test temperature bounds (0.0-2.0)."""
        with pytest.raises(ValidationError):
            GenerationConfig(temperature=-0.1)
        with pytest.raises(ValidationError):
            GenerationConfig(temperature=2.5)


# =============================================================================
# GeneratedCode Tests
# =============================================================================


class TestGeneratedCode:
    """Tests for GeneratedCode model."""

    def test_valid_generated_code(self) -> None:
        """Test valid generated code."""
        code = GeneratedCode(
            code="def backtest(): pass",
            strategy_summary="Simple buy and hold strategy",
            model_info=ModelInfo(provider="test", model_id="test-model"),
        )
        assert "backtest" in code.code
        assert "buy and hold" in code.strategy_summary

    def test_empty_code_rejected(self) -> None:
        """Test that empty code raises ValidationError."""
        with pytest.raises(ValidationError):
            GeneratedCode(
                code="",
                strategy_summary="Summary",
                model_info=ModelInfo(provider="test", model_id="test-model"),
            )


# =============================================================================
# Serialization Tests
# =============================================================================


class TestSerialization:
    """Tests for model serialization/deserialization."""

    def test_backtest_params_json_roundtrip(self) -> None:
        """Test BacktestParams JSON serialization roundtrip."""
        params = BacktestParams(
            start_date=date(2020, 1, 1),
            end_date=date(2024, 1, 1),
            initial_capital=10000.0,
            benchmarks=["SPY", "QQQ"],
            contribution=ContributionPlan(
                frequency=ContributionFrequency.MONTHLY,
                amount=1000.0,
            ),
        )

        # Serialize to JSON
        json_str = params.model_dump_json()

        # Deserialize back
        restored = BacktestParams.model_validate_json(json_str)

        assert restored.start_date == params.start_date
        assert restored.end_date == params.end_date
        assert restored.initial_capital == params.initial_capital
        assert restored.benchmarks == params.benchmarks
        assert restored.contribution.frequency == params.contribution.frequency
        assert restored.contribution.amount == params.contribution.amount

    def test_backtest_request_json_structure(self) -> None:
        """Test BacktestRequest JSON structure matches expected API contract."""
        request = BacktestRequest(
            strategy="Test strategy with sufficient length",
            params=BacktestParams(
                start_date=date(2020, 1, 1),
                end_date=date(2024, 1, 1),
                initial_capital=10000.0,
                benchmarks=["SPY"],
            ),
        )

        data = request.model_dump()

        # Verify structure
        assert "strategy" in data
        assert "params" in data
        assert "start_date" in data["params"]
        assert "end_date" in data["params"]
        assert "initial_capital" in data["params"]
        assert "benchmarks" in data["params"]
        assert "contribution" in data["params"]
        assert "fees" in data["params"]

    def test_generated_code_json_structure(self) -> None:
        """Test GeneratedCode JSON structure matches PRD contract."""
        code = GeneratedCode(
            code="def backtest(): pass",
            strategy_summary="Test summary",
            model_info=ModelInfo(
                provider="openrouter",
                model_id="anthropic/claude-3.5-sonnet",
                max_tokens=8192,
                supports_system_prompt=True,
                cost_per_1k_input=0.003,
                cost_per_1k_output=0.015,
            ),
        )

        data = code.model_dump()

        # Verify structure matches PRD section 2.2.1
        assert "code" in data
        assert "strategy_summary" in data
        assert "model_info" in data
        assert "provider" in data["model_info"]
        assert "model_id" in data["model_info"]
        assert "max_tokens" in data["model_info"]
        assert "supports_system_prompt" in data["model_info"]
        assert "cost_per_1k_input" in data["model_info"]
        assert "cost_per_1k_output" in data["model_info"]


# =============================================================================
# Property-Based Tests (using standard pytest parametrize)
# =============================================================================


class TestDateOrderingProperty:
    """Property-based tests for date ordering validation."""

    @pytest.mark.parametrize(
        "start_offset,end_offset",
        [
            (0, 0),     # Same day
            (0, 1),     # One day apart
            (0, 30),    # One month apart
            (0, 365),   # One year apart
            (0, 1000),  # Multiple years apart
        ],
    )
    def test_valid_date_ranges(self, start_offset: int, end_offset: int) -> None:
        """Test various valid date ranges."""
        base_date = date(2020, 1, 1)
        start_date = base_date + timedelta(days=start_offset)
        end_date = base_date + timedelta(days=end_offset)

        # Should not raise
        params = BacktestParams(
            start_date=start_date,
            end_date=end_date,
            initial_capital=10000.0,
            benchmarks=["SPY"],
        )
        assert params.start_date <= params.end_date

    @pytest.mark.parametrize(
        "days_before_end",
        [1, 7, 30, 365],
    )
    def test_invalid_date_ranges(self, days_before_end: int) -> None:
        """Test that end_date before start_date is rejected."""
        base_date = date(2020, 6, 15)
        start_date = base_date
        end_date = base_date - timedelta(days=days_before_end)

        with pytest.raises(ValidationError) as exc_info:
            BacktestParams(
                start_date=start_date,
                end_date=end_date,
                initial_capital=10000.0,
                benchmarks=["SPY"],
            )
        assert "must be before or equal to" in str(exc_info.value)
