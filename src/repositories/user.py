import asyncio

from sqlalchemy.ext.asyncio import AsyncSession
from src.models.user import User, VerificationCode
from datetime import datetime
from src.schemas.user import UserCreate
from src.core.security import get_password_hash
from sqlalchemy import or_, select, func
import uuid


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def create_user(db: AsyncSession, user_in: UserCreate) -> User:
    hashed_pass = await asyncio.to_thread(get_password_hash, user_in.password)
    new_user = User(id=uuid.uuid4(),email=user_in.email, password=hashed_pass, name=user_in.name)

    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    return new_user

async def create_verification_code(db: AsyncSession, user_id: uuid.UUID, code: str, expires_at: datetime) -> VerificationCode:
    new_code = VerificationCode(
        id=uuid.uuid4(),
        user_id=user_id,
        code=code,
        expires_at=expires_at
    )
    db.add(new_code)
    await db.commit()
    await db.refresh(new_code)
    return new_code

async def get_verification_code(db: AsyncSession, user_id: uuid.UUID, code: str) -> VerificationCode | None:
    result = await db.execute(
        select(VerificationCode).where(
            VerificationCode.user_id == user_id,
            VerificationCode.code == code,
        )
    )
    return result.scalar_one_or_none()

async def update_user_password(db: AsyncSession, user: User, hashed_pass: str):
    user.password = hashed_pass
    await db.commit()
    await db.refresh(user)

async def delete_verification_code(db: AsyncSession, verification_code: VerificationCode):
    await db.delete(verification_code)
    await db.commit()


async def get_user_by_google_id(db: AsyncSession, google_id: str) -> User | None:
    result = await db.execute(select(User).where(User.google_id == google_id))
    return result.scalar_one_or_none()


async def create_oauth_user(db: AsyncSession, email: str, name: str | None, google_id: str) -> User:
    new_user = User(id=uuid.uuid4(), email=email, name=name, google_id=google_id)
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return new_user


async def link_google_account(db: AsyncSession, user: User, google_id: str) -> User:
    user.google_id = google_id
    await db.commit()
    await db.refresh(user)
    return user

async def get_users_paginated(db: AsyncSession, skip: int, limit: int, search: str | None = None):
    stmt = select(User)

    if search:
        search_term = f"%{search}%"
        stmt = stmt.where(
            or_(
                User.email.ilike(search_term),
                User.name.ilike(search_term)
            )
        )

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    result = await db.execute(
        stmt.order_by(User.created_at.desc()).offset(skip).limit(limit)
    )
    users = result.scalars().all()

    return total, users

async def set_user_active_status(db: AsyncSession, user: User, is_active: bool) -> User:
    user.is_active = is_active
    await db.commit()
    await db.refresh(user)
    return user

async def delete_user(db: AsyncSession, user: User):
    await db.delete(user)
    await db.commit()