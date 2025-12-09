"""
Tests for the dependency injection container.
"""

import pytest

from app.core.config import Settings
from app.core.container import (
    Container,
    clear_container_cache,
    get_container,
    get_http_client_dep,
    get_settings_dep,
)


class TestContainer:
    """Tests for Container class."""

    def test_container_settings(self, test_settings: Settings) -> None:
        """Test container provides settings."""
        container = Container(settings=test_settings)
        assert container.settings is test_settings

    def test_container_settings_lazy_load(self) -> None:
        """Test container lazily loads settings if not provided."""
        container = Container()
        # Should not raise, settings loaded on access
        settings = container.settings
        assert settings is not None

    def test_http_client_singleton(self, test_container: Container) -> None:
        """Test HTTP client is singleton within container."""
        client1 = test_container.get_http_client()
        client2 = test_container.get_http_client()
        assert client1 is client2

    @pytest.mark.asyncio
    async def test_close_http_client(self, test_container: Container) -> None:
        """Test HTTP client can be closed."""
        client = test_container.get_http_client()
        assert client is not None

        await test_container.close_http_client()
        # After closing, internal reference should be None
        assert test_container._http_client is None

    @pytest.mark.asyncio
    async def test_startup_initializes_resources(
        self, test_container: Container
    ) -> None:
        """Test startup initializes resources."""
        await test_container.startup()

        # After startup, resources should be initialized
        assert test_container._settings is not None
        assert test_container._http_client is not None

    @pytest.mark.asyncio
    async def test_shutdown_cleans_up(self, test_container: Container) -> None:
        """Test shutdown cleans up resources."""
        await test_container.startup()
        await test_container.shutdown()

        # After shutdown, HTTP client should be closed
        assert test_container._http_client is None


class TestGetContainer:
    """Tests for get_container function."""

    def test_returns_singleton(self) -> None:
        """Test get_container returns singleton."""
        container1 = get_container()
        container2 = get_container()
        assert container1 is container2

    def test_cache_clear_resets(self) -> None:
        """Test cache clear creates new instance."""
        container1 = get_container()
        clear_container_cache()
        container2 = get_container()
        assert container1 is not container2


class TestDependencyFunctions:
    """Tests for FastAPI dependency functions."""

    def test_get_settings_dep(self) -> None:
        """Test get_settings_dep returns settings."""
        settings = get_settings_dep()
        assert isinstance(settings, Settings)

    def test_get_http_client_dep(self) -> None:
        """Test get_http_client_dep returns HTTP client."""
        import httpx

        client = get_http_client_dep()
        assert isinstance(client, httpx.AsyncClient)
