# Current State

- Last updated: 2026-08-16
- Last known commit before current documentation work:
  `c27b15b Record Stage 10 hosted release evidence (#12)`
- Current working branch/implementation commit:
  `agent/complete-real-llm-point5` / `9c54425 Implement secure real-model evaluation through Phase N`
- Draft review: GitHub PR `#26`; all nine reported hosted checks passed on the
  implementation commit.
- Active goal: implement the real LLM and bounded-agent roadmap
- Active plan: `docs/real-llm-agent-implementation-plan.md`
- Default implementation provider: `fake` / `fake-deterministic`
- Opt-in real provider: `gemini` / `gemma-4-26b-a4b-it`

## Active roadmap status

| Poin | Work package | Status | Next requirement |
|---|---|---|---|
| 1 | Choose provider and model | Selesai | Gemini API with `gemma-4-26b-a4b-it`; ADR-0035 Accepted |
| 2 | Implement real API adapter | Selesai | Live structured smoke passed with `gemma-4-26b-a4b-it` |
| 3 | Connect secure configuration | Selesai | Second rotation stored only in ignored `.env`; exact-match audit and live smoke passed |
| 4 | Test adapter and pipeline | Selesai | 12 mocked Gemini pipeline cases; combined regression 332 passed, 4 skipped |
| 5 | Evaluate real model | Terblokir | Phase N passed 5/6 using 7/12 requests; `AGG-007` still needs an explicit cardinality/projection policy; holdout 0 |
| 6 | Create bounded agent tools | Belum dimulai | Stable/evaluated model integration |
| 7 | Implement bounded agent loop | Belum dimulai | Typed tools and authority boundaries |

## Immediate next action

Decide whether unbounded analytical lists should have a product-level default
cardinality/projection policy that justifies the 20-row, two-column
`AGG-007` expectation. Do not encode that expectation by case ID. Phase N
proved the other five corrections but missed its accuracy gate at 4/5
analytical cases, so do not freeze a candidate, open holdout, or begin points
6-7. Any new live development run needs a new versioned protocol and exact
request authorization.
The current `stage-7-v1` holdout is disqualified as an unseen final set because
a local read-only diagnostic accidentally displayed records outside the
development split. Provider calls and scored holdout cases remain zero. Before
any future final holdout, create an independently curated sealed replacement
that this agent does not inspect.

## Decisions currently awaiting the user

- Choose an explicit product policy for unbounded analytical list cardinality
  and projections, or accept that `AGG-007` remains a development mismatch and
  stop this candidate. Phase N must not be reinterpreted or retried in place.
- The existing holdout cannot be used for final claims despite zero provider
  calls/scoring; a new independently sealed holdout version is required before
  any future freeze-to-holdout transition.
- No paid budget remains: hosted Gemma 4 is free-only at the decision date and
  the paid budget is USD 0.
- No credential action remains. The active replacement must stay only in
  ignored `.env`; never copy it into chat, an example file, documentation, or
  Git.
- Public deployment remains optional and is not part of points 1-7 unless the
  user explicitly expands the scope.

## Current documentation changes

The following memory/plan work was created on 2026-08-07. Always verify with
`git status --short` because a later session may have committed it:

- `AGENTS.md`;
- `project-memory/`;
- `docs/real-llm-agent-implementation-plan.md`;
- `docs/llm-provider-decision.md`;
- a README link to the plan and memory entry point.

## Latest verification evidence

- Phase N evaluated the six remaining Phase-M development failures on frozen
  source `126c6ecdbc...` with `gemma-4-31b-it`, prompt `v5-plan`, and
  `semantic-v2`. It used 7/12 requests and passed 5/6 overall. Structured
  validity was 6/6; valid SQL and read-only execution were 5/5; execution
  accuracy was 4/5 (80%); unsafe blocking was 1/1; hallucination, false
  blocking, security bypass, measured cost, and holdout calls were zero.
  `AGG-007` alone failed because the returned relation had three columns while
  the development expectation has two (and its unexplained 20-row convention
  remains a product-policy question). No candidate was frozen.
- Pre-live verification now passes 411 tests with four PostgreSQL skips and
  90.10% coverage, plus Ruff format/lint, strict Mypy on 165 files, Stage 5-10
  offline gates, and `git diff --check`. `scripts/dev.py verify` now forces
  `fake` / `fake-deterministic` and an empty child-process credential even
  when local `.env` selects Gemini. This closes a reproducibility defect found
  when the first preflight accidentally made one free 26B request; that call
  failed on truncated JSON, did not access holdout, and produced no report.
- GitPython is pinned at 3.1.58. `pip-audit` reports no known vulnerabilities;
  the focused security/provider suite passed 51 tests. GitHub PR #26 then
  passed all nine reported checks, including source security, container
  security/Trivy, CodeQL, Docker Compose, PostgreSQL, and both Python quality
  jobs. This closes the Docker evidence gap left by the unavailable local
  engine.
- Phase M completed all 18 selected Phase-L development failures using 19/36
  requests and improved the same cases from 0/18 to 12/18. Structured validity
  was 17/18 (94.44%); all 17 analytical outcomes had valid SQL and successful
  read-only execution; execution accuracy was 12/17 (70.59%). Six passes were
  presentation-equivalent, five safe executions were substantive mismatches,
  hallucination/bypass/cost/holdout were zero, and the unsafe case failed
  closed before SQL but missed the unsupported classification. The target
  failed, so no candidate was frozen. Subsequent generic offline corrections
  for five remaining patterns pass 409 tests, four skips, 90.10% coverage,
  Ruff/format, strict Mypy on 164 files, and diff-check at source hash
  `126c6ecdbc...`; Phase N subsequently used that exact source.
- Phase L completed all 70 development cases using 74/136 requests. It passed
  52/70 overall; structured validity was 64/68 (94.12%), valid SQL and
  read-only execution were 58/61 (95.08%), and execution accuracy was 44/61
  (72.13%). Clarification was 2/2, hallucination 0/61, false blocking 0, and no
  security bypass occurred. Known-unsafe blocking was 6/7 (85.71%): `UNS-007`
  failed closed at strict plan validation without compiling/executing SQL, but
  missed the required unsupported classification. Five repairs succeeded 20%
  of the time; token usage was 156,921/29,517, P50/P95 latency was
  12,937.98/31,259.27 ms, cost USD 0, and holdout calls 0. The gate failed
  structured validity, execution accuracy, and unsafe blocking; no candidate
  was frozen.
- Phase K corrected the two Phase-J mismatches generically: explicit
  superlative rankings retain their value order with a primary-key tie-breaker,
  while bounded global-average detail filters order by their projected
  comparison value and then primary key. `RNK-004` and `SUB-001` passed exactly
  at 2/2 using 2/4 requests with no repair. Structured validity, valid SQL, and
  read-only execution were 2/2; hallucination, bypass, paid cost, and holdout
  calls remained zero. Source hash `02d6c693...` stayed stable. Pre-live gates:
  390 passed, 4 skipped, 90.26% coverage; 73 focused security/evaluator tests,
  Ruff, strict Mypy on 164 files, and `git diff --check` passed. Post-live Ruff
  formatting made no logic or provider-call change; current source hash is
  `eb467958...`, and its full regression again passed 390 with 4 skips and
  90.26% coverage.
- The exact final Stage-1 hard pilot completed all 12 selected development
  cases using 12/24 requests and no repair. Ten passed (83.33%); structured
  validity, valid SQL, and execution success were each 12/12 (100%). `RNK-004`
  and `SUB-001` executed safely with the expected three-column relation but
  differed in row values or required ordering. Same-case progression is now
  0/12 -> 2/12 -> 6/12 -> 8/12 -> 10/12. Source hash
  `54343c9e1f5d622a4943ab9dc7f4d72203327cc2c8cf2f37107ba31d8784aad5`
  was stable before/after; hallucination, bypass, paid cost, and holdout calls
  remained zero. The formal gate failed only execution accuracy because
  83.33% is below 85%; no candidate was frozen.
- Stage-1 targeted correction evidence now passes all four Phase-F failures:
  Phase G passed `FLT-003`, `JON-003`, and `JON-011` at 3/4 with 5/8 requests;
  after one fail-closed 2-request benchmark diagnostic, Phase I passed
  `SUB-004` exactly in 1/2 requests without repair. Each final passing outcome
  used one request; failed `SUB-004` diagnostics made the correction-cycle
  total 8. Hallucination, bypass, paid cost, and holdout calls remained zero.
  These successive-source smokes do not
  prove a same-source 12/12 result. The final Stage-1 source freeze passed 388 tests with
  4 PostgreSQL skips and 90.28% coverage; Ruff, strict Mypy on 164 files, and
  `git diff --check` passed.
- The `v5-plan` candidate now uses strict AnalysisPlan generation, deterministic
  schema grounding/join derivation/SQL compilation, hybrid reviewed-example
  retrieval, independent alignment validation, existing AST security, one
  sanitized repair, and adapter-level hard request metering. The new path
  requires provider `gemini` and has no FakeLLM fallback. Pre-live regression:
  370 passed, 4 skipped, 90.56% coverage; Ruff, strict Mypy on 164 files, and
  `git diff --check` passed.
- Phase A14 source freeze passed 377 tests with 4 PostgreSQL skips and 90.45%
  coverage; Ruff, strict Mypy on 164 backend/script/test source files, and
  `git diff --check` passed. A broader non-gate Mypy run found six existing
  Streamlit/Altair typing issues outside the v5-plan path.
- Phase C1 source freeze passed 378 tests with 4 PostgreSQL skips and 90.33%
  coverage; Ruff, strict Mypy on 164 backend/script/test source files, and
  `git diff --check` passed. A single transient Streamlit timeout passed on
  isolated rerun and on the complete rerun.
- Phase C2 source freeze passed 379 tests with 4 PostgreSQL skips and 90.36%
  coverage; Ruff, strict Mypy on 164 backend/script/test source files, and
  `git diff --check` passed.
- Phase C3 source freeze passed 379 tests with 4 PostgreSQL skips and 90.33%
  coverage; Ruff, strict Mypy on 164 backend/script/test source files, and
  `git diff --check` passed.
- Phase C4 source freeze passed 379 tests with 4 PostgreSQL skips and 90.30%
  coverage; Ruff, strict Mypy on 164 backend/script/test source files, and
  `git diff --check` passed.
- Phase E source freeze passed 380 tests with 4 PostgreSQL skips and 90.30%
  coverage; Ruff, strict Mypy on 164 backend/script/test source files, and
  `git diff --check` passed.
- Protocol-v4 Phase A consumed 2/2 requests and received sanitized HTTP 400
  `INVALID_ARGUMENT` before candidate generation. No SQL executed. The provider
  schema was reduced from 5,910 characters/depth 16/17 `anyOf` nodes to 1,285
  characters/depth 4/no `anyOf`; strict local validation is unchanged. Phase A2
  is capped at exactly 2 requests before any 12-case pilot.
- Phase A2 then consumed 2/2 requests: provider JSON was returned, but both
  plans failed strict local validation and no SQL was compiled. The repair code
  was too generic. Phase A3 records and returns only a sanitized first-invalid-
  field/error-type code, is capped at exactly 2 requests, and keeps holdout 0.
- Phase A3 consumed 2/2 and isolated `outputs_0_kind_missing`. Phase A4 restores
  provider typing for output/filter/order components with a 3,256-character,
  depth-8 schema while retaining simplified deep components and strict local
  validation. Its exact cap is 2; no SQL or holdout call has occurred.
- Phase A4 stopped after 1/2 maximum calls with provider HTTP 400, so its schema
  was still too complex. Phase A5 uses a 1,432-character/depth-7 envelope that
  requires only output `kind`/`alias`, plus a full unrelated plan-shape example
  in the prompt. Its exact cap is 2; holdout remains 0.
- Phase A5 also stopped after 1/2 with provider HTTP 400, proving any nested
  item properties are rejected. Phase A6 returns to the provider-accepted
  1,285-character/depth-4 generic envelope while retaining the new full shape
  example. Its exact cap is 2; no SQL or holdout call has occurred.
- Phase A6 consumed 2/2; both candidates were non-empty invalid JSON and no SQL
  was compiled. Phase A7 returns only a sanitized shape class (fenced,
  truncated, malformed, array, or text) to the single repair. Its exact cap is
  2; holdout remains 0.
- Phase A7 consumed 2/2 and confirmed a truncated JSON object. Phase A8 raises
  only the provider completion ceiling to 8,192 tokens while retaining the
  20,000-character local cap and all authority boundaries. Its exact cap is 2;
  holdout remains 0.
- Phase A8 consumed 2/2 and remained truncated at 8,192 tokens. Phase A9 keeps
  that ceiling and records only token counts plus final output character count
  on failure. Its exact cap is 2; Phase B and holdout remain closed.
- Phase A9 consumed 2/2 and measured only 318 total output tokens plus 511 final
  characters, ruling out both configured ceilings. Phase A10 records only the
  provider `finishReason` enum. Its exact cap is 2; Phase B/holdout remain
  closed.
- Phase A10 consumed 2/2 with `finishReason=STOP`, ruling out token exhaustion
  and isolating provider structured-schema decoding. Phase A11 omits
  `responseJsonSchema` only for v5-plan while retaining JSON MIME and all strict
  local enforcement.
- Phase A11 used 1/2 maximum calls and reached strict plan validation,
  deterministic SQL compilation, AST validation, read-only execution, and
  semantic-v2 comparison without repair. The case failed only because its
  actual relation had fewer columns than expected. A12 changes the unrelated
  detail-shape example from one output to identifier/name/filtering-attribute
  outputs and records only expected/actual column counts. Its exact cap is 2;
  Phase B and holdout remain closed.
- Phase A12 also used 1/2 maximum calls and increased the actual result from
  one to two of three expected columns, but did not pass. A13 adds a narrow
  deterministic completeness invariant for bounded single-table lists filtered
  by a non-primary ID. An incomplete plan is rejected before compilation and
  may use the one existing sanitized repair. Its exact cap is 2; Phase B and
  holdout remain closed.
- Phase A13 consumed 2/2 calls. Both initial and repaired plans were stopped
  before SQL because a required projection role remained missing. A14 replaces
  the generic diagnostic with one role-specific sanitized code/instruction for
  primary identifier, display, or filter identifier. Its exact cap is 2;
  Phase B and holdout remain closed.
- Phase A14 consumed 2/2 calls and passed: exact 3/3 result columns, safe SQL,
  successful read-only execution, semantic-v2 exact match, and no security
  bypass. Phase B may now run on the exact frozen source with maximum 24 calls;
  holdout remains 0.
- The frozen Phase-B pilot completed 12/12 cases using 20/24 maximum calls and
  passed 2/12 versus the same-case v4 baseline 0/12. Structured validity, valid
  SQL, and execution success were each 5/12; no schema hallucination or bypass
  occurred. Phase C1 targets the dominant safe failures with deterministic
  alias canonicalization and narrow benchmark normalization; its two-case cap
  is 4 and holdout remains 0.
- Phase C1 used 2/4 maximum calls and moved both selected cases from contract
  failure to safe SQL/execution, but each returned 2/3 columns and neither
  passed. Phase C2 adds a narrow schema-derived detail projection policy across
  four development failures; its exact cap is 8 and holdout remains 0.
- Phase C2 used 6/8 maximum calls and passed 2/4: join display and explicit
  ranking attribute cases now match, while both Invoice cases failed closed
  because repair omitted the default local relationship ID. Phase C3 completes
  only trusted base-table default roles deterministically; its cap is 4 and
  holdout remains 0.
- Phase C3 used 2/4 maximum calls: `SUB-001` now passes exact, while `FLT-005`
  safely returned one extra non-ID filtering column. C4 prunes only that narrow
  presentation role while retaining its predicate; its cap is 2 and holdout
  remains 0.
- Phase C4 passed `FLT-005` exactly in 1/2 maximum calls without repair. All
  four projection smoke cases now have passing evidence. Phase-D hard pilot v2
  is open with maximum 24 calls on exact frozen source; holdout remains 0.
- Phase-D hard pilot v2 used 15/24 maximum calls and passed 6/12, improving
  0% -> 16.67% -> 50% across the two baselines and v2. Structured validity,
  valid SQL, and execution success reached 9/12; hallucination/bypass stayed
  zero. Phase E targets two generic projection conflicts with maximum 4 calls;
  holdout remains 0.
- Phase E used 3/4 maximum calls and passed 2/2 with safe execution. Phase-F
  hard pilot v3 is open on exact source with maximum 24 calls; holdout remains
  zero.
- Phase-F hard pilot v3 used 14/24 maximum calls and passed 8/12, meeting the
  subset engineering target. Structured validity/valid SQL/execution success
  were each 10/12; hallucination/bypass remained zero; cost was USD 0. The
  formal gate is still false, no candidate is frozen, and holdout remains 0.
- The complete protocol-v3 semantic-v2 development rerun used 68 requests
  across 70 cases: 37/70 passed, structured validity 66/68 (97.06%), valid SQL
  and execution success 53/61 (86.89%), and execution accuracy 28/61 (45.90%).
  Semantic-v2 accepted 10 presentation-equivalent cases and kept 25
  substantive result mismatches rejected. Clarification was 2/2, schema
  hallucination 0/61, known-unsafe protection 7/7, paid cost USD 0, and holdout
  cases scored 0. The candidate was not frozen.
- Semantic comparison policy v2 is implemented as explicit opt-in versioning.
  The development-only audit accepted 61/61 exact and 61/61 presentation-only
  variants; rejected 122/122 substantive and 47/47 required-order variants;
  accepted 1/1 irrelevant-order variant; and scored zero holdout cases. Policy
  identity is frozen into checkpoints, provenance, candidates, and summaries.
  Combined regression passed 347 tests with 4 skipped and 90.32% coverage;
  Ruff, strict Mypy on 158 source files, and `git diff --check` passed.
- The complete 31B/v4 formal development run used 68 provider requests across
  70 cases: 27/70 passed, structured validity 66/68 (97.06%), valid SQL and
  execution success 53/61 (86.89%), execution accuracy 18/61 (29.51%),
  clarification 2/2, schema hallucination 0/61, known-unsafe protection 7/7,
  and false blocking 6/61. Token usage was 66,561 input/9,895 output,
  latency P50/P95 was 5,038.28/9,347.81 ms, paid cost was USD 0, and holdout
  calls remained zero. The candidate was not frozen.
- Point 5 runner/protocol is implemented with explicit live confirmation,
  development/holdout isolation, exact request caps, sequential cadence,
  checkpoints, source-drift hashing, candidate freezing, and privacy-safe JSON/
  Markdown reports. Offline focused tests passed.
- The prior 26B development calibration was blocked: prompt v3 passed 1/4 cases, structured
  validity was 50%, execution accuracy was 25%, P50/P95 latency was
  9,886/88,553 ms, token usage was 1,761/343, paid cost was USD 0, and holdout
  calls were zero. The candidate was not frozen.
- Point 5 implementation regression: combined 337 passed, 4 skipped, 90.53%
  coverage; Ruff, strict Mypy, and `git diff --check` passed.
- Point 4 completed on 2026-08-08 with 12 offline mocked-Gemini pipeline cases
  covering safe execution, unsupported/ambiguous requests, unknown schema
  references, dangerous and multi-statement SQL, prompt injection, timeout, and
  declared-source mismatch. Every unsafe path stopped before execution.
- Combined full regression: 332 passed, 4 skipped, 91.55% coverage. Ruff,
  strict Mypy, and `git diff --check` passed. The point 4 test makes no network
  request and does not read the local API key.
- `git diff --check`: passed after the initial real-LLM/agent plan was added.
- `uv run pytest tests/unit/test_stage10_release.py -q --no-cov`: 2 passed.
- Gemini adapter, token metadata, factory/configuration, Compose injection, and
  credential redaction runtime code have been implemented.
- Ordinary pytest runs are now forced to the fake provider even when the local
  `.env` selects Gemini, preventing accidental provider calls during regression.
- The second replacement is stored only in ignored local `.env`. An exact-value
  audit found zero matches across all tracked Git files.
- One opt-in live smoke passed: provider `gemini`, model
  `gemma-4-26b-a4b-it`, structured intent `unsupported`, 63 input tokens, 89
  output tokens, and 152 total tokens. No secret, prompt, or raw response was
  printed.
- Point 3 audit found a credential-like value in tracked
  `.env.compose.example`; it was replaced with safe fake defaults and an empty
  `LLM_API_KEY`. A regression test now enforces empty credentials in both
  tracked environment examples. Focused security/config tests: 41 passed.
- Point 3 remediation revalidation on 2026-08-08: ignored/untracked `.env`,
  empty tracked examples, zero frontend secret references, zero tracked exact-
  credential matches, successful bounded live smoke, 129 unit tests passed with
  1 timestamp-mutating test deselected, Ruff and strict Mypy passed.
- Point 2 re-verification on 2026-08-07: 60 focused adapter/config/parser tests
  passed; the remaining non-Stage-10 regression passed as 317 tests with 4
  PostgreSQL tests skipped; Ruff and Mypy passed.
- Full regression excluding the timestamp-mutating Stage 10 release test:
  317 passed, 4 skipped, 91.53% coverage; Ruff and Mypy passed.
- Point 1 research compared three providers using official documentation.
- ADR-0035 is Accepted for Gemini API `gemma-4-26b-a4b-it`.

## Known caution

Running the Stage 10 evaluator/test can rewrite the timestamp inside
`reports/evaluation/stage-10-readiness.json`. Do not retain a timestamp-only
diff unless intentionally regenerating release evidence.
