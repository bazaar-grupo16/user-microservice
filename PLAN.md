# Users Metrics — Execution Checklist

**Spec:** [docs/superpowers/specs/2026-06-02-users-metrics-design.md](docs/superpowers/specs/2026-06-02-users-metrics-design.md)  
**Detailed plan:** [docs/superpowers/plans/2026-06-02-users-metrics.md](docs/superpowers/plans/2026-06-02-users-metrics.md)

**Workflow:** Complete one task → run tests → commit → mark `[x]` here → **wait for approval** before the next task.

- [x] **Task 0** — `PLAN.md` + docs commit
- [ ] **Task 1** — DB index (`scripts/add_users_created_at_index.sql`, `conftest.py`)
- [ ] **Task 2** — `src/schemas/metrics.py`
- [ ] **Task 3** — `src/repositories/metrics.py`
- [ ] **Task 4** — `src/services/metrics.py`
- [ ] **Task 5** — `src/api/routers/metrics.py` + `main.py`
- [ ] **Task 6** — `tests/test_metrics.py`
- [ ] **Task 7** — README metrics section

**Test command:** `./scripts/run_tests.sh`
