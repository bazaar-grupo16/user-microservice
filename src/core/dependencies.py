"""
FastAPI dependencies for dependency injection.

Add shared dependencies here (e.g. database sessions, auth context).
"""

from collections.abc import AsyncGenerator
from uuid import UUID
from typing import Annotated

import httpx
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import SessionLocal
from src.models.user import User
from src.repositories import user as user_repo
from src.services import auth_client


async def _get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield a SQLAlchemy session and ensure it is closed afterwards."""
    db = SessionLocal()
    try:
        yield db
    finally:
        await db.close()


# Re-usable annotated dependency for route signatures.
DbSession = Annotated[AsyncSession, Depends(_get_db)]


async def require_admin(
    db: DbSession,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )

    try:
        validation_response = await auth_client.validate_token(authorization=authorization)
        user_id = UUID(str(validation_response["user_id"]))
    except (httpx.HTTPError, KeyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )

    user = await user_repo.get_user_by_id(db=db, user_id=user_id)
    if not user or not user.is_active or not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )

    return user


AdminUser = Annotated[User, Depends(require_admin)]


async def require_user(
    db: DbSession,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )

    try:
        validation_response = await auth_client.validate_token(authorization=authorization)
        user_id = UUID(str(validation_response["user_id"]))
    except (httpx.HTTPError, KeyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )

    user = await user_repo.get_user_by_id(db=db, user_id=user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )

    return user


AuthenticatedUser = Annotated[User, Depends(require_user)]
