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

---

## Repository Structure

```
faultline/
├── .env.example                     # Environment template configuration
├── Dockerfile                       # Production container specification
├── docker-compose.yml               # Multi-container orchestration (API + Postgres)
├── pyproject.toml                   # Project metadata, dependencies, and tool settings
├── alembic.ini                      # Alembic migration configuration
├── README.md                        # Technical documentation
└── backend/
    ├── migrations/                  # Database migration management
    │   ├── env.py                   # Alembic environment runner
    │   ├── script.py.mako           # Migration template
    │   └── versions/                # Versioned migration files
    │       └── 0001_initial_schema.py
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
    │   │   └── failure_report.py
    │   ├── schemas/                 # Pydantic v2 models and common response types
    │   │   ├── common.py
    │   │   ├── project.py
    │   │   ├── repository_connection.py
    │   │   ├── code_snapshot.py
    │   │   ├── analysis_run.py
    │   │   ├── baseline_execution.py
    │   │   ├── mutation_record.py
    │   │   ├── execution_result.py
    │   │   └── failure_report.py
    │   ├── repositories/            # Data access layer
    │   │   ├── base.py
    │   │   ├── project_repository.py
    │   │   └── analysis_repository.py
    │   ├── services/                # Business logic services
    │   │   ├── project_service.py
    │   │   └── analysis_service.py
    │   └── api/
    │       └── v1/                  # Versioned API routes
    │           ├── router.py
    │           └── endpoints/
    │               ├── health.py
    │               ├── projects.py
    │               └── analyses.py
    └── tests/                       # Pytest test suite
        ├── conftest.py              # Test database fixtures and FastAPI test client
        ├── test_health.py           # Health checks and application metadata tests
        ├── test_projects.py         # Project CRUD and duplicate slug tests
        └── test_analyses.py         # Analysis listing and retrieval tests
```

---

## Local Installation & Setup

### Prerequisites
- Python 3.12+
- PostgreSQL 16 (optional for local SQLite development, required for production)
- Docker & Docker Compose (optional for containerized runtime)

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
| `GET` | `/api/v1/analyses` | Paginated list of analysis runs (filters: `project_id`, `status`) |
| `GET` | `/api/v1/analyses/{analysis_id}` | Retrieve analysis details with execution & report counts |

---

## Verification & Testing

Run unit and integration tests using Pytest:

```bash
pytest -v
```

Run code formatting and lint verification using Ruff:

```bash
ruff check backend
ruff format --check backend
```

---

## Current Implementation Status

### Implemented (Milestones 01, 02 & 03)
- [x] Eight domain SQLAlchemy models with relationships, cascades, and indexes:
  - `Project`, `RepositoryConnection`, `CodeSnapshot`, `AnalysisRun`, `BaselineExecution`, `MutationRecord`, `ExecutionResult`, `FailureReport`
- [x] Full Pydantic v2 schemas for all domain entities, creation inputs, detailed responses, and paginated wrappers.
- [x] Decoupled Repository and Service layers for Projects, Analyses, Repositories, and Snapshots.
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
- [x] Repository connection and snapshot API endpoints (`/projects/{id}/repositories`, `/repositories/{id}`, `/repositories/{id}/sync`, `/repositories/{id}/snapshots`, `/snapshots/{id}`).
- [x] Pytest suite covering application startup, health endpoints, project CRUD, duplicate slug conflicts, ingestion security, and snapshot workflows.
- [x] Ruff linting and style configuration.

### Planned (Upcoming Milestones)
- [ ] Code-level mutation injection engine (AST-based syntax-valid mutations).
- [ ] Isolated test sandbox execution runner (containerized baseline and mutation runs).
- [ ] AI-driven root cause diagnostic engine and remediation patch generator.
- [ ] Frontend user interface (pending design system and global styling specifications).
