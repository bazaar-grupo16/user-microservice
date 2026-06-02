# Users Metrics — Design Spec

**Date:** 2026-06-02  
**Service:** user-microservice (Bazaar)  
**Epic:** Métricas — usuarios registrados (historia obligatoria #21 + optativa export #41)

## Context

The backoffice needs analytics endpoints for user registration metrics. Orders, revenue, and product rankings live in other microservices. This service owns user registration data (`users.created_at`).

References:

- `.agents/metricas/openapi.json` (response shapes; paths extended with service prefix)
- `.agents/Historias de Usuario.md` — Épica Métricas CA1, Exportar datos CA1–CA3
- `.agents/Requisitos No Funcionales.md` — Observability red lines
- `.agents/Guía de Arquitectura e Infraestructura.txt` — Layered architecture, `/livez` / `/readyz`

Existing observability (JSON logs, correlation ID, `/livez`, `/readyz`, Prometheus `/metrics`) is already implemented and is not part of this change.

## Goals

1. Expose admin-only metrics JSON and CSV export for user registrations.
2. Compute all totals via SQL aggregation (no in-memory list aggregation).
3. Protect memory: DB index on `created_at`, Pydantic max 6-month date range.
4. Follow Router → Service → Repository for new code.
5. Integration tests against real PostgreSQL (`docker-compose.test.yml`); mock only external HTTP (auth/profile).

## Non-goals

- Order, revenue, category, or product metrics (other services).
- Changes to `k8s/ingress.yaml` in this repository.
- Refactoring existing auth controllers to a Service layer.
- Async export jobs; export is synchronous download (optative story CA2).

## User counting rules

Approved rule (**A + C**):

- **Include:** all rows in `users` regardless of `is_active` (active and blocked).
- **Exclude:** rows where `is_admin = true`.

Apply this filter in every metric query (`total_registered_all_time`, `new_users_in_period`, timeseries buckets).

## API contract

### Base path prefix

Multiple microservices expose `admin/metrics/*`. The API Gateway routes by domain prefix. **Public paths:**

| Method | Path | Description |
|--------|------|-------------|
| GET | `/users/admin/metrics/users` | Summary + timeseries JSON |
| GET | `/users/admin/metrics/users/export` | CSV download for the same period |

Internal FastAPI routes match these paths (no ingress change in user-microservice).

The reference OpenAPI at `.agents/metricas/openapi.json` documents shapes under `/admin/metrics/users`; the implemented paths add the `/users` prefix documented here.

### Authentication

- Same as other admin endpoints: `AdminUser` dependency (Bearer token validated via auth-microservice mock/real client).
- Unauthenticated or non-admin → 401/403 consistent with `/admin/users`.

### Query parameters

**`GET /users/admin/metrics/users`**

| Parameter | Required | Type | Notes |
|-----------|----------|------|-------|
| `start_date` | yes | `date-time` | Period start (inclusive), UTC |
| `end_date` | yes | `date-time` | Period end (inclusive), UTC |
| `interval` | no | `day` \| `week` \| `month` | Default `day` |

**`GET /users/admin/metrics/users/export`**

| Parameter | Required | Type |
|-----------|----------|------|
| `start_date` | yes | `date-time` |
| `end_date` | yes | `date-time` |

### Validation (Pydantic)

- `end_date >= start_date`
- Maximum range: **6 calendar months** between `start_date` and `end_date`
- Missing dates on export → 422 (optative story CA3)

### Response JSON (`UsersMetricResponse`)

```json
{
  "summary": {
    "total_registered_all_time": 0,
    "new_users_in_period": 0
  },
  "timeseries": [
    { "date": "2026-01-01", "count": 0 }
  ]
}
```

| Field | Semantics |
|-------|-----------|
| `total_registered_all_time` | `COUNT(*)` eligible users (non-admin), all time |
| `new_users_in_period` | Eligible users with `created_at` in `[start_date, end_date]` |
| `timeseries[].date` | Bucket start date (ISO `date`) |
| `timeseries[].count` | New eligible users in that bucket |

### CSV export

- `Content-Type: text/csv`
- `Content-Disposition: attachment; filename="users-metrics-{start}-{end}.csv"`
- Columns: `date`, `new_users` (one row per bucket; same interval default as JSON `day` unless export spec adds `interval` later — **v1 uses `day` buckets only for CSV** to keep export aligned with simplest backoffice use; if `interval` is added to export query later, document in README)
- Summary row(s) optional header comment or leading rows: `total_registered_all_time`, `new_users_in_period` as labeled fields before timeseries data

**Clarification for v1:** Export endpoint accepts only `start_date` and `end_date` per OpenAPI; CSV contains daily (`day`) buckets plus summary metadata in header rows.

### Timezone

All comparisons and `date_trunc` bucketing use **UTC**, consistent with `User.created_at` defaults.

## Architecture

```
src/api/routers/metrics.py
  └── depends: AdminUser, DbSession, query params → MetricsService

src/services/metrics.py
  └── business rules: gap-fill empty buckets, build CSV, logging

src/repositories/metrics.py
  └── SQLAlchemy: func.count, date_trunc, group_by, WHERE is_admin = false

src/schemas/metrics.py
  └── request validators + response models
```

Register router in `src/main.py` with paths under `/users/admin/metrics`.

### Database performance

Add index (idempotent SQL script or migration):

```sql
CREATE INDEX IF NOT EXISTS ix_users_created_at ON users (created_at);
```

Optional if explain plans show benefit:

```sql
CREATE INDEX IF NOT EXISTS ix_users_non_admin_created_at ON users (created_at) WHERE is_admin = false;
```

Use partial index only if the team’s PostgreSQL version and migration approach support it; otherwise composite filter in queries with `ix_users_created_at` is sufficient for TP scale.

### SQL rules (strict)

- **Forbidden:** `query(User).all()` then `len()` or Python loops for totals.
- **Required:** `func.count()`, `date_trunc('day'|'week'|'month', ...)`, `GROUP BY`, `WHERE User.is_admin.is_(False)`.

### Timeseries gap-fill

SQL returns only buckets with data. `MetricsService` generates the full date sequence from `start_date` to `end_date` for the chosen `interval` and merges SQL results, filling missing buckets with `count: 0`.

### Observability (per request)

- Propagate existing correlation ID (middleware already active).
- Log at **INFO** on successful metrics read: `correlation_id`, `start_date`, `end_date`, `interval`, duration_ms — **no email or PII**.
- Log at **WARN** on validation failures.

No changes to `/livez` / `/readyz` semantics.

## Testing strategy

File: `tests/test_metrics.py` (integration, PostgreSQL real).

| Case | Expected |
|------|----------|
| Admin + valid range | 200, schema match |
| Regular user token | 403 |
| Missing/invalid token | 401 |
| Admin user row in DB | Excluded from counts |
| Blocked non-admin user | Included in counts |
| `end_date < start_date` | 422 |
| Range > 6 months | 422 |
| Seeded users across days | Timeseries counts correct for `day` |
| Week/month interval | Buckets align with `date_trunc` |
| Export | `text/csv`, correct rows, attachment header |

Reuse `conftest.py` patterns: `TestClient`, direct DB seeding via SQLAlchemy session, admin Bearer `token-for-{uuid}`.

## Implementation plan (atomic steps)

Executed iteratively: one commit per step, update `PLAN.md` after each step, pause for explicit approval before the next step.

| Step | Deliverable |
|------|-------------|
| 0 | `PLAN.md` checklist from this spec |
| 1 | DB index script + apply in test lifecycle if needed |
| 2 | `src/schemas/metrics.py` (validators + response models) |
| 3 | `src/repositories/metrics.py` (aggregations only) |
| 4 | `src/services/metrics.py` (gap-fill, CSV builder) |
| 5 | `src/api/routers/metrics.py` + register in `main.py` |
| 6 | `tests/test_metrics.py` full coverage |
| 7 | README: document public paths and counting rules |

**Explicitly out of scope for steps:** `k8s/ingress.yaml` changes (gateway routes `/users/admin/metrics/*` to this service externally).

## Decisions log

| Decision | Rationale |
|----------|-----------|
| Prefix `/users/admin/metrics` | Gateway disambiguates users vs orders metrics; matches `/users/livez` pattern |
| No ingress edit in repo | Routing owned by API Gateway / other team config |
| Exclude admins only | Product metric = platform users, not staff accounts |
| Include blocked users | User chose “all registrations” (A) minus admins (C) |
| Service layer for metrics only | User directive; avoid refactoring auth in same epic |
| Gap-fill in service | Continuous chart for backoffice without generating empty SQL buckets |
| UTC everywhere | Avoid ambiguous local timezone in aggregations |

## Open questions (resolved)

| Question | Resolution |
|----------|------------|
| Which users to count? | Non-admin only; active + blocked |
| Path prefix? | `/users/admin/metrics` |
| Ingress update? | No |

None remaining for implementation.
