from __future__ import annotations

import calendar
from datetime import date, datetime, timezone
from enum import Enum

from pydantic import BaseModel, model_validator


class MetricsInterval(str, Enum):
    day = "day"
    week = "week"
    month = "month"


def _add_calendar_months(dt: datetime, months: int) -> datetime:
    month_index = dt.month - 1 + months
    year = dt.year + month_index // 12
    month = month_index % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    day = min(dt.day, last_day)
    return dt.replace(year=year, month=month, day=day)


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class MetricsDateRangeParams(BaseModel):
    start_date: datetime
    end_date: datetime

    @model_validator(mode="after")
    def validate_range(self) -> MetricsDateRangeParams:
        start = _ensure_utc(self.start_date)
        end = _ensure_utc(self.end_date)
        if end < start:
            raise ValueError("end_date must be greater than or equal to start_date")
        if end > _add_calendar_months(start, 6):
            raise ValueError("date range cannot exceed 6 months")
        self.start_date = start
        self.end_date = end
        return self


class UsersMetricSummary(BaseModel):
    total_registered_all_time: int
    new_users_in_period: int


class UsersTimeseriesData(BaseModel):
    date: date
    count: int


class UsersMetricResponse(BaseModel):
    summary: UsersMetricSummary
    timeseries: list[UsersTimeseriesData]
