"""
Integration test for the health check endpoint.

Runs against the FastAPI test client — no database connection required.
"""

from fastapi.testclient import TestClient

from app import app


def test_health_check() -> None:
    """Health endpoint returns 200 with ok status."""
    # TestClient requires no env vars for the health route
    import unittest.mock as mock
    with mock.patch("api.config.get_settings") as mock_settings:
        mock_settings.return_value = mock.MagicMock(
            cors_origins=["http://localhost:3000"],
            is_production=False,
        )
        client = TestClient(app)
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
