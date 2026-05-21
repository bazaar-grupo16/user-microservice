"""Create or promote the initial admin user.

Required environment variables:
ADMIN_EMAIL, ADMIN_PASSWORD, ADMIN_NAME
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from pydantic import ValidationError

from src.core.database import SessionLocal
from src.core.security import get_password_hash
from src.models.user import User
from src.schemas.user import UserCreate


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def main() -> None:
    email = _required_env("ADMIN_EMAIL")
    password = _required_env("ADMIN_PASSWORD")
    name = _required_env("ADMIN_NAME")

    with SessionLocal() as db:
        user = db.query(User).filter(User.email == email).first()
        if user:
            user.is_admin = True
            user.is_active = True
            if not user.name:
                user.name = name
            db.commit()
            print(f"Promoted existing user to admin: {email}")
            return

        try:
            user_in = UserCreate(email=email, password=password, name=name)
        except ValidationError as exc:
            raise RuntimeError(f"Invalid admin seed input: {exc}") from exc

        db.add(
            User(
                id=uuid4(),
                email=user_in.email,
                password=get_password_hash(user_in.password),
                name=user_in.name,
                is_active=True,
                is_admin=True,
            )
        )
        db.commit()
        print(f"Created initial admin user: {email}")


if __name__ == "__main__":
    main()
