# Task ID: 4

**Title:** OpenRouter·Claude·OpenAI LLM 어댑터 및 LangChain 구현

**Status:** done

**Dependencies:** 3 ✓

**Priority:** medium

**Description:** OpenRouter(OpenAI SDK 사용)와 LangChain 기반 어댑터 구현을 완료하고, Anthropic(Claude) 및 OpenAI 네이티브 어댑터를 추가 구현하여 팩토리에 연동합니다.

**Details:**

Implementation Status:
- [DONE] `OpenRouterAdapter`: Implemented in `app/providers/llm/openrouter.py` using `openai.AsyncOpenAI`. Supports OpenRouter API.
- [DONE] `LangChainAdapter`: Implemented in `app/providers/llm/langchain_adapter.py` using `langchain_openai.ChatOpenAI`. Connects to OpenRouter.
- [DONE] Factory & Error Handling: `LLMProviderFactory` registers 'openrouter' and 'langchain'. Unified `LLMGenerationError` implemented.
- [PENDING] `AnthropicAdapter`: Needs implementation using native `anthropic` SDK for direct Claude API access.
- [PENDING] `OpenAIAdapter`: Needs implementation using native `openai` SDK for direct OpenAI API access (distinct from OpenRouter).
- [PENDING] Factory Update: Register 'anthropic' and 'openai' types in the factory.

**Test Strategy:**

- Maintain passing status for existing 65 provider tests (OpenRouter/LangChain).
- Create new tests for `AnthropicAdapter` using mocked `anthropic.AsyncAnthropic`.
- Create new tests for `OpenAIAdapter` using mocked `openai.AsyncOpenAI` (direct).
- Verify `LLMProviderFactory` correctly instantiates the new adapters based on configuration.
- Ensure cost metadata and error handling normalization applies to the new native adapters.

## Subtasks

### 4.6. Implement Native Anthropic (Claude) Adapter

**Status:** done  
**Dependencies:** 4.3  

Implement a dedicated adapter for Anthropic using the native Anthropic SDK.

**Details:**

Create `app/providers/llm/anthropic_adapter.py`. Use `anthropic.AsyncAnthropic` client. Implement `generate` and `get_model_info`. Map Anthropic specific exceptions to unified `LLMGenerationError`.

### 4.7. Implement Native OpenAI Adapter

**Status:** done  
**Dependencies:** 4.3  

Implement a full native OpenAI adapter for direct API usage.

**Details:**

Create or update `app/providers/llm/openai_adapter.py` (distinct from OpenRouter logic). Use `openai.AsyncOpenAI` with direct API key. Ensure strict separation from OpenRouter configuration.

### 4.8. Register Native Adapters in Factory

**Status:** done  
**Dependencies:** 4.6, 4.7  

Update LLMProviderFactory to support 'anthropic' and 'openai' types.

**Details:**

Modify `app/providers/llm/factory.py` to instantiate `AnthropicAdapter` or `OpenAIAdapter` when config specifies these provider types.

### 4.1. Implement OpenRouter LLM Adapter

**Status:** completed  
**Dependencies:** None  

Create the OpenRouter adapter class using AsyncOpenAI client.

**Details:**

Implemented `OpenRouterAdapter`. Uses `AsyncOpenAI` to communicate with OpenRouter. Handles `Authorization` and `HTTP-Referer` headers.

[2025-12-09] OpenRouter Thinking 모델 지원 개선:
- LLMConfig에 reasoning_enabled, reasoning_max_tokens 설정 추가
- extra_body에 reasoning 파라미터 추가 (OpenRouter reasoning tokens API)
- reasoning_details 필드 파싱 로직 추가 (text, summary 추출)
- reasoning 필드 및 model_extra dict 파싱 지원
- 빈 content + reasoning 응답 시 reasoning을 content로 사용
- config.yaml에 reasoning 설정 예시 추가

### 4.2. Implement LangChain LLM Adapter

**Status:** completed  
**Dependencies:** None  

Create adapter using LangChain's ChatOpenAI for flexible integration.

**Details:**

Implemented `LangChainAdapter` that wraps `langchain_openai.ChatOpenAI`. Allows easy switching of underlying models and leveraging LangChain ecosystem if needed.

### 4.3. Refine OpenAI Native Adapter (Optional)

**Status:** done  
**Dependencies:** None  

Stub or basic implementation for native OpenAI direct connection.

**Details:**

Structure in place for native OpenAI support if OpenRouter is bypassed. Currently superseded by OpenRouter adapter which handles OpenAI models.

### 4.4. Wire Adapters into LLM Factory

**Status:** completed  
**Dependencies:** 4.1, 4.2  

Register the new adapters in the LLM Factory.

**Details:**

Factory now returns `OpenRouterAdapter` or `LangChainAdapter` based on configuration.

### 4.5. Standardize Error Handling and Cost Metadata

**Status:** completed  
**Dependencies:** 4.1, 4.2  

Ensure all adapters return consistent error types and usage metadata.

**Details:**

Implemented unified `LLMGenerationError`. Metadata includes `cost_per_1k_input` and output fields.
