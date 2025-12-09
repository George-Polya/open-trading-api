"""
Tests for the backtest configuration endpoints.

Tests cover:
- GET /api/v1/backtest/config/llm-providers
- GET /api/v1/backtest/config/data-sources
"""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    app = create_app()
    return TestClient(app)


class TestGetLLMProvidersEndpoint:
    """Tests for GET /api/v1/backtest/config/llm-providers endpoint."""

    def test_get_llm_providers_success(self, client):
        """Test successful retrieval of LLM providers."""
        response = client.get("/api/v1/backtest/config/llm-providers")

        assert response.status_code == 200
        data = response.json()

        # Check response structure
        assert "providers" in data
        assert isinstance(data["providers"], list)
        assert len(data["providers"]) > 0

        # Check provider structure
        provider = data["providers"][0]
        assert "name" in provider
        assert "description" in provider
        assert "available" in provider
        assert isinstance(provider["name"], str)
        assert isinstance(provider["description"], str)
        assert isinstance(provider["available"], bool)

    def test_get_llm_providers_contains_expected_providers(self, client):
        """Test that response contains expected LLM providers."""
        response = client.get("/api/v1/backtest/config/llm-providers")

        assert response.status_code == 200
        data = response.json()

        provider_names = [p["name"] for p in data["providers"]]

        # Check that common providers are present
        expected_providers = ["openrouter", "anthropic", "openai", "langchain"]
        for expected in expected_providers:
            assert expected in provider_names, f"Expected provider '{expected}' not found"

    def test_get_llm_providers_has_descriptions(self, client):
        """Test that all providers have non-empty descriptions."""
        response = client.get("/api/v1/backtest/config/llm-providers")

        assert response.status_code == 200
        data = response.json()

        for provider in data["providers"]:
            assert len(provider["description"]) > 0
            assert provider["available"] is True

    def test_get_llm_providers_idempotent(self, client):
        """Test that endpoint is idempotent."""
        response1 = client.get("/api/v1/backtest/config/llm-providers")
        response2 = client.get("/api/v1/backtest/config/llm-providers")

        assert response1.status_code == 200
        assert response2.status_code == 200
        assert response1.json() == response2.json()


class TestGetDataSourcesEndpoint:
    """Tests for GET /api/v1/backtest/config/data-sources endpoint."""

    def test_get_data_sources_success(self, client):
        """Test successful retrieval of data sources."""
        response = client.get("/api/v1/backtest/config/data-sources")

        assert response.status_code == 200
        data = response.json()

        # Check response structure
        assert "providers" in data
        assert isinstance(data["providers"], list)
        assert len(data["providers"]) > 0

        # Check data source structure
        source = data["providers"][0]
        assert "name" in source
        assert "description" in source
        assert "supported_exchanges" in source
        assert isinstance(source["name"], str)
        assert isinstance(source["description"], str)
        assert isinstance(source["supported_exchanges"], list)

    def test_get_data_sources_contains_expected_sources(self, client):
        """Test that response contains expected data sources."""
        response = client.get("/api/v1/backtest/config/data-sources")

        assert response.status_code == 200
        data = response.json()

        source_names = [s["name"] for s in data["providers"]]

        # Check that common data sources are present
        expected_sources = ["kis", "yfinance", "mock"]
        for expected in expected_sources:
            assert expected in source_names, f"Expected data source '{expected}' not found"

    def test_get_data_sources_has_exchanges(self, client):
        """Test that data sources have exchange information."""
        response = client.get("/api/v1/backtest/config/data-sources")

        assert response.status_code == 200
        data = response.json()

        for source in data["providers"]:
            assert len(source["description"]) > 0
            # At least some sources should have exchanges
            if source["name"] in ["kis", "yfinance"]:
                assert len(source["supported_exchanges"]) > 0

    def test_get_data_sources_kis_exchanges(self, client):
        """Test that KIS data source has correct exchanges."""
        response = client.get("/api/v1/backtest/config/data-sources")

        assert response.status_code == 200
        data = response.json()

        kis_source = next(
            (s for s in data["providers"] if s["name"] == "kis"),
            None,
        )
        assert kis_source is not None
        assert "KRX" in kis_source["supported_exchanges"]
        assert "NASDAQ" in kis_source["supported_exchanges"]

    def test_get_data_sources_idempotent(self, client):
        """Test that endpoint is idempotent."""
        response1 = client.get("/api/v1/backtest/config/data-sources")
        response2 = client.get("/api/v1/backtest/config/data-sources")

        assert response1.status_code == 200
        assert response2.status_code == 200
        assert response1.json() == response2.json()


class TestConfigEndpointsIntegration:
    """Integration tests for configuration endpoints."""

    def test_both_config_endpoints_accessible(self, client):
        """Test that both configuration endpoints are accessible."""
        llm_response = client.get("/api/v1/backtest/config/llm-providers")
        data_response = client.get("/api/v1/backtest/config/data-sources")

        assert llm_response.status_code == 200
        assert data_response.status_code == 200

        llm_data = llm_response.json()
        data_data = data_response.json()

        assert len(llm_data["providers"]) > 0
        assert len(data_data["providers"]) > 0

    def test_config_responses_have_different_structures(self, client):
        """Test that LLM and data source responses have appropriate structures."""
        llm_response = client.get("/api/v1/backtest/config/llm-providers")
        data_response = client.get("/api/v1/backtest/config/data-sources")

        llm_provider = llm_response.json()["providers"][0]
        data_source = data_response.json()["providers"][0]

        # LLM providers have 'available' field
        assert "available" in llm_provider

        # Data sources have 'supported_exchanges' field
        assert "supported_exchanges" in data_source

        # Both have name and description
        assert "name" in llm_provider and "name" in data_source
        assert "description" in llm_provider and "description" in data_source
