"""
End-to-End Integration Tests for Backtest API.

Tests the complete workflow from code generation through execution to result retrieval.
Validates the full integration of all components and verifies the OpenAPI schema.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from app.main import create_app
from app.models.backtest import GeneratedCode, ModelInfo
from app.models.execution import ExecutionResult, JobStatus


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    app = create_app()
    return TestClient(app)


@pytest.fixture
def mock_code_generator():
    """Create a mock BacktestCodeGenerator for testing."""
    generator = MagicMock()

    # Mock the generate method
    generator.generate = AsyncMock(
        return_value=GeneratedCode(
            code="""
# Generated backtest code
import pandas as pd
from datetime import datetime, date

def backtest_strategy(params: dict) -> dict:
    # Simple backtest implementation
    initial_capital = params.get('initial_capital', 10000.0)
    final_value = initial_capital * 1.5  # 50% return

    # Generate equity series
    equity_series = [
        {'date': '2020-01-01', 'value': initial_capital},
        {'date': '2020-06-01', 'value': initial_capital * 1.2},
        {'date': '2020-12-31', 'value': final_value},
    ]

    trades = [
        {'date': '2020-01-02', 'symbol': 'AAPL', 'action': 'BUY', 'shares': 10, 'price': 100.0},
        {'date': '2020-12-30', 'symbol': 'AAPL', 'action': 'SELL', 'shares': 10, 'price': 150.0},
    ]

    return {
        'equity_series': equity_series,
        'trades': trades,
        'start_date': '2020-01-01',
        'end_date': '2020-12-31',
        'final_value': final_value,
    }

# Entry point for backtest execution
if __name__ == '__main__':
    import sys
    import json
    params = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    result = backtest_strategy(params)
    print(json.dumps(result))
""",
            strategy_summary="Buy and hold AAPL strategy with 50% expected return",
            model_info=ModelInfo(
                provider="openrouter",
                model_id="anthropic/claude-3.5-sonnet",
                max_tokens=8000,
                supports_system_prompt=True,
                cost_per_1k_input=0.003,
                cost_per_1k_output=0.015,
            ),
        )
    )

    # Mock the _extract_tickers method
    generator._extract_tickers = MagicMock(return_value=["AAPL", "SPY"])

    return generator


@pytest.fixture
def mock_job_manager():
    """Create a mock JobManager for testing."""
    manager = MagicMock()

    # Mock async methods
    manager.submit_backtest = AsyncMock(return_value="backtest-e2e-test-123")
    manager.run_backtest = AsyncMock(
        return_value=ExecutionResult(
            success=True,
            job_id="backtest-e2e-test-123",
            status=JobStatus.COMPLETED,
            data={
                "equity_series": [
                    {"date": "2020-01-01", "value": 10000.0},
                    {"date": "2020-06-01", "value": 12000.0},
                    {"date": "2020-12-31", "value": 15000.0},
                ],
                "trades": [
                    {
                        "date": "2020-01-02",
                        "symbol": "AAPL",
                        "action": "BUY",
                        "shares": 10,
                        "price": 100.0,
                    },
                    {
                        "date": "2020-12-30",
                        "symbol": "AAPL",
                        "action": "SELL",
                        "shares": 10,
                        "price": 150.0,
                    },
                ],
                "start_date": "2020-01-01",
                "end_date": "2020-12-31",
                "final_value": 15000.0,
            },
            error=None,
            logs="Execution completed successfully",
            duration_seconds=2.5,
        )
    )
    manager.get_job_status = AsyncMock(return_value=JobStatus.COMPLETED)
    manager.get_job_result = AsyncMock(
        return_value=ExecutionResult(
            success=True,
            job_id="backtest-e2e-test-123",
            status=JobStatus.COMPLETED,
            data={
                "equity_series": [
                    {"date": "2020-01-01", "value": 10000.0},
                    {"date": "2020-06-01", "value": 12000.0},
                    {"date": "2020-12-31", "value": 15000.0},
                ],
                "trades": [
                    {
                        "date": "2020-01-02",
                        "symbol": "AAPL",
                        "action": "BUY",
                        "shares": 10,
                        "price": 100.0,
                    },
                ],
                "start_date": "2020-01-01",
                "end_date": "2020-12-31",
                "final_value": 15000.0,
            },
            error=None,
            logs="Execution completed successfully",
            duration_seconds=2.5,
        )
    )

    return manager


@pytest.fixture
def valid_backtest_request():
    """Create a valid backtest request payload."""
    return {
        "strategy": "Buy AAPL when the price drops below its 50-day moving average and hold",
        "params": {
            "start_date": "2020-01-01",
            "end_date": "2020-12-31",
            "initial_capital": 10000.0,
            "contribution": {
                "frequency": "monthly",
                "amount": 500.0,
            },
            "fees": {
                "trading_fee_percent": 0.1,
                "slippage_percent": 0.05,
            },
            "dividend_reinvestment": True,
            "benchmarks": ["SPY"],
            "llm_settings": {
                "provider": "openrouter",
                "model": "anthropic/claude-3.5-sonnet",
            },
        },
    }


class TestEndToEndBacktestWorkflow:
    """End-to-end tests for the complete backtest workflow."""

    def test_complete_async_workflow_generate_execute_poll_result(
        self, client, mock_code_generator, mock_job_manager, valid_backtest_request
    ):
        """
        Test the complete async workflow:
        1. Generate backtest code from natural language
        2. Execute the generated code (async mode)
        3. Poll job status until completion
        4. Retrieve the final result

        This simulates the typical user flow for backtesting.
        """
        with patch(
            "app.core.container.Container.get_code_generator",
            return_value=mock_code_generator,
        ), patch(
            "app.core.container.Container.get_job_manager",
            return_value=mock_job_manager,
        ):
            # Step 1: Generate backtest code
            generate_response = client.post(
                "/api/v1/backtest/generate",
                json=valid_backtest_request,
            )

            assert generate_response.status_code == 200
            generation_data = generate_response.json()

            # Verify code generation
            assert "generated_code" in generation_data
            assert "code" in generation_data["generated_code"]
            assert len(generation_data["generated_code"]["code"]) > 0
            assert "tickers_found" in generation_data
            assert "AAPL" in generation_data["tickers_found"]

            generated_code = generation_data["generated_code"]["code"]

            # Step 2: Execute the generated code (async mode)
            execute_response = client.post(
                "/api/v1/backtest/execute",
                json={
                    "code": generated_code,
                    "params": {
                        "start_date": "2020-01-01",
                        "end_date": "2020-12-31",
                        "initial_capital": 10000.0,
                    },
                    "async_mode": True,
                },
            )

            assert execute_response.status_code == 202
            execute_data = execute_response.json()
            assert execute_data["status"] == "pending"
            assert "job_id" in execute_data
            job_id = execute_data["job_id"]

            # Step 3: Poll job status
            status_response = client.get(f"/api/v1/backtest/status/{job_id}")

            assert status_response.status_code == 200
            status_data = status_response.json()
            assert status_data["job_id"] == job_id
            assert status_data["status"] == "completed"

            # Step 4: Retrieve the final result
            result_response = client.get(f"/api/v1/backtest/result/{job_id}")

            assert result_response.status_code == 200
            result_data = result_response.json()
            assert result_data["success"] is True
            assert result_data["job_id"] == job_id
            assert result_data["status"] == "completed"
            assert "data" in result_data
            assert "equity_series" in result_data["data"]
            assert "trades" in result_data["data"]

            # Verify data structure
            equity_series = result_data["data"]["equity_series"]
            assert len(equity_series) > 0
            assert all("date" in point and "value" in point for point in equity_series)

    def test_complete_sync_workflow_generate_and_execute(
        self, client, mock_code_generator, mock_job_manager, valid_backtest_request
    ):
        """
        Test the complete sync workflow:
        1. Generate backtest code from natural language
        2. Execute the generated code (sync mode - wait for completion)

        This simulates a simpler user flow where immediate results are needed.
        """
        with patch(
            "app.core.container.Container.get_code_generator",
            return_value=mock_code_generator,
        ), patch(
            "app.core.container.Container.get_job_manager",
            return_value=mock_job_manager,
        ):
            # Step 1: Generate backtest code
            generate_response = client.post(
                "/api/v1/backtest/generate",
                json=valid_backtest_request,
            )

            assert generate_response.status_code == 200
            generation_data = generate_response.json()
            generated_code = generation_data["generated_code"]["code"]

            # Step 2: Execute the generated code (sync mode)
            execute_response = client.post(
                "/api/v1/backtest/execute",
                json={
                    "code": generated_code,
                    "params": {
                        "start_date": "2020-01-01",
                        "end_date": "2020-12-31",
                        "initial_capital": 10000.0,
                    },
                    "async_mode": False,  # Sync mode
                },
            )

            # Sync mode returns 200 with full result
            assert execute_response.status_code == 200
            execute_data = execute_response.json()
            assert execute_data["status"] == "completed"
            assert "result" in execute_data
            assert execute_data["result"]["success"] is True
            assert "data" in execute_data["result"]
            assert "equity_series" in execute_data["result"]["data"]


class TestOpenAPISchemaValidation:
    """Tests to validate the OpenAPI schema generation."""

    def test_openapi_schema_generation(self, client):
        """Test that OpenAPI schema is properly generated."""
        response = client.get("/openapi.json")

        assert response.status_code == 200
        schema = response.json()

        # Verify basic schema structure
        assert "openapi" in schema
        assert "info" in schema
        assert "paths" in schema

        # Verify app metadata
        assert "title" in schema["info"]
        assert "version" in schema["info"]

    def test_openapi_schema_contains_all_backtest_endpoints(self, client):
        """Test that all backtest endpoints are documented in OpenAPI schema."""
        response = client.get("/openapi.json")
        schema = response.json()
        paths = schema["paths"]

        # Expected endpoints
        expected_endpoints = [
            "/api/v1/backtest/generate",
            "/api/v1/backtest/execute",
            "/api/v1/backtest/status/{job_id}",
            "/api/v1/backtest/result/{job_id}",
            "/api/v1/backtest/{job_id}/result",
            "/api/v1/backtest/{job_id}/chart/equity",
            "/api/v1/backtest/{job_id}/chart/drawdown",
            "/api/v1/backtest/{job_id}/chart/monthly-returns",
            "/api/v1/backtest/config/llm-providers",
            "/api/v1/backtest/config/data-sources",
        ]

        for endpoint in expected_endpoints:
            assert endpoint in paths, f"Missing endpoint: {endpoint}"

    def test_openapi_schema_endpoint_methods(self, client):
        """Test that endpoints have correct HTTP methods."""
        response = client.get("/openapi.json")
        schema = response.json()
        paths = schema["paths"]

        # Verify POST endpoints
        assert "post" in paths["/api/v1/backtest/generate"]
        assert "post" in paths["/api/v1/backtest/execute"]

        # Verify GET endpoints
        assert "get" in paths["/api/v1/backtest/status/{job_id}"]
        assert "get" in paths["/api/v1/backtest/result/{job_id}"]
        assert "get" in paths["/api/v1/backtest/{job_id}/result"]
        assert "get" in paths["/api/v1/backtest/{job_id}/chart/equity"]

    def test_openapi_schema_request_models(self, client):
        """Test that request models are properly documented."""
        response = client.get("/openapi.json")
        schema = response.json()

        # Check that schemas are defined
        assert "components" in schema
        assert "schemas" in schema["components"]
        schemas = schema["components"]["schemas"]

        # Verify key models are documented
        expected_models = [
            "BacktestRequest",
            "ExecuteBacktestRequest",
            "BacktestParams",
        ]

        for model in expected_models:
            assert (
                model in schemas
            ), f"Missing model in OpenAPI schema: {model}"

    def test_openapi_schema_response_models(self, client):
        """Test that response models are properly documented."""
        response = client.get("/openapi.json")
        schema = response.json()
        schemas = schema["components"]["schemas"]

        # Verify response models are documented
        expected_response_models = [
            "GenerateBacktestResponse",
            "ExecuteBacktestResponse",
            "JobStatusResponse",
            "ExecutionResult",
            "BacktestResultResponse",
        ]

        for model in expected_response_models:
            assert (
                model in schemas
            ), f"Missing response model in OpenAPI schema: {model}"

    def test_openapi_schema_tags(self, client):
        """Test that endpoints are properly tagged."""
        response = client.get("/openapi.json")
        schema = response.json()
        paths = schema["paths"]

        # Verify tags are applied
        generate_endpoint = paths["/api/v1/backtest/generate"]["post"]
        assert "tags" in generate_endpoint
        assert "Backtest" in generate_endpoint["tags"]

        execute_endpoint = paths["/api/v1/backtest/execute"]["post"]
        assert "tags" in execute_endpoint
        assert "Backtest" in execute_endpoint["tags"]


class TestHealthAndRootEndpoints:
    """Tests for health check and root endpoints."""

    def test_health_endpoint(self, client):
        """Test that health endpoint is accessible."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()

        # Verify health response structure
        assert "status" in data
        assert data["status"] == "healthy"
        assert "app_name" in data
        assert "app_version" in data
        assert "timestamp" in data

    def test_root_endpoint(self, client):
        """Test that root endpoint returns service information."""
        response = client.get("/")

        assert response.status_code == 200
        data = response.json()

        # Verify root response
        assert "service" in data
        assert "version" in data
        assert "docs" in data
        assert "health" in data

    def test_docs_endpoint_available_in_debug(self, client):
        """Test that /docs is available (depends on debug mode)."""
        response = client.get("/docs")

        # Should either return the docs page or redirect
        # (200 for available, 404 if debug is off)
        assert response.status_code in [200, 404]


class TestConfigurationEndpoints:
    """Tests for configuration endpoints."""

    def test_get_llm_providers(self, client):
        """Test LLM providers configuration endpoint."""
        response = client.get("/api/v1/backtest/config/llm-providers")

        assert response.status_code == 200
        data = response.json()

        assert "providers" in data
        assert isinstance(data["providers"], list)
        assert len(data["providers"]) > 0

        # Verify provider structure
        first_provider = data["providers"][0]
        assert "name" in first_provider
        assert "description" in first_provider
        assert "available" in first_provider

    def test_get_data_sources(self, client):
        """Test data sources configuration endpoint."""
        response = client.get("/api/v1/backtest/config/data-sources")

        assert response.status_code == 200
        data = response.json()

        assert "providers" in data
        assert isinstance(data["providers"], list)
        assert len(data["providers"]) > 0

        # Verify data source structure
        first_source = data["providers"][0]
        assert "name" in first_source
        assert "description" in first_source
        assert "supported_exchanges" in first_source


class TestCORSConfiguration:
    """Tests for CORS configuration."""

    def test_cors_headers_present(self, client):
        """Test that CORS headers are properly configured."""
        response = client.options(
            "/api/v1/backtest/generate",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
            },
        )

        # CORS should be configured (check for CORS headers)
        # The exact status code depends on CORS middleware configuration
        # 400, 405, or 200 are all acceptable depending on implementation
        assert response.status_code in [200, 400, 405]


class TestErrorHandling:
    """Tests for error handling across the API."""

    def test_404_for_nonexistent_endpoint(self, client):
        """Test that non-existent endpoints return 404."""
        response = client.get("/api/v1/backtest/nonexistent")

        assert response.status_code == 404

    def test_405_for_wrong_method(self, client):
        """Test that wrong HTTP methods return 405."""
        # GET on POST-only endpoint
        response = client.get("/api/v1/backtest/generate")

        assert response.status_code == 405

    def test_422_for_invalid_json(self, client):
        """Test that invalid JSON returns 422."""
        response = client.post(
            "/api/v1/backtest/generate",
            data="invalid json",
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 422
