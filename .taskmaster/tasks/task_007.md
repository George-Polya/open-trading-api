# Task ID: 7

**Title:** BacktestCodeGenerator 및 프롬프트 빌더 작성

**Status:** done

**Dependencies:** 2 ✓, 3 ✓, 5 ✓

**Priority:** medium

**Description:** 자연어 전략을 코드로 변환하는 핵심 서비스를 구현합니다.

**Details:**

Implementation:
- Create app/services/code_generator.py implementing BacktestCodeGenerator described in PRD 3.2.2 with dependencies llm_provider + data_provider injected.
- Components:
  * _extract_tickers: regex + NLP heuristics to detect tickers from strategy + params benchmarks.
  * _check_data_availability: call data_provider.get_available_date_range; adjust start/end accordingly.
  * _build_prompt: load system prompt template from file (e.g., app/prompts/backtest_system.txt) and format with params.
  * _extract_code/_extract_summary: parse Markdown fences from LLM response.
  * validator attribute (Task 8) invoked before returning GeneratedCode.
- Ensure asynchronous generate() orchestrates steps: gather data concurrently via asyncio.gather, call llm.generate with GenerationConfig(temperature=0.2,...), and handle ValidationError raising CodeGenerationError.
Pseudo Snippet:
```
async def generate(...):
    tickers = self._extract_tickers(text)
    data_range = await self._check_data_availability(...)
    prompt = self._build_prompt(...)
    response = await self.llm.generate(prompt,...)
    code = self._extract_code(response)
    validation = self.validator.validate(code)
    return GeneratedCode(...)
```
- Store model_info = llm.get_model_info() for audit.

**Test Strategy:**

- pytest-asyncio: mock llm to return canned response; assert CodeGenerator returns GeneratedCode and calls validator.
- Tests for _extract_tickers using variety of strings to ensure multi ticker detection.
- Snapshot test verifying prompt contains data bounds and parameter table.

## Subtasks

### 7.1. Create System Prompt Template for Backtest Generation

**Status:** done  
**Dependencies:** None  

Create the system prompt text file used by the code generator to instruct the LLM on how to convert natural language strategies into Python code.

**Details:**

Create `app/prompts/backtest_system.txt`. The prompt should define the persona (Quant Developer), explain the required output format (Python code within markdown fences, summary section), list available libraries (pandas, backtesting.py, etc.), and specify how to handle constraints like data date ranges and risk parameters. It must include placeholders (e.g., `{strategy}`, `{params}`) for string formatting.

### 7.2. Implement Helper Methods for Ticker and Code Extraction

**Status:** done  
**Dependencies:** 7.1  

Implement utility methods in the CodeGenerator class to parse input text for tickers and extract code blocks from LLM responses.

**Details:**

Create `app/services/code_generator.py` with `BacktestCodeGenerator` class. Implement `_extract_tickers(self, text: str) -> List[str]` using regex (e.g., `\b[A-Z]{1,5}\b`) and NLP heuristics to identify stock symbols. Implement `_extract_code(self, response: str) -> str` and `_extract_summary(self, response: str) -> str` to parse Markdown code fences (```python ... ```) from the raw LLM output strings.

### 7.3. Implement Data Availability and Prompt Builder Logic

**Status:** done  
**Dependencies:** 7.2  

Implement logic to check data availability via the DataProvider and construct the final prompt by filling the template.

**Details:**

In `BacktestCodeGenerator`, implement `_check_data_availability(self, tickers: List[str], start_date, end_date)` which calls the injected `data_provider.get_available_date_range`. Implement `_build_prompt(self, strategy_text: str, context: dict) -> str` which loads `app/prompts/backtest_system.txt` and formats it with the strategy, validated date ranges, and parameters defined in `BacktestParams`.

### 7.4. Implement Main Asynchronous Generate Method

**Status:** done  
**Dependencies:** 7.3  

Implement the main `generate` entry point that orchestrates data checks, prompt building, and LLM execution.

**Details:**

Implement `async def generate(self, request: BacktestRequest) -> GeneratedCode`. It should: 1. Extract tickers. 2. `await` `_check_data_availability`. 3. Build the prompt. 4. Call `self.llm_provider.generate(prompt, config=...)`. 5. Parse the result using extraction helpers. Handle `CodeGenerationError` if steps fail. Inject `llm_provider` and `data_provider` via `__init__`.

### 7.5. Integrate Validation Step in Generation Workflow

**Status:** done  
**Dependencies:** 7.4  

Integrate the CodeValidator (Task 8 interface) into the generation pipeline to ensure generated code is safe and syntax-valid before returning.

**Details:**

Update the `generate` method to call `self.validator.validate(code_str)` after extraction. If validation fails, raise a `ValidationError` or retry (if retry logic is in scope, otherwise just raise). This ensures the `GeneratedCode` object returned to the API layer contains only validated, safe code. Define the interface for the validator if Task 8 is not yet complete.
