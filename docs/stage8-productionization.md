# Tahap 8 — PostgreSQL, FastAPI, and Metadata Database

- Implementation status: complete
- PostgreSQL container verification: passed, 4/4 tests
- Date: 2026-07-21

## Architecture

The final application boundary is now:

```text
Streamlit (no database credential)
  -> FastAPI /api/v1
    -> orchestration and SQL AST policy
      -> chinook / analytics_readonly / analytics schema
    -> durable audit repository
      -> analyst_metadata / app_metadata_user / app_metadata schema
```

The analytics and metadata engines require different database names and exact
application identities. Startup rejects an owner, superuser, role creator,
database creator, RLS bypass role, wrong driver, or wrong username.

## Reproducible Chinook PostgreSQL

The official `Chinook_PostgreSql.sql` asset from Chinook v1.4.5 is pinned at
600,200 bytes with SHA-256
`e3fde5c1a5b51a2a91429a702c9ca6e69ba56e6c7f5e112724d70c3d03db695e`.
Bootstrap removes only the upstream database-level `DROP DATABASE`,
`CREATE DATABASE`, and `\c` commands, then loads the remaining official schema
and data into the owner-only `chinook_data` schema.

The application sees an `analytics` compatibility-view schema that preserves
the established logical Chinook table and column contract. The PostgreSQL
logical snapshot is content-addressed separately with hash
`f3569fc49358ddbd50328badf58ac4748cd0ccc60995c741648cb79b2db02e4e`.
The `semantic/postgresql.yaml` overlay changes only dialect-specific verified
SQL while keeping business definitions, grain, joins, and `project_verified`
review status single-sourced.

## Roles and Privileges

| Role | Login | Purpose | Allowed access |
|---|---|---|---|
| `analytics_owner` | No | Own physical data and views | Never used by the app |
| `analytics_readonly` | Yes | Execute analytics | `CONNECT`, analytics `USAGE`, view `SELECT` only |
| `app_metadata_user` | Yes | Runtime audit metadata | DML only in `app_metadata` |
| `migration_user` | Yes | Alembic ownership | Migration time only |

`analytics_readonly` receives a role-level read-only transaction default, a
five-second statement timeout, and the `analytics, pg_temp` search path. The
executor independently issues `SET TRANSACTION READ ONLY`, a local timeout,
and a local allowlisted search path for every validated query. `PUBLIC` database
and schema privileges are revoked where applicable, and neither application
identity receives `CREATE`.

## Metadata and Migrations

Alembic revision `20260720_0001` creates:

- `data_sources`, `schema_snapshots`, and `verified_queries`;
- `query_requests`, `query_attempts`, and `query_feedback`;
- `evaluation_cases`, `evaluation_runs`, and `evaluation_results`;
- `usage_events`.

Indexes cover source/schema identity, request status/time, feedback, evaluation
lookup, and usage time series. The schema deliberately has no `raw_question`,
`raw_sql`, or `result_rows` columns. Runtime audit data stores status,
fingerprints, source identities, bounded counts, latency, feedback, and version
provenance. Alembic offline SQL generation from an empty PostgreSQL database
completed successfully.

## FastAPI Contracts

The application factory exposes:

- `GET /api/v1/health`;
- `POST /api/v1/query`;
- `GET /api/v1/schema`;
- `GET /api/v1/history`;
- `POST /api/v1/feedback`;
- protected `GET /api/v1/evaluation/baseline`.

Pydantic models reject extra or malformed fields. CORS permits only configured
origins and `GET`/`POST`; wildcard production origins are rejected. Every HTTP
response receives a server-controlled request ID. Validation, domain, HTTP, and
unexpected exceptions use sanitized stable payloads. Health responses contain
only `healthy`/`degraded` and the API version—never a host, role, URL, or secret.

`frontend/streamlit_api_app.py` uses only `AnalystAPIClient`. The retained
`frontend/streamlit_app.py` is an explicitly named Tahap 6 regression fixture,
not the final frontend entrypoint.

## Commands

After PostgreSQL credentials are supplied through environment variables:

```powershell
uv run python scripts/bootstrap_postgres.py
uv run python scripts/dev.py api
uv run python scripts/dev.py ui
```

The actual ephemeral-container gate is:

```powershell
uv run python scripts/dev.py test-postgres
```

It uses `postgres:17.10-alpine3.24`, generates temporary random passwords,
bootstraps both databases, runs migrations from empty, executes the marked
PostgreSQL tests, and removes the named test container by default.

## Verification State

Implementation readiness passed every deterministic check. The complete local
suite passed 289 tests with four environment-gated PostgreSQL tests skipped and
91.36% branch coverage; Ruff and Mypy strict also passed. Alembic offline
upgrade SQL generated all ten models and grants successfully.

After hardware virtualization was enabled and WSL2 restored, the separate
ephemeral-container gate passed 4/4 tests. It proved migration upgrade/downgrade
from empty, actual `analytics_readonly` write and physical-table rejection,
credential/database isolation, and end-to-end FastAPI metadata persistence.
The container was removed after the run. `stage_gate_passed` is now true.
