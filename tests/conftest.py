"""
Shared pytest fixtures for the test suite.

Tests run against a **real PostgreSQL** database provided by
``docker-compose.test.yml``.  Connection details come from the
same environment variables the application uses in production
(DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME).

**No mocking is used.**

The application is now fully async (asyncpg + SQLAlchemy AsyncSession), but
the test suite still drives it through Starlette's *synchronous* ``TestClient``
(``pytest-asyncio`` is intentionally not a dependency).  ``TestClient`` opens a
fresh event loop per request, so a shared connection pool would reuse a
connection bound to a closed loop.  We therefore force ``NullPool`` for the
async engine during tests by setting ``DB_USE_NULL_POOL`` *before* importing
anything that builds the engine.
"""

import os

os.environ["DB_USE_NULL_POOL"] = "1"

import asyncio
from pathlib import Path

import pytest
import httpx
from fastapi.testclient import TestClient
from sqlalchemy import text

from src.core.database import Base, engine
from src.main import app

# Provide a simple mock for the external auth service during tests.
@pytest.fixture(autouse=True)
def mock_external_auth_service(monkeypatch):
    # Ensure the app has an AUTH_SERVICE_URL so the client code will attempt to call it.
    os.environ["AUTH_SERVICE_URL"] = "http://external-auth.test"

    # Monkeypatch the auth_client.issue_token to return a deterministic token
    from src.services import auth_client

    async def _fake_issue_token(user_id, is_admin: bool = False, timeout: float = 5.0):
        return {
            "access_token": f"token-for-{user_id}",
            "refresh_token": f"refresh-token-for-{user_id}",
            "token_type": "bearer",
            "expires_in": 3600,
            "refresh_expires_in": 86400,
        }

    async def _fake_validate_token(authorization: str, timeout: float = 5.0):
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token.startswith("token-for-"):
            request = httpx.Request("GET", "http://external-auth.test/validate")
            response = httpx.Response(401, request=request)
            raise httpx.HTTPStatusError("Invalid token", request=request, response=response)

        return {"status": "valid", "user_id": token.removeprefix("token-for-")}

    async def _fake_delete_token(user_id, timeout: float = 5.0):
        return None

    monkeypatch.setattr(auth_client, "issue_token", _fake_issue_token)
    monkeypatch.setattr(auth_client, "validate_token", _fake_validate_token)
    monkeypatch.setattr(auth_client, "delete_token", _fake_delete_token)
    yield

@pytest.fixture(autouse=True)
def mock_google_service(monkeypatch):
    from src.services import google_client

    # ``verify_id_token`` is invoked via ``asyncio.to_thread`` by the
    # controller, so the stub stays synchronous.
    def _fake_verify_id_token(token: str):
        if token == "valid-google-token":
            return {"sub": "google-sub-123", "email": "googleuser@gmail.com", "name": "Google User", "email_verified": True}
        raise ValueError("Invalid token")

    monkeypatch.setattr(google_client, "verify_id_token", _fake_verify_id_token)
    yield


@pytest.fixture(autouse=True)
def mock_profile_service(monkeypatch):
    """Mockea nuestro propio cliente de perfiles durante los tests."""

    os.environ["PROFILE_SERVICE_URL"] = "http://fake-profile-service.test"

    from src.services import profile_client

    async def _fake_create_profile(user_id: str, name: str):
        return {
            "id": "fake-profile-uuid",
            "user_id": user_id,
            "name": name
        }

    monkeypatch.setattr(profile_client, "create_profile", _fake_create_profile)
    yield


async def _create_schema() -> None:
    sql_path = (
        Path(__file__).resolve().parents[1] / "scripts" / "add_users_created_at_index.sql"
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text(sql_path.read_text()))
    # Point 1: flush the pool created in this loop so each per-request test
    # loop gets fresh connections.
    await engine.dispose()


async def _drop_schema() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    # Point 2: flush the pool after the teardown loop.
    await engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def _setup_database():
    """Create all tables before the session and tear them down after."""
    asyncio.run(_create_schema())
    yield
    asyncio.run(_drop_schema())


@pytest.fixture(autouse=True)
def _dispose_engine_after_test():
    """Point 3: flush the connection pool after every test so the next test's
    event loop never reuses a connection bound to a closed loop."""
    yield
    asyncio.run(engine.dispose())


@pytest.fixture()
def client() -> TestClient:
    """Return a ``TestClient`` bound to the FastAPI application."""
    return TestClient(app)
