"""
Backtest Code Generator Service.

Converts natural language investment strategies into executable Python backtest code
using LLM providers and validates the generated code for safety and correctness.
"""

import asyncio
import json
import logging
import re
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Protocol

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

    def _unescape_json_string(self, s: str) -> str:
        """
        Properly unescape a JSON string value, handling multiple levels of escaping.

        Some LLMs output double-escaped content (e.g., \\\\n instead of \\n).
        This function applies unescaping iteratively, focusing on converting
        escaped newlines to actual newlines while preserving other escape
        sequences that might be intentional (like \\t in regex patterns).

        Args:
            s: The JSON string value (already extracted from JSON)

        Returns:
            The unescaped string with proper newlines, tabs, quotes, and backslashes
        """
        # First pass: full JSON unescape
        s = self._unescape_once(s)

        # Additional passes: handle remaining backslash-n sequences
        # This handles double/triple escaped newlines from LLMs
        # We iterate until no more \n (backslash + n) sequences remain
        max_iterations = 3
        for _ in range(max_iterations):
            # Check if there are any remaining \n (as two characters) to unescape
            if '\\n' not in s:
                break
            s = self._unescape_newlines_only(s)
        return s

    def _unescape_newlines_only(self, s: str) -> str:
        """
        Unescape backslash-n sequences to actual newlines.

        Handles both single backslash-n and double backslash-n:
        - \\n (one backslash + n) → newline
        - \\\\n (two backslashes + n) → one backslash + newline (which becomes just newline in next pass)

        Args:
            s: The string to unescape

        Returns:
            The string with one level of backslash-n converted to newlines
        """
        result = []
        i = 0
        while i < len(s):
            # Check for backslash
            if s[i] == '\\' and i + 1 < len(s):
                next_char = s[i + 1]
                if next_char == 'n':
                    # \n → newline
                    result.append('\n')
                    i += 2
                elif next_char == '\\' and i + 2 < len(s) and s[i + 2] == 'n':
                    # \\n → newline (skip both backslashes)
                    result.append('\n')
                    i += 3
                else:
                    # Other escape, keep as-is
                    result.append(s[i])
                    i += 1
            else:
                result.append(s[i])
                i += 1
        return ''.join(result)

    def _unescape_once(self, s: str) -> str:
        """
        Apply one level of JSON unescape to a string.

        Handles JSON escape sequences in a single pass to avoid
        issues with overlapping patterns (e.g., \\\\n vs \\n).

        Args:
            s: The string to unescape

        Returns:
            The string with one level of escaping removed
        """
        result = []
        i = 0
        while i < len(s):
            if s[i] == '\\' and i + 1 < len(s):
                next_char = s[i + 1]
                if next_char == 'n':
                    result.append('\n')
                    i += 2
                elif next_char == 't':
                    result.append('\t')
                    i += 2
                elif next_char == 'r':
                    result.append('\r')
                    i += 2
                elif next_char == '"':
                    result.append('"')
                    i += 2
                elif next_char == "'":
                    result.append("'")
                    i += 2
                elif next_char == '\\':
                    result.append('\\')
                    i += 2
                elif next_char == '/':
                    result.append('/')
                    i += 2
                elif next_char == 'b':
                    result.append('\b')
                    i += 2
                elif next_char == 'f':
                    result.append('\f')
                    i += 2
                elif next_char == 'u' and i + 5 < len(s):
                    # Unicode escape: \uXXXX
                    try:
                        hex_val = s[i + 2:i + 6]
                        result.append(chr(int(hex_val, 16)))
                        i += 6
                    except (ValueError, IndexError):
                        # Invalid unicode escape, keep as-is
                        result.append(s[i])
                        i += 1
                else:
                    # Unknown escape, keep as-is
                    result.append(s[i])
                    i += 1
            else:
                result.append(s[i])
                i += 1
        return ''.join(result)

    def _parse_json_response(self, response: str) -> dict | None:
        """
        Try to parse JSON from LLM response.

        Handles:
        1. Clean JSON object
        2. JSON wrapped in markdown code fences
        3. JSON with leading/trailing text
        4. Improperly escaped code strings
        5. Direct extraction of "code" and "summary" fields

        Args:
            response: Raw LLM response text

        Returns:
            Parsed dict if successful, None otherwise
        """
        # First, strip thinking tags
        cleaned = self._strip_thinking_tags(response)
        logger.info(f"Attempting to parse JSON from response (length: {len(cleaned)})")

        # Try direct JSON parse
        try:
            result = json.loads(cleaned.strip())
            logger.info("JSON parsed successfully (direct)")
            return result
        except json.JSONDecodeError as e:
            logger.info(f"Direct JSON parse failed at position {e.pos}: {e.msg}")
            # Show context around the error position
            if e.pos is not None:
                start = max(0, e.pos - 50)
                end = min(len(cleaned), e.pos + 50)
                logger.info(f"Error context: ...{cleaned[start:end]!r}...")

        # Try extracting JSON object by finding balanced braces
        # This is more robust than regex for nested structures
        start_idx = cleaned.find('{')
        if start_idx >= 0:
            # Find matching closing brace (handle nested braces and strings)
            depth = 0
            in_string = False
            escape_next = False
            end_idx = -1

            for i, char in enumerate(cleaned[start_idx:], start_idx):
                if escape_next:
                    escape_next = False
                    continue

                if char == '\\' and in_string:
                    escape_next = True
                    continue

                if char == '"' and not escape_next:
                    in_string = not in_string
                    continue

                if not in_string:
                    if char == '{':
                        depth += 1
                    elif char == '}':
                        depth -= 1
                        if depth == 0:
                            end_idx = i
                            break

            if end_idx > start_idx:
                json_str = cleaned[start_idx:end_idx + 1]
                logger.info(f"Brace matching found JSON (length: {len(json_str)})")
                try:
                    result = json.loads(json_str)
                    logger.info("JSON parsed successfully (brace matching)")
                    return result
                except json.JSONDecodeError as e:
                    logger.warning(f"Brace-matched JSON parse failed at pos {e.pos}: {e.msg}")
                    # Show context around the error position
                    if e.pos is not None:
                        start = max(0, e.pos - 50)
                        end = min(len(json_str), e.pos + 50)
                        logger.warning(f"Error context: ...{json_str[start:end]!r}...")
            else:
                logger.warning(f"Brace matching failed: start_idx={start_idx}, end_idx={end_idx}, in_string={in_string}, depth={depth}")

        # Try extracting from code fence (fallback for ```json blocks)
        # Use greedy match to handle nested code blocks in code field
        json_fence_pattern = re.compile(
            r"```json\s*\n([\s\S]*?)\n```(?!\w)",
            re.MULTILINE
        )
        match = json_fence_pattern.search(cleaned)
        if match:
            json_content = match.group(1).strip()
            try:
                result = json.loads(json_content)
                logger.debug("JSON parsed successfully (code fence)")
                return result
            except json.JSONDecodeError as e:
                logger.debug(f"Code fence JSON parse failed: {e}")

        # FALLBACK: Extract code by finding "code": " and scanning to the end
        # This is more robust for very long code with complex escaping
        code_start_pattern = re.search(r'"code"\s*:\s*"', cleaned)
        if code_start_pattern:
            code_start = code_start_pattern.end()
            code_content = []
            i = code_start
            escape_next = False

            while i < len(cleaned):
                char = cleaned[i]
                if escape_next:
                    code_content.append(char)
                    escape_next = False
                    i += 1
                    continue
                if char == '\\':
                    code_content.append(char)
                    escape_next = True
                    i += 1
                    continue
                if char == '"':
                    # Found a potential end quote
                    # Look at what follows to determine if this is truly the end
                    rest = cleaned[i+1:].lstrip()

                    # More robust end detection:
                    # 1. End of JSON object: }
                    # 2. Next field: , followed by " (for "summary" or other keys)
                    # 3. Newline + } for formatted JSON
                    if (rest.startswith('}') or
                        rest.startswith(',') or
                        rest.startswith('\n}') or
                        rest.startswith('\r\n}')):

                        # Additional validation: make sure it's not code containing these patterns
                        # by checking if rest looks like valid JSON continuation
                        rest_stripped = rest.lstrip(',').lstrip()

                        # If followed by "summary" or end of object, this is likely the real end
                        if (rest.startswith('}') or
                            rest_stripped.startswith('"summary"') or
                            rest_stripped.startswith('"') or
                            rest.startswith('\n}')):

                            logger.info("Extracted code via robust character-by-character scan")
                            code_str = ''.join(code_content)

                            # Extract summary if present
                            summary = "Strategy converted to backtest code."
                            summary_match = re.search(
                                r'"summary"\s*:\s*"((?:[^"\\]|\\.)*)"',
                                cleaned,
                                re.DOTALL
                            )
                            if summary_match:
                                summary = summary_match.group(1)

                            return {
                                "code": code_str,
                                "summary": summary,
                            }

                code_content.append(char)
                i += 1

            # If we reached the end without finding a proper closing quote,
            # the JSON might be truncated. Try to use what we have.
            if code_content:
                logger.warning("Code string appears truncated, using partial content")
                code_str = ''.join(code_content)
                return {
                    "code": code_str,
                    "summary": "Strategy converted to backtest code (response may be truncated).",
                }

        # Last resort: Try simple regex extraction (may fail on complex code)
        code_match = re.search(r'"code"\s*:\s*"((?:[^"\\]|\\.)*)"\s*[,}]', cleaned, re.DOTALL)
        summary_match = re.search(r'"summary"\s*:\s*"((?:[^"\\]|\\.)*)"\s*[,}]', cleaned, re.DOTALL)

        if code_match:
            logger.info("Extracted code via regex fallback")
            code = code_match.group(1)
            summary = summary_match.group(1) if summary_match else "Strategy converted to backtest code."
            return {
                "code": code,
                "summary": summary,
            }

        logger.warning("Failed to parse JSON from LLM response")
        return None

    def _extract_code(self, response: str) -> str:
        """
        Extract Python code from LLM response.

        Handles multiple formats:
        1. JSON response with "code" field (preferred)
        2. Code blocks with ```python fencing
        3. Code blocks with ``` fencing
        4. Raw code without fencing

        Args:
            response: Raw LLM response text containing code blocks

        Returns:
            Extracted Python code as a single string

        Raises:
            CodeGenerationError: If no code block is found

        Example:
            >>> response = '{"code": "print(\\'hello\\')", "summary": "..."}'
            >>> generator._extract_code(response)
            "print('hello')"
        """
        # Try JSON parsing first (preferred format)
        json_data = self._parse_json_response(response)
        if json_data:
            logger.info(f"JSON parsed successfully, keys: {list(json_data.keys())}")
            if "code" in json_data:
                code = json_data["code"]
                if code and isinstance(code, str):
                    # Handle escaped sequences from LLM using proper JSON unescaping
                    code = self._unescape_json_string(code)
                    logger.info(f"Extracted code from JSON response (length: {len(code)})")
                    return code.strip()
                else:
                    logger.warning(f"'code' field is empty or not a string: {type(code)}")
            else:
                logger.warning("JSON parsed but no 'code' field found")
        else:
            logger.warning("JSON parsing returned None, trying fallback extraction")

        # Fallback: strip thinking tags from thinking models
        cleaned_response = self._strip_thinking_tags(response)

        # Try to extract from cleaned response first
        matches = self.CODE_FENCE_PATTERN.findall(cleaned_response)
        logger.debug(f"Code fence matches in cleaned response: {len(matches)}")

        # If no matches in cleaned, try original (code might be in thinking block)
        if not matches:
            matches = self.CODE_FENCE_PATTERN.findall(response)
            logger.debug(f"Code fence matches in original response: {len(matches)}")

        if not matches:
            # Try to find code without explicit fence
            # Sometimes LLM might not use proper fencing
            # Use cleaned response to avoid thinking content
            logger.debug("No code fences found, trying line-by-line extraction")
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
                logger.info(f"Extracted {len(code_lines)} lines via line-by-line extraction")
                return "\n".join(code_lines).strip()

            # Log detailed error information
            logger.error("No code block found in LLM response")
            logger.error(f"Response length: {len(response)}")
            logger.error(f"Cleaned response length: {len(cleaned_response)}")
            logger.error(f"Response preview (first 1000 chars): {response[:1000]}")

            raise CodeGenerationError(
                "No code block found in LLM response",
                {"response_preview": response[:500]},
            )

        # Join multiple code blocks with newlines
        logger.info(f"Extracted {len(matches)} code blocks via regex")
        return "\n\n".join(match.strip() for match in matches)

    def _extract_summary(self, response: str) -> str:
        """
        Extract strategy summary from LLM response.

        Handles multiple formats:
        1. JSON response with "summary" field (preferred)
        2. SUMMARY section from structured response
        3. First paragraph before code block

        Args:
            response: Raw LLM response text

        Returns:
            Extracted summary text, or default message if not found
        """
        # Try JSON parsing first (preferred format)
        json_data = self._parse_json_response(response)
        if json_data and "summary" in json_data:
            summary = json_data["summary"]
            if summary and isinstance(summary, str):
                # Unescape the summary as well
                summary = self._unescape_json_string(summary)
                logger.info("Extracted summary from JSON response")
                return summary.strip()

        # Fallback: try SUMMARY section pattern
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
        # Use the model's max_output_tokens from config, not hardcoded value
        model_info = self.llm_provider.get_model_info()

        # Build extra config with dynamic web_search_enabled from request
        extra_config: dict[str, Any] = {}
        if request.params.llm_settings.web_search_enabled:
            extra_config["web_search_enabled"] = True

        generation_config = GenerationConfig(
            temperature=0.2,
            max_tokens=model_info.max_output_tokens,
            extra=extra_config,
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

        # Log LLM response for debugging
        logger.info(f"LLM response received (length: {len(raw_response)})")
        logger.debug(f"LLM response content:\n{raw_response[:2000]}...")

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
        # Reuse model_info from Step 4
        backtest_model_info = self._convert_model_info(model_info)

        return GeneratedCode(
            code=code,
            strategy_summary=summary,
            model_info=backtest_model_info,
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
