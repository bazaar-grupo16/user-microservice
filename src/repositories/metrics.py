from __future__ import annotations

from datetime import datetime
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.user import User

IntervalLiteral = Literal["day", "week", "month"]


def _eligible_users_filter():
    return User.is_admin.is_(False)


async def count_total_registered(db: AsyncSession) -> int:
    stmt = select(func.count()).select_from(User).where(_eligible_users_filter())
    return int(await db.scalar(stmt) or 0)


async def count_new_users_in_period(db: AsyncSession, start: datetime, end: datetime) -> int:
    stmt = (
        select(func.count())
        .select_from(User)
        .where(
            _eligible_users_filter(),
            User.created_at >= start,
            User.created_at <= end,
        )
    )
    return int(await db.scalar(stmt) or 0)


async def fetch_registration_buckets(
    db: AsyncSession,
    start: datetime,
    end: datetime,
    interval: IntervalLiteral,
) -> list[tuple[datetime, int]]:
    bucket = func.date_trunc(interval, User.created_at).label("bucket")
    stmt = (
        select(bucket, func.count())
        .where(
            _eligible_users_filter(),
            User.created_at >= start,
            User.created_at <= end,
        )
        .group_by(bucket)
        .order_by(bucket)
    )
    rows = (await db.execute(stmt)).all()
    return [(row[0], int(row[1])) for row in rows if row[0] is not None]
