"""Acceptance tests for the upcoming login flow.

These scenarios are intentionally skipped for now because the login route,
JWT issuance, and authenticated endpoints are not implemented yet.
"""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient


@pytest.mark.skip(reason="Pending login route and JWT implementation")
class TestLoginAcceptance:
    """Business-level acceptance scenarios for user login/session."""

    def _register_user(
        self,
        client: TestClient,
        email: str,
        password: str = "correct-password",
        name: str = "Acceptance User",
    ) -> None:
        response = client.post(
            "/auth/register",
            json={"email": email, "password": password, "name": name},
        )
        assert response.status_code == 201

    def test_registered_user_can_log_in_and_receive_access_token(
        self, client: TestClient
    ) -> None:
        email = f"accepted-{uuid4().hex}@example.com"
        password = "correct-password"
        self._register_user(client=client, email=email, password=password)

        response = client.post(
            "/auth/login",
            json={"email": email, "password": password},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["access_token"]
        assert body["token_type"] == "bearer"

    def test_login_with_wrong_password_returns_generic_error(
        self, client: TestClient
    ) -> None:
        email = f"wrong-pass-{uuid4().hex}@example.com"
        self._register_user(client=client, email=email, password="correct-password")

        response = client.post(
            "/auth/login",
            json={"email": email, "password": "wrong-password"},
        )

        assert response.status_code == 401
        assert response.json() == {"detail": "Invalid credentials"}

    def test_login_with_unregistered_email_returns_generic_error(
        self, client: TestClient
    ) -> None:
        response = client.post(
            "/auth/login",
            json={
                "email": f"unknown-{uuid4().hex}@example.com",
                "password": "any-password",
            },
        )

        assert response.status_code == 401
        assert response.json() == {"detail": "Invalid credentials"}

    def test_expired_session_cannot_access_authenticated_action(
        self, client: TestClient
    ) -> None:
        response = client.get(
            "/auth/protected-action",
            headers={"Authorization": "Bearer expired-or-invalid-token"},
        )

        assert response.status_code == 401
        assert response.json() == {"detail": "Could not validate credentials"}
