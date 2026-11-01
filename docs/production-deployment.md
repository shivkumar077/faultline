# Production Deployment

This guide deploys the existing Faultline API, Next.js frontend, PostgreSQL
database, and isolated test runner using `compose.production.yml`. It is a private
deployment profile, not a turnkey public SaaS setup. Configure a TLS ingress
with user authentication before allowing users to reach the frontend.

## Architecture and security boundary

- The frontend is the only published service and binds to `127.0.0.1` by
  default. Put an authenticated HTTPS reverse proxy in front of it.
- The frontend's same-origin `/api/v1` proxy adds the shared backend bearer
  token from a server-side secret file. The token is not a `NEXT_PUBLIC_`
  variable and is not sent to browser JavaScript.
- The frontend and API communicate on a private internal Compose network.
  PostgreSQL has no published host port and is attached only to the internal
  network.
- The API token is shared service authentication, not user identity,
  authorization, tenant isolation, or project-level access control. The
  ingress must authenticate users and enforce per-user limits.
- API rate limits are process-local. Proxied API calls share the frontend
  container's source address, so enforce user/IP rate limits at the ingress or
  API gateway.
- Untrusted tests run in separate, non-root, resource-limited containers with
  networking disabled. The API connects to a Docker daemon using mutual TLS;
  never expose an unauthenticated Docker TCP endpoint or mount its socket into
  a runner container.
- Docker daemon bind mounts are resolved on the daemon host. The workspace
  directory must be mounted at the same absolute path in the backend container
  and be available at that path on the daemon host.
- Compose file-backed secrets are read-only mounts, not encrypted secret
  storage. Restrict host access to secret files and backups, or use an
  orchestrator that provides managed secrets.

## Requirements

- Docker Engine and Docker Compose v2.
- A PostgreSQL 16 service. The included profile provisions PostgreSQL with a
  persistent Docker volume; using a separately managed database requires
  adapting the Compose database service and network configuration.
- A mutually authenticated TLS Docker daemon endpoint, reachable by the API.
- A daemon-visible shared workspace directory with enough free space.
- An HTTPS reverse proxy/ingress that authenticates users.
- A trusted host name in `FAULTLINE_TRUSTED_HOSTS`; keep
  `CORS_ORIGINS=[]` for the same-origin frontend proxy.

Docker Desktop is suitable for local development, but production runner
execution requires verifying daemon connectivity and shared bind mounts in the
actual deployment environment.

## Configure secrets and environment

Run Compose commands from the repository root. Copy the non-secret template:

```sh
cp production.env.example production.env
mkdir -p secrets
chmod 700 secrets
umask 077
python -c "import secrets; print(secrets.token_urlsafe(48), end='')" > secrets/api-token
python -c "import secrets; print(secrets.token_urlsafe(48), end='')" > secrets/postgres-password
chmod 600 secrets/*
```

PowerShell equivalent for the directory and generated tokens:

```powershell
Copy-Item production.env.example production.env
New-Item -ItemType Directory -Force secrets
python -c "import secrets; print(secrets.token_urlsafe(48), end='')" | Set-Content -NoNewline secrets\api-token
python -c "import secrets; print(secrets.token_urlsafe(48), end='')" | Set-Content -NoNewline secrets\postgres-password
```

Set the secret file paths and deployment values in the private
`production.env`. Do not commit the file or `secrets/`. The `DATABASE_URL` file
must use the same PostgreSQL username, password, database, and service hostname
as Compose's `POSTGRES_USER`, `POSTGRES_DB`, and password secret. URL-encode
special characters in the URL password. Use a PostgreSQL host reachable from
the Compose network; the Compose service name `postgres` is the default.

The database URL file format is:

```text
postgresql+psycopg2://USER:URL_ENCODED_PASSWORD@postgres:5432/DATABASE
```

Create `secrets/database-url` with the matching URL, without adding quotes or
logging the value. Confirm that `FAULTLINE_DATABASE_URL_FILE` points to it.

Restrict the `secrets/` directory and its files to the deployment identity;
apply restrictive NTFS ACLs on Windows rather than relying on Unix `chmod`.

Set the Docker mutual-TLS endpoint and certificate paths in `production.env`.
The certificate files must be readable by the API container and must authorize
the configured `DOCKER_HOST`. Create `FAULTLINE_WORKSPACE_ROOT` on the Compose
host and Docker daemon host at the exact same absolute path, writable by the
backend's non-root UID (10001). Do not use a temporary or shared-with-other-
tenants path.

`FAULTLINE_TRUSTED_HOSTS` is a JSON string array for host headers accepted by
the API, typically including its internal service name. It is not the public
frontend hostname unless the API itself is intentionally routed through that
host. Production CORS origins, if enabled for another browser client, must be
explicit HTTPS origins. The frontend server proxy is same-origin and does not
need browser CORS access.

External ForgeFit target URLs are disabled by default. Keep
`FORGEFIT_ALLOW_EXTERNAL_TARGETS=false` unless the target service and egress
boundary enforce destination restrictions. The application requires an
explicit request acknowledgement and checks resolved addresses, but DNS
rebinding or redirects cannot be fully controlled by a one-time application
check.

## Migrate and start

Back up the database before schema changes. Start PostgreSQL and apply
migrations explicitly as a single deployment operation; application startup
does not run migrations:

```sh
docker compose --env-file production.env -f compose.production.yml up -d postgres
docker compose --env-file production.env -f compose.production.yml run --rm backend alembic upgrade head
```

Build the runner image on the configured Docker daemon, then build and start the
application:

```sh
docker compose --env-file production.env -f compose.production.yml --profile image-build run --rm runner-image
docker compose --env-file production.env -f compose.production.yml up -d --build backend frontend
```

The runner image must be available to the same daemon used by the API. If using
a remote daemon, set up the Compose client's Docker context or TLS environment
to target that daemon for both image build and container startup.

Check service status and health:

```sh
docker compose --env-file production.env -f compose.production.yml ps
docker compose --env-file production.env -f compose.production.yml logs --tail=100 backend frontend postgres
curl -fsS http://127.0.0.1:3000/api/v1/health
curl -fsS http://127.0.0.1:3000/api/v1/health/ready
```

The unauthenticated health endpoints expose operational status only. Readiness
returns HTTP 503 when PostgreSQL is unavailable; if the database is reachable
but the Docker runner is not, it reports `degraded`. Migrations must be applied
before the service is considered ready for application traffic.

The production Docker Compose file binds the frontend to localhost and
intentionally publishes neither the API nor PostgreSQL. Configure the ingress
to proxy to the frontend's local port and provide TLS, user login, request-size
limits, per-user/IP rate limits, and workflow-appropriate upstream timeouts
(repair evaluations may run for up to an hour). Do not expose port 3000
directly to the public Internet. A containerized ingress needs a private network
route to the frontend; host loopback binding is directly reachable only from
the Docker host. Terminate TLS at the ingress and configure HSTS and appropriate
browser security headers there.

## Environment reference

Compose settings required in `production.env`:

| Variable | Purpose |
|---|---|
| `POSTGRES_DB`, `POSTGRES_USER` | Initial database identity |
| `POSTGRES_PASSWORD_FILE` | Host path to the PostgreSQL password secret |
| `FAULTLINE_API_TOKEN_FILE` | Host path to the generated API bearer token |
| `FAULTLINE_DATABASE_URL_FILE` | Host path to the PostgreSQL URL secret |
| `FAULTLINE_TRUSTED_HOSTS` | JSON array of accepted API host headers |
| `DOCKER_HOST` | Mutual-TLS Docker daemon endpoint |
| `DOCKER_CA_FILE`, `DOCKER_CLIENT_CERT_FILE`, `DOCKER_CLIENT_KEY_FILE` | TLS client credentials |
| `FAULTLINE_WORKSPACE_ROOT` | Shared absolute workspace path on backend and daemon |
| `FAULTLINE_WEB_HOST_PORT` | Localhost-only frontend port |

Optional controls include `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`,
`DB_POOL_TIMEOUT`, `DB_CONNECT_TIMEOUT_SECONDS`, `DB_STATEMENT_TIMEOUT_MS`,
`DB_LOCK_TIMEOUT_MS`, `DB_POOL_RECYCLE_SECONDS`, `LOG_LEVEL`,
`MAX_REQUEST_BODY_BYTES`, `RATE_LIMIT_REQUESTS_PER_MINUTE`,
`EXPENSIVE_RATE_LIMIT_REQUESTS_PER_MINUTE`, and `RATE_LIMIT_WINDOW_SECONDS`.
Production settings reject debug mode, missing secrets, non-PostgreSQL
databases, wildcard hosts, and non-HTTPS CORS origins.

When ForgeFit requires an API key, supply it as a mounted secret and set
`FORGEFIT_API_KEY_FILE` to the in-container secret path through the deployment's
secret configuration. The base Compose profile intentionally does not inject
that optional credential.

The frontend's `NEXT_PUBLIC_API_BASE_URL` is a public URL path, not a secret.
Production uses `/api/v1`; the backend URL and token are server-only runtime
settings. Never place API tokens or other credentials in `NEXT_PUBLIC_*`.

Application settings used by the production API:

| Variable | Production behavior |
|---|---|
| `ENVIRONMENT` | Must be `production` |
| `DEBUG` | Must be `false` |
| `PRIVATE_DEPLOYMENT` | Must be `true`; this is an operator assertion, not a network firewall |
| `DATABASE_URL` / `DATABASE_URL_FILE` | PostgreSQL connection; use the secret-file form |
| `API_AUTH_TOKEN` / `API_AUTH_TOKEN_FILE` | Shared bearer token; use the secret-file form |
| `CORS_ORIGINS` | Exact HTTPS origins only; `[]` for the same-origin frontend proxy |
| `TRUSTED_HOSTS` | Explicit host allowlist; wildcard entries are rejected |
| `LOG_LEVEL` | Standard logging level; production rejects `DEBUG` |
| `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_TIMEOUT`, `DB_POOL_RECYCLE_SECONDS` | SQLAlchemy PostgreSQL pool bounds |
| `DB_CONNECT_TIMEOUT_SECONDS`, `DB_STATEMENT_TIMEOUT_MS`, `DB_LOCK_TIMEOUT_MS` | Database connection and query limits |
| `DB_ECHO` | Must be `false` in production |
| `MAX_REQUEST_BODY_BYTES` | Maximum buffered HTTP request body |
| `RATE_LIMIT_REQUESTS_PER_MINUTE`, `EXPENSIVE_RATE_LIMIT_REQUESTS_PER_MINUTE`, `RATE_LIMIT_WINDOW_SECONDS` | Process-local API limits |
| `FORGEFIT_BASE_URL`, `FORGEFIT_API_KEY_FILE` | Optional trusted ForgeFit service and secret |
| `FORGEFIT_ALLOW_EXTERNAL_TARGETS` | Disabled by default; operator opt-in for external scenario targets |
| `FORGEFIT_TIMEOUT_SECONDS`, `FORGEFIT_MAX_WAIT_SECONDS`, `FORGEFIT_POLL_INTERVAL_SECONDS` | ForgeFit request and polling limits |
| `DOCKER_HOST`, `DOCKER_TLS_VERIFY`, `DOCKER_CERT_PATH`, `TMPDIR` | Secured runner-daemon endpoint and shared workspace |

## Operations and troubleshooting

- **API returns 401 through the frontend:** verify the mounted API token file
  matches the API's configured token and contains a valid URL-safe token.
- **Readiness reports database unavailable:** inspect the database URL secret,
  network/DNS, PostgreSQL health, and connection limits. The database URL
  password must be URL-encoded.
- **Runner is unavailable:** verify Docker CLI daemon connectivity and mutual
  TLS files inside the backend, then confirm the runner image exists on that
  daemon. Inspect Docker daemon logs without logging credentials.
- **Runner cannot mount a workspace:** ensure the path exists on both the
  backend container and daemon host, is writable by UID 10001, and is identical
  in both environments.
- **Ingress requests are rejected as untrusted hosts:** add the internal
  backend `Host` value sent by the frontend proxy to `FAULTLINE_TRUSTED_HOSTS`;
  do not use `*`.
- **Correlate a failed request:** use the response's `X-Request-ID` or
  `request_id` with structured JSON logs. Logs omit request bodies, tokens, and
  source contents.
- **ForgeFit DNS checks:** application-level checks are defense in depth, not a
  substitute for egress allowlists or destination controls at the remote
  service.
- **Rotate the shared API token:** update the backend and frontend secret from
  the same new value, then restart both services together.

Migrations are not automatically applied on startup to avoid multi-replica
races and unsafe data changes. Downgrading is migration-specific and may drop
persisted data; take and verify a backup and test rollback against a
representative copy before production use.

## Production checklist

- [ ] Use PostgreSQL with tested backups and restore procedures.
- [ ] Provision strong API, database, and Docker TLS secrets outside Git.
- [ ] Keep the application behind an authenticated HTTPS ingress.
- [ ] Keep API and database ports unpublished; keep PostgreSQL internal-only.
- [ ] Confirm remote daemon TLS, runner image availability, and shared workspace
      behavior on the target hosts.
- [ ] Apply reviewed migrations once before deploying application replicas.
- [ ] Enforce ingress-level per-user/IP limits and request-size limits.
- [ ] Keep external ForgeFit targets disabled unless egress protections are in
      place.
- [ ] Monitor health/readiness and structured request-correlated logs.
- [ ] Run image scans and verify resource limits against the deployment
      workload.

## Known limitations

- The bearer token is a shared service credential. User identity, roles,
  project-level authorization, and tenant isolation are not implemented.
- Rate limiting is in-memory and per-process; it is not distributed.
- The runner concurrency cap is per API process, not cluster-wide.
- File-backed Compose secrets rely on host filesystem protections rather than an
  encrypted secret manager.
- The runner includes Python and pytest, not arbitrary dependencies from
  connected repositories.
- A one-time DNS lookup cannot prevent all DNS rebinding or redirect-based SSRF
  behavior; the egress network and ForgeFit service must constrain destinations.
- Docker builds, daemon-backed execution, and end-to-end health checks must be
  validated on the production Docker infrastructure. A successful Compose
  configuration check alone does not validate those integrations.
