from __future__ import annotations

import csv
import io
import logging
import time
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.observability import get_observability_correlation_id
from src.repositories import metrics as metrics_repo
from src.schemas.metrics import (
    MetricsInterval,
    UsersMetricResponse,
    UsersMetricSummary,
    UsersTimeseriesData,
)

logger = logging.getLogger(__name__)


def _to_naive_utc(value: datetime) -> datetime:
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _week_start(value: date) -> date:
    return value - timedelta(days=value.weekday())


def _month_start(value: date) -> date:
    return value.replace(day=1)


def _sql_bucket_to_date(bucket: datetime, interval: MetricsInterval) -> date:
    if bucket.tzinfo is not None:
        bucket = bucket.astimezone(timezone.utc)
    bucket_date = bucket.date()
    if interval == MetricsInterval.week:
        return _week_start(bucket_date)
    if interval == MetricsInterval.month:
        return _month_start(bucket_date)
    return bucket_date


def _generate_bucket_starts(
    start: datetime,
    end: datetime,
    interval: MetricsInterval,
) -> list[date]:
    start_date = start.date()
    end_date = end.date()
    buckets: list[date] = []

    if interval == MetricsInterval.day:
        current = start_date
        while current <= end_date:
            buckets.append(current)
            current += timedelta(days=1)
        return buckets

    if interval == MetricsInterval.week:
        current = _week_start(start_date)
        last_bucket = _week_start(end_date)
        while current <= last_bucket:
            buckets.append(current)
            current += timedelta(days=7)
        return buckets

    current = _month_start(start_date)
    last_bucket = _month_start(end_date)
    while current <= last_bucket:
        buckets.append(current)
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)
    return buckets


def _merge_buckets(
    start: datetime,
    end: datetime,
    interval: MetricsInterval,
    sql_rows: list[tuple[datetime, int]],
) -> list[UsersTimeseriesData]:
    counts_by_date = {
        _sql_bucket_to_date(bucket, interval): count for bucket, count in sql_rows
    }
    return [
        UsersTimeseriesData(date=bucket_date, count=counts_by_date.get(bucket_date, 0))
        for bucket_date in _generate_bucket_starts(start, end, interval)
    ]


async def get_users_metrics(
    db: AsyncSession,
    start: datetime,
    end: datetime,
    interval: MetricsInterval,
) -> UsersMetricResponse:
    started_at = time.perf_counter()

    # ``created_at`` is stored as a naive (UTC) timestamp.  asyncpg refuses to
    # compare a naive column against tz-aware parameters, so normalise the
    # incoming bounds to naive UTC before they reach the query.
    start = _to_naive_utc(start)
    end = _to_naive_utc(end)

    total_registered = await metrics_repo.count_total_registered(db)
    new_users = await metrics_repo.count_new_users_in_period(db, start, end)
    sql_rows = await metrics_repo.fetch_registration_buckets(
        db,
        start,
        end,
        interval.value,
    )
    timeseries = _merge_buckets(start, end, interval, sql_rows)

    duration_ms = (time.perf_counter() - started_at) * 1000
    logger.info(
        "users_metrics_computed correlation_id=%s start_date=%s end_date=%s interval=%s duration_ms=%.2f",
        get_observability_correlation_id(),
        start.isoformat(),
        end.isoformat(),
        interval.value,
        duration_ms,
    )

    return UsersMetricResponse(
        summary=UsersMetricSummary(
            total_registered_all_time=total_registered,
            new_users_in_period=new_users,
        ),
        timeseries=timeseries,
    )


async def build_users_metrics_csv(
    db: AsyncSession,
    start: datetime,
    end: datetime,
) -> tuple[str, str]:
    metrics = await get_users_metrics(db, start, end, MetricsInterval.day)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["metric", "value"])
    writer.writerow(["total_registered_all_time", metrics.summary.total_registered_all_time])
    writer.writerow(["new_users_in_period", metrics.summary.new_users_in_period])
    writer.writerow([])
    writer.writerow(["date", "new_users"])
    for point in metrics.timeseries:
        writer.writerow([point.date.isoformat(), point.count])

    filename = f"users-metrics-{start.date().isoformat()}-{end.date().isoformat()}.csv"
    return buffer.getvalue(), filename
