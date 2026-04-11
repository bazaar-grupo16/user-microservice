"""Tests for the auth registration route.

These tests exercise the controller through the FastAPI route and use the
real PostgreSQL-backed test setup.
"""

from datetime import datetime
from uuid import uuid4

from fastapi.testclient import TestClient


class TestAuthRegister:
    def _payload(self, email: str) -> dict[str, str | None]:
        return {
            "email": email,
            "password": "super-secret-password",
            "name": "Test User",
        }

    def test_register_returns_created_user(self, client: TestClient) -> None:
        email = f"user-{uuid4().hex}@example.com"

        response = client.post("/auth/register", json=self._payload(email))

        assert response.status_code == 201

        body = response.json()
        assert body["id"] > 0
        assert body["email"] == email
        assert body["name"] == "Test User"
        assert body["is_active"] is True
        assert datetime.fromisoformat(body["created_at"])

    def test_register_rejects_duplicate_email(self, client: TestClient) -> None:
        email = f"duplicate-{uuid4().hex}@example.com"
        payload = self._payload(email)

        first_response = client.post("/auth/register", json=payload)
        assert first_response.status_code == 201

        duplicate_response = client.post("/auth/register", json=payload)

        assert duplicate_response.status_code == 400
        assert duplicate_response.json() == {
            "detail": "User with this email already exists",
        }

    def test_register_rejects_invalid_email(self, client: TestClient) -> None:
        response = client.post(
            "/auth/register",
            json={
                "email": "not-an-email",
                "password": "super-secret-password",
                "name": "Test User",
            },
        )

        assert response.status_code == 422
