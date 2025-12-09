"""
Tests for the health endpoint and FastAPI application.
"""

from fastapi.testclient import TestClient

from app.main import app


class TestHealthEndpoint:
    """Tests for the /health endpoint."""

    def test_health_returns_200(self, client: TestClient) -> None:
        """Test that health endpoint returns 200 OK."""
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_response_structure(self, client: TestClient) -> None:
        """Test that health response has expected structure."""
        response = client.get("/health")
        data = response.json()

        assert "status" in data
        assert "app_name" in data
        assert "app_version" in data
        assert "timestamp" in data
        assert "debug" in data
        assert "llm_provider" in data
        assert "data_provider" in data
        assert "execution_provider" in data

    def test_health_status_healthy(self, client: TestClient) -> None:
        """Test that health status is 'healthy'."""
        response = client.get("/health")
        data = response.json()
        assert data["status"] == "healthy"

    def test_health_timestamp_format(self, client: TestClient) -> None:
        """Test that timestamp is ISO format."""
        response = client.get("/health")
        data = response.json()

        # Should be able to parse ISO timestamp
        timestamp = data["timestamp"]
        assert "T" in timestamp  # ISO format includes T separator
        assert ":" in timestamp  # Contains time

    def test_health_providers_are_strings(self, client: TestClient) -> None:
        """Test that provider values are strings."""
        response = client.get("/health")
        data = response.json()

        assert isinstance(data["llm_provider"], str)
        assert isinstance(data["data_provider"], str)
        assert isinstance(data["execution_provider"], str)


class TestRootEndpoint:
    """Tests for the / root endpoint."""

    def test_root_returns_200(self, client: TestClient) -> None:
        """Test that root endpoint returns 200 OK."""
        response = client.get("/")
        assert response.status_code == 200

    def test_root_response_structure(self, client: TestClient) -> None:
        """Test that root response has expected structure."""
        response = client.get("/")
        data = response.json()

        assert "service" in data
        assert "version" in data
        assert "health" in data

    def test_root_health_link(self, client: TestClient) -> None:
        """Test that root response includes health endpoint link."""
        response = client.get("/")
        data = response.json()
        assert data["health"] == "/health"


class TestApplicationLifespan:
    """Tests for application lifespan management."""

    def test_app_startup_shutdown(self) -> None:
        """Test that app properly starts up and shuts down."""
        # Using TestClient context manager handles lifespan
        with TestClient(app) as client:
            response = client.get("/health")
            assert response.status_code == 200
        # After context exit, shutdown should have completed without error


class TestContainerIntegration:
    """Tests for container integration with FastAPI."""

    def test_settings_injected(self, client: TestClient) -> None:
        """Test that settings are properly injected into endpoints."""
        response = client.get("/health")
        data = response.json()

        # These values come from injected settings
        assert data["app_name"] == "Natural Language Backtesting Service"
        assert data["app_version"] == "0.1.0"
