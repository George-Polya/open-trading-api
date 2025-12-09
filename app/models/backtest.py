"""
Backtest domain models and request validation.

Defines Pydantic models for backtest parameters, requests, and responses
following PRD section 3.1 specifications.
"""

from datetime import date
from enum import Enum
from typing import Optional

from pydantic import (
    BaseModel,
    Field,
    PositiveFloat,
    field_validator,
    model_validator,
    ConfigDict,
)

from app.core.config import LLMProvider


# =============================================================================
# Constants
# =============================================================================

# Default available data range for backtesting
# KIS API typically provides data from 2015 onwards for overseas stocks
AVAILABLE_DATA_START = date(2015, 1, 1)
AVAILABLE_DATA_END = date.today()


# =============================================================================
# Enums
# =============================================================================


class ContributionFrequency(str, Enum):
    """
    Contribution (dollar-cost averaging) frequency options.

    Defines how often periodic contributions are made to the portfolio.
    """

    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    SEMIANNUAL = "semiannual"
    ANNUAL = "annual"


# =============================================================================
# Sub-models
# =============================================================================


class ContributionPlan(BaseModel):
    """
    Periodic contribution (dollar-cost averaging) settings.

    Attributes:
        frequency: How often to make contributions.
        amount: Amount to contribute each period (must be positive).
    """

    model_config = ConfigDict(frozen=True)

    frequency: ContributionFrequency = Field(
        default=ContributionFrequency.MONTHLY,
        description="Contribution frequency (monthly, quarterly, etc.)",
    )
    amount: float = Field(
        default=0.0,
        ge=0.0,
        description="Amount to contribute each period (0 means no contribution)",
    )

    @field_validator("amount", mode="before")
    @classmethod
    def validate_amount(cls, v: float) -> float:
        """Validate that amount is not negative."""
        if v < 0:
            raise ValueError("Contribution amount cannot be negative")
        return v


class FeeSettings(BaseModel):
    """
    Trading fee and slippage settings.

    Attributes:
        trading_fee_percent: Trading commission as percentage (e.g., 0.1 for 0.1%).
        slippage_percent: Expected slippage as percentage (e.g., 0.05 for 0.05%).
    """

    model_config = ConfigDict(frozen=True)

    trading_fee_percent: float = Field(
        default=0.1,
        ge=0.0,
        le=10.0,
        description="Trading fee as percentage (default: 0.1%)",
    )
    slippage_percent: float = Field(
        default=0.05,
        ge=0.0,
        le=10.0,
        description="Slippage as percentage (default: 0.05%)",
    )


class LLMSettings(BaseModel):
    """
    LLM provider and model selection for code generation.

    Reuses LLMProvider enum from core config for consistency.

    Attributes:
        provider: LLM provider (openrouter, anthropic, openai).
        model: Model identifier (provider-specific).
    """

    model_config = ConfigDict(frozen=True)

    provider: LLMProvider = Field(
        default=LLMProvider.OPENROUTER,
        description="LLM provider to use for code generation",
    )
    model: Optional[str] = Field(
        default=None,
        description="Model identifier (uses provider default if not specified)",
    )


# =============================================================================
# Main Models
# =============================================================================


class BacktestParams(BaseModel):
    """
    Backtest configuration parameters.

    Contains all settings needed to run a backtest including:
    - Time period (start/end dates)
    - Capital settings (initial capital, contributions)
    - Fee settings
    - Benchmark tickers for comparison
    - LLM settings for code generation

    Attributes:
        start_date: Backtest start date.
        end_date: Backtest end date.
        initial_capital: Starting capital amount.
        contribution: Periodic contribution settings.
        fees: Trading fee and slippage settings.
        dividend_reinvestment: Whether to reinvest dividends.
        benchmarks: List of benchmark tickers for comparison.
        llm_settings: LLM provider and model settings.
    """

    model_config = ConfigDict(frozen=False, validate_assignment=True)

    start_date: date = Field(
        ...,
        description="Backtest start date",
    )
    end_date: date = Field(
        ...,
        description="Backtest end date",
    )
    initial_capital: PositiveFloat = Field(
        ...,
        description="Initial capital amount (must be positive)",
    )
    contribution: ContributionPlan = Field(
        default_factory=ContributionPlan,
        description="Periodic contribution settings",
    )
    fees: FeeSettings = Field(
        default_factory=FeeSettings,
        description="Trading fee and slippage settings",
    )
    dividend_reinvestment: bool = Field(
        default=True,
        description="Whether to reinvest dividends",
    )
    benchmarks: list[str] = Field(
        ...,
        min_length=1,
        description="Benchmark tickers for comparison (at least 1 required)",
    )
    llm_settings: LLMSettings = Field(
        default_factory=LLMSettings,
        description="LLM provider and model settings",
    )

    @field_validator("benchmarks", mode="before")
    @classmethod
    def validate_benchmarks(cls, v: list[str]) -> list[str]:
        """Ensure benchmarks list is not empty and contains valid tickers."""
        if not v:
            raise ValueError("At least one benchmark ticker is required")
        # Convert to uppercase for consistency
        return [ticker.upper().strip() for ticker in v if ticker.strip()]

    @model_validator(mode="after")
    def validate_date_range(self) -> "BacktestParams":
        """
        Validate that:
        1. start_date <= end_date
        2. Date range is within available data range
        """
        if self.start_date > self.end_date:
            raise ValueError(
                f"start_date ({self.start_date}) must be before or equal to "
                f"end_date ({self.end_date})"
            )

        if self.start_date < AVAILABLE_DATA_START:
            raise ValueError(
                f"start_date ({self.start_date}) is before available data range "
                f"(starts from {AVAILABLE_DATA_START})"
            )

        if self.end_date > AVAILABLE_DATA_END:
            raise ValueError(
                f"end_date ({self.end_date}) is after available data range "
                f"(ends at {AVAILABLE_DATA_END})"
            )

        return self


# =============================================================================
# Request/Response DTOs
# =============================================================================


class BacktestRequest(BaseModel):
    """
    Backtest API request model.

    Combines natural language strategy description with backtest parameters.

    Attributes:
        strategy: Natural language description of the investment strategy.
        params: Backtest configuration parameters.
    """

    model_config = ConfigDict(frozen=False)

    strategy: str = Field(
        ...,
        min_length=10,
        max_length=10000,
        description="Natural language description of the investment strategy",
    )
    params: BacktestParams = Field(
        ...,
        description="Backtest configuration parameters",
    )

    @field_validator("strategy", mode="before")
    @classmethod
    def validate_strategy(cls, v: str) -> str:
        """Ensure strategy text is not empty or whitespace only."""
        stripped = v.strip()
        if not stripped:
            raise ValueError("Strategy description cannot be empty")
        return stripped


class ModelInfo(BaseModel):
    """
    LLM model metadata.

    Contains information about the LLM model used for code generation.

    Attributes:
        provider: LLM provider name (e.g., "openrouter", "anthropic").
        model_id: Model identifier (e.g., "anthropic/claude-3.5-sonnet").
        max_tokens: Maximum tokens the model can generate.
        supports_system_prompt: Whether the model supports system prompts.
        cost_per_1k_input: Cost per 1000 input tokens (USD).
        cost_per_1k_output: Cost per 1000 output tokens (USD).
    """

    model_config = ConfigDict(frozen=True)

    provider: str = Field(
        ...,
        description="LLM provider name",
    )
    model_id: str = Field(
        ...,
        description="Model identifier",
    )
    max_tokens: int = Field(
        default=4096,
        gt=0,
        description="Maximum tokens the model can generate",
    )
    supports_system_prompt: bool = Field(
        default=True,
        description="Whether the model supports system prompts",
    )
    cost_per_1k_input: float = Field(
        default=0.0,
        ge=0.0,
        description="Cost per 1000 input tokens (USD)",
    )
    cost_per_1k_output: float = Field(
        default=0.0,
        ge=0.0,
        description="Cost per 1000 output tokens (USD)",
    )


class GenerationConfig(BaseModel):
    """
    Code generation configuration.

    Settings for LLM text generation.

    Attributes:
        temperature: Sampling temperature (0.0-2.0).
        max_tokens: Maximum tokens to generate.
        top_p: Top-p sampling parameter.
        stop_sequences: Sequences that stop generation.
    """

    model_config = ConfigDict(frozen=True)

    temperature: float = Field(
        default=0.2,
        ge=0.0,
        le=2.0,
        description="Sampling temperature",
    )
    max_tokens: int = Field(
        default=8000,
        gt=0,
        description="Maximum tokens to generate",
    )
    top_p: float = Field(
        default=0.9,
        ge=0.0,
        le=1.0,
        description="Top-p sampling parameter",
    )
    stop_sequences: Optional[list[str]] = Field(
        default=None,
        description="Sequences that stop generation",
    )


class GeneratedCode(BaseModel):
    """
    Generated backtest code response.

    Contains the generated Python code and metadata.

    Attributes:
        code: Generated Python backtest code.
        strategy_summary: AI-generated summary of the interpreted strategy.
        model_info: Information about the LLM model used.
        tickers: List of ticker symbols extracted from the strategy.
    """

    model_config = ConfigDict(frozen=False)

    code: str = Field(
        ...,
        min_length=1,
        description="Generated Python backtest code",
    )
    strategy_summary: str = Field(
        ...,
        description="AI-generated summary of the interpreted strategy",
    )
    model_info: ModelInfo = Field(
        ...,
        description="Information about the LLM model used for generation",
    )
    tickers: list[str] = Field(
        default_factory=list,
        description="List of ticker symbols extracted from the strategy",
    )
