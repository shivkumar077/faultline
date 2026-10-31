# FAULTLINE

Faultline is a code-level failure engineering, diagnosis, and automated remediation platform. It stress-tests target codebases by methodically injecting syntactically and semantically valid code mutations, running baseline and regression test suites, capturing failure deltas, and providing structured root-cause analysis with actionable remediation patches.

---

## Relationship with Synthetic and ForgeFit

Faultline operates within a triad of engineering reliability systems:

- **Synthetic**: Generates synthetic workloads, high-entropy test fixtures, and contract-conforming edge-case inputs to simulate complex runtime environments.
- **ForgeFit**: Defines deterministic fitness criteria, repair evaluation harnesses, and benchmarks for judging candidate patches and automated refactorings.
- **Faultline**: The central orchestration and failure-injection platform. Faultline connects to target repositories, captures code snapshots, injects systematic code-level faults, captures baseline vs. mutated execution differences, and produces diagnostic failure reports and remediation guidance.

```
       +-----------------------------------------------+
       |                   FAULTLINE                   |
       |  (Repository Management, Code Snapshots,     |
       |   Mutation Engine, Analysis & Failure Reports) |
       +-----------------------+-----------------------+
                               |
               +---------------+---------------+
               |                               |
               v                               v
     +-------------------+           +-------------------+
     |     SYNTHETIC     |           |     FORGEFIT      |
     | (Workload & Test  |           | (Fitness Scoring  |
     |  Fixture Synth)   |           |  & Patch Harness) |
     +-------------------+           +-------------------+
```

---

## Backend Architecture

The backend follows a layered, decoupled service-repository architecture designed for maintainability and deterministic testing:

- **API Layer (`app/api/v1/`)**: FastAPI routers and endpoints handling HTTP serialization, validation, status codes, query pagination, and routing.
- **Service Layer (`app/services/`)**: Core domain workflows, slugification, business constraints, cascade handling, and count aggregation.
- **Repository Layer (`app/repositories/`)**: Abstracted query operations built on SQLAlchemy 2.0 select statements, count optimizations, and pagination queries.
- **Data Models (`app/models/`)**: Declarative SQLAlchemy models with UUID primary keys, explicit foreign key cascades, JSON/Text fields, and indexed lookups.
- **Schemas (`app/schemas/`)**: Pydantic v2 data transfer objects ensuring strict schema validation and serialization for inputs, responses, and paginated wrappers.
- **Database Runtime (`app/db/`)**: Engine configuration supporting pooled PostgreSQL connections for production and SQLite compatibility for isolated unit tests.
- **Migrations (`migrations/`)**: Alembic database versioning and reversible migration scripts.

---

## Technology Stack

- **Runtime**: Python 3.12+
- **Framework**: FastAPI (v0.110+)
- **Server**: Uvicorn with standard extras
- **ORM**: SQLAlchemy 2.0+ (DeclarativeBase, typed mapped columns)
- **Database Migrations**: Alembic
- **Primary Database**: PostgreSQL 16
- **Database Driver**: psycopg2-binary
- **Data Validation & Settings**: Pydantic v2 & Pydantic-Settings
- **Testing**: Pytest, FastAPI TestClient, in-memory SQLite with static connection pooling
- **Code Quality**: Ruff (linter & code formatter)
- **Containerization**: Docker (multi-stage Python 3.12 slim), Docker Compose
- **Frontend**: Next.js App Router, React, TypeScript, Tailwind CSS v4 theme processing, ESLint, and Lucide icons

---

## Repository Structure

```
faultline/
├── .env.example                     # Environment template configuration
├── Dockerfile                       # Production container specification
├── docker/
│   └── runner.Dockerfile             # Separate untrusted-test runner image
├── docker-compose.yml               # Multi-container orchestration (API + Postgres)
├── pyproject.toml                   # Project metadata, dependencies, and tool settings
├── alembic.ini                      # Alembic migration configuration
├── README.md                        # Technical documentation
├── frontend/                        # Next.js application and typed API client
│   ├── app/                          # App Router pages and copied global stylesheet
│   ├── components/                   # Responsive shell and shared UI
│   ├── lib/                          # API client, types, and formatters
│   ├── .env.example                  # Frontend API base URL
│   └── package.json                  # Frontend scripts and dependencies
└── backend/
    ├── migrations/                  # Database migration management
    │   ├── env.py                   # Alembic environment runner
    │   ├── script.py.mako           # Migration template
    │   └── versions/                # Versioned migration files
    │           ├── 0001_initial_schema.py
    │           ├── 0002_execution_engine.py
    │           ├── 0003_failure_diagnosis.py
    │           ├── 0004_repair_candidates.py
    │           └── 0005_repair_evaluations.py
    ├── app/
    │   ├── main.py                  # FastAPI application entry point
    │   ├── core/                    # Application settings and custom exceptions
    │   │   ├── config.py
    │   │   └── exceptions.py
    │   ├── db/                      # Session factory and Base model registration
    │   │   ├── base.py
    │   │   └── session.py
    │   ├── models/                  # SQLAlchemy 2.0 ORM models
    │   │   ├── project.py
    │   │   ├── repository_connection.py
    │   │   ├── code_snapshot.py
    │   │   ├── analysis_run.py
    │   │   ├── baseline_execution.py
    │   │   ├── mutation_record.py
    │   │   ├── execution_result.py
    │   │   ├── failure_report.py
    │   │   └── repair_candidate.py
    │   ├── schemas/                 # Pydantic v2 models and common response types
    │   │   ├── common.py
    │   │   ├── project.py
    │   │   ├── repository_connection.py
    │   │   ├── code_snapshot.py
    │   │   ├── analysis_run.py
    │   │   ├── baseline_execution.py
    │   │   ├── mutation_record.py
    │   │   ├── execution_result.py
    │   │   ├── failure_report.py
    │   │   ├── diagnosis.py
    │   │   └── repair_candidate.py
    │   ├── repositories/            # Data access layer
    │   │   ├── base.py
    │   │   ├── project_repository.py
    │   │   ├── analysis_repository.py
    │   │   ├── failure_report_repository.py
    │   │   └── repair_candidate_repository.py
    │   ├── services/                # Business logic services
    │   │   ├── project_service.py
    │   │   ├── analysis_service.py
    │   │   ├── diagnosis_parser.py
    │   │   ├── diagnosis_service.py
    │   │   ├── repair_patch_generator.py
    │   │   └── repair_service.py
    │   └── api/
    │       └── v1/                  # Versioned API routes
    │           ├── router.py
    │           └── endpoints/
    │               ├── health.py
    │               ├── projects.py
    │               ├── analyses.py
    │               ├── diagnoses.py
    │               └── repairs.py
    └── tests/                       # Pytest test suite
        ├── conftest.py              # Test database fixtures and FastAPI test client
        ├── test_health.py           # Health checks and application metadata tests
        ├── test_projects.py         # Project CRUD and duplicate slug tests
        ├── test_analyses.py         # Analysis listing and retrieval tests
        ├── test_repair_service.py   # Repair safety and patch generation tests
        └── test_repair_api.py       # Repair candidate API tests
```

---

## Local Installation & Setup

### Prerequisites
- Python 3.12+
- Node.js 20.9+ and npm (frontend)
- PostgreSQL 16 (optional for local SQLite development, required for production)
- Docker & Docker Compose (optional for containerized runtime)

### Frontend workspace

The Next.js App Router frontend lives in `frontend/` and consumes the versioned
FastAPI API directly. It does not provide a second backend or mock production
data. The backend currently has no authentication; the UI reflects that API
contract. CORS already permits the local Next.js origin (`http://localhost:3000`).

```powershell
cd frontend
npm install
Copy-Item .env.example .env.local
npm run dev
```

Set `NEXT_PUBLIC_API_BASE_URL` to the FastAPI v1 base URL, including `/api/v1`;
for example, `http://localhost:8000/api/v1`. The default matches the Compose
backend port. Start the API and database separately from the repository root
with `docker compose up --build`. Run `npm run build`, `npm run typecheck`, and
`npm run lint` from `frontend/` before deployment.

The interface supports project creation/deletion, public GitHub repository
connections and synchronization, snapshot inventory, deterministic mutation
generation, test execution, diagnosis reports, patch review, and candidate
evaluation. Execution remains subject to the backend's Docker runner setup.
ForgeFit scenarios are optional and require server-side ForgeFit configuration
and authorization for any external target. The backend exposes no consolidated
activity feed or global search endpoint; the dashboard derives counts from
available API records, and project/analysis search is scoped to the currently
loaded page.

### 1. Clone & Set Up Virtual Environment

```bash
git clone https://github.com/shivkumar077/faultline.git
cd faultline

# Create and activate virtual environment
python -m venv .venv

# On Linux/macOS:
source .venv/bin/activate
# On Windows PowerShell:
.\.venv\Scripts\Activate.ps1

# Install project and development dependencies
pip install -e ".[dev]"
```

### 2. Environment Configuration

Copy the sample environment file:

```bash
cp .env.example .env
```

Key environment parameters:
- `DATABASE_URL`: Connection string (e.g., `postgresql://faultline:faultline_dev_secret@localhost:5432/faultline`)
- `ENVIRONMENT`: `development` | `staging` | `production`
- `DEBUG`: `true` | `false`
- `API_V1_PREFIX`: API route prefix (`/api/v1`)
- `CORS_ORIGINS`: Allowed origins list as JSON array or comma-delimited strings

---

## Database Migrations

Alembic manages database revisions. Ensure `PYTHONPATH` includes the `backend` folder when executing migrations directly:

```bash
# Apply all pending migrations to database
alembic upgrade head

# Roll back the most recent migration
alembic downgrade -1

# Check current revision status
alembic current

# Create a new migration revision
alembic revision --autogenerate -m "describe_change"
```

---

## Running with Docker Compose

To start the full stack (PostgreSQL database + Faultline FastAPI backend):

```bash
# Build and start containers in the background
docker compose up --build -d

# Check service logs
docker compose logs -f backend

# Apply migrations inside the container
docker compose exec backend alembic upgrade head

# Stop services and remove networks
docker compose down
```

---

## API Overview

Interactive OpenAPI documentation is automatically served:
- **Swagger UI**: [http://localhost:8000/api/v1/docs](http://localhost:8000/api/v1/docs)
- **ReDoc**: [http://localhost:8000/api/v1/redoc](http://localhost:8000/api/v1/redoc)
- **OpenAPI Schema**: [http://localhost:8000/api/v1/openapi.json](http://localhost:8000/api/v1/openapi.json)

### Core Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Service root metadata and health link |
| `GET` | `/health` | Container and load-balancer health check |
| `GET` | `/api/v1/health` | Versioned API health check |
| `GET` | `/api/v1/projects` | Paginated listing of registered projects |
| `POST` | `/api/v1/projects` | Register a new project (auto-slug or custom) |
| `GET` | `/api/v1/projects/{project_id}` | Retrieve project details with relationship counts |
| `DELETE` | `/api/v1/projects/{project_id}` | Delete a project and cascade its data |
| `POST` | `/api/v1/projects/{project_id}/repositories` | Register a public GitHub repository connection |
| `GET` | `/api/v1/projects/{project_id}/repositories` | List repository connections for a project |
| `GET` | `/api/v1/repositories/{repository_id}` | Retrieve repository connection details |
| `POST` | `/api/v1/repositories/{repository_id}/sync` | Ingest repository, capture source inventory snapshot |
| `GET` | `/api/v1/repositories/{repository_id}/snapshots` | List source snapshots for a repository connection |
| `GET` | `/api/v1/snapshots/{snapshot_id}` | Retrieve source inventory and snapshot metadata |
| `POST` | `/api/v1/snapshots/{snapshot_id}/mutations` | Generate deterministic AST code mutations |
| `GET` | `/api/v1/analyses` | Paginated list of analysis runs (filters: `project_id`, `status`) |
| `GET` | `/api/v1/analyses/{analysis_id}` | Retrieve analysis details with execution & report counts |
| `GET` | `/api/v1/analyses/{analysis_id}/mutations` | List generated mutation records for an analysis run |
| `POST` | `/api/v1/analyses/{analysis_id}/execute` | Run and persist the baseline followed by each mutant |
| `GET` | `/api/v1/analyses/{analysis_id}/executions` | Paginated baseline and mutant execution records |
| `GET` | `/api/v1/executions/{execution_id}` | Retrieve a baseline or mutant execution by UUID |
| `POST` | `/api/v1/analyses/{analysis_id}/diagnose` | Compare persisted baseline and selected mutant results |
| `GET` | `/api/v1/analyses/{analysis_id}/diagnoses` | Paginated diagnosis reports for an analysis |
| `GET` | `/api/v1/diagnoses/{report_id}` | Retrieve one diagnosis report by UUID |
| `POST` | `/api/v1/analyses/{analysis_id}/repair-candidates` | Generate candidates for eligible diagnoses |
| `POST` | `/api/v1/analyses/{analysis_id}/diagnoses/{report_id}/repair-candidates` | Generate a candidate for one diagnosis |
| `GET` | `/api/v1/analyses/{analysis_id}/repair-candidates` | Paginated repair candidates for an analysis |
| `GET` | `/api/v1/repair-candidates/{candidate_id}` | Retrieve candidate metadata |
| `GET` | `/api/v1/repair-candidates/{candidate_id}/diff` | Retrieve the unified diff and source hashes |
| `PATCH` | `/api/v1/repair-candidates/{candidate_id}/review` | Mark a candidate reviewed or rejected |
| `POST` | `/api/v1/repair-candidates/{candidate_id}/evaluations` | Apply an isolated patch and run the approved test suite |
| `GET` | `/api/v1/repair-candidates/{candidate_id}/evaluations` | Paginated evaluation history |
| `GET` | `/api/v1/repair-evaluations/{evaluation_id}` | Retrieve one persisted evaluation |

### Milestone 05: Isolated Execution

The backend runs only the approved pytest or unittest discovery command inside a
separate `faultline-runner:py312` image. It never falls back to running target
code on the host. Build the image on the machine that runs the backend:

```powershell
docker build -f docker/runner.Dockerfile -t faultline-runner:py312 .
```

The backend image includes the Docker CLI; the API process also needs access to
a Docker daemon. When the API itself runs in a container, configure a secured
remote Docker endpoint through `DOCKER_HOST` (and provision its TLS credentials
through your deployment's secret mechanism). Do not expose an unauthenticated
Docker TCP endpoint. For safety, the runner receives no host environment
variables, secrets, or arbitrary mounts. Do not mount the Docker socket into an
untrusted runner container. The API runtime uses a uniquely named container per
execution and removes it after completion, including timeout paths.

The runner container uses a non-root UID, disabled networking, a read-only
container root and source mount, dropped Linux capabilities,
`no-new-privileges`, CPU/memory/PID limits, bounded stdout/stderr capture, and
a timeout. Only `/tmp` is writable via a size-limited tmpfs. The image includes
Python 3.12 and a pinned pytest; it does not install dependencies from target
repositories. Projects whose tests require additional packages must provide a
compatible prebuilt runner image in a future configurable runner-image feature.

Test discovery supports Python pytest and unittest suites. The exact snapshot
commit is materialized independently for baseline and each mutant. Before each
mutation, Faultline verifies the source SHA-256, uniquely locates the AST
expression from its line/column metadata, applies one replacement, and checks
the resulting Python syntax. Execution outputs and test counts are persisted.

Mutation classifications are `KILLED`, `SURVIVED`, `TIMEOUT`, `ERROR`, and
`INVALID`. Only killed and survived mutants contribute to the score:
`killed / (killed + survived) * 100`; an empty denominator produces `null`.
Baseline failures stop mutation execution and leave the score undefined.

---

## Milestone 06: Failure Diagnosis

Diagnosis consumes persisted output only; it does not rerun tests, modify source
code, generate patches, or call an LLM. `diagnosis_parser.py` extracts observed
pytest/unittest failure identifiers, exception data, assertions, source frames,
and explicitly named passing tests. Missing or truncated information remains
null. `diagnosis_service.py` compares each result against its analysis baseline
and persists reports through the existing `FailureReport` model. Reports link
to the analysis and, when applicable, the baseline execution, mutant result,
and mutation record. A unique diagnosis key makes repeated requests
idempotent; report writes are committed separately from execution records.

The diagnosis endpoint accepts an optional list of mutant execution IDs; an
omitted list means all persisted results. Send `{}` to diagnose all results:

```json
{
  "execution_ids": ["<execution-result-uuid>"]
}
```

Diagnosis categories include `baseline_failure`, `introduced_failure`,
`existing_baseline_failure`, `failure_changed`, `timeout`,
`infrastructure_error`, `execution_error`, and `invalid_mutation`. A failure
is classified as introduced only when the baseline passed and the mutant
failed. A matching baseline test and failure signature are explicitly marked
pre-existing; a changed signature is reported as a changed symptom, not as a
new failure. Timeouts, infrastructure errors, and invalid mutations do not
produce source-level causal claims. When both runs passed, named test IDs are
compared only if output explicitly contains them; otherwise the response notes
run-level success with no asserted test identity.

Confidence is a deterministic evidence score from 0.0 to 1.0, not a
probability. For an introduced failure, scoring starts at 0.55 and adds 0.10
for an identified test, 0.15 for a traceback frame in the mutated file, 0.10
for a frame on the mutation line, and 0.05 for an observed exception or
assertion, capped at 0.95. Changed failures use a 0.45 base with the same
evidence increments. Exact pre-existing failure matches score 0.98 for the
classification but are marked `not_attributed`; timeout and infrastructure
classification scores describe confidence in the observed execution status,
not in a code cause. Each report includes its evidence and whether its
attribution is inferred, unknown, or explicitly not attributed.

Example response (IDs and values are illustrative):

```json
{
  "analysis_run_id": "<analysis-uuid>",
  "baseline_execution_id": "<baseline-uuid>",
  "summary": {
    "baseline_failures": 0,
    "introduced_failures": 1,
    "existing_failures": 0,
    "changed_failures": 0,
    "passed_both_tests_observed": 0,
    "failure_details_unavailable": 0,
    "timed_out": 0,
    "infrastructure_errors": 0,
    "execution_errors": 0,
    "invalid_mutations": 0,
    "passing_runs_without_shared_test_ids": 0
  },
  "comparisons": [{
    "execution_result_id": "<execution-result-uuid>",
    "mutation_record_id": "<mutation-uuid>",
    "test_identifier": "tests/test_math.py::test_total",
    "category": "introduced_failure",
    "confidence_score": 0.95,
    "explanation": "The baseline passed and this mutant execution failed; association is not proof of sole cause."
  }],
  "reports": [{
    "id": "<failure-report-uuid>",
    "analysis_run_id": "<analysis-uuid>",
    "execution_result_id": "<execution-result-uuid>",
    "baseline_execution_id": null,
    "mutation_record_id": "<mutation-uuid>",
    "diagnosis_key": "<sha256>",
    "title": "Introduced failure: tests/test_math.py::test_total (AssertionError)",
    "failure_type": "introduced_failure",
    "category": "introduced_failure",
    "severity": "high",
    "confidence_score": 0.95,
    "causal_attribution": "inferred",
    "affected_test": "tests/test_math.py::test_total",
    "test_identifier": "tests/test_math.py::test_total",
    "test_file": "tests/test_math.py",
    "test_class": null,
    "test_function": "test_total",
    "mutation_file": "src/math_ops.py",
    "mutation_line": 27,
    "original_expression": "left * right",
    "mutated_expression": "left + right",
    "exception_type": "AssertionError",
    "exception_message": "expected values to match",
    "failing_assertion": "assert actual == expected",
    "failure_summary": "AssertionError: expected values to match",
    "source_file": "src/math_ops.py",
    "source_line": 27,
    "source_function": "multiply",
    "traceback_frames": [{
      "file_path": "src/math_ops.py",
      "line_number": 27,
      "function_name": "multiply",
      "source_line": "return left + right"
    }],
    "evidence": [{
      "kind": "mutation_line_in_traceback",
      "detail": "A traceback frame points to the mutated line.",
      "source": "TracebackFrame.line_number",
      "supports_cause": true
    }],
    "comparison_summary": "The baseline passed; the mutant failed. Association is not proof of sole cause.",
    "root_cause_analysis": "The mutant execution newly failed after the expression changed; this remains an inferred association.",
    "suggested_repair": "Review the failing assertion and mutated expression, then add or update a regression test. No code patch was generated.",
    "status": "open",
    "created_at": "2026-10-31T00:00:00Z",
    "updated_at": "2026-10-31T00:00:00Z"
  }]
}
```

`GET /api/v1/analyses/{analysis_id}/diagnoses` supports `page` and
`page_size` pagination. `GET /api/v1/diagnoses/{report_id}` retrieves an
individual persisted report. The request returns `409` if execution is still
running or no baseline exists, `404` for missing resources, and `422` for
invalid execution IDs or pagination values.

---

## Milestone 07: Automated Repair Candidate Generation

Repair generation consumes persisted `FailureReport` and `MutationRecord`
metadata; it does not rerun tests, call an LLM, execute target code, or modify
the connected repository. It accepts only inferred `introduced_failure`
diagnoses with causal evidence and confidence of at least `0.55`, an applied
mutation, and matching diagnosis/mutation expressions. Other diagnoses are
returned as explicit skip reason codes.

For each eligible diagnosis, Faultline materializes the analysis snapshot's
exact commit in an isolated temporary workspace and verifies the recorded
source hash. It rejects absolute or traversing paths, symlinks, missing files,
hash mismatches, unsupported mutation types, and AST locations that do not
identify exactly one expression. The supported deterministic restorations
reverse a recorded comparison-operator, boolean-operator, numeric-boundary,
or single arithmetic-operator mutation. Exact source expression matches use
`exact_mutation_reversal`; formatting differences use
`ast_expression_restoration` after AST location and mutation checks. The
replacement must be the recorded pre-mutation expression and the resulting
Python file must parse in a separate candidate workspace.

Candidate records include the snapshot commit, relative target path, source
hashes, expressions, strategy, diagnosis evidence references, confidence,
unified diff, syntax-validation status, and review state. A unique
diagnosis/snapshot/strategy constraint makes generation idempotent. Candidate
review transitions from `pending` to `reviewed` or `rejected` and cannot be
reversed. List endpoints support `page` and `page_size`; the candidate detail
response omits patch content, which is available from the dedicated diff
endpoint. File hashes use the same UTF-8 universal-newline-normalized content
as the existing mutation engine; the commit hash identifies the exact snapshot.

Send `{}` to generate candidates for every diagnosis in an analysis, or
provide an optional report-ID filter:

```json
{
  "failure_report_ids": ["<failure-report-uuid>"]
}
```

Example generated diff:

```diff
--- a/src/math_ops.py
+++ b/src/math_ops.py
@@ -8,1 +8,1 @@
-    return left + right
+    return left * right
```

`validation_status: "syntax_valid"` means only that the generated file parses.
It does not mean tests passed or that the repair is correct. Faultline never
writes generated changes to the connected repository.

---

## Milestone 08: Repair Candidate Evaluation

Evaluation starts from a persisted, syntax-validated candidate and its
`introduced_failure` diagnosis. Faultline verifies the exact snapshot commit,
materializes it in a temporary workspace, copies that snapshot into a separate
candidate workspace without following symlinks, and validates the stored
unified diff itself. The target path must be a relative Python file inside the
workspace; the original SHA-256, AST expression location, patch context, and
proposed SHA-256 must all match before the changed file is parsed. The
candidate test suite runs only through the existing Docker-backed
`BaselineRunner` and its two approved pytest/unittest commands. Target code is
never executed on the API host, and the connected source repository is never
modified.

Evaluation outcomes are `PASSED`, `PARTIALLY_PASSED`, `FAILED`, `TIMEOUT`,
`ERROR`, and `INVALID`. A baseline that did not pass, missing diagnosis or
execution evidence, unsupported frameworks, unsafe paths, malformed patches,
and hash/AST mismatches are reported as invalid rather than attributed to a
repair. Docker or runner infrastructure failures are errors, not repair
failures. The service compares parsed baseline, mutant, and candidate test
identifiers. Partial success is reported only when the diagnosed test is
explicitly observed passing while other failures remain, or when available
test-count evidence shows fewer tests ran. Unparsed or truncated output is
not treated as proof that a diagnosis was fixed. Raw test output and host
filesystem paths are not returned or stored in evaluation evidence.

Each request creates a persisted evaluation-history record; a database
constraint permits at most one active evaluation per candidate. Outcomes
summarize the test run and failure identifiers and explicitly set
`behavioral_correctness_proven` to `false`. A passing test run is evidence, not
a proof that the repair is correct. Rejected candidates cannot be evaluated.

### Optional ForgeFit adapter

When a `forgefit_scenario` is supplied in the evaluation request and
`FORGEFIT_BASE_URL` is configured, Faultline uses ForgeFit's existing
`GET /api/status`, `POST /api/runs`, and `GET /api/runs/{run_id}` contract.
It submits only a named resilience scenario and candidate/evaluation IDs as
tags; it does not send source code, patches, or credentials in the scenario.
The adapter records a bounded aggregate report separately from the Faultline
repair verdict. A missing ForgeFit configuration, unavailable service, failed
run, or polling timeout is visible in the ForgeFit fields and does not turn a
passing or failing local test result into a different repair verdict.

ForgeFit is optional. Configure `FORGEFIT_BASE_URL` and, when required by the
ForgeFit deployment, `FORGEFIT_API_KEY` through deployment secrets. Polling
and request timeouts are controlled by the `FORGEFIT_*_SECONDS` settings.
ForgeFit enforces loopback-by-default targets; for a non-loopback target, the
request must set both `allow_external` and `authorized_acknowledgement`.
Operators remain responsible for authorizing that target. The adapter does not
invent or call a patch-scoring endpoint; ForgeFit's resilience run is
complementary evidence, not a repair evaluation.

### Evaluation API

```http
POST /api/v1/repair-candidates/{candidate_id}/evaluations
GET  /api/v1/repair-candidates/{candidate_id}/evaluations?page=1&page_size=20
GET  /api/v1/repair-evaluations/{evaluation_id}
```

The request body may be `{}` for local Docker evaluation. `timeout_seconds`
optionally overrides the configured runner limit (1–3600 seconds). An optional
`forgefit_scenario` accepts a validated `target_url`, request count, timeout,
fault parameters, and the two external-target authorization flags.

Example request (ForgeFit omitted):

```json
{
  "timeout_seconds": 60
}
```

Example response:

```json
{
  "id": "c841ef81-30cc-4cd7-9674-d7e01b93c4e7",
  "repair_candidate_id": "66c7b51e-46f2-43fa-9aad-775e0ac9fd0e",
  "analysis_run_id": "17d2a37d-b547-4750-9c94-6f4a54b6f4f4",
  "failure_report_id": "c95409a8-457c-48af-9b05-971c0e8c2443",
  "baseline_execution_id": "bf9624e4-0ea5-4476-ad1f-d473d41e7363",
  "mutant_execution_result_id": "58a048b7-54ea-4f4d-b824-68419554acbe",
  "status": "PASSED",
  "error_code": null,
  "exit_code": 0,
  "duration_ms": 240,
  "passed_count": 12,
  "failed_count": 0,
  "skipped_count": 0,
  "evidence": {
    "classification": "candidate_test_execution",
    "baseline_status": "passed",
    "mutant_status": "failed",
    "candidate_failure_ids": [],
    "diagnosed_test_state": "not_observed",
    "behavioral_correctness_proven": false
  },
  "forgefit_status": "not_requested",
  "forgefit_run_id": null,
  "forgefit_result": null,
  "forgefit_error_code": null,
  "created_at": "2026-10-31T00:00:00Z",
  "completed_at": "2026-10-31T00:00:01Z"
}
```

**Limitations:** evaluation depends on Docker daemon availability and the
existing approved pytest/unittest commands. Diagnosis comparison is limited
to test identifiers parsed from captured output; output truncation can prevent
per-test attribution. ForgeFit reports resilience metrics only and is not
proof that a code repair is correct. No patch is automatically accepted,
committed, or written back to the source repository.

---

## Verification & Testing

Run unit and integration tests using Pytest:

```bash
pytest -v
```

Run lint and formatting verification using Ruff:

```bash
ruff check .
ruff format --check .
```

---

## Current Implementation Status

### Implemented (Milestones 01–09)
- [x] Ten domain SQLAlchemy models with relationships, cascades, and indexes:
  - `Project`, `RepositoryConnection`, `CodeSnapshot`, `AnalysisRun`, `BaselineExecution`, `MutationRecord`, `ExecutionResult`, `FailureReport`, `RepairCandidate`, `RepairEvaluation`
- [x] Persisted repair candidates with migration `0004_repair_candidates`, uniqueness constraints, source hashes, patch content, syntax-validation state, and review lifecycle.
- [x] Full Pydantic v2 schemas for all domain entities, creation inputs, detailed responses, and paginated wrappers.
- [x] Decoupled Repository and Service layers for Projects, Analyses, Repositories, Snapshots, and Mutations.
- [x] FastAPI application entry point (`backend/app/main.py`) with lifespan management, CORS, and centralized exception handling.
- [x] Root and versioned health endpoints (`/health` and `/api/v1/health`).
- [x] Alembic migration configuration and initial migration (`0001_initial_schema`) covering all eight tables.
- [x] PostgreSQL connection string auto-normalization (`postgresql://` to `postgresql+psycopg2://`).
- [x] Production Dockerfile with multi-stage build, health check, and Alembic support.
- [x] Multi-service `docker-compose.yml` with PostgreSQL 16, health checks, and volume mounts.
- [x] Public GitHub repository registration with strict URL normalization, credential rejection, and duplicate prevention.
- [x] Safe shallow Git cloning using subprocess without shell, timeout limits, and isolated temporary directory lifecycle.
- [x] Source inventory inspection with language distribution, SHA-256 hashing, directory pruning, binary skipping, and symlink protection.
- [x] Source snapshot persistence and deduplication on identical commit hashes.
- [x] Exact snapshot commit materialization in isolated temporary workspaces.
- [x] Deterministic Python AST mutation engine with 3 modular operators:
  - Comparison operator mutation (`==`, `!=`, `>`, `>=`, `<`, `<=`)
  - Boolean operator mutation (`and` $\leftrightarrow$ `or`)
  - Numeric boundary mutations in comparison expressions ($n-1, n+1$)
- [x] Syntax validation through post-mutation parsing (`ast.parse`) and seeded deterministic sampling.
- [x] AnalysisRun and MutationRecord persistence with full reproducibility manifests.
- [x] API endpoints for mutation generation (`/snapshots/{id}/mutations`) and retrieval (`/analyses/{id}/mutations`).
- [x] Controlled Python 3.12 runner image with pinned pytest, non-root execution, and no runtime package installation.
- [x] Docker sandbox with bounded concurrent output capture, timeout termination, named-container cleanup, fail-closed behavior, strict command allowlisting, and resource/security limits.
- [x] Strict mutation application with snapshot source hash verification, AST-position matching, syntax validation, and an independent exact-commit workspace for each mutant.
- [x] Persisted baseline and mutant results, test counts, timeout/infrastructure metadata, all five classifications, and mutation score.
- [x] Execution API endpoints for starting an analysis execution and listing/retrieving execution records.
- [x] Alembic migration `0002_execution_engine` for execution metadata and duplicate-execution constraints.
- [x] Deterministic pytest/unittest failure and traceback parsing, with nulls for unavailable evidence.
- [x] Baseline-to-mutant diagnosis for introduced, pre-existing, changed, passed-both, timeout, infrastructure, execution, and invalid-mutation outcomes.
- [x] Evidence-backed `FailureReport` fields and relationships, deterministic confidence scoring, idempotent persistence, and migration `0003_failure_diagnosis`.
- [x] Versioned diagnosis, paginated report-list, and report-detail API endpoints.
- [x] Deterministic isolated repair patch generation from eligible diagnosis evidence and AST mutation metadata.
- [x] Repair candidate generation, paginated retrieval, diff retrieval, and review API endpoints.
- [x] Persisted repair evaluation history, isolated patch application, hash/AST/diff validation, baseline/mutant/candidate comparison, and reversible migration `0005_repair_evaluations`.
- [x] Versioned repair evaluation APIs, pagination, timeout/infrastructure classification, and an optional adapter for ForgeFit's existing asynchronous run contract.
- [x] Responsive Next.js frontend with project/repository/snapshot management, mutation analysis, execution, diagnosis, repair review, and repair evaluation workflows.
- [x] Typed API client and validated inputs against the existing FastAPI contracts; API connectivity, loading, empty, and error states use live responses rather than mock records.
- [x] Supplied Syntactiq CSS copied unchanged as the frontend global stylesheet, with responsive components using its palette and typography tokens.
- [x] Pytest suite covering application startup, CRUD, ingestion and mutation behavior, sandbox policy/lifecycle, persistence, classifications, scoring, and execution APIs.
- [x] Ruff linting and style configuration.
- [x] Frontend production build, TypeScript checking, and ESLint.

### Known Limitations
- The API host must have Docker CLI and daemon access. Docker socket mounts are not made available to untrusted runner containers.
- The Docker daemon resolves bind-mount paths on its own host. For local Docker Desktop execution, run the API on the host; the provided backend Compose service does not expose a daemon socket or shared daemon-visible workspace.
- The default runner includes pytest but not arbitrary target-repository dependencies; those tests may fail until additional controlled images are supported.
- Docker integration could not be smoke-tested in this environment because Docker Desktop is unavailable. The execution tests mock Docker/subprocess boundaries.
- The default pytest quiet and unittest discovery commands do not emit passing test identifiers. In those cases diagnosis can compare run-level success but cannot name every test that passed in both runs.
- Diagnosis depends on captured output; truncated or malformed output may yield a report with missing test or exception details.
- Diagnosis is deterministic and evidence-based but does not prove causation. It provides remediation guidance and does not generate patches itself or use an LLM.
- Repair candidates are mutation reversals, not confirmed fixes. Syntax validation and test outcomes are evidence only and do not establish behavioral correctness.
- Repair generation currently supports Python expression mutations with recorded AST locations and exact source hashes. Unsupported diagnoses, mutation types, or ambiguous/missing source evidence are skipped.
- Execution, diagnosis, and repair generation currently use synchronous API requests.
- The frontend exposes no authentication because the API currently requires none. Configure deployment access controls before exposing this API to untrusted users.
- Dashboard totals require multiple existing API requests because the backend has no aggregate endpoint; large workspaces may load more slowly. Project and analysis search is limited to the currently loaded page because no global search endpoint exists.
- Frontend pages were not exercised against a live database-backed API in this environment. The local OpenAPI/health contract and frontend rendering/error states were checked; live repository ingestion, Docker test execution, and ForgeFit runs were not.

### Planned (Upcoming Milestones)
- [ ] Optional LLM-assisted diagnosis or remediation.
- [ ] Authentication and authorization, paired with backend API support.
