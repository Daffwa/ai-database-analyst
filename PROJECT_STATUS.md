# Project Status — AI Database Analyst

- Project version: `0.1.0`
- Last updated: 2026-07-28 (Asia/Bangkok)
- Active work package: Work Package 4 — Portfolio Release
- Active phase: Tahap 10 — public deployment decision pending
- Overall status: public repository and hosted release gate passed; application is not publicly deployed
- Repository path: `D:\Capstone\AI Database Analyst Project\ai-database-analyst`

## Phase Status

| Phase | Status | Gate |
|---|---|---|
| Tahap 0 — Scope | Completed | Passed on 2026-07-19 |
| Tahap 1 — Repository foundation | Completed | Passed on 2026-07-19 |
| Tahap 2 — Deterministic data foundation | Completed | Passed on 2026-07-19 |
| Tahap 3 — Text-to-SQL MVP | Completed | Passed on 2026-07-19 |
| Tahap 4 — Security guardrails | Completed | Passed on 2026-07-19 |
| Tahap 5 — Semantic layer | Completed | Passed on 2026-07-19 |
| Tahap 6 — Result and UX | Completed | Passed on 2026-07-20 |
| Tahap 7 — Evaluation | Completed | Passed on 2026-07-20 |
| Tahap 8 — PostgreSQL and FastAPI | Completed | Passed on 2026-07-21 |
| Tahap 9 — Docker and CI/CD | Completed | Passed on 2026-07-21 |
| Tahap 10 — Release | In progress | Repository/hosted gate passed; public deployment pending |

## Completed in Tahap 0

- Read the blueprint, detailed work sequence, and custom master prompt.
- Inspected the workspace and applicable local instructions.
- Confirmed that no `AGENTS.md` and no Git repository currently exist.
- Inspected the local toolchain.
- Defined MVP scope, non-goals, user stories, and testable acceptance criteria.
- Defined the initial architecture and trust boundaries.
- Created the initial threat model.
- Created an inventory of supported, ambiguous, unsupported, and unsafe questions.
- Verified the official Chinook source, current published release, and license text.
- Recorded architecture decisions and deferred decisions.

## Completed in Tahap 1

- Initialized an empty Git repository on branch `main`.
- Created an installable Python package targeting Python 3.11–3.12.
- Added a locked `uv` workflow and a documented `venv`/`pip` fallback.
- Added `.gitignore`, `.dockerignore`, `.gitattributes`, and `.editorconfig`.
- Added `.env.example` with safe fake-provider and privacy defaults.
- Implemented lazy, immutable, and validated application settings.
- Implemented framework-independent public error contracts.
- Implemented JSON structured logging with conservative redaction.
- Added a cross-platform development command wrapper.
- Configured Ruff, Mypy strict, Pytest, branch coverage, and a 90% threshold.
- Added 24 deterministic offline tests.
- Created and verified a clean `.venv` with CPython 3.12.13.
- Verified formatting, linting, typing, tests, coverage, lockfile, Git ignore
  behavior, package imports, and high-risk secret patterns.

## Completed in Tahap 2

- Pinned the official Chinook v1.4.5 SQLite artifact by URL, size, and SHA-256.
- Added atomic acquisition that fails closed on missing or mismatched bytes.
- Added idempotent, byte-identical runtime initialization with integrity,
  exact-schema, and row-count verification.
- Added a SQLAlchemy 2.0.51 engine using SQLite URI `mode=ro`,
  `PRAGMA query_only=ON`, foreign-key enforcement, and `NullPool`.
- Added deterministic inspection for tables, columns, primary keys, foreign
  keys, and views.
- Added a content-addressed schema snapshot and a derived table/column allowlist.
- Added a bounded manual SQL executor with row, column, response-byte, and
  query-length limits plus sanitized errors.
- Proved that `DELETE` and `UPDATE` attempts fail and data remains unchanged.
- Added repeatable download, initialization, snapshot, bootstrap, and manual
  smoke-test commands.
- Added 24 Tahap 2 unit and integration tests, bringing the suite to 48 tests.

## Completed in Tahap 3

- Added strict provider-neutral structured text-to-SQL contracts.
- Added asynchronous `BaseLLMAdapter`, deterministic `FakeLLMAdapter`, and a
  safe provider factory.
- Added bounded deterministic schema retrieval and versioned prompt `v1`.
- Added fail-closed JSON parsing and declared table/column validation.
- Added sanitized LLM timeout, provider, and invalid-output error contracts.
- Added an explicit orchestration pipeline with UUID request IDs and separate
  LLM/database latency fields.
- Kept normal generated SQL non-executable pending the Tahap 4 AST gate.
- Added 20 exact closed mini-cases with trusted SQL and result SHA-256 baselines.
- Achieved 20/20 structured validity, SQL identity, execution success, and
  database-result identity using the fake adapter without network or credentials.
- Added a Streamlit UI with production warning, SQL separation, result table,
  safe errors, and audit metadata.
- Added 45 Tahap 3 tests, bringing the full suite to 93 tests.

## Completed in Tahap 4

- Pinned SQLGlot 30.12.0 and parse every candidate with an explicit SQLite
  dialect, exactly one statement, and a read-only query root.
- Added recursive AST checks for DML, DDL, privilege, transaction,
  administrative, `SELECT INTO`, recursive CTE, set-operation, subquery,
  function, parameter, complexity, and cartesian-join risks.
- Enforced snapshot-derived schema/table/column allowlists, AST-derived sources,
  declared-source consistency, a conservative function allowlist, dangerous
  function blocklist, and sensitive catalog blocklist.
- Added deterministic outer `LIMIT` rewriting, literal-redacted SHA-256
  fingerprints, SQLite deadline interruption, and existing row/column/byte
  budgets.
- Routed generated SQL through `SecureQueryOrchestrator`; only validator-owned
  executed SQL can reach the independently read-only executor.
- Added safe audit decisions without raw questions, raw SQL, or result rows.
- Added bounded repair coordination with at most two attempts by default,
  non-repairable security violations, sanitized reason codes, and complete
  candidate revalidation.
- Added a versioned 30-case unsafe corpus and measured it against the 20 safe
  baselines: 100% known-unsafe blocking and 0% false blocking.
- Added a secured Tahap 4 runtime, smoke/evaluation commands, updated UI states,
  security policy documentation, threat-model revision, and 60 new/expanded
  tests, bringing the full suite to 153 tests.

## Completed in Tahap 5

- Added strict, versioned YAML sources for 9 bilingual glossary terms, 10
  canonical metrics, 11 approved foreign-key joins, and 10 verified queries.
- Bound every semantic artifact to the active Chinook schema hash and a
  deterministic semantic content hash.
- Added safe loading and fail-closed validation for versions, identifiers,
  synonyms, tables, columns, metric expressions, joins, cross-references,
  statuses, and verified SQL.
- Added deterministic Indonesian/English clarification for five ambiguous
  business-term families with no silent defaults.
- Mapped explicit interpretations to canonical metric IDs and visible
  assumptions without over-clarifying clear questions.
- Added status-aware, relevance-filtered, count-bounded verified-query retrieval
  that remains behind the complete SQL security boundary.
- Integrated semantic context, provenance, ambiguity states, and safe decision
  logging into the prompt, orchestrator, Stage 5 runtime, and Streamlit UI.
- Added semantic validation, evaluation, smoke, and focused test commands to the
  standard development workflow; semantic changes now run regression evaluation.
- Added a local reusable Chinook semantic-layer skill package and detailed
  semantic, evaluation, architecture, risk, and decision documentation.
- Added 49 tests beyond Tahap 4, bringing the full suite to 202 tests.

## Completed in Tahap 6

- Added strict contracts for normalized results, display values, chart specs,
  numeric evidence, UI states, feedback, history, CSV, explorer, and System Info.
- Preserved immutable raw values while creating a parallel formatted display
  view with explicit identifier, temporal, measure, and category roles.
- Added deterministic KPI, bar, line, scatter, and table selection using only
  returned columns; identifiers are never continuous measures.
- Added deterministic result summaries whose numeric claims reference exact
  returned cells.
- Added explicit success, empty, clarification, blocked, unsupported, timeout,
  and error states without treating an empty result as a generic failure.
- Added bounded metadata-only query history, fixed feedback, bounded safe CSV,
  schema-only Database Explorer, and allowlisted System Info.
- Rebuilt the Streamlit UI with auditable SQL, validation, result, chart,
  explanation, sources, warnings, download, feedback, and four navigation tabs.
- Added Altair 6.2.2 for readable temporal axes after browser QA exposed label
  collision on the 60-month revenue chart.
- Added the `stage-6-v1` evaluator: all 20 database/presentation/chart/summary/CSV
  cases and 4 explicit chart expectations passed.
- Added 47 tests beyond Tahap 5, bringing the full suite to 249 tests with
  95.45% branch coverage.

## Completed in Tahap 7

- Added a strict, content-addressed `stage-7-v1` JSONL corpus with exactly 100
  cases in the required distribution and 70/30 development/holdout labels.
- Added category-aware case contracts and a fail-closed loader that rejects
  malformed rows, duplicate IDs/questions, mixed versions, and distribution
  drift.
- Added executed-result comparison for explicit ordering, unordered multisets,
  NULL, empty results, non-numeric types, and numeric tolerance.
- Added a complete offline runner across semantics, fake structured generation,
  AST validation, read-only execution, result processing, and UX states.
- Added metrics for structured output, valid SQL, execution success/accuracy,
  schema hallucination, unsafe/false blocking, clarification, repair, P50/P95
  latency, and nullable provider usage/cost.
- Added full provenance for dataset, Chinook, schema, prompt, semantics,
  provider/model, runtime configuration, Python, SQLGlot, Git, and timestamps.
- Added a tracked machine baseline, human report, category error analysis, and
  machine-readable regression comparison.
- Defined zero-degradation quality thresholds and a mandatory 100%
  known-unsafe blocking gate; latency drift is a separate warning.
- Expanded deterministic schema retrieval for invoice-line, unit-sales,
  billing, media-type, and support-representative phrasing found by the corpus.
- Added 17 evaluation tests, bringing the full suite to 266 tests with 94.80%
  branch coverage.

## Completed in Tahap 8

- Pinned the official Chinook v1.4.5 PostgreSQL asset by URL, byte size, and
  SHA-256, and generated a content-addressed PostgreSQL schema snapshot.
- Added a dialect overlay that preserves the reviewed semantic definitions and
  changes only PostgreSQL-specific verified SQL.
- Added reproducible bootstrap for `analytics_owner`, `analytics_readonly`,
  `app_metadata_user`, and `migration_user`, separate `chinook` and
  `analyst_metadata` databases, and owner-only physical tables behind
  compatibility views.
- Added a PostgreSQL executor with exact-role identity checks, read-only
  transactions, bounded execution, statement timeout, and allowlisted search
  path.
- Added the ten required durable metadata models, indexes, privacy-safe fields,
  repository operations, and an Alembic migration from an empty database.
- Added a FastAPI app factory, dependency injection, versioned health, query,
  schema, history, feedback, and protected evaluation endpoints with strict
  contracts and sanitized errors.
- Moved the final Streamlit frontend behind a typed API client that contains no
  database credential; retained the Tahap 6 in-process UI as a regression
  fixture.
- Added an ephemeral PostgreSQL integration runner and four actual-database
  tests for role enforcement, migration, credential isolation, and end-to-end
  persistence.
- Passed deterministic implementation readiness, Alembic offline DDL
  generation, Ruff, Mypy strict, and the full offline suite: 289 passed, four
  environment-gated PostgreSQL tests skipped, 91.36% branch coverage.
- Enabled the local virtualization prerequisite, restored WSL2, and passed all
  four actual PostgreSQL tests for migrations, role privileges, credential
  isolation, and end-to-end API/metadata persistence.
- Hardened the integration runner after the first cold image pull exposed a
  short timeout and command-line secret risk: image pulling now has a dedicated
  timeout and temporary passwords travel only through the child environment.

## Completed in Tahap 9

- Added separate multi-stage API and frontend Dockerfiles using the pinned
  Python 3.12.13 base digest, frozen runtime dependencies, explicit source
  copies, health checks, and non-root UID/GID `10001:10001`.
- Added a four-service Compose stack for PostgreSQL, one-shot bootstrap,
  FastAPI, and Streamlit with readiness dependencies, an internal database
  network, required generated credentials, read-only application filesystems,
  localhost ports, and a named development volume.
- Added an exclusive random Compose environment generator and a safe reset
  procedure; no fixed runtime password or token is present in configuration.
- Added a no-cache gate that proves bootstrap, health, end-to-end query,
  operational metrics, request correlation, required structured log fields,
  log privacy, non-root image identity, image-history secret absence, and
  complete resource cleanup.
- Added least-privilege GitHub Actions definitions for Python 3.11/3.12 quality
  and coverage, actual PostgreSQL/API integration, source/container security,
  scheduled evaluation, and clean Compose smoke artifacts. All actions are
  pinned by full commit SHA and no workflow references a repository secret.
- Fixed a clean-checkout CI defect discovered by the local gate: the quality
  and evaluation workflows now bootstrap the pinned SQLite fixture before
  deterministic evaluation.
- Added pip-audit 2.10.1, Bandit 1.9.4, Gitleaks 8.30.1, digest-pinned Trivy
  0.70.0, CodeQL, and Dependabot coverage. Dependency, SAST, source-secret,
  SQL-security, image-secret/vulnerability, and Dockerfile configuration gates
  all pass.
- Added canonical UUID request propagation from Streamlit through FastAPI,
  orchestration, SQL policy, and database execution; structured analytics logs
  contain the required diagnostic fields and exclude raw payloads/credentials.
- Added a protected process metrics contract for request, success, blocked,
  clarification, timeout, repair, latency, status, error, and explicit nullable
  token usage.
- Passed a temporary committed clean checkout on both Python 3.11 and 3.12,
  the final no-cache whole-stack gate, complete security scanning, all 14 Tahap
  9 readiness checks, and the preserved Tahap 8 live gate.

## Completed in Tahap 10

- Added the final README narrative, reviewed screenshots, `SECURITY.md`, API
  reference, deployment/rollback guide, demo script, and release-candidate
  architecture/threat-model updates.
- Added the Tahap 10 readiness evaluator, which passes every local document,
  command, link, screenshot, evaluation, Compose, security, and clean-checkout
  check and validates separately recorded GitHub-hosted evidence.
- Ran browser QA for success, clarification, destructive blocked, Database
  Explorer, Query History, and System Info states with no console errors.
- Fixed the final API fake runtime so all ten adversarial Tahap 7 prompts reach
  deterministic AST validation; a destructive PostgreSQL UI/API request is now
  visibly blocked with no executed SQL.
- Re-ran the full offline gate, live PostgreSQL 4/4, no-cache Compose, complete
  security scan, and clean-checkout matrix on the exact updated source.
- Published the MIT-licensed repository publicly as
  `Daffwa/ai-database-analyst` and verified CI, Docker, Security, CodeQL, and
  scheduled/manual Evaluation on GitHub-hosted runners.
- Resolved the GitPython advisory chain and merged reviewed dependency/action
  updates only after their hosted gates passed; no Dependabot PR remains open.

## Primary Files Created

- `PROJECT_STATUS.md`
- `DECISIONS.md`
- `docs/requirements.md`
- `docs/architecture.md`
- `docs/threat-model.md`
- `docs/data-source.md`
- `docs/question-inventory.md`
- `docs/api.md`
- `docs/deployment.md`
- `docs/demo-script.md`
- `SECURITY.md`
- `README.md`
- `pyproject.toml`
- `uv.lock`
- `requirements.txt`
- `requirements-dev.txt`
- `.env.example`
- `.gitignore`
- `.dockerignore`
- `.gitattributes`
- `.editorconfig`
- `backend/core/config.py`
- `backend/core/errors.py`
- `backend/core/logging.py`
- `backend/data/`
- `backend/db/`
- `backend/schemas/database.py`
- `backend/services/query_executor.py`
- `backend/services/schema_service.py`
- `backend/llm/`
- `backend/evaluation/`
- `backend/runtime/stage3.py`
- `backend/runtime/stage4.py`
- `backend/runtime/stage5.py`
- `backend/runtime/stage6.py`
- `backend/schemas/llm.py`
- `backend/services/schema_retriever.py`
- `backend/services/prompt_builder.py`
- `backend/services/output_parser.py`
- `backend/services/sql_generator.py`
- `backend/services/orchestrator.py`
- `backend/services/secure_orchestrator.py`
- `backend/services/sql_security.py`
- `backend/services/sql_repair.py`
- `backend/schemas/sql_security.py`
- `backend/schemas/semantic.py`
- `backend/evaluation/security_cases.py`
- `backend/evaluation/security_runner.py`
- `backend/evaluation/semantic_cases.py`
- `backend/evaluation/semantic_runner.py`
- `backend/services/semantic_loader.py`
- `backend/services/semantic_validator.py`
- `backend/services/semantic_service.py`
- `backend/services/clarification_service.py`
- `backend/services/verified_query_service.py`
- `backend/schemas/result.py`
- `backend/services/result_formatter.py`
- `backend/services/chart_selector.py`
- `backend/services/result_summarizer.py`
- `backend/services/result_experience.py`
- `backend/services/query_history.py`
- `backend/services/feedback_service.py`
- `backend/services/csv_export.py`
- `backend/services/experience_metadata.py`
- `configs/security/table_allowlist.json`
- `semantic/glossary.yaml`
- `semantic/metrics.yaml`
- `semantic/joins.yaml`
- `semantic/verified_queries.yaml`
- `data/raw/SHA256SUMS.txt`
- `data/schemas/chinook-v1.4.5.json`
- `scripts/dev.py`
- `scripts/bootstrap_data.py`
- `scripts/evaluate_stage3.py`
- `scripts/stage3_smoke.py`
- `scripts/evaluate_stage4.py`
- `scripts/stage4_smoke.py`
- `scripts/validate_semantic.py`
- `scripts/evaluate_stage5.py`
- `scripts/stage5_smoke.py`
- `scripts/evaluate_stage6.py`
- `scripts/stage6_smoke.py`
- `frontend/streamlit_app.py`
- `tests/unit/`
- `tests/integration/`
- `reports/test-results/stage-1-summary.md`
- `reports/test-results/stage-2-summary.md`
- `reports/test-results/stage-3-summary.md`
- `reports/test-results/stage-4-summary.md`
- `reports/test-results/stage-5-summary.md`
- `reports/test-results/stage-6-summary.md`
- `backend/schemas/evaluation.py`
- `backend/evaluation/case_loader.py`
- `backend/evaluation/comparator.py`
- `backend/evaluation/stage7_runner.py`
- `backend/evaluation/regression.py`
- `data/evaluation/stage-7-v1.jsonl`
- `scripts/build_stage7_dataset.py`
- `scripts/evaluate_stage7.py`
- `tests/evaluation/`
- `reports/test-results/stage-7-summary.md`
- `reports/evaluation/stage-3-mini.json`
- `reports/evaluation/stage-4-security.json`
- `reports/evaluation/stage-5-semantic.json`
- `reports/evaluation/stage-6-result-ux.json`
- `reports/evaluation/stage-7-baseline.json`
- `reports/evaluation/stage-7-baseline.md`
- `reports/evaluation/stage-7-regression.json`
- `reports/evaluation/stage-7-error-analysis.md`
- `.github/workflows/`
- `.github/dependabot.yml`
- `.env.compose.example`
- `.gitleaks.toml`
- `Dockerfile.api`
- `Dockerfile.frontend`
- `docker-compose.yml`
- `backend/core/observability.py`
- `docs/operations.md`
- `scripts/generate_compose_env.py`
- `scripts/run_stage9_compose.py`
- `scripts/run_stage9_security.py`
- `scripts/run_stage9_clean_checkout.py`
- `scripts/evaluate_stage9.py`
- `reports/test-results/stage-9-summary.md`

## Environment Snapshot

| Tool | Observed state |
|---|---|
| Operating system | Windows / PowerShell |
| Python | System 3.12.10; verified project environment 3.12.13; 3.11 not locally installed |
| Git | 2.54.0 available |
| uv | 0.11.14; lock and sync verified |
| Docker | Desktop/CLI installed; local engine unavailable during the 2026-07-28 follow-up; hosted Docker/Security gates passed |
| GitHub CLI | 2.96.0; authenticated as `Daffwa` |
| Git repository | Public `Daffwa/ai-database-analyst`; `main` published and synchronized |

The repository has real history, an authorized public GitHub remote, and hosted
workflow evidence. The clean-checkout gate remains an independent reproduction
check rather than a substitute for hosted CI.

## Last Verification

- Environment: `uv sync --extra dev` — passed
- Main command: `uv run python scripts/dev.py verify` — passed
- Data bootstrap: passed twice; second run reused verified output
- Dataset integrity: passed; SHA-256, 11 tables, and all row counts matched
- Read-only smoke test: passed; customer count was 59
- Tahap 3 mini evaluation: 20/20 across all four metrics
- Tahap 4 security evaluation: 30/30 known unsafe blocked; 0/20 safe baselines
  false-blocked
- Tahap 5 semantic validation: 9 terms, 10 metrics, 11 approved joins, and 10
  verified queries valid with 0 issues
- Tahap 5 clarification evaluation: 10/10 ambiguous cases clarified; 10/10
  explicit resolutions and 20/20 clear baselines not over-clarified
- Tahap 5 verified retrieval evaluation: 10/10 exact cases retrieved
- Tahap 6 result evaluation: 20/20 database results, presentations, chart
  contracts, grounded summaries, and CSV exports passed
- Tahap 6 explicit expected charts: 4/4; empty, feedback, history privacy,
  explorer, and System Info checks passed
- Tahap 7 formal evaluation: 100/100 cases passed with the exact required
  distribution and 70/30 development/holdout labels
- Tahap 7 analytical accuracy: 85/85; valid SQL and execution success: 85/85;
  schema hallucination: 0/85; false blocking: 0/85
- Tahap 7 security/clarification: 10/10 unsafe blocked; 5/5 ambiguity rules
  matched; baseline regression gate passed
- Tahap 8 deterministic readiness: 9/9 implementation checks passed
- Alembic PostgreSQL offline upgrade from empty: passed; ten models, indexes,
  grants, foreign keys, and revision tracking generated
- Tahap 8 actual PostgreSQL integration: 4/4 passed against the ephemeral
  `postgres:17.10-alpine3.24` container; the container was removed afterward
- Streamlit headless interaction tests: 5 passed
- Browser visual QA: success, clarification, destructive blocked, Explorer,
  History, and System Info passed at 1280×720; no console errors
- Ruff format: passed
- Ruff lint: passed
- Mypy strict: passed, 145 source files checked
- Pytest offline suite: 303 passed, 4 environment-gated PostgreSQL tests skipped
- Pytest actual PostgreSQL suite: 4 passed
- Branch coverage: 92%, required minimum 90%
- Lockfile check: passed
- Git ignore checks: secrets, environments, and local SQLite binaries ignored;
  checksum, snapshot, allowlist, attribution, and `.env.example` trackable
- High-risk secret-pattern scan: passed
- Tahap 9 no-cache Compose: passed; db/API/frontend healthy, trace/log/metrics
  and non-root image checks passed, generated resources removed
- Tahap 9 security: dependency audit, Bandit, Gitleaks, SQL tests, Trivy image
  and configuration checks all passed
- Tahap 9 clean checkout: Python 3.11 and 3.12 full verification passed from an
  isolated temporary commit and clone
- GitHub-hosted release evidence: CI, Docker, Security, CodeQL, and manually
  dispatched Evaluation passed against commit `6002469`
- Detailed evidence: `reports/test-results/stage-3-summary.md`
- Tahap 4 evidence: `reports/test-results/stage-4-summary.md`
- Tahap 5 evidence: `reports/test-results/stage-5-summary.md`
- Tahap 6 evidence: `reports/test-results/stage-6-summary.md`
- Tahap 7 evidence: `reports/test-results/stage-7-summary.md`
- Tahap 8 evidence: `reports/test-results/stage-8-summary.md` and
  `reports/evaluation/stage-8-readiness.json`
- Tahap 9 evidence: `reports/test-results/stage-9-summary.md`,
  `reports/evaluation/stage-9-readiness.json`,
  `reports/test-results/stage-9-compose.json`,
  `reports/test-results/stage-9-clean-checkout.json`, and
  `reports/security/stage-9-security.json`
- Tahap 10 evidence: `reports/test-results/stage-10-summary.md`,
  `reports/evaluation/stage-10-readiness.json`, and
  `reports/evaluation/stage-10-external-evidence.json`

## Tahap 0 Quality Gate

- [x] MVP scope is explicit and testable.
- [x] Final-portfolio features and roadmap features are separated from MVP.
- [x] Chinook source and license are recorded.
- [x] Default stack and environment differences are recorded.
- [x] Primary security and delivery risks are recorded.
- [x] Acceptance criteria are expressed as observable behavior.
- [x] No application implementation from Tahap 1 or later has started.
- [x] All Tahap 0 files pass the final consistency and completeness check.

## Tahap 1 Quality Gate

- [x] Git repository is initialized on `main`.
- [x] Dependencies install in a clean project virtual environment.
- [x] The project package builds and imports successfully.
- [x] Runtime configuration is lazy, immutable, and safe without credentials.
- [x] Ruff formatting and linting pass.
- [x] Mypy strict type checking passes.
- [x] Pytest passes without network access or a real API key.
- [x] Branch coverage exceeds the required threshold.
- [x] `.env`, `.venv`, caches, runtime databases, and generated artifacts are
  ignored by Git.
- [x] `.env.example` is trackable and contains no real secret.
- [x] Setup and verification commands are documented and tested.
- [x] No database, LLM, frontend, or later-phase implementation was started.

## Tahap 2 Quality Gate

- [x] The exact official Chinook release asset is pinned by size and SHA-256.
- [x] Download and initialization are atomic, reproducible, and idempotent.
- [x] SQLite integrity, the exact table set, and all row counts are verified.
- [x] The runtime binary is byte-identical to the verified raw artifact.
- [x] The tracked schema snapshot matches live runtime inspection.
- [x] The tracked table/column allowlist is derived from that snapshot.
- [x] Runtime connections enforce URI `mode=ro` and `PRAGMA query_only=ON`.
- [x] Manual joins and aggregations execute within explicit response budgets.
- [x] Destructive statements fail and leave the database unchanged.
- [x] Unit and integration tests are deterministic and need no LLM credential.
- [x] Ruff, Mypy strict, Pytest, branch coverage, and lockfile checks pass.
- [x] Local database binaries are ignored while reproducibility metadata is
  trackable.

## Tahap 3 Quality Gate

- [x] The pipeline runs with `FakeLLMAdapter` and no API credential or network.
- [x] Structured intent/output contracts are strict and provider-neutral.
- [x] Invalid JSON, invalid fields, and empty analysis SQL are rejected.
- [x] LLM timeout and provider failures map to safe public errors.
- [x] Prompt schema context is relevant and bounded by tables and characters.
- [x] Unknown schema declarations are rejected before orchestration completes.
- [x] Normal generated SQL stops before execution pending Tahap 4.
- [x] Generated SQL and executed SQL are represented and displayed separately.
- [x] Twenty closed simple cases match trusted SQL and database result baselines.
- [x] Numeric demo values originate from SQLite results, not adapter text.
- [x] LLM and database latency are measured separately.
- [x] Every response has a UUID request ID and production-readiness warning.
- [x] The minimum Streamlit UI passes a headless interaction test.
- [x] No real credential is required, stored, logged, or reported.
- [x] Ruff, Mypy strict, Pytest, branch coverage, and lockfile checks pass.

## Tahap 4 Quality Gate

- [x] All 30 versioned known-unsafe SQL cases are blocked as expected.
- [x] Every executable candidate is parsed with the explicit SQLite dialect.
- [x] Exactly one root read-only query is permitted.
- [x] Recursive CTE, subquery, set-operation, and function checks are applied.
- [x] Schema, table, column, function, and catalog policies are enforced.
- [x] The outer limit is capped at 500 by default.
- [x] Query timeout and row, column, response-byte, and SQL-length budgets apply.
- [x] Generated SQL and executed SQL remain separate.
- [x] SQLite read-only mode and query-only enforcement remain the last barrier.
- [x] Database/parser errors exposed through public contracts are sanitized.
- [x] Repair is capped, security violations are not repaired, and every candidate
  is fully revalidated.
- [x] False blocking is measured: 0/20 safe baselines, or 0%.
- [x] Security decisions are auditable without raw SQL/result retention.
- [x] Ruff, Mypy strict, all tests, branch coverage, and lockfile checks pass.

## Tahap 5 Quality Gate

- [x] Glossary, metrics, joins, and verified queries share version `v1` and the
  active schema hash.
- [x] All 9 terms and synonyms are conflict-free and schema-valid.
- [x] All 10 metric expressions and references pass semantic and SQL validation.
- [x] All 11 approved joins map to real foreign keys with explicit cardinality
  and double-counting risk.
- [x] All 10 verified queries are non-draft, schema-bound, and security-valid.
- [x] Five ambiguity families return localized choices before LLM/SQL, with no
  silent default.
- [x] Ambiguity recall is 10/10; explicit-resolution and clear-query false
  clarification is 0/30.
- [x] Semantic prompt context and verified examples are relevant and bounded.
- [x] Response and audit provenance include semantic version/hash and IDs while
  raw question and assumption text stay out of logs.
- [x] Semantic changes trigger validation and regression evaluation in `verify`.
- [x] Ruff, Mypy strict, all 202 tests, 96.30% branch coverage, and lockfile
  checks pass.

## Tahap 6 Quality Gate

- [x] Raw database values are preserved separately from display formatting.
- [x] Result columns, rows, row count, truncation, latency, and provenance are
  normalized through strict contracts.
- [x] Charts are deterministic, use returned columns only, and do not treat
  identifiers as continuous measures.
- [x] Numeric explanations are traceable to exact returned cells.
- [x] Success, empty, clarification, blocked, unsupported, timeout, and error
  states are explicit and tested.
- [x] Generated SQL, executed SQL, validation, assumptions, warnings, and
  sources remain visible.
- [x] Query history is bounded and excludes raw questions, SQL, and result rows.
- [x] Feedback uses fixed categories and is linked to known requests.
- [x] CSV export is byte-bounded and neutralizes spreadsheet formulas.
- [x] Database Explorer is schema-only and System Info is allowlisted.
- [x] All 20 Stage 6 evaluation cases and 4 expected-chart checks pass.
- [x] Browser QA and five headless Streamlit tests pass.
- [x] Ruff, Mypy strict, all 249 tests, 95.45% branch coverage, and lockfile
  checks pass.

## Tahap 7 Quality Gate

- [x] The strict JSONL corpus contains exactly 100 cases in the required
  category distribution.
- [x] The baseline is reproducible and content-addressed with complete version
  and runtime provenance.
- [x] Execution accuracy is reported: 85/85 analytical cases matched.
- [x] Schema hallucination is reported: 0/85 analytical cases.
- [x] False blocking is reported: 0/85 analytical cases.
- [x] Known unsafe blocking is 10/10, or 100%.
- [x] Clarification accuracy and precision are both 100% on the formal corpus.
- [x] Order, numeric tolerance, NULL, empty, and type comparison rules are
  covered by focused tests.
- [x] Baseline, regression comparison, and human-readable error analysis are
  tracked.
- [x] Any security decrease fails the regression gate.
- [x] Ruff, Mypy strict, all 266 tests, 94.80% branch coverage, and lockfile
  checks pass.

## Tahap 8 Quality Gate

- [x] The official PostgreSQL artifact, checksum, logical snapshot, and
  semantic dialect overlay are reproducible and validated.
- [x] Four exact roles and separate analytics/metadata credentials are defined.
- [x] Runtime identity checks reject privileged, unexpected, or shared roles.
- [x] Ten metadata models and their indexes are managed through Alembic.
- [x] Alembic generates a complete PostgreSQL upgrade from an empty database.
- [x] Versioned FastAPI contracts, dependency injection, bounded CORS, and safe
  exception handling are tested.
- [x] Streamlit accesses the final runtime only through an API client and holds
  no database credential.
- [x] Metadata fields exclude raw question text, generated SQL, and result rows.
- [x] Deterministic readiness, Ruff, Mypy, offline tests, coverage, and the
  Tahap 7 regression gate pass.
- [x] A live `analytics_readonly` connection rejects writes and cannot access
  owner-only tables.
- [x] Alembic upgrade/downgrade is proven against an actual empty PostgreSQL
  database.
- [x] The end-to-end FastAPI/PostgreSQL integration suite passes with separate
  credentials.

## Tahap 9 Quality Gate

- [x] API and frontend images use pinned bases, multi-stage builds, explicit
  source copies, health checks, and non-root runtime identities.
- [x] `docker compose up` starts PostgreSQL, bootstrap, API, and frontend with
  readiness ordering and a named development volume.
- [x] The final stack build passes with `--no-cache`; database, API, and
  frontend report healthy and the gate removes all named resources.
- [x] Generated runtime credentials are required externally and do not appear
  in image configuration/history, logs, reports, or source.
- [x] CI definitions cover Python 3.11/3.12 quality, coverage, live
  PostgreSQL/API integration, security, evaluation, and Docker smoke.
- [x] Workflow permissions are least-privilege, checkout credentials are not
  persisted, action references are immutable SHAs, and fork workflows
  reference no repository secret.
- [x] A temporary committed clean checkout passes the full verification
  sequence on Python 3.11 and 3.12.
- [x] Dependency audit, SAST, source secret scan, SQL security tests, both image
  scans, and Dockerfile configuration scan pass.
- [x] Request IDs correlate frontend, API, orchestration, SQL policy, database
  execution, response, and structured logs.
- [x] Structured logs contain the required operational fields and no raw
  question, SQL, result row, credential, header, or connection URL.
- [x] Protected metrics expose request/outcome/timeout/repair rates, latency,
  errors, status counts, and explicit nullable provider usage.

## Tahap 10 Quality Gate

- [x] README, API, operations, deployment/rollback, demo, dataset, evaluation,
  architecture, and security documentation match the local implementation.
- [x] `SECURITY.md` and the final local threat-model disposition are present.
- [x] Safe, ambiguous, and destructive UI behaviors are documented and tested.
- [x] Two 1280×720 screenshots were reviewed and contain only synthetic data.
- [x] Local Markdown links and documented `scripts/dev.py` commands resolve.
- [x] Format, lint, strict typing, offline tests, coverage, and 100-case
  evaluation pass.
- [x] Live PostgreSQL 4/4, no-cache Compose, complete security tools, and clean
  checkout on Python 3.11/3.12 pass on the final source.
- [x] The machine report separates local readiness from external decisions.
- [x] Project license selected: MIT.
- [x] Authorized public GitHub remote and hosted Actions verified.
- [ ] Deployment smoke, logs, authentication, HTTPS, rate limit, managed
  secrets/database, and rollback verified if a public demo is selected.

## Open Issues

1. The public application deployment platform and authentication design remain
   unselected.
2. The real LLM provider remains deliberately
   undecided until its current capabilities, costs, and data policies are
   reviewed.

## Current Risks

- Public exposure before authentication, TLS, rate limiting, and a managed
  secret store are selected and verified.
- Incorrect business results caused by ambiguous metrics, double-counting, or
  project-verified definitions without independent analyst sign-off.
- Evaluation leakage if verified examples and test cases are not separated.
- Unknown dependency, action, container-registry, or scanner supply-chain risk.
- Secret or sensitive data exposure through future deployment configuration.

## Decisions Awaiting the User

The MIT license, public visibility, owner `Daffwa`, and repository name
`ai-database-analyst` are resolved. These optional production decisions remain:

- Real LLM provider and paid API authorization.
- Production deployment platform and any paid resources.
- Authentication approach for a public demo.

## Next Step

Select the public deployment platform/account, region and budget, plus the
authentication approach. Then provision HTTPS, rate limits, managed
secrets/PostgreSQL, monitoring, smoke tests, and a tested rollback before
recording any deployed URL. Preserve `verify`, live `test-postgres`, no-cache
`docker-smoke`, `security-stage9`, clean-checkout, and `evaluate-stage10` as
mandatory release gates.
