"""
Tests for the backtest execution endpoints.

Tests cover:
- POST /api/v1/backtest/execute (async and sync modes)
- GET /api/v1/backtest/status/{job_id}
- GET /api/v1/backtest/result/{job_id}
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from app.main import create_app
from app.models.execution import ExecutionResult, JobStatus
from app.services.execution.storage import JobNotFoundError


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    app = create_app()
    return TestClient(app)


@pytest.fixture
def mock_job_manager():
    """Create a mock JobManager for testing."""
    manager = MagicMock()

    # Mock async methods
    manager.submit_backtest = AsyncMock(return_value="backtest-test123")
    manager.run_backtest = AsyncMock(
        return_value=ExecutionResult(
            success=True,
            job_id="backtest-sync456",
            status=JobStatus.COMPLETED,
            data={"portfolio_value": 150000, "returns": 0.5},
            error=None,
            logs="Test execution logs",
            duration_seconds=2.5,
        )
    )
    manager.get_job_status = AsyncMock(return_value=JobStatus.RUNNING)
    manager.get_job_result = AsyncMock(
        return_value=ExecutionResult(
            success=True,
            job_id="backtest-result789",
            status=JobStatus.COMPLETED,
            data={"portfolio_value": 150000},
            error=None,
            logs="Logs",
            duration_seconds=3.0,
        )
    )

    return manager


class TestExecuteBacktestEndpoint:
    """Tests for POST /api/v1/backtest/execute endpoint."""

    def test_execute_backtest_async_mode_success(self, client, mock_job_manager):
        """Test successful async execution (default mode)."""
        with patch(
            "app.core.container.Container.get_job_manager",
            return_value=mock_job_manager,
        ):
            response = client.post(
                "/api/v1/backtest/execute",
                json={
                    "code": "print('Hello World')",
                    "params": {"ticker": "AAPL"},
                    "async_mode": True,
                },
            )

            assert response.status_code == 202
            data = response.json()
            assert data["job_id"] == "backtest-test123"
            assert data["status"] == "pending"
            assert "submitted successfully" in data["message"].lower()
            assert data["result"] is None

            # Verify JobManager was called correctly
            mock_job_manager.submit_backtest.assert_called_once()
            call_args = mock_job_manager.submit_backtest.call_args
            assert call_args.kwargs["code"] == "print('Hello World')"
            assert call_args.kwargs["params"] == {"ticker": "AAPL"}

    def test_execute_backtest_sync_mode_success(self, client, mock_job_manager):
        """Test successful sync execution."""
        with patch(
            "app.core.container.Container.get_job_manager",
            return_value=mock_job_manager,
        ):
            response = client.post(
                "/api/v1/backtest/execute",
                json={
                    "code": "print('Sync execution')",
                    "params": {},
                    "async_mode": False,
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["job_id"] == "backtest-sync456"
            assert data["status"] == "completed"
            assert "completed successfully" in data["message"].lower()
            assert data["result"] is not None
            assert data["result"]["success"] is True
            assert data["result"]["data"]["portfolio_value"] == 150000

            # Verify JobManager was called correctly
            mock_job_manager.run_backtest.assert_called_once()

    def test_execute_backtest_sync_mode_failure(self, client, mock_job_manager):
        """Test sync execution with failure result."""
        mock_job_manager.run_backtest = AsyncMock(
            return_value=ExecutionResult(
                success=False,
                job_id="backtest-fail789",
                status=JobStatus.FAILED,
                data=None,
                error="Division by zero",
                logs="Error traceback...",
                duration_seconds=1.0,
            )
        )

        with patch(
            "app.core.container.Container.get_job_manager",
            return_value=mock_job_manager,
        ):
            response = client.post(
                "/api/v1/backtest/execute",
                json={
                    "code": "x = 1 / 0",
                    "params": {},
                    "async_mode": False,
                },
            )

            assert response.status_code == 200  # Still 200, but result indicates failure
            data = response.json()
            assert data["status"] == "failed"
            assert "failed" in data["message"].lower()
            assert "Division by zero" in data["message"]
            assert data["result"]["success"] is False

    def test_execute_backtest_with_timeout(self, client, mock_job_manager):
        """Test execution with custom timeout."""
        with patch(
            "app.core.container.Container.get_job_manager",
            return_value=mock_job_manager,
        ):
            response = client.post(
                "/api/v1/backtest/execute",
                json={
                    "code": "import time; time.sleep(10)",
                    "params": {},
                    "timeout": 300,
                },
            )

            assert response.status_code == 202

            # Verify timeout was passed
            call_args = mock_job_manager.submit_backtest.call_args
            assert call_args.kwargs["timeout"] == 300

    def test_execute_backtest_missing_code(self, client, mock_job_manager):
        """Test validation error when both code and code_reference are missing."""
        with patch(
            "app.core.container.Container.get_job_manager",
            return_value=mock_job_manager,
        ):
            response = client.post(
                "/api/v1/backtest/execute",
                json={"params": {}},
            )

            assert response.status_code == 400
            assert "must provide either" in response.json()["detail"].lower()

    def test_execute_backtest_both_code_and_reference(self, client, mock_job_manager):
        """Test validation error when both code and code_reference are provided."""
        with patch(
            "app.core.container.Container.get_job_manager",
            return_value=mock_job_manager,
        ):
            response = client.post(
                "/api/v1/backtest/execute",
                json={
                    "code": "print('test')",
                    "code_reference": "ref-123",
                    "params": {},
                },
            )

            assert response.status_code == 400
            assert "cannot provide both" in response.json()["detail"].lower()

    def test_execute_backtest_empty_code(self, client, mock_job_manager):
        """Test validation error for empty code string."""
        with patch(
            "app.core.container.Container.get_job_manager",
            return_value=mock_job_manager,
        ):
            response = client.post(
                "/api/v1/backtest/execute",
                json={
                    "code": "   ",  # Whitespace only
                    "params": {},
                },
            )

            assert response.status_code == 422  # Pydantic validation error

    def test_execute_backtest_code_reference_not_implemented(self, client, mock_job_manager):
        """Test that code_reference raises NotImplementedError."""
        with patch(
            "app.core.container.Container.get_job_manager",
            return_value=mock_job_manager,
        ):
            response = client.post(
                "/api/v1/backtest/execute",
                json={
                    "code_reference": "ref-123",
                    "params": {},
                },
            )

            assert response.status_code == 501  # Not Implemented
            assert "not yet implemented" in response.json()["detail"].lower()

    def test_execute_backtest_invalid_timeout(self, client, mock_job_manager):
        """Test validation error for invalid timeout."""
        with patch(
            "app.core.container.Container.get_job_manager",
            return_value=mock_job_manager,
        ):
            response = client.post(
                "/api/v1/backtest/execute",
                json={
                    "code": "print('test')",
                    "params": {},
                    "timeout": 700,  # Exceeds max of 600
                },
            )

            assert response.status_code == 422

    def test_execute_backtest_job_manager_exception(self, client, mock_job_manager):
        """Test handling of JobManager exceptions."""
        mock_job_manager.submit_backtest = AsyncMock(
            side_effect=Exception("Backend error")
        )

        with patch(
            "app.core.container.Container.get_job_manager",
            return_value=mock_job_manager,
        ):
            response = client.post(
                "/api/v1/backtest/execute",
                json={
                    "code": "print('test')",
                    "params": {},
                },
            )

            assert response.status_code == 500
            assert "failed to execute" in response.json()["detail"].lower()


class TestGetJobStatusEndpoint:
    """Tests for GET /api/v1/backtest/status/{job_id} endpoint."""

    def test_get_job_status_success(self, client, mock_job_manager):
        """Test successful job status retrieval."""
        with patch(
            "app.core.container.Container.get_job_manager",
            return_value=mock_job_manager,
        ):
            response = client.get("/api/v1/backtest/status/backtest-test123")

            assert response.status_code == 200
            data = response.json()
            assert data["job_id"] == "backtest-test123"
            assert data["status"] == "running"

            mock_job_manager.get_job_status.assert_called_once_with("backtest-test123")

    def test_get_job_status_not_found(self, client, mock_job_manager):
        """Test job status retrieval for non-existent job."""
        mock_job_manager.get_job_status = AsyncMock(
            side_effect=JobNotFoundError("nonexistent-job")
        )

        with patch(
            "app.core.container.Container.get_job_manager",
            return_value=mock_job_manager,
        ):
            response = client.get("/api/v1/backtest/status/nonexistent-job")

            assert response.status_code == 404
            assert "not found" in response.json()["detail"].lower()


class TestGetJobResultEndpoint:
    """Tests for GET /api/v1/backtest/result/{job_id} endpoint."""

    def test_get_job_result_success(self, client, mock_job_manager):
        """Test successful job result retrieval."""
        with patch(
            "app.core.container.Container.get_job_manager",
            return_value=mock_job_manager,
        ):
            response = client.get("/api/v1/backtest/result/backtest-result789")

            assert response.status_code == 200
            data = response.json()
            assert data["job_id"] == "backtest-result789"
            assert data["status"] == "completed"
            assert data["success"] is True
            assert data["data"]["portfolio_value"] == 150000

            mock_job_manager.get_job_result.assert_called_once_with(
                "backtest-result789"
            )

    def test_get_job_result_not_found(self, client, mock_job_manager):
        """Test job result retrieval for non-existent job."""
        mock_job_manager.get_job_result = AsyncMock(
            side_effect=JobNotFoundError("nonexistent-job")
        )

        with patch(
            "app.core.container.Container.get_job_manager",
            return_value=mock_job_manager,
        ):
            response = client.get("/api/v1/backtest/result/nonexistent-job")

            assert response.status_code == 404
            assert "not found" in response.json()["detail"].lower()


class TestRequestValidation:
    """Tests for ExecuteBacktestRequest validation."""

    def test_code_max_length_validation(self, client, mock_job_manager):
        """Test that code exceeding max length is rejected."""
        with patch(
            "app.core.container.Container.get_job_manager",
            return_value=mock_job_manager,
        ):
            # Create code that exceeds 100000 characters
            long_code = "x = 1\n" * 20000  # Approx 120000 chars

            response = client.post(
                "/api/v1/backtest/execute",
                json={
                    "code": long_code,
                    "params": {},
                },
            )

            assert response.status_code == 422

    def test_default_async_mode(self, client, mock_job_manager):
        """Test that async_mode defaults to True."""
        with patch(
            "app.core.container.Container.get_job_manager",
            return_value=mock_job_manager,
        ):
            response = client.post(
                "/api/v1/backtest/execute",
                json={
                    "code": "print('test')",
                    "params": {},
                    # async_mode not specified
                },
            )

            assert response.status_code == 202  # Async mode (202 Accepted)
            mock_job_manager.submit_backtest.assert_called_once()

    def test_default_params(self, client, mock_job_manager):
        """Test that params defaults to empty dict."""
        with patch(
            "app.core.container.Container.get_job_manager",
            return_value=mock_job_manager,
        ):
            response = client.post(
                "/api/v1/backtest/execute",
                json={
                    "code": "print('test')",
                    # params not specified
                },
            )

            assert response.status_code == 202
            call_args = mock_job_manager.submit_backtest.call_args
            assert call_args.kwargs["params"] == {}


class TestEndpointIntegration:
    """Integration tests for the complete endpoint workflow."""

    def test_submit_check_status_get_result_workflow(self, client, mock_job_manager):
        """Test the complete workflow: submit -> check status -> get result."""
        job_id = "backtest-workflow123"

        # Setup mock to return different statuses
        mock_job_manager.submit_backtest = AsyncMock(return_value=job_id)
        mock_job_manager.get_job_status = AsyncMock(return_value=JobStatus.COMPLETED)
        mock_job_manager.get_job_result = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                job_id=job_id,
                status=JobStatus.COMPLETED,
                data={"final_value": 200000},
                error=None,
                logs="Execution completed",
                duration_seconds=5.0,
            )
        )

        with patch(
            "app.core.container.Container.get_job_manager",
            return_value=mock_job_manager,
        ):
            # Step 1: Submit backtest
            submit_response = client.post(
                "/api/v1/backtest/execute",
                json={"code": "print('workflow test')", "params": {}},
            )
            assert submit_response.status_code == 202
            assert submit_response.json()["job_id"] == job_id

            # Step 2: Check status
            status_response = client.get(f"/api/v1/backtest/status/{job_id}")
            assert status_response.status_code == 200
            assert status_response.json()["status"] == "completed"

            # Step 3: Get result
            result_response = client.get(f"/api/v1/backtest/result/{job_id}")
            assert result_response.status_code == 200
            result_data = result_response.json()
            assert result_data["success"] is True
            assert result_data["data"]["final_value"] == 200000
