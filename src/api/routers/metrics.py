from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from src.core.dependencies import AdminUser, DbSession
from src.schemas.metrics import MetricsDateRangeParams, MetricsInterval, UsersMetricResponse
from src.services import metrics as metrics_service

router = APIRouter(prefix="/users/admin/metrics", tags=["Metrics"])


def get_metrics_date_range(
    start_date: datetime = Query(...),
    end_date: datetime = Query(...),
) -> MetricsDateRangeParams:
    return MetricsDateRangeParams(start_date=start_date, end_date=end_date)


MetricsDateRange = Annotated[MetricsDateRangeParams, Depends(get_metrics_date_range)]


@router.get("/users", response_model=UsersMetricResponse)
def get_users_metrics(
    _admin_user: AdminUser,
    db: DbSession,
    date_range: MetricsDateRange,
    interval: MetricsInterval = Query(default=MetricsInterval.day),
):
    return metrics_service.get_users_metrics(
        db=db,
        start=date_range.start_date,
        end=date_range.end_date,
        interval=interval,
    )


@router.get("/users/export")
def export_users_metrics(
    _admin_user: AdminUser,
    db: DbSession,
    date_range: MetricsDateRange,
):
    csv_body, filename = metrics_service.build_users_metrics_csv(
        db=db,
        start=date_range.start_date,
        end=date_range.end_date,
    )
    return Response(
        content=csv_body,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
