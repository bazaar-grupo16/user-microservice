# Users Metrics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add admin-only user registration metrics (`GET /users/admin/metrics/users` + CSV export) with SQL aggregations, 6-month date guardrails, and PostgreSQL integration tests.

**Architecture:** New code follows Router → `MetricsService` → `MetricsRepository`. Eligible users = `is_admin = false` (includes blocked). Gateway path prefix `/users/admin/metrics`; no ingress changes in this repo.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2.x, PostgreSQL 17, pytest + TestClient.

**Spec:** `docs/superpowers/specs/2026-06-02-users-metrics-design.md`

---

## File map

| File | Responsibility |
|------|----------------|
| `scripts/add_users_created_at_index.sql` | Idempotent index on `users.created_at` |
| `src/schemas/metrics.py` | Query params, 6-month validation, response models |
| `src/repositories/metrics.py` | `func.count`, `date_trunc`, `group_by` |
| `src/services/metrics.py` | Gap-fill buckets, CSV builder, structured logs |
| `src/api/routers/metrics.py` | HTTP layer, `AdminUser`, `StreamingResponse` for CSV |
| `src/main.py` | Register metrics router |
| `tests/test_metrics.py` | Integration tests (real DB) |
| `PLAN.md` | Checkbox tracker (updated each step) |
| `README.md` | Document paths + counting rules |

---

## Execution rules (from product owner)

1. **One atomic commit per task** below (after tests pass for that task).
2. **Update `PLAN.md`** marking the task done before pausing.
3. **Stop and wait for explicit approval** before starting the next task.
4. Run full suite: `./scripts/run_tests.sh` (or `docker compose -f docker-compose.test.yml up --build --abort-on-container-exit`).

---

### Task 0: Tracking checklist

**Files:**
- Create: `PLAN.md`

- [ ] **Step 1:** Create `PLAN.md` mirroring Tasks 1–7 with `- [ ]` boxes and link to this plan.

- [ ] **Step 2:** Commit**

```bash
git add PLAN.md docs/superpowers/specs/2026-06-02-users-metrics-design.md docs/superpowers/plans/2026-06-02-users-metrics.md
git commit -m "docs: add users metrics design spec and implementation plan"
```

---

### Task 1: Database index

**Files:**
- Create: `scripts/add_users_created_at_index.sql`
- Modify: `tests/conftest.py` (apply index after `create_all`)

- [ ] **Step 1:** Add SQL script

```sql
-- scripts/add_users_created_at_index.sql
CREATE INDEX IF NOT EXISTS ix_users_created_at ON users (created_at);
```

- [ ] **Step 2:** Apply in test session fixture** (`tests/conftest.py`, inside `_setup_database` after `create_all`):

```python
from sqlalchemy import text

def _apply_metrics_indexes() -> None:
    sql_path = Path(__file__).resolve().parents[1] / "scripts" / "add_users_created_at_index.sql"
    with engine.begin() as conn:
        conn.execute(text(sql_path.read_text()))
```

Call `_apply_metrics_indexes()` after `Base.metadata.create_all(bind=engine)`.

- [ ] **Step 3:** Run tests** — existing suite still green:

```bash
./scripts/run_tests.sh
```

Expected: all tests PASS.

- [ ] **Step 4:** Commit**

```bash
git add scripts/add_users_created_at_index.sql tests/conftest.py
git commit -m "perf: add index on users.created_at for metrics queries"
```

---

### Task 2: Pydantic schemas and date validation

**Files:**
- Create: `src/schemas/metrics.py`

- [ ] **Step 1:** Implement schemas**

```python
# src/schemas/metrics.py
from __future__ import annotations

import calendar
from datetime import date, datetime, timezone
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, Field, model_validator


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
```

- [ ] **Step 2:** Optional unit-style check** (no new file required): import in Python REPL or add a minimal test later in Task 6.

- [ ] **Step 3:** Commit**

```bash
git add src/schemas/metrics.py
git commit -m "feat: add metrics schemas with 6-month date validation"
```

---

### Task 3: Metrics repository (SQL only)

**Files:**
- Create: `src/repositories/metrics.py`

- [ ] **Step 1:** Implement repository**

```python
# src/repositories/metrics.py
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
```

- [ ] **Step 2:** Commit**

```bash
git add src/repositories/metrics.py
git commit -m "feat: add SQL aggregations for user metrics repository"
```

---

### Task 4: Metrics service (gap-fill + CSV)

**Files:**
- Create: `src/services/metrics.py`

- [ ] **Step 1:** Implement service**

Key functions:

- `get_users_metrics(db, start, end, interval) -> UsersMetricResponse`
- `build_users_metrics_csv(db, start, end) -> str`
- `_generate_bucket_starts(start, end, interval) -> list[date]`
- `_merge_buckets(generated, sql_rows, interval) -> list[UsersTimeseriesData]`

Gap-fill algorithm (day example):

```python
from datetime import date, datetime, timedelta, timezone

def _generate_bucket_starts(start: datetime, end: datetime, interval: MetricsInterval) -> list[date]:
    current = start.date()
    end_d = end.date()
    buckets: list[date] = []
    if interval == MetricsInterval.day:
        while current <= end_d:
            buckets.append(current)
            current += timedelta(days=1)
        return buckets
    # week: align to Monday of start week (PostgreSQL date_trunc week = Monday)
    # month: first day of each month from start.month through end.month
    ...
```

Map SQL `date_trunc` results to `date` keys in UTC. Log success:

```python
logger.info(
    "users_metrics_computed",
    extra={
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "interval": interval.value,
        "duration_ms": duration_ms,
    },
)
```

CSV format (v1 daily buckets):

```csv
metric,value
total_registered_all_time,42
new_users_in_period,7

date,new_users
2026-01-01,2
2026-01-02,0
```

- [ ] **Step 2:** Commit**

```bash
git add src/services/metrics.py
git commit -m "feat: add metrics service with timeseries gap-fill and CSV export"
```

---

### Task 5: Router + app registration

**Files:**
- Create: `src/api/routers/metrics.py`
- Modify: `src/main.py`

- [ ] **Step 1:** Router**

```python
# src/api/routers/metrics.py
import logging
from datetime import datetime

from fastapi import APIRouter, Query
from fastapi.responses import Response

from src.core.dependencies import AdminUser, DbSession
from src.schemas.metrics import MetricsDateRangeParams, MetricsInterval, UsersMetricResponse
from src.services import metrics as metrics_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users/admin/metrics", tags=["Metrics"])


@router.get("/users", response_model=UsersMetricResponse)
def get_users_metrics(
    admin_user: AdminUser,
    db: DbSession,
    start_date: datetime = Query(...),
    end_date: datetime = Query(...),
    interval: MetricsInterval = Query(default=MetricsInterval.day),
):
    params = MetricsDateRangeParams(start_date=start_date, end_date=end_date)
    return metrics_service.get_users_metrics(
        db=db,
        start=params.start_date,
        end=params.end_date,
        interval=interval,
    )


@router.get("/users/export")
def export_users_metrics(
    admin_user: AdminUser,
    db: DbSession,
    start_date: datetime = Query(...),
    end_date: datetime = Query(...),
):
    params = MetricsDateRangeParams(start_date=start_date, end_date=end_date)
    csv_body, filename = metrics_service.build_users_metrics_csv(
        db=db,
        start=params.start_date,
        end=params.end_date,
    )
    return Response(
        content=csv_body,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
```

Wrap Pydantic `ValidationError` in router or use a dependency — prefer catching in router:

```python
from pydantic import ValidationError
from fastapi import HTTPException

try:
    params = MetricsDateRangeParams(...)
except ValidationError as exc:
    raise HTTPException(status_code=422, detail=exc.errors()) from exc
```

- [ ] **Step 2:** Register in `src/main.py`**

```python
from src.api.routers.metrics import router as metrics_router
# ...
app.include_router(metrics_router)
```

- [ ] **Step 3:** Manual smoke** (local DB): `GET /users/admin/metrics/users?...` with admin token.

- [ ] **Step 4:** Commit**

```bash
git add src/api/routers/metrics.py src/main.py
git commit -m "feat: expose users admin metrics and CSV export endpoints"
```

---

### Task 6: Integration tests

**Files:**
- Create: `tests/test_metrics.py`

- [ ] **Step 1:** Implement test class** (pattern from `tests/test_auth.py`):

```python
# tests/test_metrics.py — structure
class TestUsersMetrics:
    def _create_user(self, *, created_at: datetime, is_admin: bool = False, is_active: bool = True) -> User: ...

    def _admin_headers(self, admin: User) -> dict[str, str]:
        return {"Authorization": f"Bearer token-for-{admin.id}"}

    def test_metrics_returns_200_for_admin(self, client): ...
    def test_metrics_excludes_admin_users_from_counts(self, client): ...
    def test_metrics_includes_blocked_users(self, client): ...
    def test_metrics_rejects_non_admin(self, client): ...
    def test_metrics_rejects_missing_token(self, client): ...
    def test_metrics_rejects_range_over_six_months(self, client): ...
    def test_metrics_rejects_end_before_start(self, client): ...
    def test_metrics_timeseries_day_buckets(self, client): ...
    def test_metrics_timeseries_week_interval(self, client): ...
    def test_export_returns_csv_with_summary_and_rows(self, client): ...
```

Use fixed UTC timestamps for deterministic buckets, e.g.:

```python
start = "2026-01-01T00:00:00Z"
end = "2026-01-03T23:59:59Z"
```

- [ ] **Step 2:** Run**

```bash
./scripts/run_tests.sh
```

Expected: all tests PASS including new module.

- [ ] **Step 3:** Commit**

```bash
git add tests/test_metrics.py
git commit -m "test: add integration tests for users metrics endpoints"
```

---

### Task 7: README documentation

**Files:**
- Modify: `README.md`

- [ ] **Step 1:** Add section **Admin metrics** with:

- Paths `/users/admin/metrics/users` and `.../export`
- Query params and `interval` enum
- Counting rule: non-admin only, includes blocked
- Note: gateway routes by `/users` prefix; no change to this repo's ingress

- [ ] **Step 2:** Commit**

```bash
git add README.md
git commit -m "docs: document users admin metrics endpoints"
```

---

## Plan self-review (spec coverage)

| Spec requirement | Task |
|------------------|------|
| Paths `/users/admin/metrics/*` | Task 5 |
| Admin auth | Task 5 (`AdminUser`) |
| 6-month validation | Task 2 |
| SQL aggregations only | Task 3 |
| Index `created_at` | Task 1 |
| Exclude admins, include blocked | Task 3 filter + Task 6 tests |
| Gap-fill timeseries | Task 4 |
| CSV export daily v1 | Task 4 + 6 |
| No ingress change | N/A (documented) |
| Integration tests PostgreSQL | Task 6 |
| INFO logs no PII | Task 4 |
| README | Task 7 |

No placeholders remain.

---

## Post-completion

- [ ] Mark all items in `PLAN.md` complete
- [ ] Confirm CI (`ci-dev.yml`) passes on branch
- [ ] Coordinate API Gateway route for `/users/admin/metrics/*` (outside this repo)
