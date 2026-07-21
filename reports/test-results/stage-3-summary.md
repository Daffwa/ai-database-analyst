# Tahap 3 Verification Summary

- Verification date: 2026-07-19 (Asia/Bangkok)
- Runtime: CPython 3.12.13 on Windows
- Result: passed

## Delivered Behavior

- Provider-neutral asynchronous `BaseLLMAdapter`.
- Deterministic offline `FakeLLMAdapter` and provider factory.
- Strict Pydantic structured-output contract with intent-dependent invariants.
- Versioned prompt `v1` that forbids pre-execution numeric answers and private
  chain-of-thought.
- Deterministic schema retrieval with table-count and character budgets.
- Fail-closed JSON parser and declared table/column checks.
- Explicit orchestrator stages, UUID request IDs, and separate LLM/database
  latency fields.
- Default orchestration stops at `generated_pending_security` without execution.
- Closed exact-match trusted baseline execution for 20 known demo questions.
- Minimum Streamlit UI with production warning, input, process status, generated
  SQL, executed SQL, database table, safe errors, and audit metadata.

## Mini-Evaluation Evidence

- Cases: 20
- Structured output valid: 20/20
- Generated SQL exact baseline match: 20/20
- Execution success: 20/20
- Normalized database result hash match: 20/20
- Default smoke result: customer count `59`, returned by SQLite
- Network calls: 0
- API credentials: 0

The exact catalog and result hashes are tracked. These cases are a closed
mechanical baseline, not a formal real-model quality claim.

## Automated Verification

- `uv sync --extra dev`: passed
- `uv run python scripts/dev.py evaluate-stage3`: 20/20 in every metric
- `uv run python scripts/dev.py stage3-smoke`: passed
- `uv run python scripts/dev.py test-integration`: 6 passed
- `uv run python scripts/dev.py test-ui`: 1 passed
- `uv run python scripts/dev.py verify`: passed
- Ruff format check: 53 Python files formatted
- Ruff lint: passed
- Mypy strict: 52 source files checked, no issues
- Pytest: 93 passed
- Branch coverage: 98.45%, required minimum 90%
- `uv lock --check`: passed

Streamlit 1.59.2 is pinned. NumPy 2.3.5 is explicitly pinned because it is the
compatible branch required to preserve the project's Python 3.11–3.12 support;
newer resolved NumPy builds require Python 3.12.

## Security Boundary

No arbitrary adapter SQL crossed the database boundary. The closed runner
executes only a trusted case constant after exact proposal identity checks.
Unknown questions remain unexecuted. Tahap 4 remains mandatory before any
free-form LLM-generated SQL can execute.
