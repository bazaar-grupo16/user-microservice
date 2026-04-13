# Project Guidelines

## Architecture
- FastAPI entry point lives in [src/main.py](../src/main.py); routers are under [src/api/](../src/api/), core app wiring is under [src/core/](../src/core/), ORM models under [src/models/](../src/models/), repositories under [src/repositories/](../src/repositories/), and schemas under [src/schemas/](../src/schemas/).
- The app waits for PostgreSQL on startup and creates tables from ORM metadata for development convenience. Use migrations for production work instead of adding more startup-side schema changes.
- Health checks are split between liveness and readiness endpoints in [src/api/health.py](../src/api/health.py).

## Build and Test
- On Linux/macOS, run tests with [scripts/run_tests.sh](../scripts/run_tests.sh). On Windows, use [scripts/run_tests.ps1](../scripts/run_tests.ps1). Both wrap Docker Compose and run pytest against a real PostgreSQL database.
- For direct Docker Compose execution, use `docker compose -f docker-compose.test.yml up --build --abort-on-container-exit --exit-code-from test-runner`.
- For local development, use `uvicorn src.main:app --reload` after loading the environment variables from [.env.example](../.env.example).

## Conventions
- Keep configuration in environment variables. Do not hardcode database credentials or app settings.
- Tests use a real PostgreSQL instance and do not rely on mocking. Preserve that pattern when adding coverage.
- Keep changes focused and consistent with the existing package layout. The current router package has a filename typo at [src/api/routers/__init_.py](../src/api/routers/__init_.py); do not rename it casually without checking imports.
- Use [README.md](../README.md) as the source of truth for deployment, Kubernetes, and CI/CD details rather than duplicating those instructions here.