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


class TestGoogleLogin:
    def _stub_google(self, monkeypatch, email: str, google_id: str, name: str = "Google User"):
        from src.services import google_client
        monkeypatch.setattr(
            google_client,
            "verify_id_token",
            lambda token: {"sub": google_id, "email": email, "name": name, "email_verified": True},
        )

    def test_new_user_is_created_and_returns_tokens(self, client: TestClient, monkeypatch) -> None:
        email = f"new-google-{uuid4().hex}@gmail.com"
        google_id = f"google-sub-{uuid4().hex}"
        self._stub_google(monkeypatch, email=email, google_id=google_id)

        response = client.post("/login/google", json={"google_id_token": "any-token"})

        assert response.status_code == 200
        body = response.json()
        assert isinstance(body["access_token"], str)
        assert isinstance(body["refresh_token"], str)
        assert body["token_type"] == "bearer"

        with SessionLocal() as db:
            user = db.query(User).filter(User.email == email).first()
            assert user is not None
            assert user.google_id == google_id
            assert user.password is None

    def test_existing_password_account_is_linked(self, client: TestClient, monkeypatch) -> None:
        email = f"link-{uuid4().hex}@gmail.com"
        google_id = f"google-sub-{uuid4().hex}"

        with SessionLocal() as db:
            existing = User(
                id=uuid4(),
                email=email,
                password=get_password_hash("Correct-P4ssw0rd!"),
                name="Existing User",
            )
            db.add(existing)
            db.commit()
            existing_id = existing.id

        self._stub_google(monkeypatch, email=email, google_id=google_id)
        response = client.post("/login/google", json={"google_id_token": "any-token"})

        assert response.status_code == 200

        with SessionLocal() as db:
            user = db.query(User).filter(User.id == existing_id).first()
            assert user.google_id == google_id
            assert user.password is not None  # original password preserved

    def test_returning_google_user_gets_tokens(self, client: TestClient, monkeypatch) -> None:
        email = f"returning-{uuid4().hex}@gmail.com"
        google_id = f"google-sub-{uuid4().hex}"

        with SessionLocal() as db:
            returning = User(id=uuid4(), email=email, google_id=google_id, name="Returning User")
            db.add(returning)
            db.commit()

        self._stub_google(monkeypatch, email=email, google_id=google_id)
        response = client.post("/login/google", json={"google_id_token": "any-token"})

        assert response.status_code == 200
        assert isinstance(response.json()["access_token"], str)

    def test_invalid_token_returns_401(self, client: TestClient) -> None:
        # autouse mock_google_service raises HTTPStatusError for any token != "valid-google-token"
        response = client.post("/login/google", json={"google_id_token": "bad-token"})

        assert response.status_code == 401
        assert response.json() == {"detail": "Invalid Google ID token"}

    def test_missing_field_returns_422(self, client: TestClient) -> None:
        response = client.post("/login/google", json={})

        assert response.status_code == 422


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


class TestRegisterProfileServiceFailure:
    def test_register_returns_500_when_profile_service_fails(self, client: TestClient, monkeypatch) -> None:
        from src.services import profile_client

        monkeypatch.setattr(profile_client, "create_profile", lambda **_: (_ for _ in ()).throw(Exception("down")))

        email = f"profile-fail-{uuid4().hex}@example.com"
        response = client.post("/register", json={
            "email": email,
            "password": "Correct-P4ssw0rd!",
            "name": "Test User",
        })

        assert response.status_code == 500
        assert "perfiles" in response.json()["detail"].lower()

    def test_register_rolls_back_user_when_profile_service_fails(self, client: TestClient, monkeypatch) -> None:
        from src.services import profile_client

        monkeypatch.setattr(profile_client, "create_profile", lambda **_: (_ for _ in ()).throw(Exception("down")))

        email = f"profile-fail-rollback-{uuid4().hex}@example.com"
        client.post("/register", json={
            "email": email,
            "password": "Correct-P4ssw0rd!",
            "name": "Test User",
        })

        with SessionLocal() as db:
            user = db.query(User).filter(User.email == email).first()
            assert user is None


class TestLoginBlockedUser:
    def _create_user(self, email: str, password: str = "Correct-P4ssw0rd!", is_active: bool = True) -> User:
        with SessionLocal() as db:
            user = User(
                id=uuid4(),
                email=email,
                password=get_password_hash(password),
                name="Blocked Test User",
                is_active=is_active,
                is_admin=False,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            db.expunge(user)
            return user

    def test_blocked_user_cannot_login(self, client: TestClient) -> None:
        email = f"blocked-login-{uuid4().hex}@example.com"
        password = "Correct-P4ssw0rd!"
        self._create_user(email=email, password=password, is_active=False)

        response = client.post("/login", json={"email": email, "password": password})

        assert response.status_code == 403
        assert response.json() == {"detail": "Tu cuenta está suspendida. Por favor, contacta a soporte."}


class TestAdminBlockUser:
    def _create_user(
        self,
        email: str,
        password: str = "Correct-P4ssw0rd!",
        is_admin: bool = False,
        is_active: bool = True,
    ) -> User:
        with SessionLocal() as db:
            user = User(
                id=uuid4(),
                email=email,
                password=get_password_hash(password),
                name="Block Test User",
                is_active=is_active,
                is_admin=is_admin,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            db.expunge(user)
            return user

    def test_admin_blocks_user_successfully(self, client: TestClient) -> None:
        admin = self._create_user(email=f"admin-block-{uuid4().hex}@example.com", is_admin=True)
        target = self._create_user(email=f"target-block-{uuid4().hex}@example.com")

        response = client.patch(
            f"/admin/users/{target.id}/block",
            headers={"Authorization": f"Bearer token-for-{admin.id}"},
        )

        assert response.status_code == 200
        assert response.json() == {"message": "Usuario bloqueado correctamente"}

        with SessionLocal() as db:
            updated = db.query(User).filter(User.id == target.id).first()
            assert updated.is_active is False

    def test_blocked_user_cannot_login_after_block(self, client: TestClient) -> None:
        admin = self._create_user(email=f"admin-block2-{uuid4().hex}@example.com", is_admin=True)
        email = f"target-block2-{uuid4().hex}@example.com"
        password = "Correct-P4ssw0rd!"
        target = self._create_user(email=email, password=password)

        client.patch(
            f"/admin/users/{target.id}/block",
            headers={"Authorization": f"Bearer token-for-{admin.id}"},
        )

        login_response = client.post("/login", json={"email": email, "password": password})
        assert login_response.status_code == 403

    def test_admin_cannot_block_themselves(self, client: TestClient) -> None:
        admin = self._create_user(email=f"admin-self-block-{uuid4().hex}@example.com", is_admin=True)

        response = client.patch(
            f"/admin/users/{admin.id}/block",
            headers={"Authorization": f"Bearer token-for-{admin.id}"},
        )

        assert response.status_code == 400
        assert response.json() == {"detail": "Un administrador no puede bloquearse a sí mismo."}

    def test_admin_block_returns_404_for_nonexistent_user(self, client: TestClient) -> None:
        admin = self._create_user(email=f"admin-block-404-{uuid4().hex}@example.com", is_admin=True)

        response = client.patch(
            f"/admin/users/{uuid4()}/block",
            headers={"Authorization": f"Bearer token-for-{admin.id}"},
        )

        assert response.status_code == 404
        assert response.json() == {"detail": "Usuario no encontrado"}

    def test_non_admin_cannot_block_user(self, client: TestClient) -> None:
        regular = self._create_user(email=f"regular-block-{uuid4().hex}@example.com")
        target = self._create_user(email=f"target-regular-block-{uuid4().hex}@example.com")

        response = client.patch(
            f"/admin/users/{target.id}/block",
            headers={"Authorization": f"Bearer token-for-{regular.id}"},
        )

        assert response.status_code == 403
        assert response.json() == {"detail": "Admin access required"}

    def test_block_requires_authentication(self, client: TestClient) -> None:
        target = self._create_user(email=f"target-noauth-block-{uuid4().hex}@example.com")

        response = client.patch(f"/admin/users/{target.id}/block")

        assert response.status_code == 401


class TestAdminUnblockUser:
    def _create_user(
        self,
        email: str,
        password: str = "Correct-P4ssw0rd!",
        is_admin: bool = False,
        is_active: bool = True,
    ) -> User:
        with SessionLocal() as db:
            user = User(
                id=uuid4(),
                email=email,
                password=get_password_hash(password),
                name="Unblock Test User",
                is_active=is_active,
                is_admin=is_admin,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            db.expunge(user)
            return user

    def test_admin_unblocks_user_successfully(self, client: TestClient) -> None:
        admin = self._create_user(email=f"admin-unblock-{uuid4().hex}@example.com", is_admin=True)
        target = self._create_user(email=f"target-unblock-{uuid4().hex}@example.com", is_active=False)

        response = client.patch(
            f"/admin/users/{target.id}/unblock",
            headers={"Authorization": f"Bearer token-for-{admin.id}"},
        )

        assert response.status_code == 200
        assert response.json() == {"message": "Usuario desbloqueado correctamente"}

        with SessionLocal() as db:
            updated = db.query(User).filter(User.id == target.id).first()
            assert updated.is_active is True

    def test_unblocked_user_can_login_again(self, client: TestClient) -> None:
        admin = self._create_user(email=f"admin-unblock2-{uuid4().hex}@example.com", is_admin=True)
        email = f"target-unblock2-{uuid4().hex}@example.com"
        password = "Correct-P4ssw0rd!"
        target = self._create_user(email=email, password=password, is_active=False)

        client.patch(
            f"/admin/users/{target.id}/unblock",
            headers={"Authorization": f"Bearer token-for-{admin.id}"},
        )

        login_response = client.post("/login", json={"email": email, "password": password})
        assert login_response.status_code == 200

    def test_admin_unblock_returns_404_for_nonexistent_user(self, client: TestClient) -> None:
        admin = self._create_user(email=f"admin-unblock-404-{uuid4().hex}@example.com", is_admin=True)

        response = client.patch(
            f"/admin/users/{uuid4()}/unblock",
            headers={"Authorization": f"Bearer token-for-{admin.id}"},
        )

        assert response.status_code == 404
        assert response.json() == {"detail": "Usuario no encontrado"}

    def test_non_admin_cannot_unblock_user(self, client: TestClient) -> None:
        regular = self._create_user(email=f"regular-unblock-{uuid4().hex}@example.com")
        target = self._create_user(email=f"target-regular-unblock-{uuid4().hex}@example.com", is_active=False)

        response = client.patch(
            f"/admin/users/{target.id}/unblock",
            headers={"Authorization": f"Bearer token-for-{regular.id}"},
        )

        assert response.status_code == 403

    def test_unblock_requires_authentication(self, client: TestClient) -> None:
        target = self._create_user(email=f"target-noauth-unblock-{uuid4().hex}@example.com", is_active=False)

        response = client.patch(f"/admin/users/{target.id}/unblock")

        assert response.status_code == 401


class TestAdminListUsers:
    def _create_user(
        self,
        email: str,
        is_admin: bool = False,
        is_active: bool = True,
        name: str = "List Test User",
    ) -> User:
        with SessionLocal() as db:
            user = User(
                id=uuid4(),
                email=email,
                password=get_password_hash("Correct-P4ssw0rd!"),
                name=name,
                is_active=is_active,
                is_admin=is_admin,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            db.expunge(user)
            return user

    def test_admin_can_list_users(self, client: TestClient) -> None:
        admin = self._create_user(email=f"admin-list-{uuid4().hex}@example.com", is_admin=True)

        response = client.get(
            "/admin/users",
            headers={"Authorization": f"Bearer token-for-{admin.id}"},
        )

        assert response.status_code == 200
        body = response.json()
        assert isinstance(body["items"], list)
        assert isinstance(body["total"], int)
        assert body["page"] == 1
        assert body["size"] == 10

    def test_list_users_respects_pagination(self, client: TestClient) -> None:
        admin = self._create_user(email=f"admin-paginate-{uuid4().hex}@example.com", is_admin=True)

        response = client.get(
            "/admin/users?page=1&size=3",
            headers={"Authorization": f"Bearer token-for-{admin.id}"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["page"] == 1
        assert body["size"] == 3
        assert len(body["items"]) <= 3

    def test_list_users_search_filters_by_name(self, client: TestClient) -> None:
        unique_name = f"UniqueName{uuid4().hex[:8]}"
        admin = self._create_user(email=f"admin-search-{uuid4().hex}@example.com", is_admin=True)
        self._create_user(email=f"search-target-{uuid4().hex}@example.com", name=unique_name)

        response = client.get(
            f"/admin/users?search={unique_name}",
            headers={"Authorization": f"Bearer token-for-{admin.id}"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["total"] >= 1
        assert any(u["name"] == unique_name for u in body["items"])

    def test_non_admin_cannot_list_users(self, client: TestClient) -> None:
        regular = self._create_user(email=f"regular-list-{uuid4().hex}@example.com")

        response = client.get(
            "/admin/users",
            headers={"Authorization": f"Bearer token-for-{regular.id}"},
        )

        assert response.status_code == 403

    def test_list_users_requires_authentication(self, client: TestClient) -> None:
        response = client.get("/admin/users")

        assert response.status_code == 401

    def test_list_users_rejects_page_less_than_one(self, client: TestClient) -> None:
        admin = self._create_user(email=f"admin-badpage-{uuid4().hex}@example.com", is_admin=True)

        response = client.get(
            "/admin/users?page=0",
            headers={"Authorization": f"Bearer token-for-{admin.id}"},
        )

        assert response.status_code == 422

    def test_list_users_rejects_size_over_maximum(self, client: TestClient) -> None:
        admin = self._create_user(email=f"admin-badsize-{uuid4().hex}@example.com", is_admin=True)

        response = client.get(
            "/admin/users?size=101",
            headers={"Authorization": f"Bearer token-for-{admin.id}"},
        )

        assert response.status_code == 422


class TestVerifyCode:
    def _register_and_create_code(
        self, client: TestClient, email: str, code: str, expired: bool = False
    ) -> None:
        client.post("/register", json={
            "email": email,
            "password": "Correct-P4ssw0rd!",
            "name": "Verify User",
        })
        with SessionLocal() as db:
            user = db.query(User).filter(User.email == email).first()
            expiry = (
                datetime.utcnow() - timedelta(minutes=1)
                if expired
                else datetime.utcnow() + timedelta(minutes=10)
            )
            db.add(VerificationCode(id=uuid4(), user_id=user.id, code=code, expires_at=expiry))
            db.commit()

    def test_verify_code_succeeds_with_valid_code(self, client: TestClient) -> None:
        email = f"verify-ok-{uuid4().hex}@example.com"
        self._register_and_create_code(client, email, "777777")

        response = client.post("/verify-code", json={"email": email, "code": "777777"})

        assert response.status_code == 200
        assert response.json() == {"message": "Código verificado con éxito"}

    def test_verify_code_rejects_wrong_code(self, client: TestClient) -> None:
        email = f"verify-bad-{uuid4().hex}@example.com"
        self._register_and_create_code(client, email, "888888")

        response = client.post("/verify-code", json={"email": email, "code": "000000"})

        assert response.status_code == 400
        assert response.json() == {"detail": "Código inválido"}

    def test_verify_code_rejects_expired_code(self, client: TestClient) -> None:
        email = f"verify-expired-{uuid4().hex}@example.com"
        self._register_and_create_code(client, email, "999999", expired=True)

        response = client.post("/verify-code", json={"email": email, "code": "999999"})

        assert response.status_code == 400
        assert response.json() == {"detail": "El código ha expirado"}

    def test_verify_code_returns_404_for_unknown_email(self, client: TestClient) -> None:
        response = client.post("/verify-code", json={
            "email": f"nonexistent-{uuid4().hex}@example.com",
            "code": "123456",
        })

        assert response.status_code == 404
        assert response.json() == {"detail": "Usuario no encontrado"}


class TestForgotPassword:
    def test_forgot_password_returns_200_for_registered_email(self, client: TestClient, monkeypatch) -> None:
        import resend
        monkeypatch.setattr(resend.Emails, "send", lambda params: {"id": "fake-email-id"})

        email = f"forgot-ok-{uuid4().hex}@example.com"
        client.post("/register", json={
            "email": email,
            "password": "Correct-P4ssw0rd!",
            "name": "Forgot User",
        })

        response = client.post("/forgot-password", json={"email": email})

        assert response.status_code == 200
        assert response.json() == {"message": "Si el email está registrado, te enviaremos un código."}

    def test_forgot_password_returns_same_message_for_unregistered_email(self, client: TestClient) -> None:
        response = client.post("/forgot-password", json={
            "email": f"notregistered-{uuid4().hex}@example.com",
        })

        assert response.status_code == 200
        assert response.json() == {"message": "Si el email está registrado, te enviaremos un código."}
