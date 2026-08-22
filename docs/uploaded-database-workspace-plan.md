# Uploaded Database Workspace Plan

- Date: 2026-08-18
- Scope: SQLite/BAK/SQL/CSV/JSON upload, schema inspection, and prompt-to-query
- Status: Extended implementation locally verified
- Model-qualification impact: none; Point 5 remains independently gated

## Goal

Let a local user upload a SQLite database/backup, restricted SQLite SQL dump,
CSV, or JSON, inspect
its schema, and ask natural-language questions whose generated SQL executes
only against that upload.

## Completed checklist

- [x] Audit FastAPI, Streamlit, schema inspection, LLM, SQL policy, and executor boundaries.
- [x] Define opaque, expiring workspace contracts without paths or credentials.
- [x] Add bounded SQLite-file validation and restricted SQL-dump import.
- [x] Add bounded CSV/JSON conversion and SQLite-only `.bak` recognition.
- [x] Build a schema-derived allowlist and independent SQLite query processor per workspace.
- [x] Keep the upload separate from Chinook PostgreSQL and metadata persistence.
- [x] Add create/schema/query/delete API endpoints and typed frontend client methods.
- [x] Add Streamlit upload, active-source, explorer, query-result, and delete UX.
- [x] Test ordinary dump/database lifecycle and hostile import/model SQL paths.
- [x] Update API, architecture, security, threat model, configuration, and memory.
- [x] Pass full offline regression without provider or holdout calls.

## Explicit non-goals

- MySQL/PostgreSQL dump execution, SQL Server `.bak` restoration, or a live connection-string upload.
- Semantic-layer authoring for arbitrary schemas.
- Public multi-user authorization, malware sandboxing, or durable workspace storage.
- Treating the deterministic fake provider as an arbitrary-schema LLM.

## Verification

- Ruff format and lint: passed.
- Strict Mypy (`backend`, `scripts`, `tests`): passed.
- Focused upload/API tests: passed.
- Full suite: 487 passed, 4 PostgreSQL skips, 90.10% coverage.
- Focused importer/config/API suite: 46 passed.
- Live provider calls: zero.
- Holdout calls: zero.
