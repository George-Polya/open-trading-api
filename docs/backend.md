# Backend Service Documentation

AI-powered Natural Language Backtesting Service Backend.

## Overview

This backend service enables users to describe investment strategies in natural language, which are then converted to Python backtesting code by AI and executed against real market data from KIS Open API.

## Quick Start

### Prerequisites

- Python >= 3.13
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

### Installation

```bash
# Using uv (recommended)
uv sync

# Install dev dependencies
uv sync --extra dev

# Or using pip
pip install -e .
pip install -e ".[dev]"
```

### Configuration

1. **민감 정보는 `.env` 파일에서 관리** (`.env.example` 참고):
   ```bash
   cp .env.example .env
   # .env 파일 편집
   ```

   ```bash
   # .env 예시
   # LLM API Key
   OPENROUTER_API_KEY=your_key_here

   # KIS API Credentials
   KIS_APP_KEY=your_kis_app_key
   KIS_APP_SECRET=your_kis_app_secret
   KIS_ACCOUNT_STOCK=12345678
   ```

2. **비민감 설정은 `config.yaml`에서 관리**:
   ```yaml
   llm:
     provider: "openrouter"
     model: "anthropic/claude-3.5-sonnet"
   ```

### Running the Server

```bash
# Development mode with auto-reload
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Or using uv
uv run uvicorn app.main:app --reload

# Production mode
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### Verify Installation

```bash
# Health check
curl http://localhost:8000/health

# Expected response:
# {
#   "status": "healthy",
#   "app_name": "Natural Language Backtesting Service",
#   "app_version": "0.1.0",
#   ...
# }
```

## Configuration Reference

### config.yaml Structure

```yaml
# LLM Provider Configuration (API keys are in .env)
llm:
  provider: "openrouter"  # openrouter | anthropic | openai
  model: "anthropic/claude-3.5-sonnet"
  temperature: 0.2
  max_tokens: 8000

# Data Provider Configuration (KIS credentials are in .env)
data:
  provider: "kis"  # kis | yfinance | mock
  fallback_providers: []
  cache_ttl_seconds: 300

# Code Execution Configuration
execution:
  provider: "docker"  # docker | local
  timeout: 300
  memory_limit: "2g"
```

### 설정 파일

| 파일 | 역할 | Git 커밋 |
|------|------|----------|
| `.env` | 민감 정보 (API keys, KIS credentials) | ❌ 절대 안됨 |
| `.env.example` | 환경 변수 템플릿 | ✅ |
| `config.yaml` | 비민감 설정 (LLM/Execution) | ✅ |

### Environment Variables (.env)

| Variable | Description | Required |
|----------|-------------|----------|
| `OPENROUTER_API_KEY` | OpenRouter API key | If using OpenRouter |
| `ANTHROPIC_API_KEY` | Anthropic API key | If using Claude directly |
| `OPENAI_API_KEY` | OpenAI API key | If using OpenAI |
| `KIS_APP_KEY` | KIS 실전투자 앱키 | If using KIS |
| `KIS_APP_SECRET` | KIS 실전투자 앱키 시크릿 | If using KIS |
| `KIS_PAPER_APP_KEY` | KIS 모의투자 앱키 | For paper trading |
| `KIS_PAPER_APP_SECRET` | KIS 모의투자 앱키 시크릿 | For paper trading |
| `KIS_ACCOUNT_STOCK` | KIS 증권계좌 8자리 | If using KIS |
| `APP_DEBUG` | Enable debug mode | No (default: false) |

## Project Structure

```
app/
├── __init__.py
├── main.py              # FastAPI application entry point
└── core/
    ├── __init__.py
    ├── config.py        # Settings loader (pydantic-settings)
    └── container.py     # Dependency injection container
```

## API Endpoints

### Health Check

```
GET /health
```

Returns service status and configuration metadata.

**Response:**
```json
{
  "status": "healthy",
  "app_name": "Natural Language Backtesting Service",
  "app_version": "0.1.0",
  "timestamp": "2024-12-09T00:00:00.000000+00:00",
  "debug": false,
  "llm_provider": "openrouter",
  "data_provider": "kis",
  "execution_provider": "docker"
}
```

### Root

```
GET /
```

Returns basic service information.

## Development

### Running Tests

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=app

# Run specific test file
uv run pytest tests/test_config.py
```

### Code Quality

```bash
# Format code
uv run ruff format .

# Lint code
uv run ruff check .

# Type check
uv run mypy app/
```

## Architecture

The backend follows SOLID principles with a clean architecture:

- **Single Responsibility**: Each module has one reason to change
- **Open/Closed**: Easy to add new LLM/Data providers via adapters
- **Liskov Substitution**: All adapters implement common interfaces
- **Interface Segregation**: Small, focused interfaces
- **Dependency Inversion**: High-level modules depend on abstractions

See the [PRD](../prd.txt) for detailed architecture documentation.
