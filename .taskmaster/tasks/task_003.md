# Task ID: 3

**Title:** LLMProvider 추상화 및 팩토리 골격 구현

**Status:** done

**Dependencies:** 1 ✓

**Priority:** medium

**Description:** SOLID DIP를 지키기 위해 ModelInfo/GenerationConfig/LLMProvider 인터페이스와 팩토리를 작성합니다.

**Details:**

Implementation:
- In app/providers/llm/base.py define dataclasses ModelInfo, GenerationConfig (defaults temperature=0.2, max_tokens=8000), and abstract class LLMProvider with async generate() and get_model_info().
- Add factory app/providers/llm/factory.py reading settings.llm dict to instantiate adapters (OpenRouter default) per PRD 2.2.4.
- Ensure interfaces expose provider-agnostic metadata for UI display.
Pseudo:
```
class LLMProvider(ABC):
    @abstractmethod
    async def generate(...):...
```

**Test Strategy:**

- Use pytest + pytest-asyncio to assert factory returns right concrete class when provider flag toggles.
- Employ unittest.mock.AsyncMock to verify interface contract (generate raises NotImplementedError when subclass missing implementation).
- mypy check to ensure typing discipline around abstract methods.

## Subtasks

### 3.1. Define LLMProvider Interface

**Status:** completed  
**Dependencies:** None  

Create abstract base class and data types in app/providers/llm/base.py.

**Details:**

Define ModelInfo, GenerationConfig, and LLMProvider(ABC).

### 3.2. Implement LLM Factory

**Status:** completed  
**Dependencies:** 3.1  

Create factory class to instantiate providers based on config.

**Details:**

Implement LLMProviderFactory.get_provider(). Load settings to determine which provider to initialize.

### 3.3. Create Dummy/Mock Provider

**Status:** completed  
**Dependencies:** 3.1  

Implement a mock provider for initial testing.

**Details:**

Create MockLLMProvider for unit testing factory logic without external calls.

### 3.4. Integrate Factory with Container

**Status:** completed  
**Dependencies:** 3.2  

Register LLM provider in the dependency container.

**Details:**

Update app/core/container.py to provide the LLM instance.

### 3.5. Unit Tests for Abstraction

**Status:** completed  
**Dependencies:** 3.1, 3.2  

Verify factory and interface logic.

**Details:**

Test that factory raises error for unknown providers and correctly instantiates known ones.
