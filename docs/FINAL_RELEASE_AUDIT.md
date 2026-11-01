# Faultline Final Release Audit

**Audit date:** 2026-11-01
**Audited starting commit:** `f7a4aef97d293c0110f7436b15852bab99908523` (`main`)
**Audit scope:** Backend, migrations, security controls, containers, frontend, and release workflow. No production database or public deployment was used.

## Release verdict

**NOT READY for production release certification.**

Application code and frontend checks pass, and the migration metadata discrepancy found in this audit has been corrected. Production readiness is still unproven because the Docker Engine was unavailable: no image builds, PostgreSQL container, isolated test execution, or real end-to-end workflow could be run. In addition, the current shared service token does not provide user or project authorization. Do not expose this deployment to public or multi-tenant users.

## Environment and versions

| Component | Version / state |
|---|---|
| OS | Windows |
| Python | 3.12.6 |
| pytest | 9.2.0 |
| Ruff | 0.17.3 |
| Node.js | 24.19.0 |
| npm | 11.17.0 |
| Next.js | 16.4.3 |
| FastAPI | 0.162.0 |
| Pydantic | 2.14.2 |
| SQLAlchemy | 2.1.6 |
| Alembic | 1.20.1 |
| Docker CLI | 29.7.2 |
| Docker Compose | 5.4.0 |
| Docker Engine | **Unavailable**; Docker Desktop Linux engine pipe was missing |

## Verification results

| Area | Verdict | Evidence |
|---|---|---|
| Backend tests | **PASS** | `python -m pytest -q`: 184 passed, 21 warnings, 0 failures. Warnings are Starlette/FastAPI deprecations. |
| Ruff lint | **PASS** | `ruff check backend`: all checks passed. |
| Ruff formatting | **PASS** | `ruff format --check backend`: 112 files formatted. |
| Python compilation | **PASS** | `python -m compileall -q backend\app backend\migrations`: exit 0. |
| Application import/startup | **PASS** | FastAPI `TestClient` started; `/health/live` returned 200. |
| Health/readiness | **PARTIAL** | `/health/ready` returned 200 with `database=available`, `execution_runner=unavailable`, `status=degraded`. The runner result matches the unavailable Docker Engine. |
| OpenAPI | **PASS** | `/api/v1/openapi.json` returned 200 and contained 31 paths. |
| Alembic history | **PASS** | One ordered chain, `0001_initial_schema` through head `0005_repair_evaluations`. |
| Fresh migration / rollback | **PASS (SQLite only)** | Disposable SQLite database upgraded to head, downgraded to base, and upgraded to head again; no production data was used. |
| Model/migration consistency | **PASS (SQLite only)** | Fresh database `alembic check` reported no new operations after the correction described below. PostgreSQL comparison was not run. |
| Frontend dependency install | **PASS** | `npm --prefix frontend ci`: 357 packages added; 358 audited; 0 vulnerabilities reported. npm emitted a deprecation warning for ESLint 9.39.5. |
| Frontend production build | **PASS** | `npm --prefix frontend run build`: Next.js production build completed. |
| Frontend TypeScript | **PASS** | `npm --prefix frontend run typecheck`: `tsc --noEmit` completed successfully. |
| Frontend lint | **PASS** | `npm --prefix frontend run lint`: ESLint completed successfully. |
| Development Compose config | **PASS** | `docker compose -f docker-compose.yml config --quiet`: exit 0. |
| Production Compose config | **PASS** | `docker compose --env-file production.env.example -f compose.production.yml config --quiet`: exit 0. This validates configuration parsing, not container startup or secret availability. |
| API, runner, frontend image builds | **BLOCKED** | Each `docker build` attempt failed because the Docker Engine endpoint was unavailable. |
| Container startup, health checks, PostgreSQL connectivity | **BLOCKED** | No Docker Engine. |
| Isolated runner smoke test | **BLOCKED** | No Docker Engine; runner security flags were reviewed statically only. |
| Browser/API integration | **BLOCKED** | The available browser showed the expected API-offline state and `ERR_CONNECTION_REFUSED` for `localhost:8000`. No live backend integration was demonstrated. |
| Complete product workflow | **NOT TESTED** | There was no continuous workflow against a disposable PostgreSQL database and real Docker runner. |

### Commands executed

The following are the final verification commands and their outcomes:

```powershell
python -m pytest -q
ruff check backend
ruff format --check backend
python -m compileall -q backend\app backend\migrations
python -m alembic -c alembic.ini history
python -m alembic -c alembic.ini heads
```

Migration verification used a unique temporary SQLite file for each run:

```powershell
python -m alembic -c alembic.ini upgrade head
python -m alembic -c alembic.ini check
python -m alembic -c alembic.ini downgrade base
python -m alembic -c alembic.ini upgrade head
```

The migration-consistency regression test uses an in-memory SQLite database and runs Alembic to head followed by `alembic check`.

Frontend:

```powershell
npm --prefix frontend ci
npm --prefix frontend run build
npm --prefix frontend run typecheck
npm --prefix frontend run lint
```

Container configuration and runtime probes:

```powershell
docker compose -f docker-compose.yml config --quiet
docker compose --env-file production.env.example -f compose.production.yml config --quiet
docker info
docker build -t faultline-audit-api -f Dockerfile .
docker build -t faultline-audit-runner -f docker\runner.Dockerfile .
docker build -t faultline-audit-frontend frontend
```

The Compose configuration commands passed. `docker info` and all three image builds failed with the missing `dockerDesktopLinuxEngine` named pipe; no replacement/mock was used.

The startup probe ran `TestClient` with `PYTHONPATH=backend` and `DATABASE_URL=sqlite://`, then requested `/health/live`, `/health/ready`, and `/api/v1/openapi.json`. It verified application startup and SQLite connectivity only.

## Backend and migration findings

The backend imports successfully and registers 31 OpenAPI paths. The test suite covers API and service behavior using in-memory SQLite and test fixtures; it does not constitute a live integration run of GitHub ingestion, Docker execution, PostgreSQL persistence, or ForgeFit.

The initial `alembic check` detected two metadata differences: `BaselineExecution` and `ExecutionResult` described unique constraints, while migration `0002_execution_engine` creates equivalently named unique indexes. The existing database semantics already enforce uniqueness, but Alembic considered the model metadata divergent. The models now describe the existing unique indexes, and `backend/tests/test_migration_consistency.py` guards the migration-to-model comparison. Fresh SQLite upgrade, downgrade, re-upgrade, and `alembic check` now pass.

PostgreSQL-specific startup, connection pooling, TLS settings, and migration behavior remain unverified. SQLite verification is not a substitute for PostgreSQL verification.

## Security findings

| Severity | Finding | Evidence and required action |
|---|---|---|
| **HIGH** | No user identity, project authorization, or tenant isolation | The backend uses a shared service bearer token, and the frontend proxy applies it server-side for requests. An ingress that merely authenticates users does not create per-project authorization. Restrict deployment to a single trusted user group, or add and validate user/project authorization before multi-user or public exposure. |
| **MEDIUM** | Repository clone storage is not bounded during the clone | Git clone has a timeout and the repository inventory enforces size/file limits after cloning. The shared workspace has no application-enforced disk quota, so the post-clone bound does not itself prevent workspace-volume exhaustion. Apply a host filesystem quota and ingress/user limits, or implement an enforced clone-time storage bound before accepting untrusted users. |
| **MEDIUM (conditional)** | External ForgeFit target enforcement is not end-to-end verifiable | Faultline requires explicit scenario authorization, performs public-address DNS checks, and defaults external targets off. The ForgeFit service performs the eventual target request; its DNS resolution and egress policy were unavailable for audit. Keep `FORGEFIT_ALLOW_EXTERNAL_TARGETS=false` unless the service independently enforces equivalent restrictions. |
| **MEDIUM (conditional)** | TLS is not required by validation for an externally configured PostgreSQL URL | The bundled Compose PostgreSQL service is private and has no published host port. If replacing it with an external database, require TLS and certificate verification in the deployment URL/configuration and verify it on the target environment. |
| **MEDIUM** | API rate limits are process-local and keyed by source IP | The frontend proxy sends API requests from the same frontend container address, so backend limits are not per end user. Enforce per-user/IP limits at the authenticated ingress/API gateway; do not rely on the backend limiter as the sole public-facing control. |

### Controls reviewed (static evidence, not runtime certification)

- Production settings require an explicit PostgreSQL URL, a secret-backed bearer token, `DEBUG=false`, `PRIVATE_DEPLOYMENT=true`, explicit trusted hosts, and HTTPS CORS origins.
- The production bearer token is compared in constant time. Health paths are intentionally unauthenticated.
- The API applies request-body limits and process-local limits to sensitive/expensive operations.
- Git calls use argument arrays with `shell=False`, an isolated Git environment, HTTPS-only protocol, shallow single-branch clones, disabled submodules, and a timeout. Repository path validation is restricted to public GitHub URLs.
- Ingestion checks workspace symlinks and imposes post-clone file/size limits.
- Docker runner configuration sets network isolation, read-only root/workspace, non-root UID, dropped capabilities, no-new-privileges, CPU/memory/PID/time/output limits, and cleanup. The runner receives no explicit API bearer token or Docker client certificate. Runtime escape resistance and secret non-exposure were not proven without a daemon.
- Structured logs include request IDs and status/timing metadata. Error logging records exception type rather than exception message; execution output is stored as workflow data, not emitted by the reviewed logging paths.
- The frontend production API token is server-side (`FAULTLINE_API_TOKEN_FILE`), not a `NEXT_PUBLIC_` variable. The public Next.js API base is the same-origin `/api/v1` proxy.
- Production Compose puts PostgreSQL on an internal network without a published port and configures Docker daemon mutual TLS rather than mounting `docker.sock`. Actual daemon TLS, secret file permissions, and same-absolute-path workspace mounts still require target-environment verification.

## Docker and deployment

Static inspection found non-root API/frontend/runner users, resource limits, read-only production containers, bounded tmpfs mounts, restart policies, health checks, PostgreSQL persistence, internal networking, and secret-file mounts. Compose parsing passed for both local and production configurations.

None of those static properties proves that the configured host, remote Docker daemon, certificate permissions, bind mounts, or runner image work together. API/frontend/runner image builds, container health, PostgreSQL connectivity, and the actual isolated execution smoke test are **BLOCKED** until a compatible Docker Engine is available.

## Frontend and browser

The frontend production build, type-check, and lint passed. The browser displayed the application’s API-offline state with an actionable backend connection message. Requests to `localhost:8000` failed with `ERR_CONNECTION_REFUSED`, so browser/API behavior with a running backend, authenticated production proxy, and production container was not tested. No complete accessibility audit or screen-reader/browser matrix was run.

## End-to-end workflow status

| Workflow stage | Status | What the evidence establishes |
|---|---|---|
| Register project | **PARTIAL** | API/service tests passed with test database fixtures; no continuous production-style run. |
| Connect/ingest repository | **PARTIAL** | Validation and service tests passed; no actual GitHub clone was exercised in this audit. |
| Create and inspect snapshot | **PARTIAL** | Component tests passed; no complete live ingestion-to-snapshot workflow. |
| Generate mutations | **PARTIAL** | Component tests passed; no live runner-backed workflow. |
| Execute baseline tests | **BLOCKED** | No Docker daemon; real untrusted code execution was not attempted. |
| Execute mutated tests | **BLOCKED** | No Docker daemon; no isolated runner smoke test. |
| Generate failure diagnoses | **PARTIAL** | Service/API behavior tested with fixtures, not from a real runner result. |
| Generate repair candidates | **PARTIAL** | Service/API behavior tested with fixtures, not from a live execution. |
| Review/reject repair candidate | **PARTIAL** | API/service tests passed; no complete user workflow. |
| Evaluate repair candidate | **PARTIAL** | Evaluation persistence/logic tests passed on test fixtures; no live test execution or ForgeFit run. |
| Retrieve evaluation history | **PARTIAL** | API/database tests passed with in-memory SQLite; PostgreSQL persistence was not tested. |
| All steps in one workflow | **NOT TESTED** | No disposable PostgreSQL database plus real isolated runner was available. |

No mocked or unit test is represented as a successful Docker or end-to-end integration test.

## Deployment blockers and required operator actions

Before any production release:

1. Provide a running Docker Engine and validate mutual-TLS connectivity from the API container. Build all three images and run the real runner smoke test, including timeout, output-limit, network isolation, cleanup, and a test repository containing hostile code.
2. Validate PostgreSQL 16 startup, readiness, connectivity, migrations, backup/restore, and upgrade procedure against a disposable PostgreSQL instance before production.
3. Configure an HTTPS ingress that authenticates the intended users and applies per-user rate limits. Keep the system restricted to a single trusted group unless project-level authorization and tenant isolation are implemented and tested.
4. Create and permission the Docker-daemon-visible workspace at the exact same absolute path; apply an operating-system disk quota and monitor free space.
5. Restrict secret files and Docker client certificates to the deployment identity. Verify secret mounts and rotation behavior on the target host.
6. Keep ForgeFit external targets disabled until the downstream service’s target validation and egress controls are independently verified.
7. Run the full 11-stage workflow against disposable PostgreSQL and a real isolated runner; retain evidence of persisted evaluation history and container cleanup.

No public deployment was performed. No production data was read, modified, or used for migration tests.

## Audit correction

The ORM metadata for the two unique indexes in migration `0002_execution_engine` was aligned with the existing schema, and an Alembic consistency regression test was added. This preserves uniqueness and does not change API contracts or the database architecture.

The starting revision audited was `f7a4aef97d293c0110f7436b15852bab99908523`. The audit correction and this report are intended to be delivered together; the starting SHA is not a claim that the post-audit changes existed in that revision.
