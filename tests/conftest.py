"""
Pytest configuration and fixtures for the backtesting service tests.
"""

from pathlib import Path
from typing import Generator

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.core.container import Container, clear_container_cache, get_container
from app.main import app, create_app


@pytest.fixture(autouse=True)
def clear_caches() -> Generator[None, None, None]:
    """
    Clear all caches before and after each test.

    This ensures test isolation by resetting singleton state.
    """
    clear_container_cache()
    yield
    clear_container_cache()


@pytest.fixture
def temp_config_file(tmp_path: Path) -> Path:
    """
    Create a temporary config.yaml file for testing.

    Args:
        tmp_path: Pytest tmp_path fixture.

    Returns:
        Path to the temporary config file.
    """
    config_content = """
llm:
  provider: "openrouter"
  model: "anthropic/claude-3.5-sonnet"
  temperature: 0.2
  max_tokens: 8000

data:
  provider: "mock"
  cache_ttl_seconds: 300

execution:
  provider: "local"
  timeout: 60
  memory_limit: "1g"
"""
    config_path = tmp_path / "config.yaml"
    config_path.write_text(config_content)
    return config_path


@pytest.fixture
def test_settings(temp_config_file: Path) -> Settings:
    """
    Create test settings from temporary config file.

    Args:
        temp_config_file: Path to temporary config file.

    Returns:
        Settings instance loaded from temporary config.
    """
    return Settings.from_yaml(temp_config_file)


@pytest.fixture
def test_container(test_settings: Settings) -> Container:
    """
    Create a test container with test settings.

    Args:
        test_settings: Test settings fixture.

    Returns:
        Container instance with test settings.
    """
    return Container(settings=test_settings)


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """
    Create a test client for the FastAPI application.

    Yields:
        TestClient instance.
    """
    with TestClient(app) as test_client:
        yield test_client
