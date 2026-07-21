# Tahap 2 Verification Summary

- Verification date: 2026-07-19 (Asia/Bangkok)
- Runtime: CPython 3.12.13 on Windows
- Dataset: Chinook v1.4.5 SQLite release asset
- Result: passed

## Reproducibility Evidence

- Official asset: `Chinook_Sqlite.sqlite`
- Size: `1,067,008` bytes
- SHA-256:
  `bdf635be69850bd3be09c9a2dbeef7ddfb80036bd3ef3381383cd03b61e4a61a`
- SQLite integrity: `ok`
- User tables: 11, matching the pinned exact set
- Row counts: all 11 tables matched the pinned counts
- First bootstrap: `database_created=true`
- Second bootstrap: `database_created=false`
- Schema hash:
  `58c6c16d147308c44996f88c3b893c0baa264a9b0ca6d06418f1ba3f199def7c`

## Functional and Security Evidence

- Runtime copy is byte-identical to the verified raw artifact.
- Runtime connections report `PRAGMA query_only=ON` and use SQLite URI
  `mode=ro`.
- A real Chinook join and grouped revenue aggregation executed successfully.
- Row truncation was reported when the configured budget was exceeded.
- `DELETE` and `UPDATE` attempts failed and the source rows remained unchanged.
- Snapshot inspection recorded tables, columns, primary keys, foreign keys, and
  views in deterministic order.
- The tracked allowlist was derived from the snapshot and matched live runtime
  inspection.
- Public failures did not expose raw driver error messages.
- LLM-generated SQL remains outside the executor's authorized boundary.

## Automated Verification

- `uv sync --extra dev`: passed
- `uv run python scripts/dev.py data-setup`: passed twice
- `uv run python scripts/dev.py data-smoke`: passed; customer count was 59
- `uv run python scripts/dev.py test-integration`: 3 passed
- `uv run python scripts/dev.py verify`: passed
- Ruff format check: 29 files formatted
- Ruff lint: passed
- Mypy strict: 29 source files checked, no issues
- Pytest: 48 passed
- Branch coverage: 98.27%, required minimum 90%
- `uv lock --check`: passed
- Git ignore audit: local raw/runtime SQLite files ignored; manifests and
  metadata trackable
- High-risk secret-pattern scan: passed

The raw and runtime SQLite binaries are ignored by Git. The checksum manifest,
schema snapshot, allowlist, attribution, implementation, tests, and this report
are trackable.
