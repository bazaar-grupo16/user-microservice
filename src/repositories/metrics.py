from __future__ import annotations

from datetime import datetime
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.models.user import User

IntervalLiteral = Literal["day", "week", "month"]


def _eligible_users_filter():
    return User.is_admin.is_(False)


def count_total_registered(db: Session) -> int:
    stmt = select(func.count()).select_from(User).where(_eligible_users_filter())
    return int(db.scalar(stmt) or 0)


def count_new_users_in_period(db: Session, start: datetime, end: datetime) -> int:
    stmt = (
        select(func.count())
        .select_from(User)
        .where(
            _eligible_users_filter(),
            User.created_at >= start,
            User.created_at <= end,
        )
    )
    return int(db.scalar(stmt) or 0)


def fetch_registration_buckets(
    db: Session,
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
    rows = db.execute(stmt).all()
    return [(row[0], int(row[1])) for row in rows if row[0] is not None]
