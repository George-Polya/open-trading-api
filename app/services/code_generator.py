"""
Backtest Code Generator Service.

Converts natural language investment strategies into executable Python backtest code
using LLM providers and validates the generated code for safety and correctness.
"""

import asyncio
import logging
import re
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Protocol

from app.models.backtest import (
    BacktestParams,
    BacktestRequest,
    GeneratedCode,
    ModelInfo as BacktestModelInfo,
)
from app.providers.data.base import DataProvider, DateRange
from app.providers.llm.base import (
    GenerationConfig,
    GenerationResult,
    LLMProvider,
    ModelInfo,
)


# =============================================================================
# Exceptions
# =============================================================================


class CodeGenerationError(Exception):
    """Base exception for code generation errors."""

    def __init__(self, message: str, details: dict | None = None):
        self.details = details or {}
        super().__init__(message)


class ValidationError(CodeGenerationError):
    """Raised when generated code fails validation."""

    def __init__(self, message: str, errors: list[str] | None = None):
        self.errors = errors or []
        super().__init__(message, {"validation_errors": self.errors})


class DataAvailabilityError(CodeGenerationError):
    """Raised when required data is not available."""

    def __init__(self, message: str, tickers: list[str] | None = None):
        self.tickers = tickers or []
        super().__init__(message, {"unavailable_tickers": self.tickers})


class PromptBuildError(CodeGenerationError):
    """Raised when prompt building fails."""

    pass


# =============================================================================
# Validator Protocol (Interface for Task 8)
# =============================================================================


class CodeValidator(Protocol):
    """
    Protocol for code validators.

    This interface will be implemented in Task 8.
    Allows dependency injection of different validation strategies.
    """

    def validate(self, code: str) -> "ValidationResult":
        """
        Validate generated Python code.

        Args:
            code: Python code string to validate

        Returns:
            ValidationResult indicating success/failure and any issues

        Raises:
            ValidationError: If validation fails with critical errors
        """
        ...


@dataclass
class ValidationResult:
    """Result of code validation."""

    is_valid: bool
    errors: list[str]
    warnings: list[str]


class DefaultValidator:
    """
    Default code validator implementation.

    Performs basic syntax and safety checks until Task 8 is complete.
    """

    # Dangerous patterns that should not appear in generated code
    FORBIDDEN_PATTERNS: list[tuple[str, str]] = [
        (r"\bexec\s*\(", "exec() function is not allowed"),
        (r"\beval\s*\(", "eval() function is not allowed"),
        (r"\b__import__\s*\(", "__import__() is not allowed"),
        (r"\bcompile\s*\(", "compile() function is not allowed"),
        (r"\bos\.system\s*\(", "os.system() is not allowed"),
        (r"\bsubprocess\.", "subprocess module is not allowed"),
        (r"\bopen\s*\(.+['\"]w", "File writing is not allowed"),
        (r"\brequests\.", "HTTP requests are not allowed"),
        (r"\burllib\.", "urllib module is not allowed"),
        (r"\bsocket\.", "socket module is not allowed"),
    ]

    # Required elements in the code
    REQUIRED_PATTERNS: list[tuple[str, str]] = [
        (r"class\s+\w+.*Strategy", "Strategy class definition required"),
        (r"def\s+next\s*\(", "next() method required in Strategy"),
    ]

    def validate(self, code: str) -> ValidationResult:
        """
        Validate Python code for syntax and safety.

        Args:
            code: Python code string to validate

        Returns:
            ValidationResult with validation status and any issues
        """
        errors: list[str] = []
        warnings: list[str] = []

        # Check for forbidden patterns
        for pattern, message in self.FORBIDDEN_PATTERNS:
            if re.search(pattern, code):
                errors.append(f"Security violation: {message}")

        # Check for required patterns
        for pattern, message in self.REQUIRED_PATTERNS:
            if not re.search(pattern, code):
                warnings.append(f"Missing element: {message}")

        # Syntax check
        try:
            compile(code, "<generated>", "exec")
        except SyntaxError as e:
            errors.append(f"Syntax error at line {e.lineno}: {e.msg}")

        is_valid = len(errors) == 0
        return ValidationResult(is_valid=is_valid, errors=errors, warnings=warnings)


# =============================================================================
# Backtest Code Generator
# =============================================================================


class BacktestCodeGenerator:
    """
    Converts natural language strategies into Python backtest code.

    This service orchestrates:
    1. Ticker extraction from strategy text
    2. Data availability verification
    3. Prompt construction from templates
    4. LLM code generation
    5. Code validation and parsing

    Follows SOLID principles with dependency injection for LLM and data providers.

    Attributes:
        llm_provider: LLM provider for code generation
        data_provider: Data provider for availability checks
        validator: Code validator for safety checks
        prompt_template_path: Path to the system prompt template

    Example:
        generator = BacktestCodeGenerator(llm_provider, data_provider)
        result = await generator.generate(backtest_request)
        print(result.code)
    """

    # Common stock ticker patterns
    TICKER_PATTERN = re.compile(
        r"\b([A-Z]{1,5})\b"  # 1-5 uppercase letters
    )

    # Korean stock code pattern (6 digits)
    KOREAN_TICKER_PATTERN = re.compile(
        r"\b(\d{6})\b"  # 6 digit code
    )

    # Common words that look like tickers but aren't
    TICKER_BLACKLIST: set[str] = {
        "I", "A", "AN", "THE", "AND", "OR", "IF", "FOR", "IN", "ON", "TO",
        "OF", "AT", "BY", "UP", "IT", "IS", "AS", "BE", "DO", "GO", "SO",
        "NO", "AM", "PM", "US", "UK", "EU", "GDP", "CEO", "CFO", "CTO",
        "API", "ETF", "IPO", "ROI", "EPS", "PE", "PB", "YTD", "QTD", "MTD",
        "BUY", "SELL", "HOLD", "LONG", "SHORT", "PUT", "CALL", "ATH", "ATL",
    }

    # Code fence patterns for extraction
    CODE_FENCE_PATTERN = re.compile(
        r"```(?:python)?\s*\n(.*?)```",
        re.DOTALL | re.IGNORECASE,
    )

    # Summary section pattern
    SUMMARY_PATTERN = re.compile(
        r"###?\s*SUMMARY\s*\n+(.*?)(?=###?\s*CODE|```|$)",
        re.DOTALL | re.IGNORECASE,
    )

    DEFAULT_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "backtest_system.txt"

    def __init__(
        self,
        llm_provider: LLMProvider,
        data_provider: DataProvider,
        validator: CodeValidator | None = None,
        prompt_template_path: Path | str | None = None,
    ):
        """
        Initialize the BacktestCodeGenerator.

        Args:
            llm_provider: LLM provider for generating code
            data_provider: Data provider for checking data availability
            validator: Optional code validator (defaults to DefaultValidator)
            prompt_template_path: Optional path to prompt template
        """
        self.llm_provider = llm_provider
        self.data_provider = data_provider
        self.validator = validator or DefaultValidator()

        if prompt_template_path:
            self.prompt_template_path = Path(prompt_template_path)
        else:
            self.prompt_template_path = self.DEFAULT_PROMPT_PATH

        self._prompt_template: str | None = None

    # =========================================================================
    # Ticker Extraction (Task 7.2)
    # =========================================================================

    def _extract_tickers(self, text: str, benchmarks: list[str] | None = None) -> list[str]:
        """
        Extract stock ticker symbols from text using regex and heuristics.

        Identifies both US tickers (uppercase letters) and Korean stock codes
        (6-digit numbers) from strategy descriptions and benchmark lists.

        Args:
            text: Strategy description text to parse
            benchmarks: Optional list of benchmark tickers to include

        Returns:
            List of unique ticker symbols found in the text

        Example:
            >>> generator._extract_tickers("Buy AAPL and TSLA when price drops")
            ['AAPL', 'TSLA']
        """
        tickers: set[str] = set()

        # Extract US-style tickers (1-5 uppercase letters)
        us_matches = self.TICKER_PATTERN.findall(text)
        for match in us_matches:
            if match not in self.TICKER_BLACKLIST and len(match) >= 2:
                tickers.add(match)

        # Extract Korean stock codes (6 digits)
        kr_matches = self.KOREAN_TICKER_PATTERN.findall(text)
        tickers.update(kr_matches)

        # Add benchmarks if provided
        if benchmarks:
            for benchmark in benchmarks:
                cleaned = benchmark.upper().strip()
                if cleaned:
                    tickers.add(cleaned)

        return sorted(list(tickers))

    def _strip_thinking_tags(self, response: str) -> str:
        """
        Remove thinking tags from LLM response.

        Thinking models (o1, deepseek-r1, kimi-k2-thinking, etc.) wrap their
        reasoning process in <think>...</think> or similar tags.

        Args:
            response: Raw LLM response that may contain thinking tags

        Returns:
            Response with thinking sections removed
        """
        # Remove <think>...</think> tags (used by many thinking models)
        cleaned = re.sub(
            r"<think>.*?</think>",
            "",
            response,
            flags=re.DOTALL | re.IGNORECASE,
        )

        # Remove <thinking>...</thinking> tags (alternative format)
        cleaned = re.sub(
            r"<thinking>.*?</thinking>",
            "",
            cleaned,
            flags=re.DOTALL | re.IGNORECASE,
        )

        # Remove <reasoning>...</reasoning> tags
        cleaned = re.sub(
            r"<reasoning>.*?</reasoning>",
            "",
            cleaned,
            flags=re.DOTALL | re.IGNORECASE,
        )

        return cleaned.strip()

    def _extract_code(self, response: str) -> str:
        """
        Extract Python code from LLM response.

        Parses markdown code fences to extract the generated Python code.
        Handles multiple code blocks by joining them.
        Supports thinking models by stripping thinking tags first.

        Args:
            response: Raw LLM response text containing code blocks

        Returns:
            Extracted Python code as a single string

        Raises:
            CodeGenerationError: If no code block is found

        Example:
            >>> response = "Here's the code:\\n```python\\nprint('hello')\\n```"
            >>> generator._extract_code(response)
            "print('hello')"
        """
        # First, strip thinking tags from thinking models
        cleaned_response = self._strip_thinking_tags(response)

        # Try to extract from cleaned response first
        matches = self.CODE_FENCE_PATTERN.findall(cleaned_response)

        # If no matches in cleaned, try original (code might be in thinking block)
        if not matches:
            matches = self.CODE_FENCE_PATTERN.findall(response)

        if not matches:
            # Try to find code without explicit fence
            # Sometimes LLM might not use proper fencing
            # Use cleaned response to avoid thinking content
            lines = cleaned_response.split("\n") if cleaned_response else response.split("\n")
            code_lines: list[str] = []
            in_code = False

            for line in lines:
                if line.strip().startswith("```"):
                    in_code = not in_code
                    continue
                if in_code or (
                    line.strip().startswith(("import ", "from ", "class ", "def "))
                ):
                    code_lines.append(line)
                    in_code = True

            if code_lines:
                return "\n".join(code_lines).strip()

            raise CodeGenerationError(
                "No code block found in LLM response",
                {"response_preview": response[:500]},
            )

        # Join multiple code blocks with newlines
        return "\n\n".join(match.strip() for match in matches)

    def _extract_summary(self, response: str) -> str:
        """
        Extract strategy summary from LLM response.

        Parses the SUMMARY section from the structured LLM response.

        Args:
            response: Raw LLM response text

        Returns:
            Extracted summary text, or default message if not found
        """
        match = self.SUMMARY_PATTERN.search(response)

        if match:
            summary = match.group(1).strip()
            # Clean up any markdown formatting
            summary = re.sub(r"^\s*[-*]\s*", "", summary, flags=re.MULTILINE)
            return summary.strip()

        # Fallback: try to extract first paragraph before code
        code_start = response.find("```")
        if code_start > 0:
            intro = response[:code_start].strip()
            # Get last paragraph before code
            paragraphs = intro.split("\n\n")
            for para in reversed(paragraphs):
                cleaned = para.strip()
                if cleaned and not cleaned.startswith("#"):
                    return cleaned

        return "Strategy converted to backtest code."

    # =========================================================================
    # Data Availability and Prompt Builder (Task 7.3)
    # =========================================================================

    async def _check_data_availability(
        self,
        tickers: list[str],
        start_date: date,
        end_date: date,
    ) -> dict[str, DateRange]:
        """
        Check data availability for requested tickers.

        Queries the data provider to verify each ticker has data
        within the requested date range.

        Args:
            tickers: List of ticker symbols to check
            start_date: Requested start date
            end_date: Requested end date

        Returns:
            Dictionary mapping ticker to its available DateRange

        Raises:
            DataAvailabilityError: If no tickers have available data
        """
        results: dict[str, DateRange] = {}
        unavailable: list[str] = []

        # Check availability for each ticker concurrently
        async def check_ticker(ticker: str) -> tuple[str, DateRange | None]:
            try:
                date_range = await self.data_provider.get_available_date_range(ticker)
                return ticker, date_range
            except Exception:
                return ticker, None

        tasks = [check_ticker(ticker) for ticker in tickers]
        check_results = await asyncio.gather(*tasks)

        for ticker, date_range in check_results:
            if date_range is not None:
                results[ticker] = date_range
            else:
                unavailable.append(ticker)

        if not results:
            raise DataAvailabilityError(
                f"No data available for any of the requested tickers: {tickers}",
                unavailable,
            )

        return results

    def _load_prompt_template(self) -> str:
        """
        Load the prompt template from file.

        Returns:
            Template string with placeholders

        Raises:
            PromptBuildError: If template file cannot be read
        """
        if self._prompt_template is not None:
            return self._prompt_template

        try:
            self._prompt_template = self.prompt_template_path.read_text(encoding="utf-8")
            return self._prompt_template
        except FileNotFoundError:
            raise PromptBuildError(
                f"Prompt template not found: {self.prompt_template_path}"
            )
        except Exception as e:
            raise PromptBuildError(f"Failed to load prompt template: {e}")

    def _build_prompt(
        self,
        strategy_text: str,
        params: BacktestParams,
        available_tickers: list[str],
        data_ranges: dict[str, DateRange],
    ) -> str:
        """
        Build the complete prompt for LLM code generation.

        Loads the template and fills in all placeholders with
        actual values from the backtest request.

        Args:
            strategy_text: Natural language strategy description
            params: Backtest parameters
            available_tickers: List of tickers with available data
            data_ranges: Dictionary of available date ranges per ticker

        Returns:
            Formatted prompt string ready for LLM

        Raises:
            PromptBuildError: If template formatting fails
        """
        template = self._load_prompt_template()

        # Calculate actual data date range (intersection of all tickers)
        data_start = max(
            (dr.start_date for dr in data_ranges.values()),
            default=params.start_date,
        )
        data_end = min(
            (dr.end_date for dr in data_ranges.values()),
            default=params.end_date,
        )

        # Adjust requested dates to available data
        effective_start = max(params.start_date, data_start)
        effective_end = min(params.end_date, data_end)

        # Calculate trading fee as decimal for code
        trading_fee_decimal = params.fees.trading_fee_percent / 100

        try:
            prompt = template.format(
                strategy_description=strategy_text,
                start_date=effective_start.isoformat(),
                end_date=effective_end.isoformat(),
                initial_capital=params.initial_capital,
                benchmarks=", ".join(params.benchmarks),
                contribution_frequency=params.contribution.frequency.value,
                contribution_amount=params.contribution.amount,
                trading_fee_percent=params.fees.trading_fee_percent,
                trading_fee_decimal=trading_fee_decimal,
                slippage_percent=params.fees.slippage_percent,
                dividend_reinvestment="Yes" if params.dividend_reinvestment else "No",
                available_tickers=", ".join(available_tickers),
                data_start_date=data_start.isoformat(),
                data_end_date=data_end.isoformat(),
            )
            return prompt
        except KeyError as e:
            raise PromptBuildError(f"Missing placeholder in template: {e}")
        except Exception as e:
            raise PromptBuildError(f"Failed to format prompt: {e}")

    # =========================================================================
    # Main Generate Method (Task 7.4)
    # =========================================================================

    async def generate(self, request: BacktestRequest) -> GeneratedCode:
        """
        Generate backtest code from a natural language strategy.

        This is the main entry point that orchestrates the complete
        code generation workflow:
        1. Extract tickers from strategy text
        2. Check data availability for each ticker
        3. Build the prompt from template
        4. Call LLM to generate code
        5. Extract and validate the generated code
        6. Return the validated result

        Args:
            request: BacktestRequest containing strategy and parameters

        Returns:
            GeneratedCode with the validated Python code and metadata

        Raises:
            CodeGenerationError: If any step in the generation fails
            ValidationError: If the generated code fails validation
            DataAvailabilityError: If required data is not available
        """
        # Step 1: Extract tickers from strategy text and benchmarks
        tickers = self._extract_tickers(
            request.strategy,
            request.params.benchmarks,
        )

        if not tickers:
            raise CodeGenerationError(
                "No ticker symbols found in strategy. "
                "Please mention specific stock symbols (e.g., AAPL, TSLA, 005930)."
            )

        # Step 2: Check data availability concurrently
        data_ranges = await self._check_data_availability(
            tickers,
            request.params.start_date,
            request.params.end_date,
        )

        available_tickers = list(data_ranges.keys())

        # Step 3: Build the prompt
        prompt = self._build_prompt(
            request.strategy,
            request.params,
            available_tickers,
            data_ranges,
        )

        # Step 4: Call LLM to generate code
        generation_config = GenerationConfig(
            temperature=0.2,
            max_tokens=8000,
        )

        try:
            result: GenerationResult = await self.llm_provider.generate(
                prompt=prompt,
                config=generation_config,
            )
        except Exception as e:
            raise CodeGenerationError(
                f"LLM generation failed: {e}",
                {"error_type": type(e).__name__},
            )

        # Step 5: Extract code and summary from response
        raw_response = result.content

        # Debug: Print full LLM response to terminal
        print("\n" + "=" * 80)
        print("LLM RESPONSE DEBUG")
        print("=" * 80)
        print(f"Response length: {len(raw_response)}")
        print("-" * 80)
        print(raw_response)
        print("=" * 80 + "\n")

        code = self._extract_code(raw_response)
        summary = self._extract_summary(raw_response)

        # Step 6: Validate the generated code (Task 7.5)
        validation_result = self.validator.validate(code)

        if not validation_result.is_valid:
            raise ValidationError(
                "Generated code failed validation",
                validation_result.errors,
            )

        # Step 7: Build and return the result
        llm_model_info = self.llm_provider.get_model_info()
        model_info = self._convert_model_info(llm_model_info)

        return GeneratedCode(
            code=code,
            strategy_summary=summary,
            model_info=model_info,
            tickers=available_tickers,
        )

    def _convert_model_info(self, llm_model_info: ModelInfo) -> BacktestModelInfo:
        """
        Convert LLM ModelInfo to Backtest ModelInfo.

        Args:
            llm_model_info: Model info from LLM provider

        Returns:
            BacktestModelInfo for the response DTO
        """
        return BacktestModelInfo(
            provider=llm_model_info.provider,
            model_id=llm_model_info.model_id,
            max_tokens=llm_model_info.max_output_tokens,
            supports_system_prompt=llm_model_info.supports_system_prompt,
            cost_per_1k_input=float(llm_model_info.cost_per_1k_input),
            cost_per_1k_output=float(llm_model_info.cost_per_1k_output),
        )
