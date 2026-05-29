"""Tests for the auth registration route.

These tests exercise the controller through the FastAPI route and use the
real PostgreSQL-backed test setup.
"""
import pytest
from datetime import datetime, timedelta
from uuid import uuid4, UUID

from fastapi.testclient import TestClient

from src.core.database import SessionLocal
from src.core.security import get_password_hash
from src.models.user import User, VerificationCode


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
        assert body["is_admin"] is False
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
        assert isinstance(body["access_token"], str)
        assert isinstance(body["refresh_token"], str)
        assert body["token_type"] == "bearer"
        assert isinstance(body["expires_in"], int)
        assert isinstance(body["refresh_expires_in"], int)

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


class TestAdminAuth:
    def _create_user(
        self,
        email: str,
        password: str = "Correct-P4ssw0rd!",
        is_admin: bool = False,
        is_active: bool = True,
        name: str = "Admin Test User",
    ) -> User:
        with SessionLocal() as db:
            user = User(
                id=uuid4(),
                email=email,
                password=get_password_hash(password),
                name=name,
                is_active=is_active,
                is_admin=is_admin,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            db.expunge(user)
            return user

    def test_admin_login_returns_200_for_admin_user(self, client: TestClient) -> None:
        email = f"admin-login-{uuid4().hex}@example.com"
        password = "Correct-P4ssw0rd!"
        admin = self._create_user(email=email, password=password, is_admin=True)

        response = client.post("/admin/login", json={"email": email, "password": password})

        assert response.status_code == 200
        body = response.json()
        assert body["access_token"] == f"token-for-{admin.id}"
        assert body["refresh_token"] == f"refresh-token-for-{admin.id}"
        assert body["token_type"] == "bearer"
        assert isinstance(body["expires_in"], int)
        assert isinstance(body["refresh_expires_in"], int)

    def test_admin_login_rejects_regular_user(self, client: TestClient) -> None:
        email = f"regular-admin-login-{uuid4().hex}@example.com"
        password = "Correct-P4ssw0rd!"
        self._create_user(email=email, password=password, is_admin=False)

        response = client.post("/admin/login", json={"email": email, "password": password})

        assert response.status_code == 401
        assert response.json() == {"detail": "Invalid credentials"}

    def test_admin_login_rejects_inactive_admin(self, client: TestClient) -> None:
        email = f"inactive-admin-login-{uuid4().hex}@example.com"
        password = "Correct-P4ssw0rd!"
        self._create_user(email=email, password=password, is_admin=True, is_active=False)

        response = client.post("/admin/login", json={"email": email, "password": password})

        assert response.status_code == 401
        assert response.json() == {"detail": "Invalid credentials"}

    def test_admin_login_returns_generic_401_for_invalid_credentials(self, client: TestClient) -> None:
        email = f"bad-admin-login-{uuid4().hex}@example.com"
        self._create_user(email=email, password="Correct-P4ssw0rd!", is_admin=True)

        response = client.post("/admin/login", json={"email": email, "password": "wrong-password"})

        assert response.status_code == 401
        assert response.json() == {"detail": "Invalid credentials"}

    def test_admin_me_returns_current_admin(self, client: TestClient) -> None:
        email = f"admin-me-{uuid4().hex}@example.com"
        admin = self._create_user(email=email, is_admin=True, name="Admin Me")

        response = client.get("/admin/me", headers={"Authorization": f"Bearer token-for-{admin.id}"})

        assert response.status_code == 200
        assert response.json() == {
            "id": str(admin.id),
            "email": email,
            "name": "Admin Me",
            "is_active": True,
            "is_admin": True,
        }

    def test_admin_me_rejects_missing_token(self, client: TestClient) -> None:
        response = client.get("/admin/me")

        assert response.status_code == 401
        assert response.json() == {"detail": "Could not validate credentials"}

    def test_admin_me_rejects_invalid_token(self, client: TestClient) -> None:
        response = client.get("/admin/me", headers={"Authorization": "Bearer invalid-token"})

        assert response.status_code == 401
        assert response.json() == {"detail": "Could not validate credentials"}

    def test_admin_me_rejects_regular_user(self, client: TestClient) -> None:
        user = self._create_user(email=f"regular-admin-me-{uuid4().hex}@example.com", is_admin=False)

        response = client.get("/admin/me", headers={"Authorization": f"Bearer token-for-{user.id}"})

        assert response.status_code == 403
        assert response.json() == {"detail": "Admin access required"}

    def test_admin_me_rejects_inactive_admin(self, client: TestClient) -> None:
        admin = self._create_user(
            email=f"inactive-admin-me-{uuid4().hex}@example.com",
            is_admin=True,
            is_active=False,
        )

        response = client.get("/admin/me", headers={"Authorization": f"Bearer token-for-{admin.id}"})

        assert response.status_code == 403
        assert response.json() == {"detail": "Admin access required"}


class TestPasswordRecovery:
    def _register_payload(self, email: str, password: str = "Correct-P4ssw0rd!") -> dict[str, str | None]:
        return {
            "email": email,
            "password": password,
            "name": "Recovery User",
        }

    def _create_valid_recovery_code(self, email: str, code: str) -> None:
        with SessionLocal() as db:
            user = db.query(User).filter(User.email == email).first()
            assert user is not None

            db.add(
                VerificationCode(
                    id=uuid4(),
                    user_id=user.id,
                    code=code,
                    expires_at=datetime.utcnow() + timedelta(minutes=10),
                )
            )
            db.commit()

    def test_reset_password_succeeds_with_valid_code(self, client: TestClient) -> None:
        email = f"recovery-ok-{uuid4().hex}@example.com"
        old_password = "Correct-P4ssw0rd!"
        new_password = "N3w-StrongPass12!"
        recovery_code = "123456"

        register_response = client.post(
            "/register",
            json=self._register_payload(email=email, password=old_password),
        )
        assert register_response.status_code == 201

        self._create_valid_recovery_code(email=email, code=recovery_code)

        reset_response = client.post(
            "/reset-password",
            json={
                "email": email,
                "code": recovery_code,
                "new_password": new_password,
            },
        )

        assert reset_response.status_code == 200
        assert reset_response.json() == {"message": "Contraseña actualizada correctamente"}

        login_old_password = client.post(
            "/login",
            json={"email": email, "password": old_password},
        )
        assert login_old_password.status_code == 401

        login_new_password = client.post(
            "/login",
            json={"email": email, "password": new_password},
        )
        assert login_new_password.status_code == 200

    def test_reset_password_rejects_when_code_is_missing_or_invalid(self, client: TestClient) -> None:
        email = f"recovery-fail-{uuid4().hex}@example.com"

        register_response = client.post(
            "/register",
            json=self._register_payload(email=email),
        )
        assert register_response.status_code == 201

        no_code_response = client.post(
            "/reset-password",
            json={
                "email": email,
                "code": "654321",
                "new_password": "N3w-StrongPass12!",
            },
        )
        assert no_code_response.status_code == 400
        assert no_code_response.json() == {"detail": "Sesión de recuperación inválida o expirada"}

        self._create_valid_recovery_code(email=email, code="111111")

        invalid_code_response = client.post(
            "/reset-password",
            json={
                "email": email,
                "code": "222222",
                "new_password": "N3w-StrongPass12!",
            },
        )
        assert invalid_code_response.status_code == 400
        assert invalid_code_response.json() == {"detail": "Sesión de recuperación inválida o expirada"}

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


class TestAuthLogout:
    def _create_user(
        self,
        email: str,
        password: str = "Correct-P4ssw0rd!",
        is_admin: bool = False,
        is_active: bool = True,
        name: str = "Test User",
    ) -> User:
        with SessionLocal() as db:
            user = User(
                id=uuid4(),
                email=email,
                password=get_password_hash(password),
                name=name,
                is_active=is_active,
                is_admin=is_admin,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            db.expunge(user)
            return user

    def test_logout_returns_204_for_valid_token(self, client: TestClient) -> None:
        user = self._create_user(email=f"logout-{uuid4().hex}@example.com")

        response = client.delete("/logout", headers={"Authorization": f"Bearer token-for-{user.id}"})

        assert response.status_code == 204

    def test_logout_rejects_missing_token(self, client: TestClient) -> None:
        response = client.delete("/logout")

        assert response.status_code == 401
        assert response.json() == {"detail": "Could not validate credentials"}

    def test_logout_rejects_invalid_token(self, client: TestClient) -> None:
        response = client.delete("/logout", headers={"Authorization": "Bearer invalid-token"})

        assert response.status_code == 401
        assert response.json() == {"detail": "Could not validate credentials"}

    def test_logout_rejects_inactive_user(self, client: TestClient) -> None:
        user = self._create_user(email=f"logout-inactive-{uuid4().hex}@example.com", is_active=False)

        response = client.delete("/logout", headers={"Authorization": f"Bearer token-for-{user.id}"})

        assert response.status_code == 401
        assert response.json() == {"detail": "Could not validate credentials"}
