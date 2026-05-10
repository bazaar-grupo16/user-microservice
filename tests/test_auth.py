"""Tests for the auth registration route.

These tests exercise the controller through the FastAPI route and use the
real PostgreSQL-backed test setup.
"""
import pytest
from datetime import datetime
from uuid import uuid4, UUID

from fastapi.testclient import TestClient


class TestAuthRegister:
    def _payload(self, email: str) -> dict[str, str | None]:
        return {
            "email": email,
            "password": "Correct-P4ssw0rd!",
            "name": "Test User",
        }

    def test_register_returns_created_user(self, client: TestClient) -> None:
        email = f"user-{uuid4().hex}@example.com"

        response = client.post("/register", json=self._payload(email))

        assert response.status_code == 201

        body = response.json()
        assert isinstance(body["id"], str)
        assert UUID(body["id"])
        assert body["email"] == email
        assert body["name"] == "Test User"
        assert body["is_active"] is True
        assert datetime.fromisoformat(body["created_at"])

    def test_register_rejects_duplicate_email(self, client: TestClient) -> None:
        email = f"duplicate-{uuid4().hex}@example.com"
        payload = self._payload(email)

        first_response = client.post("/register", json=payload)
        assert first_response.status_code == 201

        duplicate_response = client.post("/register", json=payload)

        assert duplicate_response.status_code == 400
        assert duplicate_response.json() == {
            "detail": "User with this email already exists",
        }

    def test_register_rejects_invalid_email(self, client: TestClient) -> None:
        response = client.post(
            "/register",
            json={
                "email": "not-an-email",
                "password": "Correct-P4ssw0rd!",
                "name": "Test User",
            },
        )

        assert response.status_code == 422
    
    @pytest.mark.parametrize(
        "bad_password, expected_error_msg",
        [
            ("Short1!", "Password must be at least 8 characters long"),
            ("NOLOWERCASE123!", "Password must contain at least one lowercase letter"),
            ("nouppercase123!", "Password must contain at least one uppercase letter"),
            ("Only1Number!", "Password must contain at least 2 numbers"),
            ("NoSpecialChars12", "Password must contain at least one special character"),
        ]
    )
    def test_register_rejects_weak_passwords(self, client: TestClient, bad_password: str, expected_error_msg: str) -> None:
        response = client.post(
            "/register",
            json={
                "email": f"weak-pass-{uuid4().hex}@example.com",
                "password": bad_password,
                "name": "Test User",
            },
        )

        assert response.status_code == 422
        
        errors = response.json()["detail"]
        assert expected_error_msg in errors[0]["msg"]


class TestAuthLogin:
    def _register_payload(self, email: str, password: str = "Correct-P4ssw0rd!") -> dict[str, str | None]:
        return {
            "email": email,
            "password": password,
            "name": "Login User",
        }

    def test_login_returns_200_for_valid_credentials(self, client: TestClient) -> None:
        email = f"login-{uuid4().hex}@example.com"
        password = "Correct-P4ssw0rd!"

        register_response = client.post(
            "/register",
            json=self._register_payload(email=email, password=password),
        )
        assert register_response.status_code == 201

        login_response = client.post(
            "/login",
            json={"email": email, "password": password},
        )

        assert login_response.status_code == 200
        body = login_response.json()
        assert body["access_token"]
        assert body["refresh_token"]
        assert body["token_type"] == "bearer"
        assert body["expires_in"] == 3600
        assert body["refresh_expires_in"] == 86400

    def test_login_returns_generic_401_for_wrong_password(self, client: TestClient) -> None:
        email = f"login-wrong-pass-{uuid4().hex}@example.com"

        register_response = client.post(
            "/register",
            json=self._register_payload(email=email, password="Correct-P4ssw0rd!"),
        )
        assert register_response.status_code == 201

        login_response = client.post(
            "/login",
            json={"email": email, "password": "wrong-password"},
        )

        assert login_response.status_code == 401
        assert login_response.json() == {"detail": "Invalid credentials"}

    def test_login_returns_generic_401_for_unregistered_email(self, client: TestClient) -> None:
        login_response = client.post(
            "/login",
            json={
                "email": f"not-found-{uuid4().hex}@example.com",
                "password": "Correct-P4ssw0rd!",
            },
        )

        assert login_response.status_code == 401
        assert login_response.json() == {"detail": "Invalid credentials"}
