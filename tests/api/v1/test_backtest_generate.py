"""
Tests for the backtest code generation endpoint.

Tests cover:
- POST /api/v1/backtest/generate
"""

import pytest
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.main import create_app
from app.models.backtest import GeneratedCode, ModelInfo
from app.services.code_generator import (
    CodeGenerationError,
    DataAvailabilityError,
    ValidationError,
)


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
            code="# Generated backtest code\nclass MyStrategy(Strategy):\n    pass",
            strategy_summary="Buy and hold strategy for AAPL with monthly contributions",
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
def valid_backtest_request():
    """Create a valid backtest request payload."""
    return {
        "strategy": "Buy AAPL when the price drops below its 50-day moving average",
        "params": {
            "start_date": "2020-01-01",
            "end_date": "2023-12-31",
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


class TestGenerateBacktestCodeEndpoint:
    """Tests for POST /api/v1/backtest/generate endpoint."""

    def test_generate_backtest_code_success(
        self, client, mock_code_generator, valid_backtest_request
    ):
        """Test successful code generation."""
        with patch(
            "app.core.container.Container.get_code_generator",
            return_value=mock_code_generator,
        ):
            response = client.post(
                "/api/v1/backtest/generate",
                json=valid_backtest_request,
            )

            assert response.status_code == 200
            data = response.json()

            # Check response structure
            assert "generated_code" in data
            assert "tickers_found" in data
            assert "generation_time_seconds" in data

            # Check generated code
            generated = data["generated_code"]
            assert "code" in generated
            assert "strategy_summary" in generated
            assert "model_info" in generated
            assert len(generated["code"]) > 0

            # Check tickers
            assert "AAPL" in data["tickers_found"]
            assert "SPY" in data["tickers_found"]

            # Check generation time
            assert data["generation_time_seconds"] >= 0

            # Verify generator was called
            mock_code_generator.generate.assert_called_once()

    def test_generate_backtest_code_invalid_strategy(
        self, client, mock_code_generator
    ):
        """Test validation error for invalid strategy (too short)."""
        with patch(
            "app.core.container.Container.get_code_generator",
            return_value=mock_code_generator,
        ):
            response = client.post(
                "/api/v1/backtest/generate",
                json={
                    "strategy": "Buy",  # Too short (min 10 chars)
                    "params": {
                        "start_date": "2020-01-01",
                        "end_date": "2023-12-31",
                        "initial_capital": 10000.0,
                        "benchmarks": ["SPY"],
                    },
                },
            )

            assert response.status_code == 422  # Pydantic validation error

    def test_generate_backtest_code_missing_params(self, client, mock_code_generator):
        """Test validation error for missing required params."""
        with patch(
            "app.core.container.Container.get_code_generator",
            return_value=mock_code_generator,
        ):
            response = client.post(
                "/api/v1/backtest/generate",
                json={
                    "strategy": "Buy AAPL and hold",
                    # Missing params
                },
            )

            assert response.status_code == 422

    def test_generate_backtest_code_invalid_dates(
        self, client, mock_code_generator, valid_backtest_request
    ):
        """Test validation error for invalid date range."""
        with patch(
            "app.core.container.Container.get_code_generator",
            return_value=mock_code_generator,
        ):
            # Start date after end date
            invalid_request = valid_backtest_request.copy()
            invalid_request["params"]["start_date"] = "2024-01-01"
            invalid_request["params"]["end_date"] = "2020-01-01"

            response = client.post(
                "/api/v1/backtest/generate",
                json=invalid_request,
            )

            assert response.status_code == 422

    def test_generate_backtest_code_validation_error(
        self, client, mock_code_generator, valid_backtest_request
    ):
        """Test handling of code validation errors."""
        mock_code_generator.generate = AsyncMock(
            side_effect=ValidationError(
                "Generated code failed validation",
                errors=["Syntax error", "Missing required method"],
            )
        )

        with patch(
            "app.core.container.Container.get_code_generator",
            return_value=mock_code_generator,
        ):
            response = client.post(
                "/api/v1/backtest/generate",
                json=valid_backtest_request,
            )

            assert response.status_code == 400
            assert "validation" in response.json()["detail"].lower()

    def test_generate_backtest_code_data_availability_error(
        self, client, mock_code_generator, valid_backtest_request
    ):
        """Test handling of data availability errors."""
        mock_code_generator.generate = AsyncMock(
            side_effect=DataAvailabilityError(
                "No data available for ticker",
                tickers=["INVALID_TICKER"],
            )
        )

        with patch(
            "app.core.container.Container.get_code_generator",
            return_value=mock_code_generator,
        ):
            response = client.post(
                "/api/v1/backtest/generate",
                json=valid_backtest_request,
            )

            assert response.status_code == 400
            assert "data not available" in response.json()["detail"].lower()

    def test_generate_backtest_code_generation_error(
        self, client, mock_code_generator, valid_backtest_request
    ):
        """Test handling of generic code generation errors."""
        mock_code_generator.generate = AsyncMock(
            side_effect=CodeGenerationError("LLM generation failed")
        )

        with patch(
            "app.core.container.Container.get_code_generator",
            return_value=mock_code_generator,
        ):
            response = client.post(
                "/api/v1/backtest/generate",
                json=valid_backtest_request,
            )

            assert response.status_code == 400

    def test_generate_backtest_code_unexpected_error(
        self, client, mock_code_generator, valid_backtest_request
    ):
        """Test handling of unexpected errors."""
        mock_code_generator.generate = AsyncMock(
            side_effect=Exception("Unexpected error")
        )

        with patch(
            "app.core.container.Container.get_code_generator",
            return_value=mock_code_generator,
        ):
            response = client.post(
                "/api/v1/backtest/generate",
                json=valid_backtest_request,
            )

            assert response.status_code == 500
            assert "failed" in response.json()["detail"].lower()

    def test_generate_backtest_code_model_info_structure(
        self, client, mock_code_generator, valid_backtest_request
    ):
        """Test that model info is properly structured in response."""
        with patch(
            "app.core.container.Container.get_code_generator",
            return_value=mock_code_generator,
        ):
            response = client.post(
                "/api/v1/backtest/generate",
                json=valid_backtest_request,
            )

            assert response.status_code == 200
            model_info = response.json()["generated_code"]["model_info"]

            # Check all required model info fields
            assert "provider" in model_info
            assert "model_id" in model_info
            assert "max_tokens" in model_info
            assert "supports_system_prompt" in model_info
            assert "cost_per_1k_input" in model_info
            assert "cost_per_1k_output" in model_info

    def test_generate_backtest_code_empty_benchmarks(
        self, client, mock_code_generator, valid_backtest_request
    ):
        """Test validation error for empty benchmarks list."""
        with patch(
            "app.core.container.Container.get_code_generator",
            return_value=mock_code_generator,
        ):
            invalid_request = valid_backtest_request.copy()
            invalid_request["params"]["benchmarks"] = []

            response = client.post(
                "/api/v1/backtest/generate",
                json=invalid_request,
            )

            assert response.status_code == 422

    def test_generate_backtest_code_negative_capital(
        self, client, mock_code_generator, valid_backtest_request
    ):
        """Test validation error for negative initial capital."""
        with patch(
            "app.core.container.Container.get_code_generator",
            return_value=mock_code_generator,
        ):
            invalid_request = valid_backtest_request.copy()
            invalid_request["params"]["initial_capital"] = -1000.0

            response = client.post(
                "/api/v1/backtest/generate",
                json=invalid_request,
            )

            assert response.status_code == 422

    def test_generate_backtest_code_default_contribution(
        self, client, mock_code_generator, valid_backtest_request
    ):
        """Test that contribution defaults work correctly."""
        with patch(
            "app.core.container.Container.get_code_generator",
            return_value=mock_code_generator,
        ):
            # Remove contribution from request
            request_without_contribution = valid_backtest_request.copy()
            del request_without_contribution["params"]["contribution"]

            response = client.post(
                "/api/v1/backtest/generate",
                json=request_without_contribution,
            )

            assert response.status_code == 200

    def test_generate_backtest_code_default_fees(
        self, client, mock_code_generator, valid_backtest_request
    ):
        """Test that fee defaults work correctly."""
        with patch(
            "app.core.container.Container.get_code_generator",
            return_value=mock_code_generator,
        ):
            # Remove fees from request
            request_without_fees = valid_backtest_request.copy()
            del request_without_fees["params"]["fees"]

            response = client.post(
                "/api/v1/backtest/generate",
                json=request_without_fees,
            )

            assert response.status_code == 200

    def test_generate_backtest_code_multiple_tickers(
        self, client, mock_code_generator, valid_backtest_request
    ):
        """Test code generation with multiple tickers."""
        mock_code_generator._extract_tickers = MagicMock(
            return_value=["AAPL", "TSLA", "GOOGL", "SPY"]
        )

        with patch(
            "app.core.container.Container.get_code_generator",
            return_value=mock_code_generator,
        ):
            request_with_multiple = valid_backtest_request.copy()
            request_with_multiple["strategy"] = (
                "Buy AAPL, TSLA, and GOOGL when prices drop"
            )

            response = client.post(
                "/api/v1/backtest/generate",
                json=request_with_multiple,
            )

            assert response.status_code == 200
            tickers = response.json()["tickers_found"]
            assert len(tickers) == 4
            assert "AAPL" in tickers
            assert "TSLA" in tickers
            assert "GOOGL" in tickers
            assert "SPY" in tickers


class TestGenerateEndpointIntegration:
    """Integration tests for code generation endpoint."""

    def test_generate_full_workflow(
        self, client, mock_code_generator, valid_backtest_request
    ):
        """Test complete generation workflow."""
        with patch(
            "app.core.container.Container.get_code_generator",
            return_value=mock_code_generator,
        ):
            # Generate code
            response = client.post(
                "/api/v1/backtest/generate",
                json=valid_backtest_request,
            )

            assert response.status_code == 200
            data = response.json()

            # Verify all components are present
            assert data["generated_code"]["code"] is not None
            assert data["generated_code"]["strategy_summary"] is not None
            assert data["generated_code"]["model_info"] is not None
            assert len(data["tickers_found"]) > 0
            assert data["generation_time_seconds"] >= 0

            # Verify generator was called with correct request
            call_args = mock_code_generator.generate.call_args
            assert call_args is not None

    def test_generate_with_different_llm_providers(
        self, client, mock_code_generator, valid_backtest_request
    ):
        """Test generation with different LLM providers."""
        providers = ["openrouter", "anthropic", "openai"]

        with patch(
            "app.core.container.Container.get_code_generator",
            return_value=mock_code_generator,
        ):
            for provider in providers:
                request = valid_backtest_request.copy()
                request["params"]["llm_settings"]["provider"] = provider

                response = client.post(
                    "/api/v1/backtest/generate",
                    json=request,
                )

                # All should succeed since we're mocking the generator
                assert response.status_code == 200
