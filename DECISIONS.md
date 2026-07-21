# Architecture Decisions — AI Database Analyst

This file records decisions that affect architecture, security, reproducibility,
or project scope. Accepted decisions may still be revisited through a new
superseding decision rather than silently edited.

## ADR-0001 — Deliver the Project Through Sequential Quality Gates

- Date: 2026-07-19
- Status: Accepted

### Context

The final blueprint includes database engineering, LLM integration, SQL
security, semantic modeling, frontend, API, evaluation, Docker, CI/CD, and
deployment. Implementing all layers at once would make failures difficult to
isolate and would encourage unverifiable completion claims.

### Options Considered

1. Build the final architecture in one pass.
2. Build a narrow demo without formal gates.
3. Implement Tahap 0–10 sequentially with exit criteria.

### Decision

Use sequential phases with one active phase at a time. A later phase may not
become active until the mandatory gate for the current phase passes.

### Rationale

This makes progress auditable, keeps the scope controlled, and provides a
working checkpoint at every major milestone.

### Consequences

- Delivery takes more explicit verification work.
- Production features are intentionally delayed.
- `PROJECT_STATUS.md` must be updated at every phase boundary.

### Reversal or Migration

A later decision may merge phases only after evidence shows that their gates
remain independently verifiable.

## ADR-0002 — Use Chinook SQLite for the MVP and PostgreSQL for the Final Runtime

- Date: 2026-07-19
- Status: Accepted

### Context

The MVP needs a small relational dataset that supports joins, aggregation,
ranking, and time analysis without requiring database infrastructure. The final
portfolio needs enforceable roles, transactions, timeouts, migrations, and
separate metadata storage.

### Options Considered

1. PostgreSQL from the first implementation phase.
2. SQLite for the entire project.
3. SQLite for Tahap 2–7, followed by PostgreSQL in Tahap 8.

### Decision

Use the official Chinook SQLite artifact for the MVP and migrate the reproducible
data setup to Chinook PostgreSQL in Tahap 8.

### Rationale

SQLite lowers early setup complexity. PostgreSQL later supplies the privilege
and operational controls required by the final architecture.

### Consequences

- SQL dialect differences must be explicit.
- Security tests must not treat SQLite read-only mode as the final security
  boundary.
- Evaluation cases should avoid accidental dialect coupling where practical.

### Reversal or Migration

If SQLite blocks required deterministic behavior, PostgreSQL may be introduced
earlier through a superseding ADR and an updated phase plan.

## ADR-0003 — Pin Chinook to a Verifiable Release

- Date: 2026-07-19
- Status: Accepted

### Context

Downloading from a moving branch makes the dataset non-reproducible.

### Options Considered

1. Download from the repository `master` branch.
2. Download a pinned official release artifact.
3. Commit an unverified database binary directly.

### Decision

Use an official pinned release asset. The initial target is Chinook `v1.4.5`,
release commit `4a944a9`, subject to asset verification during Tahap 2. Record
the exact URL and SHA-256 checksum after download.

### Rationale

The official repository identifies `v1.4.5` as its latest published release at
the Tahap 0 verification date and recommends downloading database scripts from
release assets.

### Consequences

- Dataset updates require an explicit decision and evaluation rerun.
- Tahap 2 must fail closed if the downloaded checksum does not match the pinned
  checksum stored by the project.

### Reversal or Migration

Create a new dataset-version decision and preserve the earlier evaluation
baseline.

## ADR-0004 — Keep LLM Integration Provider-Agnostic and Tests Offline

- Date: 2026-07-19
- Status: Accepted

### Context

Provider APIs, models, costs, and data policies can change. Unit and integration
tests must be deterministic and runnable without credentials or network access.

### Options Considered

1. Couple domain services directly to one provider SDK.
2. Use a provider adapter with a mandatory real API.
3. Use a provider-neutral interface with a mandatory fake adapter and optional
   real adapters.

### Decision

Create a provider-neutral LLM interface. `FakeLLMAdapter` is the default for
tests and the limited local demonstration. A real provider adapter is optional
and requires explicit credential setup.

### Rationale

This protects tests from network and provider instability and prevents an API
key from becoming a prerequisite for basic development.

### Consequences

- Provider-specific features stay behind the adapter boundary.
- Real-provider evaluation is a separate, explicitly marked workflow.

### Reversal or Migration

Add or replace adapters without changing the orchestration domain contract.

## ADR-0005 — Treat All LLM-Generated SQL as Untrusted

- Date: 2026-07-19
- Status: Accepted

### Context

Prompt instructions cannot enforce database security. Generated SQL may contain
unsafe operations, hallucinated schema references, expensive queries, or
attempted policy bypasses.

### Options Considered

1. Trust the system prompt.
2. Block unsafe words with regular expressions.
3. Validate the full SQL AST and enforce database least privilege.

### Decision

Fail closed. No generated or repaired SQL may execute unless it passes complete
AST validation, allowlists, function policy, statement-count checks, resource
limits, and database read-only controls.

### Rationale

Security must be enforced by deterministic code and database privileges, not by
probabilistic model behavior.

### Consequences

- Tahap 4 is a deployment blocker.
- Known destructive cases must achieve a 100% blocking rate.
- False blocking must also be measured.

### Reversal or Migration

This invariant cannot be weakened without a new threat model, independent
security review, and explicit user approval.

## ADR-0006 — Separate Generated SQL, Executed SQL, and Answer Grounding

- Date: 2026-07-19
- Status: Accepted

### Context

The validator may safely rewrite a query, for example by adding a row limit.
Users and evaluators need to know what the model proposed and what the database
actually executed. Numeric claims must originate from execution results.

### Decision

Store and present generated SQL and executed SQL separately. Build explanations
only from normalized query results and never from model predictions made before
execution.

### Consequences

- Audit data can reconstruct each attempt.
- Result summarization requires numeric consistency checks.

## ADR-0007 — Minimize Data Retention by Default

- Date: 2026-07-19
- Status: Accepted

### Context

Questions, SQL literals, query results, and logs may contain sensitive data when
the project later connects to real databases.

### Decision

Do not store raw result rows by default. Store operational metadata, sanitized
errors, version identifiers, SQL fingerprints, and feedback. Raw questions and
SQL storage must be configurable and documented.

### Consequences

- Some debugging detail is unavailable unless explicitly enabled in a safe
  environment.
- Retention and deletion policy must be documented before production use.

## ADR-0008 — Support Python 3.11 and 3.12

- Date: 2026-07-19
- Status: Accepted

### Context

The blueprint proposed Python 3.11. The inspected Windows environment currently
provides Python 3.12.10 and no Python 3.11 installation.

### Options Considered

1. Require Python 3.11 and block local work.
2. Use only the locally installed Python 3.12.
3. Define project compatibility as Python 3.11–3.12 and test both in CI.

### Decision

Target `>=3.11,<3.13`. Use Python 3.12 locally and test 3.11 and 3.12 in CI when
the CI phase is implemented.

### Consequences

- Dependencies must support both versions.
- Version-specific behavior requires tests or explicit constraints.

## ADR-0009 — Keep Frontend, Domain Services, and Providers Separated

- Date: 2026-07-19
- Status: Accepted

### Context

The MVP begins with Streamlit and SQLite, while the final architecture introduces
FastAPI and PostgreSQL. Tight coupling would make that transition expensive.

### Decision

Streamlit may call services directly during the earliest MVP only through stable
interfaces. Domain services must not import UI modules or provider SDK details.
In Tahap 8, Streamlit will access analytics through the FastAPI client.

### Consequences

- More interfaces are designed early.
- UI, provider, and database migrations remain independently testable.

## ADR-0010 — Use uv Locking with a pip-Compatible Fallback

- Date: 2026-07-19
- Status: Accepted

### Context

The local environment provides `uv`, while new contributors may have only the
standard Python `venv` and `pip` tools. The project needs both reproducibility
and a low-friction fallback.

### Decision

Track `uv.lock` as the preferred environment lock and document
`uv sync --extra dev`. Also maintain `requirements.txt` and
`requirements-dev.txt` as editable-install entry points for standard `pip`.

### Consequences

- Dependency changes must update `pyproject.toml` and `uv.lock` together.
- The pip fallback resolves the exact direct versions declared in
  `pyproject.toml`, while `uv.lock` also pins transitive dependencies.

## ADR-0011 — Use Ruff, Mypy Strict, Pytest, and a 90% Coverage Gate

- Date: 2026-07-19
- Status: Accepted

### Context

Tahap 1 requires automated format, lint, type, test, and coverage evidence that
can later run in CI.

### Decision

Use Ruff for formatting and linting, Mypy in strict mode for static typing, and
Pytest with branch coverage. Require at least 90% coverage while giving extra
attention to security-critical paths. Expose the checks through the
cross-platform `scripts/dev.py` wrapper.

### Consequences

- Public interfaces need complete annotations.
- Verification stops on the first failing command.
- Coverage is a quality signal, not proof that behavior is correct or secure.

## ADR-0012 — Use Standard-Library JSON Logging with Explicit Redaction

- Date: 2026-07-19
- Status: Accepted

### Context

The foundation needs structured logs but does not yet need a logging framework
or telemetry vendor. Logs must avoid common credential shapes.

### Decision

Use Python's standard `logging` package with a JSON formatter, recursive
field-name redaction, and common unstructured credential-pattern redaction.
Configuration is explicit and never happens as an import side effect.

### Consequences

- Logging has no additional runtime dependency.
- Redaction remains defense in depth; callers must still avoid logging sensitive
  values.
- Telemetry exporters can be introduced later without changing domain services.

## ADR-0013 — Preserve a Byte-Identical Chinook Runtime Copy

- Date: 2026-07-19
- Status: Accepted

### Context

The upstream release already supplies a complete SQLite database. Rebuilding it
from an evolving script or mutating the downloaded file would create avoidable
content drift.

### Decision

Pin the official Chinook v1.4.5 SQLite asset by exact byte size and SHA-256.
Keep the raw download unchanged and initialize the runtime database as an
atomically replaced, byte-identical copy. Verify SQLite integrity, the exact
table set, and deterministic row counts before accepting either file.

### Consequences

- Setup is repeatable and fails closed on drift or corruption.
- Raw and runtime binaries remain ignored because they can be reproduced.
- The checksum manifest, upstream license, and derivative metadata are tracked.

## ADR-0014 — Layer SQLite Read-Only Controls and Bound Manual Queries

- Date: 2026-07-19
- Status: Accepted

### Context

SQLite has no server roles, but the MVP still needs a deterministic database
boundary before the later PostgreSQL migration.

### Decision

Open the analytics file through SQLite URI `mode=ro`, set
`PRAGMA query_only=ON` on every connection, use no persistent connection pool,
and bound manual results by row count, column count, response bytes, and query
length. Surface sanitized domain errors. The manual executor is not authorized
to execute LLM output.

### Consequences

- Direct writes fail even when manual SQL reaches the driver.
- The original raw artifact is never opened by application query services.
- These controls are defense in depth, not a replacement for the PostgreSQL
  read-only role and AST validator required later.

## ADR-0015 — Content-Address Schema Metadata and Derive the Allowlist

- Date: 2026-07-19
- Status: Accepted

### Context

Later prompting and SQL validation need one auditable definition of the exact
tables, columns, primary keys, foreign keys, and views available to analytics.

### Decision

Normalize SQLAlchemy inspection into a stable JSON snapshot, hash its canonical
content, and derive the initial table/column allowlist from that same snapshot.
Track both files and require integration tests to compare them with the runtime
database.

### Consequences

- Schema drift becomes detectable before text-to-SQL execution.
- Prompt context and the future security validator can share one schema source.
- Dataset upgrades require a new snapshot, hash, allowlist, and evaluation run.

## ADR-0016 — Keep Tahap 3 Generation Provider-Neutral and Non-Executing

- Date: 2026-07-19
- Status: Accepted

### Context

Tahap 3 must prove structured text-to-SQL mechanics without making credentials,
network access, provider behavior, or the unfinished SQL security layer a test
dependency.

### Decision

Define a small asynchronous `BaseLLMAdapter`, strict provider-neutral request
and response models, a deterministic `FakeLLMAdapter`, and a factory whose safe
default is `fake`. Prompt construction, raw-output parsing, schema declaration
checks, and orchestration remain outside provider implementations. Normal
analysis responses stop at `generated_pending_security` with no executed SQL or
database result.

### Consequences

- Unit and integration tests require no provider SDK, secret, or network.
- Invalid JSON, timeouts, provider errors, and unknown schema declarations map
  to sanitized stable errors.
- A real adapter remains an optional explicit integration after provider,
  model, credentials, cost, and data policy are selected.
- Tahap 4 remains a hard prerequisite for free-form generated SQL execution.

## ADR-0017 — Use Exact-Match Trusted SQL for the Closed Tahap 3 Demo

- Date: 2026-07-19
- Status: Accepted

### Context

The phase gate asks for 20 database-backed mini-cases and a result table, while
the architecture invariant forbids unvalidated LLM SQL from crossing the
database boundary before Tahap 4.

### Decision

Create a closed catalog of 20 exact questions. The fake response must match the
case's SQL, declared tables, and declared columns exactly. The executor then
receives the trusted SQL constant stored in the case rather than the adapter's
output string. Columns and normalized rows must match a pinned SHA-256 result
identity. Unknown questions or any mismatch remain unexecuted or fail closed.

### Consequences

- The demo can show real database values without weakening the execution
  invariant.
- The mini-set proves pipeline mechanics, not real-model generalization.
- Cases are excluded from prompt examples to reduce evaluation leakage.
- This narrow mechanism must not be generalized into a substitute for AST
  parsing, recursive validation, rewriting, and allowlist enforcement.

## ADR-0018 — Use SQLGlot as a Fail-Closed SQLite AST Boundary

- Date: 2026-07-19
- Status: Accepted

### Context

Generated SQL is hostile input. Keyword matching cannot reliably detect nested
write operations, multiple statements, quoted identifiers, comments, set
operations, or dangerous functions.

### Decision

Pin SQLGlot 30.12.0, parse the complete SQL with the explicit `sqlite` dialect,
require exactly one root `Query`, and recursively reject forbidden nodes. Any
parse, qualification, dialect, or policy uncertainty fails closed and produces
stable safe reason codes without executable SQL.

### Consequences

- Model output cannot reach execution merely because it resembles `SELECT`.
- Parser upgrades are security-sensitive and require the complete corpus to be
  rerun.
- The SQLite policy cannot be reused for PostgreSQL without an explicit dialect
  and policy review.

## ADR-0019 — Derive Sources from AST and Qualify on a Copy

- Date: 2026-07-19
- Status: Accepted

### Context

LLM-declared tables and columns are untrusted. SQLGlot qualification is useful
for ambiguity and column validation, but an optimizer must not silently rewrite
the tree that will be executed.

### Decision

Derive physical tables and columns from SQL scopes, compare them with declared
metadata, and run schema qualification on an AST copy. Apply a reviewed
deny-by-default function allowlist, explicit catalog/schema policies, structural
budgets, literal-redacted fingerprints, and a deterministic outer limit rewrite
to the original validated tree copy.

### Consequences

- Declared metadata cannot hide different SQL sources.
- Validation rewrites cannot change execution semantics except for the explicit
  bounded outer `LIMIT`.
- The conservative function list may initially false-block legitimate future
  use and must be expanded only with tests and review.

## ADR-0020 — Restrict Repair and Audit Without Raw SQL Retention

- Date: 2026-07-19
- Status: Accepted

### Context

Repair can become a policy bypass if security failures are returned to a model
or repaired SQL skips validation. Raw SQL and result logging also creates an
unnecessary privacy and disclosure risk.

### Decision

Allow at most two repair attempts by default and only for syntax or
schema-resolution failures. Never repair security violations. Give callbacks
only stable reason codes and pass every candidate through the complete policy.
Audit the request ID, decision, fingerprint, derived tables, violation codes,
and limit action without raw question text, SQL text, or result rows.

### Consequences

- Repair cannot downgrade or bypass the policy layer.
- Operational audits retain decision evidence while minimizing sensitive data.
- The deterministic fake runtime keeps repair disabled because its versioned
  responses should already satisfy the contract.

## ADR-0021 — Use Strict Schema-Bound YAML for the Semantic Layer

- Date: 2026-07-19
- Status: Accepted

### Context

Business terms, metrics, and joins must be reviewable outside Python while
remaining deterministic and safe. Free-form prompt text would hide drift and
could refer to schema objects that do not exist.

### Decision

Track `glossary.yaml`, `metrics.yaml`, `joins.yaml`, and
`verified_queries.yaml` under `semantic/`. Parse with safe YAML loading into
strict extra-forbidden models. Require one semantic version, the active schema
hash, valid table/column/expression references, real foreign-key-backed approved
joins, valid cross-references, and SQL-policy-valid examples. Compute a canonical
content hash across all four artifacts.

### Consequences

- Semantic drift is visible and independently reproducible.
- Invalid configuration stops startup/evaluation rather than degrading silently.
- Schema or semantic changes require validation and regression evaluation.
- The current `project_verified` definitions still require domain-analyst review
  before use for consequential business reporting.

## ADR-0022 — Resolve Known Ambiguity Deterministically Before the LLM

- Date: 2026-07-19
- Status: Accepted

### Context

Terms such as “best customer,” “active customer,” and “largest sales” have
multiple defensible meanings. Letting a model choose silently creates plausible
but unauditable answers.

### Decision

Match versioned bilingual phrases and resolution phrases before prompt
generation. When a recognized ambiguity remains unresolved, return a localized
question with explicit options and stop before LLM/SQL. Define no default. When
the question states a choice, map it to canonical metric IDs and expose the
corresponding assumption and semantic provenance.

### Consequences

- Ambiguous questions require one extra user interaction.
- Clear and explicitly resolved questions continue without unnecessary prompts.
- Deterministic phrase matching is auditable but does not cover every linguistic
  paraphrase; broader intent resolution requires a separately evaluated design.
- Durable multi-turn clarification persistence remains a later-phase concern.

## ADR-0023 — Gate and Bound Verified-Query Retrieval

- Date: 2026-07-19
- Status: Accepted

### Context

Reviewed queries can improve generation consistency, but draft, irrelevant, or
evaluation-leaking examples can mislead a model and enlarge the prompt.

### Decision

Retrieve only `valid`, non-draft examples whose terms or metrics are relevant to
the question. Rank deterministically, apply a relevance threshold, and cap the
result at the configured maximum (three by default). Keep verified examples
separate from evaluation fixtures, and route every generated query through the
normal structured-output and SQL-security pipeline.

### Consequences

- Prompt size and example provenance remain bounded and inspectable.
- Retrieval is reproducible without embeddings or network access.
- Verified examples cannot authorize execution or bypass validation.
- Embedding-based retrieval may be reconsidered only after measured failures on
  a broader real-language corpus.

## ADR-0024 — Preserve Raw Results and Ground Summaries in Cells

- Date: 2026-07-20
- Status: Accepted

### Context

Formatting and natural-language summaries can silently change numeric meaning
or detach claims from database evidence.

### Decision

Keep immutable raw rows alongside separate display rows. Require every numeric
summary to reference an exact returned column, row index, raw value, and display
value. Do not infer a currency symbol when the dataset has no currency code.

### Consequences

- UI formatting cannot become the canonical analytical value.
- Numeric claims are testable against database cells.
- Explanations remain deliberately narrow and descriptive.

## ADR-0025 — Select Charts Deterministically from Returned Columns

- Date: 2026-07-20
- Status: Accepted

### Context

Model-selected visualizations can reference nonexistent fields, misuse IDs as
measures, or overstate sparse and high-cardinality results.

### Decision

Choose KPI, line, bar, scatter, or table with deterministic shape and type
rules. Validate temporal values, exclude identifiers from continuous axes, cap
categorical density, and restrict every chart field to the result contract.

### Consequences

- Chart selection is reproducible and independently testable.
- Some valid results intentionally fall back to a table.
- Visual semantics do not depend on an LLM.

## ADR-0026 — Bound Result History, Feedback, and Export

- Date: 2026-07-20
- Status: Accepted

### Context

Convenience features can create a second data-retention channel or expose users
to spreadsheet formula execution and secret-bearing diagnostic output.

### Decision

Use bounded process-local history with safe metadata only, fixed-category
feedback, byte-bounded CSV with formula-prefix neutralization, schema-only
exploration, and an explicit System Info allowlist.

### Consequences

- Raw questions, SQL, result rows, secrets, and URLs are excluded by default.
- History and feedback are not durable across restarts.
- Durable production metadata requires a later authenticated design.

## ADR-0027 — Use Strict JSONL with Explicit Development and Holdout Labels

- Date: 2026-07-20
- Status: Accepted

### Context

Tahap 7 requires 100 versioned cases with a fixed category distribution, while
the current provider remains deterministic and offline. Evaluation cases must
not become prompt examples or be mistaken for real-model generalization proof.

### Decision

Track `data/evaluation/stage-7-v1.jsonl` as the canonical formal corpus. Validate
every row through an extra-forbidden schema, enforce unique IDs/questions and
the exact 100-case distribution, hash the source bytes, and label 70 cases as
development and 30 as holdout. Never insert these cases into verified-query
retrieval. The fake-provider run is explicitly marked as not being a formal
real-model quality evaluation.

### Consequences

- The corpus is reviewable, portable, content-addressed, and reproducible.
- Holdout labels prepare a later opt-in provider evaluation but do not create a
  generalization claim for the exact-map fake adapter.
- Dataset changes require a new version, baseline, and provenance comparison.

### Reversal or Migration

A new dataset version may change cases or split policy while preserving this
baseline for historical comparison.

## ADR-0028 — Compare Executed Results and Fail Closed on Security Regression

- Date: 2026-07-20
- Status: Accepted

### Context

Equivalent SQL can differ syntactically. Exact SQL comparison would reject
valid alternatives, while permissive result normalization could hide NULL,
ordering, type, or numeric errors. Security must not degrade behind an aggregate
quality score.

### Decision

Compare columns and executed rows with per-case order sensitivity and numeric
tolerance, explicit NULL/empty handling, and conservative non-numeric type
identity. Record full version provenance. Require 100% known-unsafe blocking and
permit no decrease in execution accuracy, valid-SQL rate, or clarification
accuracy, and no increase in false blocking. Treat a P95 latency increase over
50% as a reported non-security warning rather than a release gate.

### Consequences

- Semantically equivalent result sets can pass without exact SQL identity.
- Any known security decrease fails even when aggregate pass rate remains high.
- Token, cost, and repair-success rates remain nullable when the offline run has
  no provider usage or repair attempts.

### Reversal or Migration

Thresholds may be revised through a superseding ADR with measured evidence.
The mandatory 100% known-unsafe gate cannot be lowered without explicit
security review and user approval.

## ADR-0029 — Preserve the Logical Contract Behind PostgreSQL Views

- Date: 2026-07-20
- Status: Accepted

### Context

The existing semantic and evaluation contracts use the reviewed Chinook
logical names, while the official PostgreSQL script has database-level commands
and PostgreSQL name-folding behavior that should not leak into every layer.

### Decision

Pin the official v1.4.5 PostgreSQL script by size and checksum, load its tables
into owner-only `chinook_data`, and expose only compatible views in `analytics`.
Keep business definitions single-sourced and use a schema-bound dialect overlay
only for PostgreSQL-specific verified SQL.

### Consequences

- Existing business grain, joins, evaluations, and provenance remain stable.
- The application role cannot select physical owner tables.
- Any source, view, snapshot, or overlay change requires semantic validation and
  regression evidence.

## ADR-0030 — Separate Analytics, Metadata, Migration, and API Boundaries

- Date: 2026-07-20
- Status: Accepted

### Context

One credential or database would make write-capable metadata work a privilege
escalation path into analytics. Direct Streamlit database access would also
spread credentials into the browser-facing process.

### Decision

Use separate `chinook` and `analyst_metadata` databases and exact
`analytics_owner`, `analytics_readonly`, `app_metadata_user`, and
`migration_user` roles. FastAPI owns both server-side engines, rejects an
unexpected or privileged identity, and exposes versioned contracts to a
credential-free Streamlit API client. Alembic owns the ten privacy-minimized
metadata models.

### Consequences

- Analytics execution is transaction-read-only and independently constrained
  by grants.
- Schema migration privileges are absent from the application runtime.
- Actual PostgreSQL role rejection and migration behavior remain mandatory
  integration gates; static configuration alone cannot complete Tahap 8.

## ADR-0031 — Package the Runtime as Pinned Non-Root Images

- Date: 2026-07-21
- Status: Accepted

### Context

Tahap 9 needs a reproducible whole stack without copying local environments,
raw assets, reports, or credentials into an image. Mutable base tags and root
runtime users weaken both reproducibility and containment.

### Decision

Use separate multi-stage API and frontend Dockerfiles with one immutable Python
base digest, a pinned uv builder, explicit allowlisted copies, health checks,
and UID/GID `10001:10001`. Compose supplies generated runtime credentials,
isolates PostgreSQL on an internal network, and uses a named development volume.
A no-cache smoke gate must inspect image identity/history and remove its own
stack and volume.

### Consequences

- Local builds are reproducible against an exact base manifest and lockfile.
- Runtime filesystem writes are limited to explicitly mounted temporary paths.
- Base, Python, and scanner pins require deliberate Dependabot/reviewed updates.

## ADR-0032 — Use Immutable Least-Privilege Delivery Workflows

- Date: 2026-07-21
- Status: Accepted

### Context

CI must exercise quality, PostgreSQL integration, security, evaluation, and
Docker readiness without exposing credentials to fork pull requests or relying
on mutable third-party action tags.

### Decision

Split quality/integration, security, evaluation, and Docker smoke into four
workflows. Default to `contents: read`, grant only CodeQL's job the required
`security-events: write`, disable persisted checkout credentials, pin every
action by full commit SHA, and reference no repository secret. Publish only
privacy-minimized artifacts. Do not push images until a registry and authorized
tag/release policy are configured.

### Consequences

- Fork-triggered work can run without receiving a repository credential.
- Workflow pins are auditable but require explicit upgrades.
- GitHub-hosted execution evidence cannot exist before Tahap 10 publication;
  equivalent commands and workflow contracts are verified locally meanwhile.

## ADR-0033 — Correlate Requests Without Retaining Payloads

- Date: 2026-07-21
- Status: Accepted

### Context

Operational diagnosis requires an end-to-end trace and measurable outcomes,
but raw questions, SQL, result rows, headers, URLs, and credentials would create
a sensitive secondary data store.

### Decision

Accept only canonical UUID request IDs or generate a replacement, propagate the
ID through frontend, API context, orchestration, security, and execution, and
emit the required structured fields with a literal-redacted SQL fingerprint.
Expose protected in-process counters and rates for request, outcomes, timeout,
repair, latency, and nullable provider usage. Retain no analytics payload.

### Consequences

- One request can be diagnosed across components without logging its content.
- Fake-provider token usage remains explicitly unavailable rather than zero.
- Metrics reset with the process; durable monitoring is a Tahap 10 deployment
  decision.

## ADR-0034 — Separate Local Release Readiness from External Publication

- Date: 2026-07-21
- Status: Accepted

### Context

Tahap 10 combines reproducibility, documentation, GitHub publication, and an
optional deployment, but license, account ownership, visibility, cost, and
authentication are user-owned external decisions. Treating missing authority as
a technical pass would make the release status misleading.

### Decision

Maintain two explicit states. The local release gate covers commands, tests,
evaluation, PostgreSQL, Compose, security, clean checkout, documentation,
links, and screenshots. The full stage gate additionally requires an approved
project license, verifiable GitHub remote and hosted Actions, and deployment
evidence only when a public demo is selected. Never create paid/public
resources or infer license and visibility.

### Consequences

- The portfolio can be audited locally without claiming a public release.
- External blockers remain machine-readable and visible in project status.
- Publication or deployment requires a fresh decision and post-action smoke
  evidence.

## Deferred Decisions

| ID | Decision | Required by | Reason for deferral |
|---|---|---|---|
| DD-001 | Real LLM provider and model | Real-provider evaluation | Costs, capabilities, and data policy must be checked at implementation time. |
| DD-002 | Public project license | Resolved 2026-07-21 | MIT selected by the owner. |
| DD-003 | Deployment platform | Tahap 10 | Availability and pricing are time-sensitive. |
| DD-004 | Authentication provider | Public production-like demo | Not required for the local portfolio MVP. |
| DD-005 | Cloud secret manager | Deployment | Depends on the selected platform. |
