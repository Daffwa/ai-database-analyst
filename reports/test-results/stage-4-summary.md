# Tahap 4 Verification Summary

- Verification date: 2026-07-19 (Asia/Bangkok)
- Runtime: CPython 3.12.13 on Windows
- Result: passed

## Delivered Behavior

- SQLGlot 30.12.0 with explicit SQLite dialect and fail-closed parsing.
- Exactly one root read-only query with recursive AST inspection.
- DML, DDL, privilege, transaction, administrative, `COPY`, `SELECT INTO`,
  dangerous function, catalog, schema escape, recursive CTE, unbound parameter,
  complexity, and cartesian-join blocking.
- Snapshot-derived schema/table/column allowlists and AST-derived source checks.
- Reviewed function allowlist plus configurable dangerous-function blocklist.
- Deterministic outer `LIMIT` addition/reduction to a maximum of 500.
- Literal-redacted SHA-256 SQL fingerprints.
- Generated and executed SQL separation through `SecureQueryOrchestrator`.
- Real SQLite progress-handler timeout plus row, column, response-byte, and SQL
  character budgets.
- SQLite URI `mode=ro` and `PRAGMA query_only=ON` retained as the independent
  final write-prevention layer.
- Bounded repair coordinator: two attempts by default, sanitized reason codes,
  no repair of security violations, and complete revalidation of every attempt.
- Safe policy audit records without raw questions, raw SQL, or result rows.
- Secured Tahap 4 runtime, smoke command, evaluation command, and Streamlit UI.

## Security Evaluation Evidence

- Dataset: `stage-4-v1`
- Known-unsafe SQL cases: 30
- Blocked with the required reason: 30/30 (100%)
- Previously accepted safe baselines: 20
- Safe baselines allowed: 20/20
- False blocks: 0 (0%)
- Prompt injection: Indonesian and English write proposals blocked before the
  executor
- Network calls: 0
- API credentials: 0

The corpus includes the mandatory destructive cases and bypass variants for
CTEs, quoting, comments, whitespace, case, subqueries, unions, and nested
functions. Additional tests verify timeout interruption, response budgets,
repair safety, audit redaction, and independent database write rejection.

## Automated Verification

- `uv sync --extra dev`: passed
- `uv run python scripts/dev.py evaluate-stage4`: 30/30 blocked, 0/20 false blocks
- `uv run python scripts/dev.py stage4-smoke`: passed
- `uv run python scripts/dev.py test-security`: 56 passed
- `uv run python scripts/dev.py test-integration`: 6 passed
- `uv run python scripts/dev.py test-ui`: 1 passed
- Ruff format check: passed
- Ruff lint: passed
- Mypy strict: 64 source files checked, no issues
- Pytest: 153 passed
- Branch coverage: 96.45%, required minimum 90%
- `uv lock --check`: passed

## Security Boundary and Residual Risk

Every generated SQL string in the active runtime must receive a safe AST report
before the rewritten SQL reaches the executor. A successful finite regression
suite does not prove absence of unknown bypasses. SQLite is not a production
authorization boundary, and this phase does not provide authentication,
row-level authorization, tenant isolation, rate limiting, PostgreSQL roles, or
business-semantic correctness. Those remain required later-stage gates.
