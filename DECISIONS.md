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

## ADR-0035 — Use Hosted Gemma 4 for the First Real-Provider Baseline

- Date: 2026-08-07
- Status: Accepted

### Context

The deterministic fake provider proves pipeline and security mechanics but not
real-model generalization. The first live candidate must support strict
structured output, later client-defined tool calls, pinned evaluation, bounded
cost, and an acceptable data policy without changing the SQL trust boundary.
Current official documentation and the project-specific comparison are recorded
in `docs/llm-provider-decision.md`.

### Decision

Use Google Gemini Developer API with hosted model `gemma-4-26b-a4b-it` through
`models.generateContent` for the first real-provider baseline. Start with
thinking level `minimal`, JSON Schema output, `store: false`, and an output cap
of 4,096 tokens. Allow only synthetic Chinook questions and bounded
schema/semantic context, keep automatic provider fallback disabled, and
preserve `FakeLLMAdapter` as the offline default.

The owner explicitly selected Google Gemini and Gemma 4, replacing the earlier
unaccepted OpenAI proposal. Current official pricing lists hosted Gemma 4 as
free-only, so the paid budget is USD 0. Free-tier content may be used to improve
Google products; therefore non-public or sensitive data remains prohibited.

### Consequences

- Hosted Gemma 4 can be tested without authorizing a paid resource.
- `gemma-4-26b-a4b-it` is the explicit evaluation identifier; the 31B variant
  requires a separate recorded comparison before use.
- Real SQL/Bahasa Indonesia quality remains an evaluation question, not an
  assumption.
- Provider errors fail safely instead of silently changing provider or data
  policy.
- A separate review is required before sending non-synthetic or sensitive data.
- A key pasted into chat on the decision date is treated as compromised and
  must be rotated before any live smoke test.

The first replacement enabled one successful synthetic structured smoke on
2026-08-07. A subsequent point 3 audit found a credential-like value in the
tracked Compose example. The value was removed immediately and a regression
test was added. A second rotation was verified on 2026-08-08: zero exact matches
exist in tracked files and one bounded live smoke passed.

## ADR-0036 - Gate Real-Model Holdout on a Frozen Development Candidate

- Date: 2026-08-08
- Status: Accepted

### Context

The fake Stage 7 baseline proves deterministic mechanics but not model
generalization. A live evaluation can leak holdout information, drift source or
prompt configuration during a long run, exceed free-tier quotas, or create a
misleading comparison if development failures are ignored.

### Decision

Run the immutable `stage-7-v1` corpus as isolated development and holdout
splits. Require explicit live confirmation, exact provider-call caps, USD 0 paid
spend, temperature 0, no automatic retry, privacy-minimized checkpoints and
reports, and a hash of evaluator source. Freeze provider, model, prompt,
semantic/schema identity, output limit, thresholds, and the passing development
report hash before any holdout call. Reject holdout when development fails.

The initial `gemma-4-26b-a4b-it` v3 development calibration failed: 50%
structured-output validity and 25% execution accuracy versus required 99% and
85%. Therefore no candidate was frozen and no holdout request was made.

### Consequences

- Point 5 is blocked rather than reported as a successful baseline.
- The fake 100/100 baseline remains separate and is not presented as an
  equivalent model-quality comparison.
- Unblocking requires an owner-approved alternate model or a new versioned
  protocol with explicitly revised thresholds/retry budget.
- Points 6-7 cannot depend on this model as a qualified baseline yet.

## ADR-0037 - Reject Gemma 4 31B at the Formal Development Gate

- Date: 2026-08-08
- Status: Accepted

### Context

After the 26B candidate failed development calibration, the owner authorized
the recommended `gemma-4-31b-it` candidate. The frozen quality/security
thresholds, USD 0 paid budget, no-retry rule, development/holdout isolation, and
read-only execution boundary were left unchanged. Eight development-only
calibration requests produced prompt v4 before the complete development run.

### Decision

Do not promote or freeze the `gemma-4-31b-it` / prompt-v4 candidate. Its formal
development run used 68 provider requests across 70 cases and achieved 97.06%
structured-output validity and 29.51% execution accuracy, below the required
99% and 85%. It did achieve 100% clarification accuracy, zero schema
hallucinations, and 100% known-unsafe protection with zero security bypasses,
but passing security metrics do not override the failed quality gate.

Keep holdout sealed, preserve both model results, and require a new versioned
candidate/protocol before another formal attempt. Do not reduce thresholds or
change the holdout contract implicitly.

### Consequences

- Point 5 remains `Terblokir`; this is a documented failed evaluation, not a
  qualified real-model baseline.
- No 31B candidate manifest is frozen and holdout provider calls remain zero.
- Points 6-7 cannot claim this candidate is evaluated and ready.
- The next owner decision should choose a stronger model or explicitly approve
  a development-derived output-contract/evaluation-protocol revision.
- The deterministic fake provider remains the offline regression default.

## ADR-0038 - Version Semantic Result Equivalence Without Weakening Correctness

- Date: 2026-08-08
- Status: Accepted

### Context

The failed 31B development report classified 29 cases as column differences.
The strict-v1 comparator required exact column names and order even when the
executed relation could be presentation-equivalent. However, loosening result
comparison can conceal mislabeled values, missing dimensions, or wrong business
answers. The privacy-safe report deliberately retained neither SQL nor result
rows, so the old evidence cannot be reliably rescored.

### Decision

Keep `strict-v1` for legacy reproducibility and add an explicit
`semantic-v2` policy for future runs. Semantic-v2 requires identical column and
row counts. It accepts normalized case/spacing/punctuation and column order, or
an otherwise unique one-to-one alignment proven by returned values. Shared
normalized names are locked to prevent misleading remapping. It preserves
numeric tolerance, NULL/type rules, and the corpus `order_sensitive` flag.

Fail closed on extra/missing columns, ambiguous mappings, changed values or row
counts, inconsistent result shapes, and required-order changes. Record the
policy in checkpoint identity, evaluator provenance, candidate manifests,
holdout validation, and summaries. Keep all frozen quality/security thresholds
unchanged and do not retrospectively alter the failed v2 report.

### Consequences

- The deterministic development-only audit must pass before any new live run.
- A candidate cannot mix comparison policies between development and holdout.
- The audit proves comparator invariants, not model quality; a fresh provider
  run remains necessary to measure execution accuracy.
- Old checkpoints cannot be resumed under semantic-v2.
- Holdout remains sealed and points 6-7 remain blocked until a complete
  semantic-v2 development run passes and is frozen.

## ADR-0039 - Reject the 31B Semantic-v2 Development Candidate

- Date: 2026-08-08
- Status: Accepted

### Context

After ADR-0038's deterministic comparator audit passed, the owner authorized a
fresh 68-request development run of `gemma-4-31b-it`, prompt v4, and
`semantic-v2`. The frozen quality/security thresholds, USD 0 paid budget,
no-retry rule, immutable development corpus, and holdout isolation remained
unchanged.

### Decision

Do not promote or freeze this candidate. Across 70 development cases, 37
passed. Semantic-v2 accepted 10 presentation-equivalent results and observed
execution accuracy reached 28/61 (45.90%), but the required threshold is 85%.
Structured-output validity remained 66/68 (97.06%) against the required 99%.

Clarification accuracy was 2/2, schema hallucination was 0/61, known-unsafe
protection was 7/7, and no security bypass occurred. These passing safety
metrics do not override the failed quality gates. Keep the holdout sealed and
require an explicitly versioned new model, prompt, or bounded runtime candidate
before another formal attempt.

### Consequences

- Point 5 remains `Terblokir`; points 6-7 cannot claim this model is qualified.
- No candidate manifest is frozen and holdout cases scored remain zero.
- Semantic-v2 remains the audited comparator for future explicitly versioned
  runs; its 10 accepted presentation-equivalent cases do not justify further
  loosening.
- The next owner decision must select a new candidate while preserving the
  quality thresholds and holdout contract unless a separate protocol change is
  explicitly approved.
- The deterministic fake provider remains the offline regression default.

## ADR-0040 - Evaluate a Gemma-Only Plan-Compiled Runtime Candidate

- Date: 2026-08-08
- Status: Accepted

### Context

The `gemma-4-31b-it` prompt-v4 development run was safe but reached only
45.90% execution accuracy. The owner explicitly requested retaining Gemma,
implementing the recommended accuracy improvements, permitting new algorithms,
and excluding FakeLLM from the new runtime path.

### Decision

Introduce versioned runtime `v5-plan`. Gemma emits a strict AnalysisPlan rather
than SQL. Deterministic services ground identifiers, retrieve reviewed examples
with a hybrid lexical/metric/schema score, derive unique approved shortest join
paths, compile every SQL token, verify plan/SQL alignment, and pass the result
through the existing AST security and read-only execution boundaries. Permit at
most one repair using a sanitized plan error code. Meter every actual Gemini
call—including repair—at the adapter boundary.

Authorize protocol v4 development-only evaluation: a one-case compatibility
smoke capped at 2 requests, followed on success by a 12-case hard pilot capped
at 24 requests. Paid budget remains USD 0 and holdout authorization remains
zero.

### Consequences

- The new path cannot instantiate or fall back to FakeLLMAdapter.
- Existing fake behavior remains available for legacy offline regression.
- SQL security violations are terminal and never enter plan repair.
- Pilot improvement must be reported against the same-case 0/12 baseline and
  cannot qualify the formal candidate or unlock holdout by itself.
- The complete development split and unchanged thresholds remain mandatory
  before candidate freezing.
- Phase A11 proved the JSON-MIME/strict-local-contract design can complete plan
  validation, deterministic compilation, security validation, execution, and
  comparison in one provider request. It still failed the compatibility case
  because the result relation had too few columns.
- Phase A12 may adjust only general unrelated detail-shape guidance and
  privacy-safe column-count telemetry. The hard pilot remains closed until the
  compatibility case passes; holdout authorization remains zero.
- A12 improved the observed result from one to two of three columns but did not
  pass. A13 may add a narrow deterministic pre-compilation invariant for a
  bounded single-table list filtered by one non-primary ID. Incomplete plans
  use the existing sanitized one-repair path; the runtime must not synthesize
  or silently add projection columns.
- A13 proved the invariant fails closed, but its generic repair code did not
  correct the plan in one attempt. A14 may expose only the missing semantic role
  (primary identifier, display, or filtering identifier) to the repair prompt;
  physical identifiers remain confined to the existing schema context and are
  not added to reports.
- A14 passed the compatibility case with one bounded repair and exact 3/3
  result columns. This satisfies ADR-0040's prerequisite for the frozen
  12-case development hard pilot, but does not authorize holdout access,
  candidate freezing, or points 6-7.
- The frozen hard pilot v1 passed 2/12 versus its 0/12 same-case baseline and
  had zero hallucination/security bypass, but missed the 8/12 engineering
  target. Continue development-only work with deterministic alias and benchmark
  normalization; do not promote this result or open holdout.
- C1 removed alias/benchmark contract failures but both selected cases remained
  2/3-column mismatches. C2 may require bounded detail-output roles derived
  solely from schema metadata and explicit question mentions, using rejection
  plus one repair rather than runtime projection synthesis.
- C2 made two of four selected failures correct, but Gemma repeatedly omitted
  an unspoken base-table relationship ID. C3 may deterministically complete and
  canonically order only trusted base-detail roles from the schema snapshot.
  It must not synthesize related displays, filters, joins, aggregates, values,
  limits, ordering, or free-form SQL, and all existing validators remain
  mandatory.
- C3 made the benchmark Invoice case exact, while the filtered Invoice case
  retained one unnecessary non-ID filter column. C4 may prune only such a
  presentation field when it is neither explicitly named nor ordered; it must
  never remove or modify the underlying predicate.
- C4 passed the remaining filtered Invoice case exactly. Run hard pilot v2 on
  the exact frozen source and compare with both prior baselines. Subset success
  still cannot authorize holdout access or candidate freezing.
- Hard pilot v2 reached 6/12 with zero hallucination/bypass, materially above
  both prior baselines but below the 8/12 engineering target. Phase E may skip
  a related display when the question/filter explicitly asks for that entity's
  ID, and may complete grouped base identity/display dimensions for bounded
  aggregate rankings. Holdout remains sealed.
- Phase E passed both targeted cases with safe execution. Authorize only the
  same-case hard pilot v3 under the existing 24-call maximum; all formal and
  holdout boundaries remain unchanged.
- Hard pilot v3 met its engineering target at 8/12 and proved a same-case
  increase from 0% to 66.67%, with zero hallucination/bypass. Do not promote it:
  structured validity was 83.33% and execution accuracy 66.67%, below formal
  99%/85% gates. A max-136 complete development run requires a new explicit
  authorization; holdout and points 6-7 remain closed.

## ADR-0041 - Ground Unambiguous Metrics and Benchmark Shapes Deterministically

- Date: 2026-08-08
- Status: Accepted

### Context

Hard pilot v3 left four development failures: one transient provider error,
one bounded detail-grain/order mismatch, one invoice-line sales metric mismatch,
and one grouped-average benchmark contract failure. The owner authorized the
first correction stage while retaining Gemma, excluding FakeLLM from the live
`v5-plan` path, and preserving all quality/security thresholds.

### Decision

Keep the maximum of two actual provider requests per case and share the second
slot between one transient-provider retry and the existing single plan repair.
When semantic resolution selects exactly one `project_verified` metric and the
plan contains exactly one measure, bind that measure to the reviewed metric
while preserving its output alias. For questions without an explicit order,
derive stable project defaults: base primary ID ascending for bounded detail
lists, or measure descending plus dimensions ascending for non-time grouped
results. Resolve the bounded-list base grain from the first explicitly named
schema entity.

Normalize only structurally equivalent benchmark shapes: `values=null` becomes
empty only where literals are semantically forbidden, a singleton string
`group_by` list becomes its sole string, and a recognized average benchmark
with a validated grouping string becomes `group_average`. Other shapes fail
closed and may receive one sanitized role-specific repair instruction. Continue
to derive joins, compile SQL, validate alignment/AST policy, and execute through
the read-only boundary deterministically.

### Consequences

- The new provider retry does not increase the existing two-request-per-case
  cap and cannot bypass adapter-level metering.
- The live Stage-1 smoke passed `FLT-003`, `JON-003`, and `JON-011` at 3/4;
  the final benchmark correction then passed `SUB-004` exactly at 1/1.
- Each final passing outcome used one request. The failed `SUB-004` attempts in
  Phases G and H used four additional requests, so the correction cycle used 8
  total. No FakeLLM, schema hallucination, security bypass, paid cost, or
  holdout call occurred.
- These were targeted runs on successive source freezes. They do not prove a
  12/12 same-source hard-pilot result and do not qualify the formal candidate.
- Before the 136-request complete-development decision, rerun the same 12 hard
  development cases on the exact final Stage-1 source with a maximum of 24 requests.
  That rerun requires a separate owner authorization. Holdout and points 6-7
  remain closed.

## ADR-0042 - Reject Promotion After the Exact Final Stage-1 Hard Pilot

- Date: 2026-08-08
- Status: Accepted

### Context

The owner authorized the same 12 hard development cases on one exact final
Stage-1 source freeze with a maximum of 24 provider requests. This run tests
whether the four targeted corrections generalize together with the eight prior
passes; it is still a development subset and cannot qualify holdout by itself.

### Decision

Record the result as a measured improvement but do not freeze or promote the
candidate. The run passed 10/12 with 12/24 requests and no repair. Structured
plan validity, valid SQL, and read-only execution success were all 12/12, but
execution accuracy was 83.33%, below the unchanged 85% threshold. `RNK-004`
and `SUB-001` produced safe three-column results whose row values or required
ordering differed under `semantic-v2`.

Keep the maximum-136 complete development run, candidate freeze, holdout, and
points 6-7 closed until the owner authorizes the next bounded development
action. Do not lower the threshold or loosen semantic comparison to convert
the two substantive mismatches into passes.

### Consequences

- Same-case accuracy progressed 0/12 -> 2/12 -> 6/12 -> 8/12 -> 10/12 while
  provider requests fell to 12/24 and structured validity reached 100%.
- Source hash remained stable before and after the run; no source drift was
  detected.
- Schema hallucination, security bypass, measured paid cost, and holdout calls
  remained zero; these safety results do not override the failed quality gate.
- The next bounded work should analyze or correct `RNK-004` and `SUB-001`
  without accessing holdout or weakening the deterministic security boundary.

## ADR-0043 - Canonicalize Bounded Superlative and Benchmark Ordering

- Date: 2026-08-08
- Status: Accepted

### Context

The exact final Stage-1 hard pilot produced valid plans, valid SQL, successful
read-only execution, and the expected three-column relation for `RNK-004` and
`SUB-001`, but selected or ordered the wrong rows. Source inspection showed
that the Stage-1 fallback ordering did not recognize `longest` as explicit
ranking intent and replaced the natural ordering of a bounded above-average
detail query with primary-key ascending.

### Decision

For a bounded detail query with explicit superlative ranking, preserve the
grounded model order and append the projected base primary key ascending as a
deterministic tie-breaker. For a bounded detail query with exactly one global-
average comparison, derive the ordering from its projected comparison column:
descending for `>`/`>=`, ascending for `<`/`<=`, then projected base primary
key ascending.

Apply the policy only to grounded physical columns and typed benchmark
operators. Do not inspect evaluation case IDs, expected SQL, or expected rows;
do not alter metrics, filters, joins, limits, comparison rules, AST security,
or read-only execution.

### Consequences

- Offline regression passed 390 tests with four PostgreSQL skips and 90.26%
  coverage; 73 focused security/evaluator tests, Ruff, strict Mypy on 164
  files, and `git diff --check` passed.
- Phase K passed both corrected development cases exactly using 2/4 maximum
  provider requests and no repair. Source hash was stable, and hallucination,
  security bypass, measured paid cost, and holdout calls remained zero.
- The passing two-case smoke is staged evidence. The maximum-136 complete
  development run requires a separate owner authorization; candidate freeze,
  holdout, and points 6-7 remain closed.

## ADR-0044 - Reject v5-plan Promotion After Complete Development

- Date: 2026-08-08
- Status: Accepted

### Context

The owner authorized all remaining Point-5 steps, conditional on each frozen
gate. Phase L evaluated the complete 70-case development split on the formatted
Phase-K source using the Gemma-only `v5-plan` runtime, `semantic-v2`, and a hard
maximum of 136 provider requests.

### Decision

Reject candidate promotion and stop before holdout. Phase L passed 52/70 cases
using 74 requests. Structured validity was 64/68 (94.12%) against 99%,
execution accuracy was 44/61 (72.13%) against 85%, and known-unsafe blocking
was 6/7 (85.71%) against the mandatory 100%. These three failures are terminal
for this candidate under the pre-registered protocol.

Do not create a candidate manifest, calculate or run the holdout split, or
generate a combined development/holdout summary. Keep Point 5 blocked and
require any continuation to use a new explicitly versioned development-only
candidate without lowering thresholds or loosening `semantic-v2`.

### Consequences

- `v5-plan` materially improved execution accuracy from 45.90% to 72.13% and
  valid SQL/execution from 86.89% to 95.08% versus the prior complete
  prompt-v4/semantic-v2 run.
- Structured reliability regressed from 97.06% to 94.12%, and known-unsafe
  blocking regressed from 100% to 85.71%; the accuracy gains cannot override
  these failures.
- The missed unsafe case failed closed at strict plan validation and never
  compiled or executed SQL, so no security bypass occurred, but it still
  failed the required unsupported-classification contract.
- Clarification remained 2/2, schema hallucination and false blocking remained
  zero, measured paid cost was USD 0, and holdout calls remained zero.
- No candidate, holdout report, or combined summary exists. Points 6-7 remain
  closed because Point 5 has not qualified a real-model candidate.

## ADR-0045 - Keep Phase M Development-Only and Prepare a New Offline Candidate

- Date: 2026-08-08
- Status: Accepted

### Context

Phase L left 18 development failures. The owner authorized a new bounded
development candidate targeting those failures without opening holdout or
lowering the formal thresholds. Phase M froze source hash `084ca023...`, used
the Gemma-only `v5-plan` path, and reserved at most 36 provider requests.

### Decision

Do not promote Phase M. It improved the same-case result from 0/18 to 12/18
using 19 requests, with 17/18 structured outcomes and 17/17 valid SQL/read-only
executions, but it missed the pre-registered 15/18 diagnostic target and again
missed the required unsafe classification.

Permit offline implementation of generic corrections for the five remaining
explainable patterns: an implicit ordered-detail sample, a named direct-
relationship display pair, grouped foreign-key entity grain, an unnumbered
display ranking, and a provider unsupported marker. Do not encode the
`AGG-007` 20-row expectation without a separately approved product
cardinality policy. Runtime code must remain independent of case IDs, expected
SQL, expected columns, and expected rows.

### Consequences

- The new offline source hash is `126c6ecdbc146098...`; it passes 409 tests
  with four PostgreSQL skips and 90.10% coverage, Ruff/format, strict Mypy on
  164 files, and `git diff --check`.
- This new source has made zero provider calls. Phase-M evidence remains bound
  to its original hash and is not retroactively reinterpreted.
- A six-case Phase-N development rerun would have an exact maximum of 12
  requests and requires separate owner authorization.
- A local diagnostic accidentally exposed records outside development. No
  holdout call or scoring occurred, but `stage-7-v1` is disqualified as an
  unseen final holdout. A replacement must be independently curated and sealed
  without this agent inspecting it.
- No candidate is frozen; holdout, combined summary, and points 6-7 remain
  closed.

## ADR-0046 - Stop Phase N Before Candidate Promotion

- Date: 2026-08-16
- Status: Accepted

### Context

The owner authorized a six-case development-only Phase N after generic offline
corrections for five of the six remaining Phase-M failures. The source was
frozen at `126c6ecdbc146098...`; the run used Gemma 4 31B, prompt `v5-plan`,
`semantic-v2`, and a hard maximum of 12 provider requests. `AGG-007` was known
to encode a 20-row expectation without an approved product cardinality policy.

### Decision

Do not promote or retry Phase N in place. It passed 5/6 cases using 7 requests,
with 6/6 structured outcomes, 5/5 valid SQL/read-only executions, 4/5 execution
accuracy, and 1/1 unsafe blocking. `AGG-007` alone failed because the returned
safe relation had three columns while the expected relation has two; the
question itself does not establish the expected 20-row boundary.

Do not hard-code the case ID, expected columns, rows, or SQL. A continuation
requires an explicit product decision for the default cardinality and
projection of unbounded analytical lists, followed by a new versioned
development protocol and exact request authorization.

### Consequences

- Phase N missed its execution-accuracy gate at 80%. No candidate manifest,
  holdout report, holdout cap, or combined summary was created.
- Schema hallucination, false blocking, security bypass, measured paid cost,
  and holdout calls were zero. These safety results do not override the failed
  quality gate.
- The existing `stage-7-v1` holdout remains disqualified. Final promotion also
  requires an independently curated and sealed replacement that this agent
  does not inspect.
- Point 5 is `Terblokir`; points 6-7 remain closed.

## ADR-0047 - Build Bounded Agent Authority Independently of Model Promotion

- Date: 2026-08-16
- Status: Accepted

### Context

Point 5 remains blocked because Phase N failed its accuracy gate and no valid
holdout remains available. The owner explicitly directed implementation of
Points 6 and 7 despite that quality dependency. Tool authority and bounded-loop
behavior can be implemented and verified offline, but doing so must not imply
that Gemma is qualified for production analytical answers.

Clarification also needs to survive API process restarts without violating the
repository defaults that prohibit storage of raw question, SQL, prompts, and
result rows. Concurrent resume attempts must not execute twice.

### Decision

Implement `bounded-agent-v1` as a separate API path while preserving the
legacy `/api/v1/query` path. Use eight typed and versioned tools behind a static
registry and per-state allowlist. Treat every model proposal as untrusted. Only
the validator may issue a request-bound one-use capability containing the
rewritten executable SQL; `execute_validated_sql` accepts that handle and has
no SQL argument. Use a second one-use capability for result formatting.

Allow repair only when every violation code is in the established repairable
set. Run each proposed repair through `SQLRepairCoordinator` and the complete
AST policy. Security-policy violations transition to `BLOCKED` without a model
repair call.

Use deterministic state transitions and initial limits of eight tool steps,
two repairs, one tool call per step, one execution per validation handle, 30
active seconds, and two clarification rounds. Optional token and cost ceilings
stop the run before its next tool call.

Persist clarification continuation in the metadata database with an opaque ID,
question digest, canonical rule/option IDs, semantic version/hash, counters,
and expiry only. Require the client to re-submit the original question and
match its digest before canonical option resolution. Claim the row under a
database lock and delete it on success/cancel; never persist raw question, SQL,
prompt, rows, credentials, or internal exception text.

### Consequences

- Points 6 and 7 can be marked complete as architecture and offline regression
  work. Point 5 remains `Terblokir`; no candidate freeze, holdout result, or
  real-model qualification is inferred.
- The default policy remains hybrid: the configured model selects analytical
  versus unsupported intent and proposes SQL, while mandatory control actions
  remain deterministic. Alternate action policies remain subordinate to the
  same registry and state authority.
- Alembic revision `20260816_0002` is required before enabling agent routes on
  an existing metadata database.
- The complete local gate passed 447 tests with four unavailable PostgreSQL/
  Docker skips, 90.69% coverage, Ruff, strict Mypy, and diff-check. Hosted
  PostgreSQL/Docker/security evidence is still required on the published
  branch.

## ADR-0048 - Version Universal Group Semantics and Seal the Replacement Holdout

- Date: 2026-08-18
- Status: Accepted

### Context

Phase N failed only `AGG-007`. Its unbounded question did not justify the
reviewed 20-row expectation, and no product rule defined whether an unrequested
artist name belonged beside the requested artist ID. Hard-coding the case would
invalidate generalization evidence. Separately, the old `stage-7-v1` holdout
could no longer support an unseen-final-set claim.

### Decision

Treat universal grouped questions as complete group requests within the
existing 500-row execution ceiling. Remove model-invented limits unless the
user requested a quantity. For universal identifier-only grouping, return the
identifier and measure; retain a display field only when explicitly requested.
Apply this from question semantics and schema metadata, never an evaluation
case ID or expected result.

Preserve `stage-7-v1` as historical evidence and create development-only
`stage-7-development-v2`. Bind any future candidate to a public manifest for an
independently curated private `stage-7-holdout-vN`. The manifest commits payload
and attestation hashes, version, case count, and category counts. The holdout
contract requires 30 cases across all eight categories (5/5/5/3/3/3/3/3).
The runner must reject drift, partial data, mixed splits, or another
distribution before provider setup.

### Consequences

- `AGG-007` now has a principled 204-row, two-column development expectation;
  runtime source contains no case-specific branch.
- Private holdout JSONL and attestation text remain outside Git and unseen by
  the development agent before freeze. Independence still relies on the owner
  selecting a trustworthy curator; flags cannot prove human process.
- Thresholds remain unchanged, and Phase N is not reinterpreted or retried.
- Point 5 remains blocked. A separately authorized complete development run
  has an exact maximum of 136 provider requests. Candidate freeze and one-time
  holdout execution remain conditional on passing gates and a valid manifest.
- The authorized complete development run later passed 67/70 using 69/136
  requests with 95.08% execution accuracy and all frozen gates satisfied.
  Candidate freeze remains pending only because no independent manifest exists.

## ADR-0049 - Isolate Uploaded Databases as Ephemeral SQLite Workspaces

- Date: 2026-08-18
- Status: Accepted

### Context

The owner requested a UI that accepts a SQL/schema or database file, lets the
AI read its schema, and generates queries from natural-language prompts. The
existing final runtime is intentionally bound to reviewed Chinook PostgreSQL
and a separate metadata database. Executing an untrusted dump there, reusing
Chinook semantics, or exposing a client path would violate established trust
boundaries.

### Decision

Implement SQLite-first, process-local workspaces. Accept SQLite database files
and a restricted UTF-8 SQLite dump subset. Create a fresh server-owned
temporary database under an opaque random ID; never execute uploaded SQL
against, attach it to, or persist it in either PostgreSQL database.

For dumps, allow only `CREATE TABLE`, `CREATE INDEX`, literal
`INSERT ... VALUES`, and transaction markers. Reject views, triggers, virtual
tables, system/cross-schema objects, computed imports/indexes, and all other
statements. Bound input bytes, resulting database bytes, statements, import
time, tables, columns, active workspaces, query results, and lifetime. Verify
SQLite integrity and reopen every workspace with `mode=ro`, `query_only=ON`,
and `trusted_schema=OFF`.

Build an independent schema snapshot, allowlist, direct prompt-v4 generator,
SQL policy, and result pipeline per workspace. Do not load the Chinook semantic
bundle for arbitrary schemas. The fake provider remains deterministic and
therefore reports unsupported for arbitrary upload questions; open-ended use
requires the separately configured Gemini provider. Send only relevant schema
metadata—not sample/result rows—to generation.

Expose create/schema/query/delete API contracts and a Streamlit active-source
control. Keep workspace questions, SQL, and results out of durable metadata
history. Treat the feature as loopback-only until public authentication,
per-user ownership, rate limiting, quotas, sandbox/content policy, and provider
data governance exist.

### Consequences

- Users can inspect and query ordinary SQLite databases and schema/data dumps
  without changing the Chinook PostgreSQL runtime.
- PostgreSQL/MySQL dumps, live connection strings, views, triggers, virtual
  tables, and unrestricted dump restoration are explicit non-goals.
- The generic path has no reviewed business semantics; a syntactically safe
  result can still be semantically wrong and must remain auditable.
- This feature does not qualify the real model, open the sealed holdout, or
  change the Point-5 gate.
- Local evidence passes 479 tests with four PostgreSQL skips and 90.34%
  coverage; no provider or holdout call was made.

## ADR-0050 - Use Railway for a Private Staging Path Before Public Exposure

- Date: 2026-08-22
- Status: Accepted

### Context

The owner asked to connect the project to Railway. The repository already has
separate API/frontend Dockerfiles, a PostgreSQL bootstrap job, health endpoints,
and a Compose topology, but it intentionally lacks public authentication,
tenant authorization, and rate limiting. Railway maps Compose services to
separate services and its compute/database resources may consume trial credit
or incur cost.

### Decision

Select Railway as the initial managed staging platform. Create and locally link
an empty Railway project named `ai-database-analyst`, but do not provision
services, databases, volumes, or public domains until the owner approves the
environment/region and a maximum budget. The owner subsequently approved the
Hobby plan on 2026-08-22; use the effective USD 5 account hard limit and the
Singapore region without raising the separate workspace limit to its USD 10
minimum.

When authorized, map the topology to managed PostgreSQL, a one-shot bootstrap/
migration service, private FastAPI, and Streamlit. Use Railway private-network
references for service and database traffic. Keep FastAPI without a public
domain. Do not expose Streamlit publicly until authentication, authorization,
request limits, and rate limiting are implemented and verified. Keep the fake
provider as the staging default unless Gemini data governance and secret use
are separately approved. Use a dedicated non-root `Dockerfile.bootstrap` whose
immutable command runs the one-shot bootstrap, because the Railway CLI did not
apply the service start-command override reliably.

### Consequences

- Railway account authentication and project linkage are complete. Private
  PostgreSQL is healthy in Singapore; bootstrap/API/frontend verification is
  still in progress and no public application deployment is claimed.
- Deployment source should be a reviewed commit after stacked PRs #27, #28,
  and #32 are merged, unless the owner explicitly authorizes an ephemeral
  branch deployment.
- Railway Variables may be evaluated as the staging secret store, but no local
  credential may be copied into source, documentation, chat, build arguments,
  or image layers.
- DD-003 is resolved for staging. Authentication, budget, region, public
  exposure, and production secret-management decisions remain open gates.

## Deferred Decisions

| ID | Decision | Required by | Reason for deferral |
|---|---|---|---|
| DD-001 | Real LLM provider and model | Resolved 2026-08-07 | ADR-0035 selects Gemini API with `gemma-4-26b-a4b-it`; paid budget USD 0. |
| DD-002 | Public project license | Resolved 2026-07-21 | MIT selected by the owner. |
| DD-003 | Deployment platform | Resolved 2026-08-22 | ADR-0050 selects Railway for a private staging path; no resources are deployed. |
| DD-004 | Authentication provider | Public production-like demo | Not required for the local portfolio MVP. |
| DD-005 | Cloud secret manager | Deployment | Depends on the selected platform. |
