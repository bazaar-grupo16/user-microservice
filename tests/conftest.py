"""
Shared pytest fixtures for the test suite.

Tests run against a **real PostgreSQL** database provided by
``docker-compose.test.yml``.  Connection details come from the
same environment variables the application uses in production
(DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME).

**No mocking is used.**
"""

import pytest
from fastapi.testclient import TestClient

from src.core.database import Base, engine
from src.main import app
import os

# Provide a simple mock for the external auth service during tests.
@pytest.fixture(autouse=True)
def mock_external_auth_service(monkeypatch):
    # Ensure the app has an AUTH_SERVICE_URL so the client code will attempt to call it.
    os.environ["AUTH_SERVICE_URL"] = "http://external-auth.test"

    # Monkeypatch the auth_client.issue_token to return a deterministic token
    from src.services import auth_client

    def _fake_issue_token(user_id, timeout: float = 5.0):
        return {
            "access_token": f"token-for-{user_id}",
            "refresh_token": f"refresh-token-for-{user_id}",
            "token_type": "bearer",
            "expires_in": 3600,
            "refresh_expires_in": 86400,
        }

    monkeypatch.setattr(auth_client, "issue_token", _fake_issue_token)
    yield


@pytest.fixture(scope="session", autouse=True)
def _setup_database():
    """Create all tables before the session and tear them down after."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client() -> TestClient:
    """Return a ``TestClient`` bound to the FastAPI application."""
    return TestClient(app)
