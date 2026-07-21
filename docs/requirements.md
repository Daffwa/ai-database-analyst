# Requirements — AI Database Analyst

- Document status: Tahap 0 baseline
- Version: 0.1.0
- Date: 2026-07-19
- Primary language: Indonesian UI and documentation; English source identifiers

## 1. Product Vision

AI Database Analyst is a conversational analytics application that lets a user
ask questions about a relational database in Indonesian or English without
writing SQL. The system translates the question into a constrained read-only
query, validates it deterministically, executes it with least privilege, and
presents an auditable answer grounded in database results.

The core principle is:

> The LLM proposes intent and SQL; deterministic validators enforce policy; the
> database calculates facts; the application exposes evidence and limitations.

## 2. Target Users

### Business User

Needs fast answers, understandable charts, clear assumptions, and no requirement
to know table names or SQL.

### Data Analyst

Needs visibility into generated and executed SQL, semantic definitions,
verified examples, evaluation failures, and user feedback.

### Database Administrator

Needs least-privilege roles, allowlists, query limits, audit metadata, and proof
that write operations are rejected.

### Application Maintainer

Needs reproducible setup, offline tests, stable contracts, structured logs,
versioned evaluation, Docker, and CI/CD.

## 3. MVP Scope

The MVP covers Work Package 1, Tahap 0–4:

1. Official pinned Chinook SQLite dataset.
2. Reproducible local database setup.
3. Schema inspection for tables, columns, primary keys, and foreign keys.
4. Read-only SQLite connection and deterministic manual query executor.
5. Indonesian and English natural-language question input.
6. Provider-neutral LLM contract.
7. Mandatory deterministic `FakeLLMAdapter` for tests.
8. Structured LLM output validated with Pydantic.
9. A basic Streamlit interface.
10. SQL AST parsing and fail-closed validation with SQLGlot.
11. Single-statement, read-only, schema/table/column, function, and catalog
    policies.
12. Maximum row, column, response-byte, and time limits.
13. Separate display of generated and executed SQL.
14. Result table, validation state, assumptions, sources, and safe errors.
15. Unit, integration, and security tests for the MVP path.

## 4. Final-Portfolio Scope

Features planned after the MVP security gate:

1. Versioned glossary, metrics, joins, and verified queries.
2. Clarification engine.
3. Deterministic chart selection and richer Streamlit UX.
4. Query history and feedback.
5. At least 100 versioned evaluation cases and regression reports.
6. PostgreSQL analytics database with a dedicated read-only role.
7. Separate metadata database credentials and Alembic migrations.
8. FastAPI backend and versioned API contracts.
9. Docker Compose, observability, GitHub Actions, and security checks.
10. Reproducible documentation, deployment, and portfolio release.

## 5. Non-Goals

The project does not initially provide:

- Data creation, modification, deletion, DDL, or administrative database tasks.
- Arbitrary database access beyond a configured allowlist.
- Autonomous business decisions or causal inference.
- Claims that are not supported by available data.
- A production multi-tenant authorization system.
- Automatic connection to confidential production databases.
- Guaranteed correctness merely because SQL is syntactically valid.
- Unrestricted exports or raw-result retention.
- Scheduled reports, Slack/Teams integration, or human approval workflows.

## 6. User Stories

### US-001 — Ask Without SQL

As a business user, I want to ask a question in Indonesian so that I can obtain
an answer without knowing the database schema or SQL.

Acceptance:

- The application accepts a non-empty Indonesian question.
- A successful response shows the executed SQL and database result.

### US-002 — Inspect Generated SQL

As a data analyst, I want to see both generated and executed SQL so that I can
audit validator rewrites.

Acceptance:

- The two values are labeled separately.
- Rewrites such as an added `LIMIT` are visible.

### US-003 — Reject Write Requests

As a database administrator, I want all write and DDL requests rejected so that
the analytics database cannot be modified by the application.

Acceptance:

- Known DML/DDL cases are blocked before execution.
- The database role independently rejects write operations.

### US-004 — Understand Ambiguity

As a business user, I want the system to ask a concise follow-up when a term such
as “best customer” has multiple meanings.

Acceptance:

- The response is `clarification_required` rather than a guessed result.
- The clarification offers relevant definitions when available.

### US-005 — See the Evidence

As a reviewer, I want to see source tables, source columns, assumptions, and
warnings so that I can assess whether an answer is credible.

Acceptance:

- Successful responses list the referenced sources derived from the validated
  SQL AST.

### US-006 — Handle Unsupported Questions Honestly

As a user, I want the application to explain when the database cannot answer my
question so that I do not receive fabricated conclusions.

Acceptance:

- Causal or out-of-domain questions are marked unsupported or narrowed to a
  supported descriptive analysis.

### US-007 — Run Tests Without an API Key

As a developer, I want deterministic tests that run without network access or a
provider credential.

Acceptance:

- Unit tests default to `FakeLLMAdapter`.
- Missing real-provider credentials do not break imports or offline tests.

### US-008 — Receive Safe Errors

As a user, I want actionable error messages without internal stack traces or
credentials.

Acceptance:

- Every failure has a stable public error code and request ID.
- Internal details are sanitized from the client response.

### US-009 — Review Quality Metrics

As a project reviewer, I want versioned evaluation results so that quality and
security claims are reproducible.

Acceptance:

- Reports include dataset, model/provider, prompt, semantic, schema, and Git
  versions where applicable.

### US-010 — Reproduce the Project

As a new maintainer, I want documented setup and verification commands so that I
can reproduce the project from a clean checkout.

Acceptance:

- Final setup succeeds from a clean environment using documented commands.

## 7. Functional Requirements

### Input and Intent

- FR-001: Accept questions in Indonesian and English.
- FR-002: Reject empty input and input over a configured length.
- FR-003: Assign a unique request ID before orchestration.
- FR-004: Distinguish analysis, clarification, unsupported, unsafe, and help
  behavior through a stable contract.

### Schema and Semantics

- FR-010: Inspect tables, columns, types, primary keys, and foreign keys.
- FR-011: Store a versioned schema snapshot and schema hash.
- FR-012: Restrict generation and validation to allowed schema objects.
- FR-013: Validate semantic definitions against the active snapshot.
- FR-014: Store versioned bilingual glossary, metric, approved-join, and
  verified-query definitions with a deterministic content hash.
- FR-015: Stop before LLM generation and SQL when a recognized business term
  has more than one valid interpretation.
- FR-016: Return localized clarification options without a silent default.
- FR-017: Attach selected metric IDs, assumptions, semantic version/hash, and
  retrieved verified-query IDs to response provenance.
- FR-018: Bound semantic prompt context and exclude draft or invalid examples.

### LLM Contract

- FR-020: Use a provider-neutral adapter.
- FR-021: Require structured output validated by Pydantic.
- FR-022: Reject missing SQL for an analysis intent.
- FR-023: Never use LLM confidence as a security or correctness decision.
- FR-024: Never request or retain private chain-of-thought.

### SQL Security and Execution

- FR-030: Parse SQL into an AST using the configured dialect.
- FR-031: Fail closed on parse error or dialect mismatch.
- FR-032: Permit only one read-only statement.
- FR-033: Recursively validate CTEs, subqueries, expressions, and set operations.
- FR-034: Enforce schema, table, column, function, and catalog policies.
- FR-035: Add or reduce a result `LIMIT` to the configured maximum.
- FR-036: Enforce a database statement timeout where supported.
- FR-037: Enforce maximum rows, columns, and response bytes.
- FR-038: Execute using a read-only database identity.
- FR-039: Revalidate every repaired query through the complete pipeline.

### Results and Auditability

- FR-040: Normalize columns, rows, row count, truncation, and latency.
- FR-041: Display generated SQL and executed SQL separately.
- FR-042: Derive source tables and columns from the validated query.
- FR-043: Ground explanations only in query results.
- FR-044: Handle success, empty, clarification, blocked, timeout, and error
  states explicitly.
- FR-045: Store safe operational metadata without raw result rows by default.
- FR-046: Select KPI, bar, line, scatter, or table deterministically using only
  returned result columns and validated temporal values.
- FR-047: Preserve raw values while formatting a parallel display view.
- FR-048: Make every numeric summary traceable to an exact returned cell.
- FR-049: Provide bounded CSV export, fixed feedback, schema-only exploration,
  and allowlisted System Info without exposing secrets.

### Evaluation

- FR-050: Support versioned evaluation cases.
- FR-051: Compare execution results rather than exact SQL text alone.
- FR-052: Measure structured-output validity, SQL validity, execution success,
  execution accuracy, hallucination, unsafe blocking, false blocking,
  clarification behavior, repair, latency, and usage.

## 8. Non-Functional Requirements

### Security

- NFR-SEC-001: All untrusted inputs and LLM outputs are treated as hostile.
- NFR-SEC-002: Security-critical parsing and validation fail closed.
- NFR-SEC-003: Runtime credentials follow least privilege.
- NFR-SEC-004: Secrets must not appear in Git, logs, reports, images, fixtures,
  screenshots, or client responses.
- NFR-SEC-005: Known destructive test cases must be blocked at 100% before
  public deployment.

### Reliability

- NFR-REL-001: Unit tests run without network access.
- NFR-REL-002: Dataset setup and metadata migrations are idempotent.
- NFR-REL-003: Retries are bounded and limited to retryable failures.
- NFR-REL-004: Every important bug receives a regression test.

### Performance Budget

- NFR-PERF-001: Default query timeout is 5 seconds.
- NFR-PERF-002: Default LLM timeout is 30 seconds.
- NFR-PERF-003: Default maximum result rows is 500.
- NFR-PERF-004: Default maximum columns is 100.
- NFR-PERF-005: Response-byte limit is configurable.
- NFR-PERF-006: Performance claims require measured P50/P95 results.

### Maintainability

- NFR-MNT-001: Domain services do not depend on Streamlit or provider SDK
  implementation details.
- NFR-MNT-002: Public interfaces use type hints.
- NFR-MNT-003: Security-critical behavior has focused tests and documentation.
- NFR-MNT-004: Configuration is centralized and validated.

### Privacy

- NFR-PRV-001: Raw result rows are not stored by default.
- NFR-PRV-002: Raw question and SQL retention are configurable.
- NFR-PRV-003: The LLM receives only the minimum relevant schema and data.
- NFR-PRV-004: Retention and deletion behavior is documented before production.

## 9. MVP Acceptance Criteria

- [x] Chinook can be created from a pinned, verified source.
- [x] The application reads and snapshots the schema.
- [x] Manual read-only queries work.
- [x] Database write attempts fail.
- [x] Indonesian questions are accepted.
- [x] LLM output is structured and validated.
- [x] Tests run using a fake adapter without an API key.
- [x] SQL is parsed with SQLGlot before execution.
- [x] Only one read-only statement is accepted.
- [x] DML, DDL, dangerous functions, and catalog access are blocked.
- [x] Allowlist, row limit, column limit, byte limit, and timeout are applied.
- [x] Generated and executed SQL are visible.
- [x] Results are displayed as a table.
- [x] Empty, blocked, clarification, timeout, and error states are distinct.
- [x] Recognized semantic ambiguity returns explicit localized options before
  LLM generation or SQL execution.
- [x] Semantic definitions and verified examples validate against the pinned
  schema and SQL policy.
- [x] Sources, assumptions, warnings, and request ID are visible.
- [x] Known destructive cases are blocked at 100%.
- [x] No secret is tracked or logged.
- [x] Setup and test commands are documented and verified.

## 10. Tahap 0 Exit Criteria

- [x] MVP scope and non-goals are explicit.
- [x] User stories have observable acceptance behavior.
- [x] Functional and non-functional requirements are identified.
- [x] Dataset source and license are documented.
- [x] Initial architecture and threat model exist.
- [x] Question inventory covers supported, ambiguous, unsupported, and unsafe
  behavior.
- [x] Deferred decisions are visible and do not block Tahap 0.

## 11. Implementation Progress Through Tahap 8

- [x] Chinook is pinned, reproducible, and schema-snapshotted.
- [x] Manual read-only queries and database write rejection are verified.
- [x] Indonesian and English question input contracts exist.
- [x] LLM integration is provider-neutral and defaults to a deterministic fake.
- [x] Structured model output is validated strictly with Pydantic.
- [x] Prompt schema context is deterministically selected and bounded.
- [x] Empty SQL, malformed JSON, provider timeout/error, and schema declaration
  mismatches fail safely.
- [x] Request IDs and separate LLM/database latency fields are visible.
- [x] Generated and executed SQL are displayed separately in Streamlit.
- [x] Twenty closed mini-cases return database-grounded baseline results.
- [x] Arbitrary generated SQL remains unexecuted unless Tahap 4 returns a safe
  validation report.
- [x] SQLGlot AST parsing and the complete SQL security policy are implemented.
- [x] Safe generated SQL can cross the security gate only as separately tracked,
  limit-rewritten executed SQL.
- [x] Known-unsafe blocking and false blocking are measured with a versioned
  corpus.
- [x] Repair attempts are bounded and every candidate is fully revalidated.
- [x] A versioned bilingual glossary, 10 canonical metrics, 11 approved joins,
  and 10 verified queries are tracked as schema-bound YAML.
- [x] Semantic artifacts have a deterministic content hash and fail closed on
  schema, reference, expression, join, status, or SQL-policy errors.
- [x] Five ambiguity families are resolved before the model with no silent
  default; explicit choices map to canonical metrics and visible assumptions.
- [x] Verified-query retrieval is relevance-filtered, status-aware, and bounded.
- [x] Semantic changes are included in the standard validation and regression
  evaluation sequence.
- [x] Results preserve raw values and expose a parallel formatted presentation.
- [x] KPI, bar, line, scatter, and table selection is deterministic and
  restricted to returned columns.
- [x] Numeric explanations include exact cell-level evidence.
- [x] Empty, clarification, blocked, unsupported, timeout, and error states have
  explicit UI contracts.
- [x] Query history and feedback are bounded and avoid raw question, SQL, and
  result-row retention.
- [x] CSV export is byte-bounded and neutralizes spreadsheet formula prefixes.
- [x] Database Explorer is schema-only and System Info is allowlisted.
- [x] The 20-case Tahap 6 result baseline and five Streamlit interaction tests
  pass.
- [x] A strict 100-case JSONL evaluation corpus matches the required category
  distribution and carries 70/30 development/holdout labels.
- [x] Result comparison handles order sensitivity, numeric tolerance, NULL,
  empty results, and type differences without requiring exact SQL identity.
- [x] Evaluation metrics cover structured output, valid SQL, execution success
  and accuracy, schema hallucination, unsafe and false blocking,
  clarification, repair, and P50/P95 latency.
- [x] Every run records dataset, schema, prompt, semantic, provider/model,
  runtime, Git, and environment provenance.
- [x] A machine-readable baseline, human summary, error analysis, and regression
  comparison are tracked.
- [x] The regression gate requires 100% blocking for the known unsafe set and
  permits no accuracy, valid-SQL, clarification, or false-block degradation.
- [x] The official Chinook PostgreSQL artifact is pinned and produces a
  content-addressed logical schema snapshot.
- [x] Four least-privilege roles and separate analytics/metadata databases are
  defined with exact runtime identity checks.
- [x] Ten privacy-minimized metadata models and indexes are managed by Alembic.
- [x] FastAPI exposes versioned health, query, schema, history, feedback, and
  protected evaluation contracts through dependency injection.
- [x] The final Streamlit UI uses a typed API client and contains no database
  credential.
- [x] Deterministic Tahap 8 readiness, offline Alembic DDL, 289 offline tests,
  Mypy strict, Ruff, and 91.36% branch coverage pass.
- [x] Actual PostgreSQL tests prove read-only write rejection, owner-table
  isolation, empty-database migration, separate credentials, and end-to-end
  persistence. All 4/4 passed on 2026-07-21.
- [x] Pinned API and frontend images use explicit multi-stage builds, health
  checks, non-root identities, and no broad source copy.
- [x] Compose provides healthy database, bootstrap, API, and frontend services,
  a named development volume, required runtime secrets, and readiness ordering.
- [x] CI definitions cover formatting, lint, typing, unit/coverage, actual
  PostgreSQL/API integration, evaluation, security, and clean Compose smoke.
- [x] Dependency audit, SAST, secret scan, SQL security tests, and
  image/configuration scans have executable privacy-minimized gates.
- [x] Request IDs propagate end to end and analytics logs contain all required
  diagnostic fields without raw question, SQL, result, URL, or credential data.
- [x] Protected operational metrics measure request, outcome, timeout, repair,
  latency, and nullable provider usage.
