"""
Tests for BacktestCodeGenerator service.

Covers:
- Ticker extraction from text
- Code extraction from LLM responses
- Summary extraction from LLM responses
- Data availability checking
- Prompt building
- Full generation workflow
- Validation integration
"""

import pytest
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.backtest import (
    BacktestParams,
    BacktestRequest,
    ContributionFrequency,
    ContributionPlan,
    FeeSettings,
    GeneratedCode,
    LLMSettings,
)
from app.providers.data.base import DateRange, DataProvider
from app.providers.llm.base import (
    GenerationConfig,
    GenerationResult,
    LLMProvider,
    ModelInfo,
)
from app.services.code_generator import (
    BacktestCodeGenerator,
    CodeGenerationError,
    DataAvailabilityError,
    DefaultValidator,
    PromptBuildError,
    ValidationError,
    ValidationResult,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_llm_provider() -> MagicMock:
    """Create a mock LLM provider."""
    mock = MagicMock(spec=LLMProvider)
    mock.provider_name = "test_provider"
    mock.get_model_info.return_value = ModelInfo(
        model_id="test/model-v1",
        provider="test_provider",
        display_name="Test Model",
        max_context_tokens=128000,
        max_output_tokens=8000,
        cost_per_1k_input=Decimal("0.01"),
        cost_per_1k_output=Decimal("0.03"),
    )
    return mock


@pytest.fixture
def mock_data_provider() -> MagicMock:
    """Create a mock data provider."""
    mock = MagicMock(spec=DataProvider)
    mock.provider_name = "test_data_provider"
    return mock


@pytest.fixture
def sample_backtest_params() -> BacktestParams:
    """Create sample backtest parameters."""
    return BacktestParams(
        start_date=date(2020, 1, 1),
        end_date=date(2023, 12, 31),
        initial_capital=100000.0,
        contribution=ContributionPlan(
            frequency=ContributionFrequency.MONTHLY,
            amount=1000.0,
        ),
        fees=FeeSettings(
            trading_fee_percent=0.1,
            slippage_percent=0.05,
        ),
        dividend_reinvestment=True,
        benchmarks=["SPY"],
    )


@pytest.fixture
def sample_backtest_request(sample_backtest_params: BacktestParams) -> BacktestRequest:
    """Create sample backtest request."""
    return BacktestRequest(
        strategy="Buy AAPL and TSLA when their RSI drops below 30, sell when RSI exceeds 70.",
        params=sample_backtest_params,
    )


@pytest.fixture
def sample_llm_response() -> str:
    """Create sample LLM response with code and summary."""
    return """### SUMMARY
This strategy implements a mean-reversion approach using RSI indicators for AAPL and TSLA.
It buys when oversold (RSI < 30) and sells when overbought (RSI > 70).

### CODE
```python
from backtesting import Backtest, Strategy
from backtesting.lib import crossover
import pandas as pd
import ta

class RSIMeanReversionStrategy(Strategy):
    \"\"\"RSI-based mean reversion strategy for AAPL and TSLA.\"\"\"

    rsi_low = 30
    rsi_high = 70
    rsi_period = 14

    def init(self):
        close = self.data.Close
        self.rsi = self.I(
            lambda x: ta.momentum.RSIIndicator(pd.Series(x), window=self.rsi_period).rsi(),
            close
        )

    def next(self):
        if self.rsi[-1] < self.rsi_low and not self.position:
            self.buy()
        elif self.rsi[-1] > self.rsi_high and self.position:
            self.position.close()


def load_data(tickers: list[str], start_date: str, end_date: str) -> dict[str, pd.DataFrame]:
    pass


# Backtest execution
bt = Backtest(
    data,
    RSIMeanReversionStrategy,
    cash=100000,
    commission=0.001,
    exclusive_orders=True
)
results = bt.run()
```
"""


@pytest.fixture
def code_generator(
    mock_llm_provider: MagicMock,
    mock_data_provider: MagicMock,
    tmp_path: Path,
) -> BacktestCodeGenerator:
    """Create a BacktestCodeGenerator instance with mocks."""
    # Create a temporary prompt template
    prompt_path = tmp_path / "backtest_system.txt"
    prompt_path.write_text("""Test prompt template.
Strategy: {strategy_description}
Start: {start_date}
End: {end_date}
Capital: {initial_capital}
Benchmarks: {benchmarks}
Contribution: {contribution_frequency} - {contribution_amount}
Trading Fee: {trading_fee_percent}%
Trading Fee Decimal: {trading_fee_decimal}
Slippage: {slippage_percent}%
Dividend Reinvestment: {dividend_reinvestment}
Available Tickers: {available_tickers}
Data Range: {data_start_date} to {data_end_date}
""")

    return BacktestCodeGenerator(
        llm_provider=mock_llm_provider,
        data_provider=mock_data_provider,
        prompt_template_path=prompt_path,
    )


# =============================================================================
# Tests for _extract_tickers (Task 7.2)
# =============================================================================


class TestExtractTickers:
    """Tests for ticker extraction from text."""

    def test_extract_single_ticker(self, code_generator: BacktestCodeGenerator) -> None:
        """Test extracting a single ticker."""
        text = "I want to buy AAPL stock."
        tickers = code_generator._extract_tickers(text)
        assert "AAPL" in tickers

    def test_extract_multiple_tickers(self, code_generator: BacktestCodeGenerator) -> None:
        """Test extracting multiple tickers."""
        text = "Buy AAPL and TSLA when the market dips, also consider GOOGL."
        tickers = code_generator._extract_tickers(text)
        assert "AAPL" in tickers
        assert "TSLA" in tickers
        assert "GOOGL" in tickers

    def test_ignore_common_words(self, code_generator: BacktestCodeGenerator) -> None:
        """Test that common words are not extracted as tickers."""
        text = "I want to BUY and SELL stocks in the US market."
        tickers = code_generator._extract_tickers(text)
        assert "BUY" not in tickers
        assert "SELL" not in tickers
        assert "US" not in tickers

    def test_extract_korean_ticker(self, code_generator: BacktestCodeGenerator) -> None:
        """Test extracting Korean stock codes (6 digits)."""
        text = "Samsung Electronics 005930 and SK Hynix 000660."
        tickers = code_generator._extract_tickers(text)
        assert "005930" in tickers
        assert "000660" in tickers

    def test_extract_with_benchmarks(self, code_generator: BacktestCodeGenerator) -> None:
        """Test extracting tickers with benchmarks provided."""
        text = "Buy tech stocks."
        benchmarks = ["SPY", "QQQ"]
        tickers = code_generator._extract_tickers(text, benchmarks)
        assert "SPY" in tickers
        assert "QQQ" in tickers

    def test_deduplicate_tickers(self, code_generator: BacktestCodeGenerator) -> None:
        """Test that duplicate tickers are removed."""
        text = "Buy AAPL, then buy more AAPL when it dips."
        tickers = code_generator._extract_tickers(text)
        assert tickers.count("AAPL") == 1

    def test_sort_tickers(self, code_generator: BacktestCodeGenerator) -> None:
        """Test that tickers are sorted alphabetically."""
        text = "Consider TSLA, AAPL, and META."
        tickers = code_generator._extract_tickers(text)
        assert tickers == sorted(tickers)

    def test_single_letter_not_extracted(self, code_generator: BacktestCodeGenerator) -> None:
        """Test that single letters are not extracted as tickers."""
        text = "Buy stock A in market B."
        tickers = code_generator._extract_tickers(text)
        assert "A" not in tickers
        assert "B" not in tickers


# =============================================================================
# Tests for _extract_code (Task 7.2)
# =============================================================================


class TestExtractCode:
    """Tests for code extraction from LLM responses."""

    def test_extract_python_code_block(
        self, code_generator: BacktestCodeGenerator, sample_llm_response: str
    ) -> None:
        """Test extracting code from markdown python block."""
        code = code_generator._extract_code(sample_llm_response)
        assert "class RSIMeanReversionStrategy" in code
        assert "def init(self)" in code
        assert "def next(self)" in code

    def test_extract_code_without_language_tag(
        self, code_generator: BacktestCodeGenerator
    ) -> None:
        """Test extracting code from block without python tag."""
        response = """Here's the code:
```
print('hello world')
```
"""
        code = code_generator._extract_code(response)
        assert "print('hello world')" in code

    def test_extract_multiple_code_blocks(
        self, code_generator: BacktestCodeGenerator
    ) -> None:
        """Test extracting multiple code blocks."""
        response = """First block:
```python
import pandas as pd
```

Second block:
```python
class Strategy:
    pass
```
"""
        code = code_generator._extract_code(response)
        assert "import pandas as pd" in code
        assert "class Strategy" in code

    def test_extract_code_no_block_raises_error(
        self, code_generator: BacktestCodeGenerator
    ) -> None:
        """Test that missing code block raises error."""
        response = "Here is some text without any code."
        with pytest.raises(CodeGenerationError, match="No code block found"):
            code_generator._extract_code(response)

    def test_extract_code_fallback_detection(
        self, code_generator: BacktestCodeGenerator
    ) -> None:
        """Test fallback detection for code without proper fencing."""
        response = """Here's the strategy:
import pandas as pd
from backtesting import Strategy

class MyStrategy(Strategy):
    def next(self):
        pass
"""
        code = code_generator._extract_code(response)
        assert "import pandas" in code


# =============================================================================
# Tests for _unescape_json_string
# =============================================================================


class TestUnescapeJsonString:
    """Tests for JSON string unescaping."""

    def test_unescape_newline(
        self, code_generator: BacktestCodeGenerator
    ) -> None:
        """Test unescaping \\n to actual newline."""
        result = code_generator._unescape_json_string("line1\\nline2")
        assert result == "line1\nline2"

    def test_unescape_tab(
        self, code_generator: BacktestCodeGenerator
    ) -> None:
        """Test unescaping \\t to actual tab."""
        result = code_generator._unescape_json_string("col1\\tcol2")
        assert result == "col1\tcol2"

    def test_unescape_quote(
        self, code_generator: BacktestCodeGenerator
    ) -> None:
        """Test unescaping \\\" to actual quote."""
        result = code_generator._unescape_json_string('say \\"hello\\"')
        assert result == 'say "hello"'

    def test_unescape_backslash(
        self, code_generator: BacktestCodeGenerator
    ) -> None:
        """Test unescaping \\\\ to single backslash."""
        result = code_generator._unescape_json_string("path\\\\to\\\\file")
        assert result == "path\\to\\file"

    def test_unescape_double_escaped_newline(
        self, code_generator: BacktestCodeGenerator
    ) -> None:
        """Test that double-escaped newlines are fully unescaped."""
        # \\\\n (double-escaped) should become real newline
        # This handles LLMs that output double-escaped content
        result = code_generator._unescape_json_string("line1\\\\nline2")
        assert result == "line1\nline2"
        assert "\n" in result

    def test_unescape_triple_escaped_newline(
        self, code_generator: BacktestCodeGenerator
    ) -> None:
        """Test that triple-escaped newlines are fully unescaped."""
        # \\\\\\\\n (triple-escaped) should become real newline
        result = code_generator._unescape_json_string("line1\\\\\\\\nline2")
        assert result == "line1\nline2"
        assert "\n" in result

    def test_unescape_mixed_escapes(
        self, code_generator: BacktestCodeGenerator
    ) -> None:
        """Test that different escape levels in the same string work."""
        # Single-escaped and double-escaped mixed
        result = code_generator._unescape_json_string("a\\nb\\\\nc")
        assert result == "a\nb\nc"
        assert result.count("\n") == 2

    def test_unescape_docstring(
        self, code_generator: BacktestCodeGenerator
    ) -> None:
        """Test unescaping triple quotes for Python docstrings."""
        result = code_generator._unescape_json_string('\\"\\"\\"\ndocstring\\n\\"\\"\\"')
        assert result == '"""\ndocstring\n"""'

    def test_unescape_unicode(
        self, code_generator: BacktestCodeGenerator
    ) -> None:
        """Test unescaping unicode escape sequences."""
        result = code_generator._unescape_json_string("Korean: \\uD55C\\uAE00")
        assert result == "Korean: 한글"

    def test_unescape_preserves_plain_text(
        self, code_generator: BacktestCodeGenerator
    ) -> None:
        """Test that plain text without escapes is preserved."""
        result = code_generator._unescape_json_string("Hello, World!")
        assert result == "Hello, World!"


# =============================================================================
# Tests for _extract_summary (Task 7.2)
# =============================================================================


class TestExtractSummary:
    """Tests for summary extraction from LLM responses."""

    def test_extract_summary_section(
        self, code_generator: BacktestCodeGenerator, sample_llm_response: str
    ) -> None:
        """Test extracting summary from SUMMARY section."""
        summary = code_generator._extract_summary(sample_llm_response)
        assert "RSI" in summary
        assert "mean-reversion" in summary

    def test_extract_summary_fallback(
        self, code_generator: BacktestCodeGenerator
    ) -> None:
        """Test fallback summary extraction when no section found."""
        response = """This strategy uses momentum indicators to trade.

```python
class Strategy:
    pass
```
"""
        summary = code_generator._extract_summary(response)
        assert "momentum" in summary.lower() or "strategy" in summary.lower()

    def test_extract_summary_default_message(
        self, code_generator: BacktestCodeGenerator
    ) -> None:
        """Test default message when no summary found."""
        response = """```python
class Strategy:
    pass
```"""
        summary = code_generator._extract_summary(response)
        assert len(summary) > 0  # Should return default message


# =============================================================================
# Tests for DefaultValidator
# =============================================================================


class TestDefaultValidator:
    """Tests for the default code validator."""

    @pytest.fixture
    def validator(self) -> DefaultValidator:
        """Create a validator instance."""
        return DefaultValidator()

    def test_valid_code(self, validator: DefaultValidator) -> None:
        """Test that valid code passes validation."""
        code = """
from backtesting import Strategy

class MyStrategy(Strategy):
    def init(self):
        pass

    def next(self):
        pass
"""
        result = validator.validate(code)
        assert result.is_valid
        assert len(result.errors) == 0

    def test_forbidden_exec(self, validator: DefaultValidator) -> None:
        """Test that exec() is forbidden."""
        code = "exec('print(1)')"
        result = validator.validate(code)
        assert not result.is_valid
        assert any("exec()" in e for e in result.errors)

    def test_forbidden_eval(self, validator: DefaultValidator) -> None:
        """Test that eval() is forbidden."""
        code = "result = eval('1+1')"
        result = validator.validate(code)
        assert not result.is_valid
        assert any("eval()" in e for e in result.errors)

    def test_forbidden_os_system(self, validator: DefaultValidator) -> None:
        """Test that os.system() is forbidden."""
        code = "import os\nos.system('rm -rf /')"
        result = validator.validate(code)
        assert not result.is_valid
        assert any("os.system()" in e for e in result.errors)

    def test_forbidden_subprocess(self, validator: DefaultValidator) -> None:
        """Test that subprocess module is forbidden."""
        code = "import subprocess\nsubprocess.run(['ls'])"
        result = validator.validate(code)
        assert not result.is_valid
        assert any("subprocess" in e for e in result.errors)

    def test_syntax_error(self, validator: DefaultValidator) -> None:
        """Test that syntax errors are caught."""
        code = "def broken(:\n    pass"
        result = validator.validate(code)
        assert not result.is_valid
        assert any("Syntax error" in e for e in result.errors)

    def test_missing_strategy_warning(self, validator: DefaultValidator) -> None:
        """Test warning for missing Strategy class."""
        code = """
def calculate():
    return 42
"""
        result = validator.validate(code)
        assert any("Strategy class" in w for w in result.warnings)


# =============================================================================
# Tests for _check_data_availability (Task 7.3)
# =============================================================================


class TestCheckDataAvailability:
    """Tests for data availability checking."""

    @pytest.mark.asyncio
    async def test_check_availability_success(
        self,
        code_generator: BacktestCodeGenerator,
        mock_data_provider: MagicMock,
    ) -> None:
        """Test successful data availability check."""
        mock_data_provider.get_available_date_range = AsyncMock(
            return_value=DateRange(
                start_date=date(2015, 1, 1),
                end_date=date(2024, 1, 1),
                ticker="AAPL",
            )
        )

        result = await code_generator._check_data_availability(
            ["AAPL"],
            date(2020, 1, 1),
            date(2023, 12, 31),
        )

        assert "AAPL" in result
        assert result["AAPL"].start_date == date(2015, 1, 1)

    @pytest.mark.asyncio
    async def test_check_availability_partial(
        self,
        code_generator: BacktestCodeGenerator,
        mock_data_provider: MagicMock,
    ) -> None:
        """Test partial data availability (some tickers unavailable)."""

        async def mock_get_range(ticker: str, exchange=None) -> DateRange:
            if ticker == "AAPL":
                return DateRange(
                    start_date=date(2015, 1, 1),
                    end_date=date(2024, 1, 1),
                    ticker=ticker,
                )
            raise Exception(f"Ticker {ticker} not found")

        mock_data_provider.get_available_date_range = AsyncMock(
            side_effect=mock_get_range
        )

        result = await code_generator._check_data_availability(
            ["AAPL", "INVALID"],
            date(2020, 1, 1),
            date(2023, 12, 31),
        )

        assert "AAPL" in result
        assert "INVALID" not in result

    @pytest.mark.asyncio
    async def test_check_availability_none_available(
        self,
        code_generator: BacktestCodeGenerator,
        mock_data_provider: MagicMock,
    ) -> None:
        """Test error when no tickers have available data."""
        mock_data_provider.get_available_date_range = AsyncMock(
            side_effect=Exception("Not found")
        )

        with pytest.raises(DataAvailabilityError, match="No data available"):
            await code_generator._check_data_availability(
                ["INVALID1", "INVALID2"],
                date(2020, 1, 1),
                date(2023, 12, 31),
            )


# =============================================================================
# Tests for _build_prompt (Task 7.3)
# =============================================================================


class TestBuildPrompt:
    """Tests for prompt building."""

    def test_build_prompt_contains_strategy(
        self,
        code_generator: BacktestCodeGenerator,
        sample_backtest_params: BacktestParams,
    ) -> None:
        """Test that prompt contains strategy description."""
        data_ranges = {
            "AAPL": DateRange(
                start_date=date(2015, 1, 1),
                end_date=date(2024, 1, 1),
                ticker="AAPL",
            )
        }

        prompt = code_generator._build_prompt(
            "Buy AAPL when price drops",
            sample_backtest_params,
            ["AAPL"],
            data_ranges,
        )

        assert "Buy AAPL when price drops" in prompt

    def test_build_prompt_contains_dates(
        self,
        code_generator: BacktestCodeGenerator,
        sample_backtest_params: BacktestParams,
    ) -> None:
        """Test that prompt contains date bounds."""
        data_ranges = {
            "AAPL": DateRange(
                start_date=date(2015, 1, 1),
                end_date=date(2024, 1, 1),
                ticker="AAPL",
            )
        }

        prompt = code_generator._build_prompt(
            "Test strategy",
            sample_backtest_params,
            ["AAPL"],
            data_ranges,
        )

        assert "2020-01-01" in prompt
        assert "2023-12-31" in prompt

    def test_build_prompt_contains_parameters(
        self,
        code_generator: BacktestCodeGenerator,
        sample_backtest_params: BacktestParams,
    ) -> None:
        """Test that prompt contains all parameters."""
        data_ranges = {
            "AAPL": DateRange(
                start_date=date(2015, 1, 1),
                end_date=date(2024, 1, 1),
                ticker="AAPL",
            )
        }

        prompt = code_generator._build_prompt(
            "Test strategy",
            sample_backtest_params,
            ["AAPL"],
            data_ranges,
        )

        assert "100000" in prompt  # Initial capital
        assert "SPY" in prompt  # Benchmark
        assert "monthly" in prompt  # Contribution frequency
        assert "0.1%" in prompt  # Trading fee


# =============================================================================
# Tests for generate (Task 7.4)
# =============================================================================


class TestGenerate:
    """Tests for the main generate method."""

    @pytest.mark.asyncio
    async def test_generate_success(
        self,
        code_generator: BacktestCodeGenerator,
        mock_llm_provider: MagicMock,
        mock_data_provider: MagicMock,
        sample_backtest_request: BacktestRequest,
        sample_llm_response: str,
    ) -> None:
        """Test successful code generation."""
        # Setup mocks
        mock_llm_provider.generate = AsyncMock(
            return_value=GenerationResult(
                content=sample_llm_response,
                model_info=mock_llm_provider.get_model_info(),
            )
        )
        mock_data_provider.get_available_date_range = AsyncMock(
            return_value=DateRange(
                start_date=date(2015, 1, 1),
                end_date=date(2024, 1, 1),
                ticker="AAPL",
            )
        )

        result = await code_generator.generate(sample_backtest_request)

        assert isinstance(result, GeneratedCode)
        assert "RSIMeanReversionStrategy" in result.code
        assert result.strategy_summary
        assert result.model_info.provider == "test_provider"

    @pytest.mark.asyncio
    async def test_generate_calls_validator(
        self,
        code_generator: BacktestCodeGenerator,
        mock_llm_provider: MagicMock,
        mock_data_provider: MagicMock,
        sample_backtest_request: BacktestRequest,
        sample_llm_response: str,
    ) -> None:
        """Test that generate calls the validator."""
        mock_validator = MagicMock()
        mock_validator.validate.return_value = ValidationResult(
            is_valid=True, errors=[], warnings=[]
        )
        code_generator.validator = mock_validator

        mock_llm_provider.generate = AsyncMock(
            return_value=GenerationResult(
                content=sample_llm_response,
                model_info=mock_llm_provider.get_model_info(),
            )
        )
        mock_data_provider.get_available_date_range = AsyncMock(
            return_value=DateRange(
                start_date=date(2015, 1, 1),
                end_date=date(2024, 1, 1),
                ticker="AAPL",
            )
        )

        await code_generator.generate(sample_backtest_request)

        mock_validator.validate.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_validation_failure(
        self,
        code_generator: BacktestCodeGenerator,
        mock_llm_provider: MagicMock,
        mock_data_provider: MagicMock,
        sample_backtest_request: BacktestRequest,
    ) -> None:
        """Test that validation failure raises ValidationError."""
        # Generate response with dangerous code
        dangerous_response = """### SUMMARY
Test strategy.

### CODE
```python
import os
os.system('rm -rf /')

class BadStrategy(Strategy):
    def next(self):
        pass
```
"""
        mock_llm_provider.generate = AsyncMock(
            return_value=GenerationResult(
                content=dangerous_response,
                model_info=mock_llm_provider.get_model_info(),
            )
        )
        mock_data_provider.get_available_date_range = AsyncMock(
            return_value=DateRange(
                start_date=date(2015, 1, 1),
                end_date=date(2024, 1, 1),
                ticker="AAPL",
            )
        )

        with pytest.raises(ValidationError, match="validation"):
            await code_generator.generate(sample_backtest_request)

    @pytest.mark.asyncio
    async def test_generate_no_tickers_error(
        self,
        code_generator: BacktestCodeGenerator,
        sample_backtest_params: BacktestParams,
    ) -> None:
        """Test error when no tickers found in strategy."""
        request = BacktestRequest(
            strategy="Just make me money somehow.",
            params=sample_backtest_params,
        )
        # Remove benchmarks to have no tickers at all
        request.params.benchmarks = ["test"]  # This won't be extracted

        # Clear benchmarks after creation to test no-ticker scenario
        code_generator._extract_tickers = MagicMock(return_value=[])

        with pytest.raises(CodeGenerationError, match="No ticker symbols found"):
            await code_generator.generate(request)

    @pytest.mark.asyncio
    async def test_generate_llm_failure(
        self,
        code_generator: BacktestCodeGenerator,
        mock_llm_provider: MagicMock,
        mock_data_provider: MagicMock,
        sample_backtest_request: BacktestRequest,
    ) -> None:
        """Test error handling when LLM fails."""
        mock_llm_provider.generate = AsyncMock(
            side_effect=Exception("API timeout")
        )
        mock_data_provider.get_available_date_range = AsyncMock(
            return_value=DateRange(
                start_date=date(2015, 1, 1),
                end_date=date(2024, 1, 1),
                ticker="AAPL",
            )
        )

        with pytest.raises(CodeGenerationError, match="LLM generation failed"):
            await code_generator.generate(sample_backtest_request)


# =============================================================================
# Integration Tests
# =============================================================================


class TestCodeGeneratorIntegration:
    """Integration tests for the full generation workflow."""

    @pytest.mark.asyncio
    async def test_full_workflow_with_real_template(
        self,
        mock_llm_provider: MagicMock,
        mock_data_provider: MagicMock,
        sample_backtest_request: BacktestRequest,
        sample_llm_response: str,
    ) -> None:
        """Test full workflow using the actual prompt template."""
        # Use the real template if it exists
        real_template = (
            Path(__file__).parent.parent.parent
            / "app"
            / "prompts"
            / "backtest_system.txt"
        )

        if not real_template.exists():
            pytest.skip("Real template not found")

        generator = BacktestCodeGenerator(
            llm_provider=mock_llm_provider,
            data_provider=mock_data_provider,
            prompt_template_path=real_template,
        )

        mock_llm_provider.generate = AsyncMock(
            return_value=GenerationResult(
                content=sample_llm_response,
                model_info=mock_llm_provider.get_model_info(),
            )
        )
        mock_data_provider.get_available_date_range = AsyncMock(
            return_value=DateRange(
                start_date=date(2015, 1, 1),
                end_date=date(2024, 1, 1),
                ticker="AAPL",
            )
        )

        result = await generator.generate(sample_backtest_request)

        assert result.code
        assert result.strategy_summary
        assert result.model_info

    def test_prompt_template_snapshot(
        self,
        mock_llm_provider: MagicMock,
        mock_data_provider: MagicMock,
        sample_backtest_params: BacktestParams,
    ) -> None:
        """Snapshot test verifying prompt contains required elements."""
        real_template = (
            Path(__file__).parent.parent.parent
            / "app"
            / "prompts"
            / "backtest_system.txt"
        )

        if not real_template.exists():
            pytest.skip("Real template not found")

        generator = BacktestCodeGenerator(
            llm_provider=mock_llm_provider,
            data_provider=mock_data_provider,
            prompt_template_path=real_template,
        )

        data_ranges = {
            "AAPL": DateRange(
                start_date=date(2015, 1, 1),
                end_date=date(2024, 1, 1),
                ticker="AAPL",
            )
        }

        prompt = generator._build_prompt(
            "Buy AAPL when RSI is low",
            sample_backtest_params,
            ["AAPL"],
            data_ranges,
        )

        # Verify prompt contains key elements
        assert "Strategy Description" in prompt or "strategy_description" in prompt.lower()
        assert "AAPL" in prompt
        assert "2020-01-01" in prompt
        assert "2023-12-31" in prompt
        assert "100000" in prompt or "100,000" in prompt
