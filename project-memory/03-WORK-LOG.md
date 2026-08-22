# Work Log

Append new entries at the top so the latest handoff is easy to find. Never store
secrets or raw sensitive payloads.

## 2026-08-22 - Railway private staging provisioning started

### Outcome

- Confirmed the owner's Hobby-plan authorization and Railway's effective USD 5
  account hard limit. Railway requires at least USD 10 for a separate workspace
  hard limit, so that limit was not raised.
- Provisioned a fresh managed PostgreSQL service in Singapore with one private
  volume and no public TCP proxy/domain. Created private bootstrap, API, and
  frontend service placeholders in the same staging environment.
- Generated distinct analytics, metadata, migration, and evaluation
  credentials locally and sent them to Railway Variables through stdin without
  printing or persisting their values. The deployed provider remains fake.
- Added a dedicated one-shot `Dockerfile.bootstrap` after Railway's CLI service
  start-command override did not apply. Added it to Dockerfile contracts and
  hosted container build/security scans.

### Verification and boundary

- PostgreSQL reports `SUCCESS`, one running Singapore replica, a ready volume,
  and no public URL. Production remains untouched.
- The first empty PostgreSQL instance was deleted and recreated after its
  initial generated password appeared in CLI JSON output. Its replacement value
  was never printed, and no temporary SSH key remains registered or on disk.
- Full offline verification passes: formatting, lint, strict Mypy on 183 source
  files, and 479 tests with four PostgreSQL skips and 90.34% coverage. Local
  Docker image build is unavailable because Docker Desktop is not running;
  hosted Linux checks must build and scan the new image before bootstrap is
  trusted.
- The first bootstrap deployment failed before build because a stale Virginia
  region made the service appear multi-region on Hobby. The service is now
  single-region Singapore; no application code or migration ran in that failed
  attempt.

## 2026-08-22 - Railway project connected without provisioning resources

### Outcome

- Reviewed current official Railway CLI, Docker Compose mapping, PostgreSQL,
  healthcheck, private networking, and trial documentation.
- Authenticated Railway CLI v5.43.1 through the owner's account, created the
  empty `ai-database-analyst` project, and linked this repository directory.
- Created an empty `staging` environment and made it the explicit local CLI
  target; the default `production` environment remains empty.
- Recorded ADR-0050 and a staged service-mapping plan for managed PostgreSQL,
  one-shot bootstrap/migration, private FastAPI, and Streamlit.

### Verification and boundary

- Railway status reported empty `staging` and `production` environments with
  zero services, buckets, or volumes; no database, domain, active deployment,
  GitHub service source, application secret, or provider call exists.
- No paid or trial-credit-consuming resource was created. Provisioning awaits
  explicit environment/region and budget approval. Public exposure remains
  blocked on authentication, authorization, request limits, and rate limiting.
- The first hosted quality run exposed one stale Stage 10 assertion that still
  required the pre-selection phrase. The contract now verifies Railway is
  connected while no service/database exists and public routing stays blocked.
- Corrective commit `d858001` then passed every hosted PR #33 gate: Python
  3.11/3.12 quality, PostgreSQL integration, clean Compose, source/container
  security, CodeQL, and CodeRabbit.

## 2026-08-22 - Uploaded workspace isolated, pushed, and hosted-verified

### Outcome

- Moved the uploaded SQLite workspace into its own branch,
  `agent/uploaded-sqlite-workspace`, stacked on the Point-5 branch so the
  feature remains reviewable independently.
- Committed the implementation as `fe7fcfe`, pushed the branch, and opened
  draft PR #32 against `agent/fix-point5-policy-holdout`.
- GitHub reported the PR mergeable. Python 3.11/3.12 quality, PostgreSQL
  integration, clean Compose, source security, container security, CodeQL,
  and CodeRabbit all passed for the implementation commit.

### Verification and boundary

- Local verification remains 479 passed, 4 PostgreSQL skips, 90.34% branch
  coverage, with Ruff format/lint and strict Mypy clean.
- No live provider or holdout request was made. Point 5 remains blocked only
  by its independent sealed-holdout manifest, candidate freeze, and separately
  authorized one-time holdout; public deployment also remains pending.

## 2026-08-18 - Ephemeral uploaded SQLite workspace implemented

### Outcome

- Added raw-byte create, schema, query, and delete API contracts for opaque,
  expiring uploaded SQLite workspaces plus typed frontend client support.
- Added Streamlit upload/source-selection UX for `.db`, `.sqlite`, `.sqlite3`,
  and restricted `.sql`, including schema explorer, prompt results, warnings,
  and explicit deletion.
- Each upload builds an independent schema snapshot, exact allowlist, prompt-v4
  generator, AST security policy, read-only executor, and result pipeline. It
  never reuses Chinook semantics or touches either PostgreSQL database.
- Added a deny-by-default SQL dump importer and SQLite integrity/active-object
  checks. Runtime connections now also set `trusted_schema=OFF`.

### Verification and boundary

- Full offline gate: 479 passed, 4 PostgreSQL skips, 90.34% coverage; Ruff and
  strict Mypy passed. No live provider or holdout call was made.
- Hostile tests reject `ATTACH`, views, virtual tables, `INSERT SELECT`, writes,
  computed index functions, and generated destructive SQL.
- The feature is local/loopback-only and SQLite-first. Public use still needs
  authentication, per-user ownership, rate limits, quotas, sandbox/content
  policy, and approved LLM-provider data governance. Point 5 remains blocked
  only on the independent sealed-holdout manifest/freeze/run sequence.

## 2026-08-18 - Complete v5 development gate passed

### Outcome

- Owner authorized the exact maximum-136 complete development run. Source
  commit `23efdea`, evaluation hash `1fce1f76...`, Gemini 31B, `v5-plan`, and
  `semantic-v2` remained frozen throughout all 70 cases.
- The run passed 67/70 using 69 requests. Structured output was 68/68; valid
  SQL and read-only execution 61/61; execution accuracy 58/61 (95.08%);
  clarification 2/2; and known-unsafe blocking 7/7.
- Hallucination, false blocking, security bypass, and measured paid cost were
  zero. Token use was 135,259 input / 27,377 output; P50/P95 latency was
  13,742.86/24,958.51 ms.
- `AGG-006`, `AGG-007`, and `AGG-017` were substantive mismatches, but every
  preregistered gate passed. The privacy-safe v3 JSON/Markdown reports contain
  no raw questions, provider responses, SQL, or result rows.

### Boundary

- Candidate freeze was not attempted because the independent curator manifest
  is absent. Holdout provider calls and scored cases remain zero.
- The only Point-5 blocker is now the independently curated 30-case manifest.
  Once supplied, freeze may proceed; the one-time holdout maximum is exactly
  54 requests and requires separate owner authorization.
- Source commit was pushed and draft PR #28 opened; all nine initial hosted
  checks passed.

## 2026-08-18 - Point 5 policy and sealed-holdout defects corrected offline

### Outcome

- Accepted ADR-0048: universal grouped requests return every group under the
  500-row execution ceiling, remove model-invented limits unless quantity is
  explicit, and omit unrequested display fields for identifier-only grouping.
  Runtime uses question semantics/schema metadata and contains no `AGG-007`
  branch.
- Added `stage-7-development-v2`: exactly 70 development-only cases; canonical
  SHA-256 `5988509...`; `AGG-007` now expects all 204 `ArtistId, album_count`
  groups without a semantic limit. The historical v1 corpus is unchanged.
- Added a public sealed-holdout manifest, independent-curator attestation flow,
  private-payload Git exclusions, separate development/holdout candidate
  identities, and fail-closed validation before provider setup.
- The replacement holdout contract requires exactly 30 cases spanning all
  eight categories (5/5/5/3/3/3/3/3). Candidate freeze derives the exact cap
  from the manifest; `v5-plan` therefore permits at most 54 holdout requests.

### Verification and boundary

- Full offline gate passed: 460 tests, 4 PostgreSQL skips, 90.56% coverage;
  Ruff format/lint, strict Mypy on 179 files, semantic validation, comparison
  audit, and Tahap 5-10 evaluators all passed.
- No provider or holdout request was made. Point 5 remains `Terblokir`: owner
  authorization is required for the exact max-136 complete development run,
  and an independent curator must supply the sealed holdout manifest. A
  candidate may be frozen and holdout run only after the prior gate passes.

## 2026-08-16 - PR #27 stale Tahap 8 gate expectations corrected

### Outcome

- The first hosted PR #27 run proved that both Alembic revisions upgraded a
  clean PostgreSQL database, then failed because two exact expected-table sets
  still described only the Tahap 8 schema.
- Added `agent_continuations` to the deterministic readiness evaluator and
  PostgreSQL integration expectation, required both migration files, and
  retained an explicit denylist for raw question, prompt, SQL, and result-row
  column names.
- Full local verification passed again: 447 tests, 4 PostgreSQL/Docker skips,
  90.69% coverage, Ruff format/lint, and strict Mypy on 176 files.
- The corrective hosted runs all passed: CI `31942701362`, Docker
  `31942701282`, and Security `31942701256`. This covers real PostgreSQL,
  Python 3.11/3.12, clean Compose, source/container scans, and CodeQL. PR #27
  was moved from draft to ready for review.

## 2026-08-16 - Points 6-7 bounded agent implemented without model promotion

### Outcome

- Merged PR #26 into `main` as `42ba532`, then created
  `agent/bounded-agent-points-6-7` from the clean merged source.
- Added eight typed/versioned tools behind a static per-state registry. The
  executor accepts only request-bound, one-use validation capabilities; result
  formatting uses a separate one-use capability. Unknown, disallowed, forged,
  duplicated, or malformed calls fail closed.
- Added an 8-step/2-repair/30-second decide-act-observe loop with distinct
  terminal outcomes, provider/query/deadline handling, optional token/cost
  stops, repairable-only `SQLRepairCoordinator`, and privacy-safe audit events.
- Added canonical clarification query/continue/cancel API contracts and
  Streamlit controls. Alembic `20260816_0002` persists restart-safe state using
  only question digest, semantic rule/option/version/hash, counters, and expiry;
  claim is atomic and raw question/SQL/prompt/rows are not stored.
- Preserved `/api/v1/query` as the deterministic compatibility path and kept
  `fake` / `fake-deterministic` as the default.

### Verification and boundary

- Local full gate: 447 passed, 4 PostgreSQL/Docker skips, 90.69% coverage;
  Ruff format/lint, strict Mypy on 176 files, and diff-check passed.
- No live provider request was made. Points 6-7 are complete as architecture
  and offline evidence, but Point 5 remains `Terblokir`; no candidate, model
  qualification, holdout, or public deployment claim follows from this work.

## 2026-08-16 - Security restored; Phase N passed 5/6 and stopped before promotion

### Outcome

- Pinned GitPython 3.1.58, clearing all seven installed-package advisories;
  focused security/provider tests passed 51/51. Local Docker was unavailable,
  so hosted scans supplied the closing evidence: all nine PR checks passed,
  including source security, container security/Trivy, CodeQL, Docker Compose,
  PostgreSQL, and Python 3.11/3.12 quality.
- Corrected `scripts/dev.py verify` so it always forces `fake` /
  `fake-deterministic` and an empty child credential. The complete offline
  gate passed 411 tests with four PostgreSQL skips, 90.10% coverage, Ruff,
  format, strict Mypy on 165 files, Stage 5-10 gates, and diff-check.
- Before that correction, the first preflight inherited local `.env` and made
  one free 26B request that failed on truncated JSON. It touched no holdout and
  created no evaluation report.
- Phase N then ran exactly the six authorized development cases on source
  `126c6ecdbc...` with a hard 12-request cap. It used 7 requests and passed
  5/6; structured validity was 6/6, valid SQL/execution 5/5, execution accuracy
  4/5, unsafe blocking 1/1, and cost/security bypass/holdout calls zero.

### Decision boundary

- `AGG-007` remains the only failure. Its 20-row/two-column expected relation
  is not justified by the unbounded question, while the model returned a safe
  three-column relation. No case-specific rule was added.
- The Phase-N accuracy gate failed at 80%, so no candidate, holdout run, or
  combined summary was created. Point 5 is `Terblokir`; points 6-7 remain
  closed pending an explicit product cardinality/projection policy and a new
  independently curated sealed holdout.
- Consolidated the 146-file Point 1-5 implementation/evidence scope into commit
  `9c54425`, pushed `agent/complete-real-llm-point5`, and opened draft PR #26.

## 2026-08-08 - Phase M improved failures to 12/18; Phase-N source prepared offline

### Outcome

- Phase M ran the 18 Phase-L development failures on frozen source
  `084ca023...` and used 19/36 maximum requests.
- Passed 12/18 versus 0/18 on the same cases in Phase L. Structured validity
  was 17/18; all 17 analytical outcomes had valid SQL and successful read-only
  execution; execution accuracy was 12/17.
- Hallucination, false blocking, security bypass, measured cost, and holdout
  calls remained zero. The unsafe case failed closed before SQL but again
  missed its required unsupported classification.
- Phase M failed the pre-registered 15/18, 18/18 structured, and unsafe targets;
  no candidate or holdout artifact was created.

### Offline continuation

- Added generic fixes for five remaining patterns: ordered detail default
  bounds, FK-role display completion, grouped-FK entity lifting, unnumbered
  display rankings, and provider unsupported markers.
- Deliberately did not hard-code the unexplained 20-row `AGG-007` expectation.
- New source `126c6ecdbc...` passes 409 tests, four PostgreSQL skips, 90.10%
  coverage, Ruff/format, strict Mypy on 164 files, and `git diff --check`.
- No provider request has used the new source. Next decision: authorize a
  six-case Phase-N development rerun with an exact cap of 12 requests, or stop
  Point 5. Holdout and points 6-7 remain closed.
- Integrity correction: a local diagnostic accidentally omitted its split
  filter and displayed records outside development. No holdout provider call,
  execution, or scoring occurred, but `stage-7-v1` is no longer an eligible
  unseen final holdout. A replacement must be independently curated and sealed
  without this agent inspecting it.

## 2026-08-08 - Phase L failed complete v5-plan development gates

### Outcome

- Completed all 70 development cases using 74/136 maximum requests on source
  hash `eb467958...`; holdout calls remained zero.
- Passed 52/70 overall. Structured validity was 64/68 (94.12%), valid SQL and
  execution success were each 58/61 (95.08%), and execution accuracy was 44/61
  (72.13%).
- Clarification passed 2/2; hallucination and false blocking were zero; no
  security bypass occurred. Known-unsafe blocking was 6/7 because one case
  failed closed at plan validation rather than returning `unsupported`; no SQL
  was compiled or executed for it.
- Five repairs had 20% success. Token usage was 156,921 input / 29,517 output,
  latency P50/P95 12,937.98/31,259.27 ms, and measured cost USD 0.

### Decision boundary

- Formal gates failed structured validity, execution accuracy, and known-
  unsafe blocking. No candidate manifest, holdout report, or combined summary
  was created.
- Compared with prompt-v4/semantic-v2, accuracy improved 45.90% -> 72.13% and
  valid SQL improved 86.89% -> 95.08%, but structured and unsafe reliability
  regressed.
- Point 5 remains blocked. Any continuation requires a new versioned
  development-only candidate; holdout and points 6-7 remain closed.

## 2026-08-08 - Phase K fixed both remaining ordering mismatches

### Outcome

- Root cause: the Stage-1 default detail ordering did not recognize `longest`
  as an explicit ranking and replaced the natural ordering of bounded
  global-average detail filters with primary-key ascending.
- Added generic canonical ordering: explicit superlatives retain their grounded
  value order plus a primary-key tie-breaker; one bounded global-average filter
  orders by its projected comparison value (`>` descending, `<` ascending)
  followed by primary key.
- No case ID, expected SQL, or expected row is inspected by runtime code.
- Phase K passed `RNK-004` and `SUB-001` exactly at 2/2 with 2/4 requests and
  no repair. Structured plan, valid SQL, and read-only execution were 2/2;
  source hash remained stable; hallucination, bypass, cost, and holdout calls
  stayed zero.

### Verification and boundary

- Full regression: 390 passed, 4 PostgreSQL skipped, 90.26% coverage. Focused
  security/evaluator suite: 73 passed. Ruff, strict Mypy on 164 files, and
  `git diff --check` passed.
- Post-live Ruff formatting changed only source layout; no provider call was
  made. Current source hash is `eb467958...`, and the formatted source repeated
  the full 390-passed/4-skipped/90.26% regression successfully.
- The result is staged development evidence. The max-136 complete development
  run, candidate freeze, holdout, and points 6-7 remain closed pending a new
  explicit owner decision.

## 2026-08-08 - Exact final Stage-1 hard pilot reached 10/12

### Outcome

- Completed the same 12 hard development cases on one exact source freeze with
  12/24 maximum Gemini requests and no repair.
- Passed 10/12 (83.33%). Structured plan validity, valid SQL, and read-only
  execution success were all 12/12 (100%). Same-case progression is
  0/12 -> 2/12 -> 6/12 -> 8/12 -> 10/12.
- `RNK-004` and `SUB-001` safely executed with the expected three-column shape
  but differed in row values or required ordering under `semantic-v2`.
- Source hash stayed `54343c9e...` before/after. No FakeLLM was used on the live
  path; hallucination, security bypass, paid cost, and holdout calls stayed
  zero.

### Decision boundary

- The unchanged 85% execution-accuracy gate failed by one case: 83.33% is not
  sufficient to freeze a candidate.
- The max-136 complete development run, holdout, and points 6-7 remain closed.
- Next owner decision: authorize targeted analysis/correction of `RNK-004` and
  `SUB-001`, or choose another explicitly bounded development action.

## 2026-08-08 - Stage-1 corrected all four pilot-v3 failures

### Outcome

- Added one bounded transient-provider retry that shares the existing maximum
  two requests per case with plan repair; the cap did not increase.
- Added deterministic binding of one unambiguous `project_verified` metric,
  bounded-list entity-grain/default-order grounding, and structurally
  equivalent grouped-benchmark normalization.
- Phase G passed `FLT-003`, `JON-003`, and `JON-011` at 3/4 using 5/8 requests.
- Phase H failed closed after 2/2 diagnostic requests and compiled no SQL.
- Phase I passed `SUB-004` exactly in 1/2 requests without repair. Across the
  correction cycle, each final passing outcome used one request and all live
  attempts used 8 requests total.
- No FakeLLM was used on the live `v5-plan` path. Schema hallucination,
  security bypass, paid cost, and holdout calls remained zero.

### Verification and boundary

- Final source freeze: 388 tests passed, 4 PostgreSQL tests skipped, 90.28%
  coverage; Ruff, strict Mypy on 164 files, and `git diff --check` passed.
- The four passing corrections used successive source freezes. They are not a
  measured 12/12 result on one exact source and do not qualify point 5.
- Next decision: authorize the same 12 hard development cases on the exact final Stage-1
  source with a maximum of 24 requests. The max-136 complete development run,
  candidate freeze, holdout, and points 6-7 remain closed.

## 2026-08-08 - Hard pilot v3 met the 8/12 engineering target

### Outcome

- Phase-F completed all 12 selected development cases using 14/24 maximum
  provider requests.
- Passed 8/12 (66.67%), meeting the subset target. Same-case progression:
  prompt-v4 0/12, pilot-v1 2/12, pilot-v2 6/12, pilot-v3 8/12.
- Structured validity, valid SQL, and execution success were each 10/12
  (83.33%). Four passes were presentation-equivalent and two safe executions
  remained substantive mismatches.
- One case had a sanitized provider error and one exhausted repair. Schema
  hallucination and security bypass remained zero; paid cost was USD 0;
  holdout calls remained zero.

### Formal boundary

- The formal gate remains false: subset execution accuracy 66.67% is below 85%
  and structured validity 83.33% is below 99%.
- No candidate was frozen; holdout and points 6-7 remain closed.
- A complete v5-plan development evaluation allows up to 136 calls and requires
  a separate frozen authorization after deciding whether to fix the remaining
  provider/ordering/metric/benchmark failures first.

## 2026-08-08 - Phase E passed; hard pilot v3 opened

### Outcome

- Phase E completed two cases with 3/4 maximum requests and passed 2/2.
- `FLT-003` passed exact after one bounded repair; `RNK-003` passed as a
  value-aligned semantic-v2 match without repair.
- Both SQL candidates passed validation and read-only execution; hallucination
  and security bypass stayed zero.
- Phase-F hard pilot v3 is open on exact frozen source with maximum 24 calls,
  the same 12 development cases, USD 0 paid budget, and holdout 0.

### Exact next action

Run `stage-7-gemini-31b-v5-plan-hard-pilot-v3`; target at least 8/12 and zero
security bypass. Do not treat the subset as formal qualification.

## 2026-08-08 - Hard pilot v2 reached 6/12; target still missed

### Outcome

- Phase-D hard pilot v2 completed all 12 development cases using 15/24 maximum
  provider requests.
- Passed 6/12: execution accuracy progressed from prompt-v4 0%, to pilot-v1
  16.67%, to pilot-v2 50%.
- Structured validity, valid SQL, and execution success were each 9/12 (75%).
  Three passes were presentation-equivalent and three safe executions remained
  substantive mismatches.
- Schema hallucination and security bypass stayed zero; paid cost was USD 0;
  holdout calls stayed zero.
- The 8/12 engineering target and formal gates were not met.

### Next improvement

Phase E resolves the generic conflict between a requested related ID versus a
related display and completes grouped base entity dimensions for aggregate
rankings. `FLT-003` and `RNK-003` are capped at four development requests; both
must pass before hard pilot v3.

### Phase E verification

- Focused v5-plan/evaluator suite: 37 passed.
- Full source-freeze regression: 380 passed, 4 skipped, 90.30% coverage.
- Ruff, strict Mypy on 164 backend/script/test source files, and
  `git diff --check` passed.

## 2026-08-08 - Phase C4 passed; hard pilot v2 opened

### Outcome

- Phase C4 passed `FLT-005` exactly with 1/2 maximum requests and no repair.
- SQL validation, read-only execution, and semantic-v2 result comparison all
  passed at 3/3 columns; no hallucination or security bypass occurred.
- Across C2-C4, all four projection target cases now have passing evidence.
- Phase-D hard pilot v2 is open on exact frozen source: the same 12 development
  cases, maximum 24 calls, one repair per case, six-second interval, USD 0 paid
  budget, and holdout 0.

### Exact next action

Run `stage-7-gemini-31b-v5-plan-hard-pilot-v2` and compare its pass count to
both 0/12 prompt-v4 and 2/12 hard-pilot-v1 baselines. Do not infer formal model
qualification from subset results.

## 2026-08-08 - Phase C3 fixed benchmark Invoice; one filter-only extra remains

### Outcome

- Phase C3 completed both Invoice cases with only 2/4 maximum requests.
- `SUB-001` now passes exact with three columns and no repair.
- `FLT-005` reached valid SQL and safe execution but returned four columns: the
  model's non-ID filter field plus the three canonical defaults.
- No security bypass or schema hallucination occurred. The 2/2 threshold was
  missed, so hard pilot v2 remains closed.

### Next improvement

Phase C4 removes only a filter-only non-ID presentation field when it is not
explicitly named or ordered. The WHERE predicate remains intact. `FLT-005` is
rerun under an exact maximum of two development requests.

### Phase C4 verification

- Focused v5-plan/evaluator suite: 36 passed.
- Full source-freeze regression: 379 passed, 4 skipped, 90.30% coverage.
- Ruff, strict Mypy on 164 backend/script/test source files, and
  `git diff --check` passed.

## 2026-08-08 - Phase C2 improved two cases; Invoice defaults remain

### Outcome

- Phase C2 completed four cases with 6/8 maximum provider requests.
- `JON-003` and `RNK-004` now pass safe execution and semantic-v2 comparison,
  improving the selected baseline from 0/4 to 2/4.
- `FLT-005` and `SUB-001` both failed closed after repair because the model did
  not add the base Invoice relationship ID. No SQL was compiled for either
  incomplete plan and no security bypass occurred.
- The required 3/4 threshold was missed; hard pilot v2 remains closed.

### Next improvement

Phase C3 deterministically completes only schema-trusted default fields for the
base detail entity, then reruns the two Invoice cases under a maximum of four
development requests. Related fields, joins, filters, values, and SQL remain
model-plan/grounder/compiler controlled and are not synthesized.

### Phase C3 verification

- Focused v5-plan/evaluator suite: 36 passed.
- Full source-freeze regression: 379 passed, 4 skipped, 90.33% coverage.
- Ruff, strict Mypy on 164 backend/script/test source files, and
  `git diff --check` passed.

## 2026-08-08 - Phase C1 fixed contracts; projection policy remains

### Outcome

- Phase C1 completed both selected cases with 2/4 maximum requests.
- Alias/benchmark normalization eliminated both prior plan-contract failures;
  each case reached validator-approved SQL and safe read-only execution.
- Both results still had two actual versus three expected columns, so quality
  remained 0/2. No security bypass or schema hallucination occurred.
- Hard pilot v2 remains closed.

### Next improvement

Phase C2 adds a metadata-derived bounded-detail projection policy and tests
`FLT-005`, `JON-003`, `RNK-004`, and `SUB-001` with an exact maximum of eight
development requests. At least three must pass before pilot v2.

### Phase C2 verification

- Focused v5-plan/evaluator suite: 36 passed.
- Full source-freeze regression: 379 passed, 4 skipped, 90.36% coverage.
- Ruff, strict Mypy on 164 backend/script/test source files, and
  `git diff --check` passed.

## 2026-08-08 - Hard pilot v1 measured improvement but missed target

### Outcome

- Frozen protocol-v4 Phase B completed all 12 selected development cases with
  20/24 maximum provider requests.
- Passed 2/12 versus the same-case prompt-v4 baseline 0/12: execution accuracy
  improved from 0% to 16.67%, but missed the engineering target of 8/12.
- Structured validity, valid SQL, and execution success were each 5/12
  (41.67%). One pass was presentation-equivalent; three executed cases remained
  substantive mismatches.
- Eight cases used repair and only one repaired successfully. Invalid display
  aliases and benchmark field-shape rigidity dominated the sanitized contract
  failures.
- Schema hallucination and security bypass stayed zero; paid cost was USD 0;
  holdout calls stayed zero. No candidate was frozen.

### Next improvement

Phase C1 adds deterministic safe alias canonicalization and narrow benchmark
normalization, then tests `JON-003` and `SUB-001` under an exact four-request
development cap before any v2 hard pilot.

### Phase C1 verification

- Focused v5-plan/evaluator suite: 35 passed.
- Full source-freeze rerun: 378 passed, 4 skipped, 90.33% coverage.
- Ruff, strict Mypy on 164 backend/script/test source files, and
  `git diff --check` passed.
- One prior full run had a single 20-second Streamlit AppTest timeout; that test
  passed alone in 4.88 seconds and the complete rerun then passed.

## 2026-08-08 - Phase A14 passed; 12-case hard pilot opened

### Outcome

- Phase A14 consumed 2/2 requests. The initial incomplete plan was stopped
  before SQL and the role-specific single repair corrected it.
- The final plan produced validator-approved SQL, successful read-only
  execution, exactly 3/3 expected columns, and an exact semantic-v2 result
  match. There was no security bypass or schema hallucination.
- This is measured progression from one actual column in A11, to two in A12,
  to a passing three-column relation in A14.
- Protocol-v4 Phase B is now open on the exact frozen runtime: 12 selected
  development failures, maximum 24 calls, one repair per case, six-second
  minimum interval, USD 0 paid budget, and holdout 0.

### Exact next action

Run `stage-7-gemini-31b-v5-plan-hard-pilot-v1` without changing source. Report
the same-case pass count against the v4 baseline of 0/12; do not extrapolate
subset evidence to the formal 85% development gate.

## 2026-08-08 - Role-specific projection-repair Phase A14 prepared

### Outcome

- Phase A13 consumed 2/2 requests. Both plans remained incomplete and were
  stopped before SQL compilation; no SQL execution or security bypass occurred.
- Split the generic completeness failure into sanitized missing-role codes for
  primary identifier, display (`Name`/`Title`), or filter identifier.
- Added a bounded role-specific repair instruction that tells Gemma what kind
  of output to add while retaining the others. Reports still reveal no column
  names, SQL, values, prompts, questions, plans, or raw model content.
- Phase A14 is development-only and capped at exactly 2 requests for `FLT-003`;
  hard pilot and holdout remain closed.

### Verification

- Focused v5-plan/evaluator suite: 34 passed.
- Full source-freeze regression: 377 passed, 4 skipped, 90.45% coverage.
- Ruff, strict Mypy on 164 backend/script/test source files, and
  `git diff --check` passed.

## 2026-08-08 - Deterministic projection-completeness Phase A13 prepared

### Outcome

- Phase A12 used 1/2 maximum requests, executed safely without repair, and
  improved the result shape from one to two of three expected columns. The
  compatibility case still failed; Phase B did not run.
- Added a narrow deterministic invariant for bounded single-table detail lists
  filtered by one non-primary ID: require the single primary key, schema
  `Name`/`Title`, and filtering ID.
- Incomplete plans fail before SQL compilation with a sanitized code and may
  consume the existing one repair. The runtime neither invents columns nor
  mutates the plan.
- Aggregates, joined detail outputs, related subqueries, text/null filters,
  composite keys, and tables without `Name`/`Title` are excluded.
- Phase A13 is development-only and capped at exactly 2 requests for `FLT-003`;
  hard pilot and holdout remain closed.

### Verification

- Focused v5-plan/evaluator suite: 34 passed.
- Full source-freeze regression: 377 passed, 4 skipped, 90.44% coverage.
- Ruff, strict Mypy on 164 backend/script/test source files, and
  `git diff --check` passed.

## 2026-08-08 - Detail-shape compatibility Phase A12 prepared

### Outcome

- Phase A11 used 1/2 maximum calls and produced a valid plan without repair.
  Grounding, deterministic compilation, alignment, AST validation, read-only
  execution, and semantic comparison all ran successfully.
- The case failed because the returned relation had fewer columns than the
  expected relation; there was no security bypass or schema hallucination.
- Replaced the unrelated one-column Customer example with a general three-field
  filtered-detail shape: identifier, useful name, and filtering attribute.
- Added privacy-safe expected/actual column counts to per-case evidence and CLI
  progress. SQL, aliases, values, rows, plans, prompts, questions, and raw model
  content remain excluded.
- Phase A12 remains development-only, capped at exactly 2 requests for
  `FLT-003`. Phase B and holdout remain closed until this case passes.

### Verification

- Focused v5-plan/evaluator suite: 33 passed.
- Full source-freeze regression: 376 passed, 4 skipped, 90.46% coverage.
- Ruff, strict Mypy on 164 backend/script/test source files, and
  `git diff --check` passed.
- An intentionally broader Mypy diagnostic found six pre-existing Streamlit/
  Altair typing issues in `frontend/streamlit_app.py`; they are outside the
  established strict gate and do not touch the v5-plan runtime.

## 2026-08-08 - JSON MIME/local-contract Phase A11 prepared

### Outcome

- Phase A10 consumed 2/2 calls with `finishReason=STOP`, 318 total output
  tokens, and a 511-character truncated final object. This is not token/local
  budget exhaustion.
- Configured only v5-plan to request JSON MIME without responseJsonSchema,
  avoiding the hosted Gemma nested-schema decoder behavior. Strict Pydantic,
  grounding, compiler, alignment, AST security, and read-only execution remain
  mandatory.
- Legacy direct-SQL generation retains its existing provider schema.
- Phase A11 is frozen at exactly 2 calls for `FLT-003`; Phase B and holdout
  remain closed.

### Verification

- 376 tests passed, 4 skipped, 90.46% coverage.
- Ruff, strict Mypy on 164 files, and `git diff --check` passed before source
  freeze.

## 2026-08-08 - Provider finish-reason telemetry prepared for Phase A10

### Outcome

- Phase A9 consumed 2/2 calls and measured 318 total output tokens with a
  511-character final candidate, ruling out provider/local output ceilings.
- Added only Gemini's bounded `finishReason` enum to adapter and evaluator
  metadata. Raw finish messages and candidate content remain discarded.
- Phase A10 remains development-only and is frozen at exactly 2 calls for
  `FLT-003`; Phase B and holdout remain closed.

### Verification

- 376 tests passed, 4 skipped, 90.45% coverage.
- Ruff, strict Mypy on 164 files, and `git diff --check` passed before source
  freeze.

## 2026-08-08 - Privacy-safe completion telemetry prepared for Phase A9

### Outcome

- Phase A8 consumed 2/2 calls and still returned truncated objects at 8,192
  provider output tokens; no SQL executed.
- Added failure-only token counts and final candidate character count to the
  privacy-safe evaluator evidence. Raw output remains discarded.
- Phase A9 keeps the 8,192 ceiling and is frozen at exactly 2 calls for
  `FLT-003`; Phase B and holdout remain closed.

### Verification

- 376 tests passed, 4 skipped, 90.44% coverage.
- Ruff, strict Mypy on 164 files, and `git diff --check` passed before source
  freeze.

## 2026-08-08 - Output-token override frozen for Phase A8

### Outcome

- Phase A7 consumed 2/2 calls and safely classified the final output as a
  truncated JSON object; no SQL executed.
- Added an evaluation-only `--max-output-tokens` override and included it in
  checkpoint identity. Provenance/candidate freezing already records the same
  setting.
- Phase A8 uses 8,192 provider output tokens but retains the 20,000-character
  local plan cap, one repair, exactly 2 provider calls, and holdout 0.

### Verification

- 376 tests passed, 4 skipped, 90.46% coverage.
- Ruff, strict Mypy on 164 files, and `git diff --check` passed before source
  freeze.

## 2026-08-08 - Sanitized malformed-JSON shape repair prepared for Phase A7

### Outcome

- Phase A6 consumed 2/2 calls; both non-empty responses were invalid JSON, so
  no plan validation, SQL compilation, or execution occurred.
- Added shape-only classification for fenced output, truncated object,
  malformed object, array text, and non-JSON text. Raw response content remains
  discarded and is regression-tested not to enter error details.
- Phase A7 is frozen at exactly 2 calls for `FLT-003`; holdout remains 0.

### Verification

- 375 tests passed, 4 skipped, 90.46% coverage.
- Ruff, strict Mypy on 164 files, and `git diff --check` passed before source
  freeze.

## 2026-08-08 - Generic-envelope shape-example Phase A6 prepared

### Outcome

- Phase A5 stopped after 1/2 maximum calls with provider HTTP 400 before any
  candidate; no SQL executed.
- Confirmed that nested provider item properties are rejected even at 1,432
  characters/depth 7.
- Returned to the 1,285-character/depth-4 envelope already accepted in A2/A3,
  while retaining the new complete unrelated plan-shape example and sanitized
  field-level repair.
- Phase A6 is frozen at exactly 2 calls for `FLT-003`; holdout remains 0.

### Verification

- 370 tests passed, 4 skipped, 90.42% coverage.
- Ruff, strict Mypy on 164 files, and `git diff --check` passed before source
  freeze.

## 2026-08-08 - Shallow output-core schema prepared after Phase A4 rejection

### Outcome

- Phase A4 stopped after 1/2 maximum calls with provider HTTP 400 before any
  candidate; no SQL executed and the unused call was not consumed.
- Reverted nested fields to the provider-accepted shallow envelope and required
  only output `kind`/`alias`, directly addressing Phase A3 without restoring
  deep schema complexity.
- Added one complete unrelated AnalysisPlan shape example to the prompt; strict
  local validation/grounding/security remains unchanged.
- Phase A5 is frozen at exactly 2 calls for `FLT-003`; holdout remains 0.

### Verification

- 370 tests passed, 4 skipped, 90.41% coverage.
- Ruff, strict Mypy on 164 files, and `git diff --check` passed before source
  freeze.

## 2026-08-08 - Typed component schema prepared after Phase A3 diagnosis

### Outcome

- Phase A3 consumed 2/2 calls and safely reported
  `outputs_0_kind_missing`; no SQL was compiled or executed.
- Restored provider-enforced schemas for output, top-level filter, and order
  components. Kept deep benchmark/related filters simplified to avoid the
  original provider rejection; strict local validation remains complete.
- The resulting schema is 3,256 characters at depth 8. Phase A4 is frozen at
  exactly 2 calls for `FLT-003`; holdout remains 0.

### Verification

- 370 tests passed, 4 skipped, 90.37% coverage.
- Ruff, strict Mypy on 164 files, and `git diff --check` passed before this
  source freeze.

## 2026-08-08 - v5-plan field-level sanitized repair prepared after Phase A2

### Outcome

- Phase A2 consumed 2/2 calls. The provider accepted the simplified schema,
  but initial and repair plans failed strict local validation; no SQL executed.
- Identified that all parse/contract failures were incorrectly collapsed to
  `declared_schema_mismatch`, preventing a useful repair.
- Added bounded codes for empty/oversized/non-object/invalid-JSON output and the
  first Pydantic field path/error type. No raw model output or field value is
  retained.
- Exception evaluation now records the sanitized plan code and actual repair
  count. Phase A3 is frozen at exactly 2 calls for `FLT-003`; holdout remains 0.

### Verification

- 370 tests passed, 4 skipped, 90.42% coverage.
- Ruff and strict Mypy passed before the full regression; `git diff --check`
  passed.

## 2026-08-08 - v5-plan provider schema simplified after safe Phase A rejection

### Outcome

- Phase A used exactly 2/2 calls and received HTTP 400 `INVALID_ARGUMENT`
  before any candidate or SQL was produced; Phase B did not run.
- Official Gemini documentation confirms only a JSON Schema subset and warns
  that large/deep schemas may be rejected.
- Reduced only the provider-enforced envelope from 5,910 characters/depth 16/
  17 `anyOf` nodes to 1,285 characters/depth 4/no `anyOf`; retained the complete
  component contract in the prompt and unchanged strict local Pydantic checks.
- Froze Phase A2 at exactly 2 requests for `FLT-003`; holdout remains 0.

### Verification

- 370 tests passed, 4 skipped, 90.54% coverage after the change.
- Ruff, strict Mypy on 164 files, and `git diff --check` passed.

## 2026-08-08 - Gemma-only v5-plan candidate prepared for bounded development pilot

### Outcome

- Replaced free-form SQL authority on the new path with strict AnalysisPlan
  generation, schema grounding, approved join derivation, deterministic SQL
  compilation, and independent alignment checks.
- Added hybrid reviewed-example retrieval, one sanitized plan repair, and
  adapter-level hard metering for every actual Gemini request.
- The new runtime path requires the real Gemini adapter and has no FakeLLM
  fallback; the legacy fake adapter remains unchanged for offline regression.
- Frozen protocol v4 before live calls: one-case compatibility smoke max 2,
  followed only on success by a 12-case development pilot max 24; holdout 0.

### Verification

- 370 tests passed, 4 skipped, 90.56% coverage.
- Ruff, strict Mypy on 164 files, and `git diff --check` passed.
- Five real-adapter HTTP-mock plan integration tests cover valid execution,
  bounded repair, unsupported output, invalid output exhaustion, provider
  failure, and timeout without using FakeLLMAdapter.

## 2026-08-08 - Point 5 semantic-v2 development gate failed

### Outcome

- Completed the owner-authorized 31B/v4 semantic-v2 development run: 68
  provider requests across all 70 cases, with no process error.
- Passed 37/70 cases. Structured-output validity was 66/68 (97.06%) and
  execution accuracy was 28/61 (45.90%), below the frozen 99% and 85% gates.
- Semantic-v2 accepted 10 presentation-equivalent cases while leaving 25
  substantive result mismatches rejected.
- Clarification passed 2/2, schema hallucination was 0/61, and known-unsafe
  protection remained 7/7 with zero bypasses.
- No candidate was frozen and holdout cases scored remained zero.

### Evidence and handoff

- Valid SQL and execution success: 53/61 (86.89%); false blocking: 6/61.
- Input/output tokens: 66,561/9,895; latency P50/P95:
  5,018.12/8,257.60 ms; measured paid cost: USD 0.
- Reports:
  `reports/evaluation/stage-7-gemini-31b-development-semantic-v2-v1.json` and
  `reports/evaluation/stage-7-gemini-31b-development-semantic-v2-analysis.md`.
- Point 5 is blocked pending an explicitly versioned new candidate. Do not open
  holdout or begin points 6-7.

## 2026-08-08 - Point 5 semantic comparison policy v2 implemented

### Outcome

- Owner selected option 3: revise the output/comparison contract without
  lowering quality or security thresholds.
- Added explicit `strict-v1` and fail-closed `semantic-v2` policies. V2 accepts
  normalized/reordered columns or a unique provable one-to-one value alignment.
- Extra/missing columns, ambiguous mappings, changed values/row counts,
  inconsistent shapes, and required-order changes remain failures.
- Froze comparison-policy identity into checkpoints, provenance, candidate
  manifests, holdout validation, and combined summaries.
- Preserved the old 29.51% report unchanged; privacy-safe reports do not retain
  enough raw data for retrospective rescoring.

### Offline evidence and next gate

- Development-only audit: exact 61/61, presentation variants 61/61,
  substantive rejection 122/122, required-order rejection 47/47, irrelevant-
  order acceptance 1/1, holdout cases scored 0.
- Combined regression: 347 passed, 4 skipped, 90.32% coverage. Ruff format/
  lint, strict Mypy on 158 source files, and `git diff --check` passed.
- Audit JSON contains no question, SQL, expected/result rows, credential, or
  authorization fields. Localhost remained healthy after implementation.
- Protocol: `docs/real-model-evaluation-protocol-v3.md`.
- Point 5 is blocked pending explicit authorization for a new 68-call
  development rerun. Holdout and points 6-7 remain locked.

## 2026-08-08 - Point 5 31B formal development gate failed

### Outcome

- Owner authorized the recommended `gemma-4-31b-it` candidate without changing
  quality/security thresholds, retry policy, paid budget, or holdout rules.
- Used eight development-only calibration requests to compare prompt v3 and the
  development-derived v4 output-shape rule.
- Completed the formal v4 development split: 68 provider requests across 70
  cases; 27/70 passed.
- Structured-output validity was 66/68 (97.06%) and execution accuracy was
  18/61 (29.51%), below the frozen 99% and 85% thresholds.
- Clarification passed 2/2, schema hallucination was 0/61, and all 7/7 known-
  unsafe cases were stopped. No security bypass reached execution.
- The candidate was not frozen and holdout provider calls remained zero.

### Evidence and handoff

- Valid SQL and execution success: 53/61 (86.89%); false blocking: 6/61.
- Input/output tokens: 66,561/9,895; latency P50/P95:
  5,038.28/9,347.81 ms; measured paid cost: USD 0.
- Total 31B requests including calibration: 76. Total point-5 provider requests
  including prior 26B calibration: 87.
- Combined regression: 337 passed, 4 skipped, 90.53% coverage. Ruff format,
  Ruff lint, strict Mypy on 154 source files, and `git diff --check` passed.
- Privacy audit found zero raw sensitive fields in the formal report and zero
  exact active-key matches in tracked files; ignored `.env` remained the only
  credential location. Localhost returned HTTP 200.
- Reports: `reports/evaluation/stage-7-gemini-31b-development-v1.json` and
  `reports/evaluation/stage-7-gemini-31b-development-analysis.md`.
- Point 5 is blocked pending a new versioned candidate/protocol. Points 6-7
  must not use this model as a qualified baseline.

## 2026-08-08 - Point 5 development candidate blocked before holdout

### Outcome

- Added an opt-in real-provider evaluator with exact split request caps,
  checkpoint/resume, source-drift hashing, frozen-candidate enforcement, token/
  latency/cost provenance, and privacy-safe JSON/Markdown reports.
- Froze temperature 0, minimal thinking, USD 0, and the point-5 quality/security
  thresholds before any holdout access.
- Used only development cases to diagnose v2 output-shape/structured failures
  and derive prompt v3.
- The four-case v3 calibration passed 1/4, with 50% structured-output validity
  and 25% execution accuracy. It cannot qualify for the formal baseline.
- The candidate manifest was not frozen and holdout provider calls remained 0.

### Evidence and next decision

- 1,761 input tokens; 343 output tokens; latency P50/P95 9,886/88,553 ms;
  estimated paid cost USD 0.
- Combined implementation regression: 337 passed, 4 skipped, 90.53% coverage;
  Ruff, strict Mypy, and `git diff --check` passed.
- Schema hallucination and false blocking were 0% in this small calibration,
  but quality thresholds failed materially.
- See `reports/evaluation/stage-7-gemini-calibration-analysis.md`.
- Point 5 is blocked pending owner approval for a different model or a revised
  threshold/retry protocol. Points 6-7 must not start yet.

## 2026-08-08 - Point 4 mocked pipeline/security matrix completed

### Outcome

- Added 12 deterministic end-to-end cases using the real Gemini adapter with an
  offline `httpx.MockTransport`.
- Exercised the semantic layer, structured proposal parser, SQL AST policy, and
  read-only/recording execution boundary as one pipeline.
- Verified a safe aggregate reaches grounded execution, while unsupported and
  ambiguous requests, unknown table/column references, write/DDL/multi-
  statement SQL, prompt injection, provider timeout, and declared-source
  mismatch never reach execution.
- Point 4 is complete; point 5 remains untouched pending a new user request.

### Verification

- Mocked pipeline matrix: 12 passed with no network or local API key access.
- Combined full regression: 332 passed, 4 skipped, 91.55% coverage.
- Timestamp-only Stage 9/10 evaluator changes were restored after verification.
- Ruff, strict Mypy, and `git diff --check`: passed.

## 2026-08-08 - Point 3 second rotation verified and closed

### Outcome

- The owner installed a second replacement credential only in ignored `.env`.
- Compared the active credential value against every tracked Git file without
  printing it; zero matches were found.
- Verified `.env` is ignored/untracked, tracked examples keep
  `LLM_API_KEY` empty, and frontend code has zero secret references.
- Ran exactly one bounded synthetic live smoke; structured parsing passed.
- Point 3 is now complete and the tracked-example credential finding is fixed.

### Verification

- Live smoke: `gemini` / `gemma-4-26b-a4b-it`, intent `unsupported`, 63 input,
  89 output, 152 total tokens.
- Unit suite: 129 passed, 1 timestamp-mutating test deselected.
- Ruff, strict Mypy, and `git diff --check`: passed.
- No credential, prompt, or raw provider response was printed or recorded.

## 2026-08-07 - Point 3 tracked-example credential incident remediated

### Finding

- The point 3 audit found a credential-like value in the tracked
  `.env.compose.example` working-tree file.
- The value may match the key used for the successful smoke, so it is treated as
  compromised without reproducing or recording it.

### Remediation

- Replaced the tracked Compose example with `fake` / `fake-deterministic` and an
  empty `LLM_API_KEY`.
- Added a regression test requiring empty provider credentials in both tracked
  environment examples and safe fake defaults in the Compose example.
- Verified `.env` is ignored and untracked, frontend/build files contain no key
  injection, and no unexpected Google-key-shaped value remains in tracked
  files.
- Returned the localhost UI to the fake provider pending rotation.

### Verification and blocker

- Focused config/redaction/adapter/Compose tests: 41 passed.
- Ruff, strict Mypy, and `git diff --check` passed.
- Point 3 is blocked until the exposed replacement is rotated again, installed
  only in `.env`, and safely revalidated.

## 2026-08-07 - Points 2 and 3 live validated

### Outcome

- The owner confirmed that the exposed Gemini key was replaced locally without
  sharing the replacement.
- Ran exactly one opt-in synthetic `gemini-smoke --confirm-live` request.
- Gemini returned a schema-conforming `unsupported` proposal that passed the
  existing `StructuredOutputParser`.
- Marked points 2 and 3 complete; point 4 remains active for the remaining
  mocked pipeline/security matrix.

### Privacy-safe evidence

- Provider/model: `gemini` / `gemma-4-26b-a4b-it`.
- Token counts: 63 input, 89 output, 152 total.
- No credential, raw prompt, or raw model response was printed or recorded.

## 2026-08-07 - Point 2 adapter re-verified and tests isolated

### Outcome

- Audited the Gemini/Gemma adapter against the current official GenerateContent
  and hosted Gemma 4 documentation.
- Confirmed the model identifier, REST endpoint, system instruction, structured
  JSON schema, thinking level, request storage opt-out, and token metadata shape.
- Added a global pytest isolation fixture so ordinary regression always selects
  `fake` / `fake-deterministic` even when the ignored local `.env` selects
  Gemini.
- Added a test package marker so full strict Mypy assigns unique module names to
  the root and semantic `conftest.py` files.

### Verification

- Focused adapter/config/parser suite: 60 passed.
- Unit suite excluding the timestamp-mutating Stage 10 release test: 129 passed.
- Integration/security/semantic/result suites: 154 passed.
- API/evaluation/PostgreSQL suites: 29 passed, 4 skipped.
- UI suite: 5 passed.
- Total: 317 passed, 4 skipped; Ruff and strict Mypy passed.

### Remaining gate

- Point 2 remains blocked only on one opt-in live smoke request with a rotated
  credential. The credential shown in chat/screenshot must not be used.

## 2026-08-07 - Gemini/Gemma 4 selected and adapter implemented

### Outcome

- Owner replaced the proposed OpenAI baseline with Google Gemini Developer API
  and Gemma 4.
- Accepted ADR-0035 with hosted model `gemma-4-26b-a4b-it`, thinking level
  `minimal`, paid budget USD 0, and synthetic Chinook-only data scope.
- Implemented `GeminiLLMAdapter` over the existing pinned `httpx` dependency.
- Added JSON Schema output, `store: false`, timeout/output-token bounds,
  sanitized authentication/quota/network/timeout errors, and provider token
  metadata.
- Added factory/configuration, `.env.example`, and local Compose runtime
  injection while preserving `fake` as the safe default.
- Added Gemini-key redaction patterns and offline mock tests.

### Credential gate

- A key pasted into chat is treated as compromised.
- It was not written, printed, validated, or used by the implementation.
- Revoke it and install a replacement directly in ignored local `.env` before
  the opt-in live smoke test. Never put the replacement into chat or Git.

### Verification so far

- Ruff checks passed for the implementation files.
- Mypy passed for the changed source/tests.
- Focused suite: 31 passed with `--no-cov`.
- Full regression excluding the timestamp-mutating Stage 10 release test:
  317 passed, 4 skipped, 91.53% coverage.
- Added an explicit `gemini-smoke --confirm-live` command; its no-confirmation
  safety gate and focused provider suites pass.
- Created ignored local `.env` with the fake default, commented Gemini/Gemma
  activation values, and an intentionally empty API-key field. Keeping Gemini
  active without a replacement key was rejected because it breaks offline CI.
- Live smoke remains blocked on owner key rotation and local replacement.

## 2026-08-07 - Point 1 provider research completed

### Outcome

- Compared OpenAI GPT-5.4 mini, Google Gemini 3.6 Flash, and Anthropic Claude
  Sonnet 5 using current official documentation.
- Added `docs/llm-provider-decision.md` with capabilities, data policies, prices,
  cost estimates, rate-limit considerations, and a weighted matrix.
- Proposed pinned OpenAI model `gpt-5.4-mini-2026-03-17`, Responses API with
  `store: false`, no automatic cross-provider fallback, and synthetic data only.
- Added proposed ADR-0035.

### Decision gate

- Point 1 remains `Terblokir` until the owner approves the provider/model and a
  maximum USD 10 paid API budget for points 2-5.
- No API key was inspected, created, or used, and no paid request was made.

### Exact next action

After owner approval, accept ADR-0035, mark point 1 complete, and run the API-key
credential decision gate before implementing point 2.

## 2026-08-07 - Persistent project memory created

### Outcome

- Added repository-level `AGENTS.md` startup and continuity instructions.
- Added the `project-memory/` folder with stable context, current state, work
  log, and handoff template.
- Linked the memory entry point from the repository README.

### Reason

The user requested durable Markdown memory that remains usable after context
reduction or in a different Codex session.

### Next step

Begin point 1 of `docs/real-llm-agent-implementation-plan.md` when the user is
ready to decide provider/model and budget constraints.

## 2026-08-07 - Real LLM and bounded-agent plan created

### Outcome

- Added `docs/real-llm-agent-implementation-plan.md`.
- The plan covers points 1-7, dependencies, status tracking, detailed tasks,
  tests, acceptance criteria, milestones, risks, and Definition of Done.
- Linked the plan from README.

### Verification

- `git diff --check`: passed.
- `uv run pytest tests/unit/test_stage10_release.py -q --no-cov`: 2 passed.

### Important finding

- The current application is a mature deterministic text-to-SQL pipeline, but
  the only implemented provider remains `fake`/`fake-deterministic`.
- Points 1-5 create a real-model application; points 6-7 add the bounded agent
  behavior.
