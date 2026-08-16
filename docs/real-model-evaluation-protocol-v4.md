# Real-Model Evaluation Protocol v4

- Status: Phase-L complete development failed formal gates; no candidate was
  frozen and holdout remained sealed
- Provider/model: Gemini Developer API / `gemma-4-31b-it`
- Candidate runtime: `v5-plan`
- Result-comparison policy: `semantic-v2`
- Semantic/schema: `v1` / pinned Chinook v1.4.5 snapshot
- Temperature/thinking: `0` / `minimal`
- Paid budget: USD 0
- Date versioned: 2026-08-08
- Holdout calls authorized: 0

## Purpose

Protocol v3 showed that asking Gemma to write unrestricted SQL reached only
45.90% development execution accuracy. Protocol v4 keeps Gemma but changes its
authority: Gemma emits a strict `AnalysisPlan`; deterministic code canonicalizes
identifiers, derives approved shortest join paths, compiles every SQL token,
checks plan/SQL alignment, runs the existing AST security validator, and only
then permits read-only execution.

The new path does not instantiate or fall back to `FakeLLMAdapter`. Existing
fake behavior remains available only for legacy offline regression. The
holdout remains sealed, thresholds are unchanged, and this pilot cannot freeze
a candidate because it is an explicit development subset.

## Versioned improvements

1. strict typed planning contract instead of free-form SQL generation;
2. physical schema grounding with fail-closed unknown identifiers;
3. hybrid lexical/metric/table retrieval over reviewed examples only;
4. approved unique-shortest-path join derivation that ignores model join hints;
5. deterministic compiler for projections, aggregates, filters, time buckets,
   ranking, average benchmarks, and bounded relationship subqueries;
6. independent SQL parse/alignment check plus the existing SQL security policy;
7. at most one repair using only a sanitized error code; security violations
   are never sent to repair;
8. adapter-level request metering so the initial call and repair both consume
   the same hard cap.

## Frozen development subsets and exact caps

### Phase A - provider/schema compatibility smoke

- Cases: `FLT-003`
- Baseline v4/semantic-v2 result: failed
- Maximum provider requests: exactly 2
- Maximum repair calls: 1
- Minimum interval between all actual requests: 6 seconds
- Stop condition: do not run Phase B if the provider rejects the plan schema or
  the runtime cannot complete the case safely.

Phase A consumed exactly 2/2 authorized requests. The evaluator request and a
sanitized classification request both returned HTTP 400 `INVALID_ARGUMENT`;
no candidate content or SQL was produced. The original provider schema was
5,910 characters, depth 16, and contained 17 `anyOf` nodes plus unsupported
string constraints.

### Phase A2 - simplified provider-schema compatibility smoke

- Cases: `FLT-003`
- Maximum provider requests: exactly 2
- Maximum repair calls: 1
- Minimum interval between all actual requests: 6 seconds
- Provider schema: 1,285 characters, depth 4, no `anyOf`, `pattern`,
  `minLength`, or `maxLength`
- Local validation: unchanged strict Pydantic AnalysisPlan contract
- Stop condition: do not run Phase B unless this case reaches the safe
  execution/comparison pipeline.

Phase A2 consumed exactly 2/2 requests. The provider accepted the simplified
schema and returned JSON on both the initial and repair calls, but both failed
strict local validation. The old repair mapping collapsed every parse/contract
failure into `declared_schema_mismatch`, so the repair lacked actionable but
safe feedback. No SQL was compiled or executed.

### Phase A3 - sanitized field-level repair compatibility smoke

- Cases: `FLT-003`
- Maximum provider requests: exactly 2
- Maximum repair calls: 1
- Minimum interval between all actual requests: 6 seconds
- Change from A2: JSON/shape/Pydantic failures now map to a bounded sanitized
  field path and error type; reports retain only this code and repair count
- Stop condition: do not run Phase B unless the complete safe pipeline is
  reached.

Phase A3 consumed exactly 2/2 requests. The sanitized final code was
`outputs_0_kind_missing`, proving that the provider's generic nested-object
schema allowed Gemma to omit the core output discriminator even after repair.
No SQL was compiled or executed.

### Phase A4 - typed component provider-schema compatibility smoke

- Cases: `FLT-003`
- Maximum provider requests: exactly 2
- Maximum repair calls: 1
- Minimum interval between all actual requests: 6 seconds
- Provider schema: 3,256 characters, depth 8; `outputs`, top-level `filters`,
  and `order_by` are typed, while deep benchmark/related-filter contents remain
  prompt-guided and strictly validated locally
- Stop condition: do not run Phase B unless the complete safe pipeline is
  reached.

Phase A4 stopped after 1/2 maximum requests with provider HTTP 400 before
candidate generation, confirming that the 3,256-character/depth-8 component
schema still exceeds this hosted model's accepted complexity. The unused
request was not consumed. No SQL was compiled or executed.

### Phase A5 - shallow output-core schema plus full shape example

- Cases: `FLT-003`
- Maximum provider requests: exactly 2
- Maximum repair calls: 1
- Minimum interval between all actual requests: 6 seconds
- Provider schema: 1,432 characters, depth 7; only output `kind` and `alias`
  are provider-required inside nested objects
- Prompt guidance: one complete unrelated AnalysisPlan shape example plus the
  complete component contract; all values remain question/schema grounded
- Local validation: unchanged strict contract, grounding, compilation,
  alignment, AST validation, and read-only execution
- Stop condition: do not run Phase B unless the complete safe pipeline is
  reached.

Phase A5 stopped after 1/2 maximum requests with provider HTTP 400 before
candidate generation. This confirms the hosted model rejects nested item
properties even when the overall schema is only 1,432 characters. No SQL was
compiled or executed.

### Phase A6 - provider-accepted generic envelope plus full shape example

- Cases: `FLT-003`
- Maximum provider requests: exactly 2
- Maximum repair calls: 1
- Minimum interval between all actual requests: 6 seconds
- Provider schema: 1,285 characters, depth 4, previously proven accepted
- Prompt guidance: complete component contract plus one complete unrelated
  AnalysisPlan shape example
- Local validation and authority boundaries: unchanged and strict
- Stop condition: do not run Phase B unless the complete safe pipeline is
  reached.

Phase A6 consumed exactly 2/2 requests. Both provider responses were non-empty
but invalid JSON, and therefore stopped before local plan validation. The
generic `invalid_plan_json` feedback did not distinguish truncation, fences, or
other malformed shapes. No SQL was compiled or executed.

### Phase A7 - sanitized malformed-JSON shape repair smoke

- Cases: `FLT-003`
- Maximum provider requests: exactly 2
- Maximum repair calls: 1
- Minimum interval between all actual requests: 6 seconds
- Change from A6: malformed JSON is classified only as fenced, truncated
  object, malformed object, array text, or non-JSON text; raw content remains
  discarded
- Stop condition: do not run Phase B unless the complete safe pipeline is
  reached.

Phase A7 consumed exactly 2/2 requests and classified the final response as a
truncated JSON object. No SQL was compiled or executed.

### Phase A8 - increased provider completion budget

- Cases: `FLT-003`
- Maximum provider requests: exactly 2
- Maximum repair calls: 1
- Minimum interval between all actual requests: 6 seconds
- Provider output-token ceiling: 8,192, frozen in checkpoint/provenance
- Local output-character ceiling: unchanged at 20,000; oversized completed
  plans still fail closed
- All schema, grounding, compiler, alignment, security, and read-only boundaries
  remain unchanged
- Stop condition: do not run Phase B unless the complete safe pipeline is
  reached.

Phase A8 consumed exactly 2/2 requests and still produced truncated objects at
8,192 output tokens. No SQL was compiled or executed. The exception path did
not yet retain token/character counts, so one final diagnostic smoke is needed
before deciding whether a larger ceiling is justified.

### Phase A9 - privacy-safe completion telemetry smoke

- Cases: `FLT-003`
- Maximum provider requests: exactly 2
- Maximum repair calls: 1
- Minimum interval between all actual requests: 6 seconds
- Provider output-token ceiling: 8,192
- Recorded fields on failure: input/output/reasoning/total token counts and
  final candidate character count only; raw output remains discarded
- Stop condition: Phase B remains closed; use the measurements to select the
  next bounded change.

Phase A9 consumed exactly 2/2 requests. Total output across both calls was only
318 tokens and the final candidate was 511 characters, proving the truncation
was not caused by either the 8,192-token provider ceiling or the 20,000-
character local ceiling. No SQL was compiled or executed.

### Phase A10 - provider finish-reason diagnostic smoke

- Cases: `FLT-003`
- Maximum provider requests: exactly 2
- Maximum repair calls: 1
- Minimum interval between all actual requests: 6 seconds
- Provider output-token ceiling: 8,192
- New recorded field: provider `finishReason` enum only, capped at 100
  characters; no finish message or raw content is retained
- Stop condition: Phase B remains closed pending a valid complete plan.

Phase A10 consumed exactly 2/2 requests. The final provider reason was `STOP`,
not `MAX_TOKENS`, while the same 318-token/511-character truncated shape
recurred. This isolates a hosted Gemma structured-schema decoding behavior. No
SQL was compiled or executed.

### Phase A11 - JSON MIME mode with strict local contract

- Cases: `FLT-003`
- Maximum provider requests: exactly 2
- Maximum repair calls: 1
- Minimum interval between all actual requests: 6 seconds
- Provider mode: `application/json` MIME without `responseJsonSchema` only for
  the `v5-plan` path
- Provider output-token ceiling: 8,192; local characters: 20,000
- Enforcement: unchanged strict AnalysisPlan validation, schema grounding,
  deterministic compilation, alignment, AST security, and read-only execution
- Legacy direct-SQL path: still uses its existing provider response schema
- Stop condition: Phase B remains closed unless the complete safe pipeline is
  reached.

Phase A11 completed after 1/2 maximum requests. Gemma returned a locally valid
plan without repair; the deterministic compiler produced validator-approved
SQL and the read-only executor completed it. The case still failed semantic-v2
comparison because the actual result had fewer columns than the three-column
expected relation. This is the first v5-plan run to complete the full safe
pipeline. No security bypass or schema hallucination occurred.

### Phase A12 - general detail-shape guidance and count telemetry

- Cases: `FLT-003`
- Maximum provider requests: exactly 2
- Maximum repair calls: 1
- Minimum interval between all actual requests: 6 seconds
- Provider output-token ceiling: 8,192
- Change from A11: the unrelated Customer example demonstrates a filtered
  detail relation with identifier, useful name, and filtering attribute rather
  than a one-column relation
- Recorded comparison fields: expected and actual column counts only; aliases,
  values, SQL, questions, plans, prompts, and raw provider content remain absent
- All local contracts, grounding, compiler, alignment, AST security, and
  read-only execution boundaries remain unchanged
- Stop condition: Phase B remains closed unless this compatibility case passes.

Phase A12 completed after 1/2 maximum requests. The plan again passed without
repair and completed safe execution. Its actual relation increased from one
column in A11 to two of three expected columns, so the general shape example
improved the observed direction but did not satisfy the compatibility gate.
No security bypass or schema hallucination occurred.

### Phase A13 - deterministic filtered-ID projection completeness

- Cases: `FLT-003`
- Maximum provider requests: exactly 2
- Maximum repair calls: 1
- Minimum interval between all actual requests: 6 seconds
- Provider output-token ceiling: 8,192
- New deterministic invariant: a bounded, single-table, non-aggregate entity
  list filtered by exactly one non-primary ID must project the table's single
  primary key, `Name`/`Title` display column, and that filtering ID
- Scope exclusions: no aggregation, joined detail output, related subquery,
  text/null filter, composite key, or table without `Name`/`Title` is changed
- Failure behavior: reject before compilation with the sanitized code
  `incomplete_filtered_entity_projection`, then permit the existing single
  repair; the runtime never invents a column or rewrites the model's plan
- All strict local contracts and security/execution boundaries remain unchanged
- Stop condition: Phase B remains closed unless this compatibility case passes.

Phase A13 consumed exactly 2/2 requests. The first plan was stopped before SQL
compilation by the new completeness invariant; the one repair still omitted a
required role and was also stopped before SQL. The final sanitized error was
`incomplete_filtered_entity_projection`. No SQL was compiled or executed, and
no security bypass occurred.

### Phase A14 - role-specific sanitized projection repair

- Cases: `FLT-003`
- Maximum provider requests: exactly 2
- Maximum repair calls: 1
- Minimum interval between all actual requests: 6 seconds
- Provider output-token ceiling: 8,192
- Change from A13: the invariant emits exactly one sanitized missing-role code:
  primary identifier, `Name`/`Title` display, or filter identifier
- Repair instruction: add the missing role while retaining the other required
  outputs; the prompt still supplies all identifier values through the normal
  bounded schema context, never through diagnostic reports
- Reports retain only the role code, request/repair counts, tokens, character
  count, and finish reason; no column names, SQL, values, or raw content
- All strict local and security/execution boundaries remain unchanged
- Stop condition: Phase B remains closed unless this compatibility case passes.

Phase A14 consumed exactly 2/2 requests and passed. The first plan was rejected
before compilation for one missing role; the role-specific repair returned a
complete strict plan. Validator-approved SQL executed read-only, all three
expected columns matched exactly under semantic-v2, and no security bypass or
schema hallucination occurred. Phase B is therefore open under the frozen cap
below; holdout remains sealed.

### Phase B - previously failed hard-case pilot

- Cases: `FLT-003`, `FLT-005`, `JON-001`, `JON-003`, `JON-004`, `JON-011`,
  `TIM-001`, `RNK-003`, `RNK-004`, `SUB-001`, `SUB-004`, `SUB-005`
- Baseline v4/semantic-v2 result: 0/12 passed
- Maximum provider requests: exactly 24
- Maximum repair calls: 1 per case
- Minimum interval between all actual requests: 6 seconds
- Selection source: development failures only; no holdout case was inspected or
  selected.
- Source freeze: the exact A14 runtime that passed `FLT-003`; no prompt,
  semantic, compiler, comparator, or security changes are permitted during the
  pilot.
- Output identity: `stage-7-gemini-31b-v5-plan-hard-pilot-v1` with a unique
  checkpoint; replacement requires an explicit new version.

The CLI requires `--max-requests` to equal these maximums. The adapter reserves
each real provider call before network I/O and fails closed when the cap is
exhausted. A valid first plan consumes one call, so actual usage may be lower
than the maximum.

Phase B completed all 12 cases with 20/24 maximum requests. It passed 2/12
cases versus the same-case v4 baseline of 0/12, so measured execution accuracy
improved from 0% to 16.67% but missed the 8/12 engineering target. Structured
plan validity, valid SQL, and execution success were each 5/12 (41.67%); no
schema hallucination or security bypass occurred. One successful case was a
presentation-equivalent semantic-v2 match. Eight cases entered repair and only
one repair succeeded. The dominant sanitized failures were invalid display
aliases and overly strict benchmark field shapes; three safely executed cases
remained substantive mismatches. Paid cost was USD 0 and holdout calls stayed
zero.

### Phase C1 - deterministic alias and benchmark compatibility smoke

- Cases: `JON-003`, `SUB-001`
- Phase-B baseline: 0/2 passed
- Maximum provider requests: exactly 4
- Maximum repair calls: 1 per case
- Minimum interval between all actual requests: 6 seconds
- Candidate changes:
  - canonicalize output aliases to safe ASCII SQL identifiers and rewrite only
    matching order/HAVING alias references before strict validation;
  - qualify a simple unqualified benchmark column/group key using the benchmark
    table already supplied by the plan, followed by normal schema grounding;
  - accept `aggregate=average` as an explicit synonym on `global_average`,
    whose compiler behavior is already fixed to `AVG`.
- Fail closed: empty/overlong/non-ASCII-leading aliases, expressions instead of
  simple benchmark identifiers, unknown schema references, duplicate aliases,
  and every existing security violation still fail validation.
- Stop condition: do not run a v2 hard pilot unless both smoke cases reach the
  complete safe comparison pipeline and at least one passes.

Phase C1 completed both cases with only 2/4 maximum requests. Both prior
contract failures were eliminated: each plan compiled to validator-approved
SQL and executed read-only. Both still failed comparison with two actual
columns versus three expected columns, so the smoke passed the safe-pipeline
condition but failed its quality condition at 0/2. No security bypass or schema
hallucination occurred, and hard pilot v2 remains closed.

### Phase C2 - schema-derived bounded-detail projection policy

- Cases: `FLT-005`, `JON-003`, `RNK-004`, `SUB-001`
- Phase-B baseline: 0/4 passed
- Maximum provider requests: exactly 8
- Maximum repair calls: 1 per case
- Minimum interval between all actual requests: 6 seconds
- Deterministic required roles for non-aggregate bounded detail lists:
  - base table single primary key;
  - base `Name`/`Title`, or for tables without one, local relationship ID plus
    a recognized core value column (`Total`, `UnitPrice`, or `Milliseconds`);
  - display columns of a uniquely reachable related entity named in the
    question;
  - a physical base-table attribute explicitly named in the question.
- Existing foreign-ID filtered-list rule remains active.
- The policy only rejects an incomplete plan with one sanitized role code and
  uses the existing bounded repair. It never synthesizes outputs or SQL.
- Aggregations, related subqueries, composite keys, ambiguous join paths, and
  unknown identifiers remain excluded/fail closed.
- Stop condition: do not run hard pilot v2 unless all four cases reach safe
  execution and at least three pass semantic-v2 comparison.

Phase C2 completed all four cases with 6/8 maximum requests and passed 2/4.
`JON-003` and `RNK-004` moved from Phase-B failures to correct safe results.
Both Invoice cases still failed closed after one repair with
`missing_entity_relationship_projection`; Gemma did not add the schema-local
relationship ID when it was not explicit in the question. No unsafe SQL was
compiled for those failures, no security bypass occurred, and hard pilot v2
remains closed because the 3/4 threshold was missed.

### Phase C3 - trusted base-detail projection completion smoke

- Cases: `FLT-005`, `SUB-001`
- Phase-B/C2 baseline: 0/2 passed
- Maximum provider requests: exactly 4
- Maximum repair calls: 1 per case
- Minimum interval between all actual requests: 6 seconds
- Change from C2: for a bounded non-aggregate detail list, reorder and complete
  only trusted base-table default roles from the schema snapshot: single
  primary key, display columns or local foreign-key columns, then recognized
  core value (`Total`, `UnitPrice`, `Milliseconds`).
- Synthesized plan outputs contain only canonical allowlisted `Table.Column`
  references and safe aliases derived from physical column names. They still
  pass plan/SQL alignment, AST validation, declared-source validation, and the
  read-only executor.
- Related-entity displays, named attributes, filters, joins, aggregates,
  values, limits, and ordering are never synthesized by this completion step.
- Stop condition: do not run hard pilot v2 unless both Invoice cases pass.

Phase C3 completed both cases with 2/4 maximum requests. `SUB-001` moved to an
exact three-column safe pass without repair. `FLT-005` executed safely but had
four actual columns because the model retained the non-ID filtering column in
addition to the three canonical base defaults. No bypass or hallucination
occurred. The required 2/2 threshold was missed and hard pilot v2 remains
closed.

### Phase C4 - deterministic filter-only presentation pruning

- Cases: `FLT-005`
- Phase-B/C3 baseline: failed
- Maximum provider requests: exactly 2
- Maximum repair calls: 1
- Minimum interval between all actual requests: 6 seconds
- Change from C3: after predicates are grounded, remove from detail projection
  only a base-table, non-ID, non-benchmark filter target that is not physically
  named in the question and is not referenced by output ordering.
- The predicate itself is never removed or changed. Foreign-ID filters,
  benchmark targets, named attributes, ordered outputs, joins, values, and
  canonical base defaults are preserved.
- Stop condition: do not run hard pilot v2 unless `FLT-005` passes.

Phase C4 completed with 1/2 maximum requests and passed exactly: three expected
and actual columns, validator-approved SQL, safe read-only execution, and exact
semantic-v2 comparison without repair. No bypass or hallucination occurred.
Together, C2-C4 now provide passing evidence for all four selected projection
cases. Hard pilot v2 is open on this exact frozen source; holdout stays sealed.

### Phase D - hard pilot v2

- Cases: `FLT-003`, `FLT-005`, `JON-001`, `JON-003`, `JON-004`, `JON-011`,
  `TIM-001`, `RNK-003`, `RNK-004`, `SUB-001`, `SUB-004`, `SUB-005`
- Baselines: prompt-v4 0/12; v5-plan hard pilot v1 2/12
- Maximum provider requests: exactly 24
- Maximum repair calls: 1 per case
- Minimum interval between all actual requests: 6 seconds
- Source freeze: exact Phase-C4 source; no runtime, semantic, prompt, compiler,
  comparator, or security changes during the pilot
- Output identity: `stage-7-gemini-31b-v5-plan-hard-pilot-v2`
- Engineering target: at least 8/12, zero schema hallucination reaching
  execution, and zero security bypass.
- Interpretation: even a target pass remains subset evidence and does not open
  holdout or replace the formal full-development 85% gate.

Phase D completed all 12 cases with 15/24 maximum requests and passed 6/12.
Execution accuracy improved from prompt-v4's 0% and pilot-v1's 16.67% to 50%.
Structured plan validity, valid SQL, and execution success each reached 9/12
(75%). Three successful results were presentation-equivalent; three safe
executions remained substantive mismatches. Schema hallucination and security
bypass stayed zero, paid cost was USD 0, and holdout calls stayed zero. The
8/12 engineering target and formal thresholds were not met.

### Phase E - ID-filter and aggregate-entity projection smoke

- Cases: `FLT-003`, `RNK-003`
- Phase-D baseline: 0/2 passed
- Maximum provider requests: exactly 4
- Maximum repair calls: 1 per case
- Minimum interval between all actual requests: 6 seconds
- Changes:
  - when a base foreign-ID filter exactly represents a related entity named in
    the question, do not additionally require that related entity's display;
  - for a bounded aggregate/metric entity ranking, canonically complete only
    the base single primary key and display dimensions as grouped outputs.
- Existing filter-ID projection, join grounding, aggregation primitives,
  ordering, alignment, AST security, and read-only execution remain unchanged.
- Stop condition: do not run hard pilot v3 unless both cases pass.

Phase E completed both cases with 3/4 maximum requests and passed 2/2.
`FLT-003` passed exactly after one bounded repair; `RNK-003` passed as a
value-aligned semantic-v2 result without repair. Both produced validator-
approved SQL and safe read-only execution with zero bypass/hallucination.
Hard pilot v3 is open on this exact source; holdout remains sealed.

### Phase F - hard pilot v3

- Cases: the same 12 development cases used by Phases B and D
- Baselines: prompt-v4 0/12; pilot-v1 2/12; pilot-v2 6/12
- Maximum provider requests: exactly 24
- Maximum repair calls: 1 per case
- Minimum interval between all actual requests: 6 seconds
- Source freeze: exact Phase-E source; no changes during the pilot
- Output identity: `stage-7-gemini-31b-v5-plan-hard-pilot-v3`
- Engineering target: at least 8/12, zero schema hallucination reaching
  execution, and zero security bypass.
- Formal boundary: success is not authorization for a full-development run,
  holdout access, candidate freezing, or points 6-7.

Phase F completed all 12 cases with 14/24 maximum requests and achieved the
engineering target at 8/12 (66.67%). Structured plan validity, valid SQL, and
execution success each reached 10/12 (83.33%). Four passes were presentation-
equivalent and two safe executions remained substantive mismatches. One case
encountered a sanitized provider error and one exhausted plan repair. Schema
hallucination and security bypass stayed zero, paid cost was USD 0, and holdout
calls stayed zero.

The measured same-case progression is prompt-v4 0/12, v5-plan pilot-v1 2/12,
pilot-v2 6/12, and pilot-v3 8/12. This proves a development-subset accuracy
increase, not formal qualification. The report's formal gate remains false
because 66.67% execution accuracy and 83.33% structured validity are below the
unchanged 85% and 99% thresholds. No candidate is frozen and holdout remains
sealed. A complete v5-plan development run would permit up to 136 provider
requests and requires a separately frozen authorization/protocol decision.

### Phase G - remaining-failure correction smoke

- Cases: `FLT-003`, `JON-003`, `JON-011`, `SUB-004`
- Phase-F baseline: 0/4 passed; the other eight hard-pilot cases remain outside
  this smoke.
- Maximum provider requests: exactly 8.
- Maximum actual requests per case: 2 shared between one transient-provider
  retry and the existing single invalid-plan repair. Retry does not increase
  the previous hard cap.
- Minimum interval between all actual requests: 6 seconds.
- Changes:
  - retry one transient provider failure with deterministic bounded backoff;
  - normalize `values=null` to an empty list only when a benchmark or null
    operator semantically requires no literal values;
  - use one unambiguous `project_verified` semantic metric as the sole measure
    instead of a competing model aggregation;
  - derive bounded-list entity grain from the first explicitly named schema
    entity and apply stable default detail/grouped-result ordering only when the
    user supplied no order.
- Existing unique approved join derivation, deterministic SQL compilation,
  plan/SQL alignment, AST security, read-only execution, and semantic-v2 result
  comparison remain mandatory.
- Output identity: `stage-7-gemini-31b-v5-plan-stage1-smoke-v1`.
- Engineering target: at least 3/4 passes, zero schema hallucination reaching
  execution, and zero security bypass. A 2/4 result would reach the previously
  stated 10/12 hard-subset floor but would not satisfy this stricter smoke
  target.
- Formal boundary: this development-only smoke cannot freeze a candidate,
  authorize the 136-request complete-development run, open holdout, or begin
  points 6-7.

Phase G completed all four cases with 5/8 maximum requests and met its target
at 3/4. `FLT-003`, `JON-003`, and `JON-011` produced validator-approved SQL,
safe read-only execution, and matching results; `JON-011` was accepted as a
value-aligned presentation equivalent. `SUB-004` remained fail-closed because
both its first plan and bounded repair represented `benchmark.group_by` with a
non-string type. Schema hallucination and security bypass remained zero,
estimated paid cost stayed USD 0, and holdout calls stayed zero.

### Phase H - grouped-benchmark shape correction smoke

- Case: `SUB-004` only.
- Phase-G baseline: failed closed after one repair.
- Maximum provider requests: exactly 2.
- Minimum interval between actual requests: 6 seconds.
- Changes:
  - normalize only a singleton string list for `benchmark.group_by` into its
    sole `Table.Column` value;
  - map any other invalid `benchmark.group_by` shape to one sanitized,
    role-specific repair instruction.
- Multiple values, non-string singleton values, objects, and unknown schema
  references remain invalid. All compiler, alignment, AST, and read-only
  boundaries remain unchanged.
- Output identity: `stage-7-gemini-31b-v5-plan-stage1-sub004-smoke-v1`.
- Engineering target: 1/1 with validator-approved SQL, exact or semantic-v2
  equivalent result, zero hallucination, and zero bypass.
- Formal boundary: a pass completes only this targeted development correction;
  it does not authorize full development, candidate freeze, holdout, or points
  6-7.

Phase H used 2/2 maximum requests and remained fail-closed. The singleton
`group_by` type reached the strict benchmark validator, which then rejected an
inconsistent benchmark kind/grouping combination after one generic repair. No
SQL was compiled or executed; hallucination, bypass, paid cost, and holdout
calls remained zero.

### Phase I - deterministic benchmark-kind correction smoke

- Case: `SUB-004` only.
- Phase-H baseline: 0/1, strict benchmark contract failure.
- Maximum provider requests: exactly 2.
- Minimum interval between actual requests: 6 seconds.
- Changes:
  - when a recognized average benchmark has one validated `group_by` string,
    canonicalize its kind to `group_average` before strict validation;
  - map other benchmark-level value errors to a sanitized instruction that
    distinguishes global from grouped-average contracts.
- No aggregate, grouping column, table, filter operator, or literal value is
  invented. Unknown identifiers and unsupported benchmark aggregates remain
  invalid, and all downstream security/read-only boundaries remain unchanged.
- Output identity: `stage-7-gemini-31b-v5-plan-stage1-sub004-smoke-v2`.
- Engineering target and formal boundary are unchanged from Phase H.

Phase I passed `SUB-004` exactly in 1/2 maximum requests without repair. The
plan passed strict local validation, deterministic compilation, alignment, AST
security, and read-only execution; all 3/3 expected columns and rows matched.
Together, Phase G and Phase I provide passing targeted evidence for all four
Phase-F failures; each final passing outcome used one request. The failed
`SUB-004` attempts in Phases G and H consumed four additional requests, so this
correction cycle used 8 bounded requests in total.
Hallucination, bypass, paid cost, and holdout calls remained zero.

This is staged development evidence, not a claim that the full 12-case hard
subset passes 12/12 on one exact source freeze. The next accuracy measurement
should rerun those same 12 cases on the final Stage-1 source with a maximum of 24
requests. That run is not authorized by this correction smoke; the 136-request
complete-development run, candidate freeze, holdout, and points 6-7 remain
closed.

### Phase J - exact final Stage-1 hard pilot

- Cases: the same 12 development cases used by Phases B, D, and F.
- Authorization: owner-approved development-only run with a hard maximum of 24
  provider requests and one optional repair per case.
- Frozen runtime: `v5-plan`, `gemma-4-31b-it`, `semantic-v2`, 8,192 output
  tokens, six-second minimum interval, and source hash
  `54343c9e1f5d622a4943ab9dc7f4d72203327cc2c8cf2f37107ba31d8784aad5`.
- Output identity:
  `stage-7-gemini-31b-v5-plan-stage1-hard-pilot-v1`.
- Formal boundary: the subset cannot freeze a candidate, open holdout, or
  authorize points 6-7 even if it meets the subset engineering target.

Phase J completed all 12 cases using 12/24 maximum requests and no repair. Ten
cases passed (83.33%), improving the same-case sequence from 0/12 to 2/12,
6/12, 8/12, and now 10/12. Structured plan validity, valid SQL, and execution
success were all 12/12 (100%). `RNK-004` and `SUB-001` reached safe read-only
execution with the expected three-column relation but failed semantic-v2
because row values or required ordering differed.

No schema hallucination or security bypass was observed. The run used 26,989
input tokens and 5,825 output tokens; latency P50/P95 was 14,153.68/22,489.87
ms, measured cost was USD 0, and holdout calls remained zero. The source hash
was identical before and after the run. The formal gate remains failed because
83.33% execution accuracy is below the unchanged 85% threshold. Do not freeze
a candidate, open holdout, run the maximum-136 complete development split, or
begin points 6-7 from this subset result.

### Phase K - bounded ordering-regression correction smoke

- Cases: `RNK-004` and `SUB-001` only, both development cases.
- Phase-J baseline: 0/2; both had valid plans, valid SQL, successful read-only
  execution, and exact three-column identity, but row values or required order
  differed.
- Maximum provider requests: exactly 4, shared as at most two requests per case
  between the initial plan, one transient retry, or one bounded plan repair.
- Minimum interval between actual requests: 6 seconds.
- Source freeze:
  `02d6c693f8e506783d61c4787d130cbc8ae1e84f326dea73fd71be00cf21d1f9`.
- Generic changes:
  - recognize bounded superlatives such as `longest`/`terpanjang` as explicit
    ranking intent, preserve the grounded value ordering, and append the base
    primary key as an ascending deterministic tie-breaker;
  - for a bounded detail list with exactly one global-average comparison,
    deterministically order the projected comparison column descending for
    `>`/`>=` and ascending for `<`/`<=`, followed by the base primary key;
  - never inspect case IDs, expected SQL, or expected rows at runtime.
- Existing strict plan validation, approved joins, deterministic compiler,
  plan/SQL alignment, AST security, read-only execution, and `semantic-v2`
  comparison remain unchanged.
- Output identity:
  `stage-7-gemini-31b-v5-plan-stage2-ordering-smoke-v1`.
- Engineering target: 2/2 matching results, 100% structured/SQL/execution,
  zero schema hallucination, and zero security bypass.
- Formal boundary: even 2/2 cannot freeze a candidate, authorize the max-136
  complete development run, open holdout, or begin points 6-7.

Pre-live verification passed: 390 tests passed, four PostgreSQL tests skipped,
coverage was 90.26%, and 73 focused security/evaluator tests passed. Ruff,
strict Mypy on 164 source files, and `git diff --check` also passed. The owner
explicitly authorized the targeted correction and limited rerun.

Phase K passed 2/2 exactly using 2/4 maximum requests and no repair. Both cases
had valid structured plans, validator-approved SQL, successful read-only
execution, exact three-column identity, and exact result comparison. The run
used 3,973 input tokens and 941 output tokens, measured cost was USD 0, and
schema hallucination/security bypass/holdout calls remained zero. Source hash
`02d6c693f8e506783d61c4787d130cbc8ae1e84f326dea73fd71be00cf21d1f9`
was identical before and after the run.

This closes the two known Phase-J mismatches but remains staged development
evidence, not a formal full-development result. The maximum-136 complete
development run, candidate freeze, holdout, and points 6-7 require a separate
owner decision and remain closed.

After the live report was finalized, Ruff applied formatting-only changes to
the implementation and test files. No additional provider call was made. The
current source hash is
`eb467958f5eea831f0a2e5628925a7a06243bfc87c481c25b140d677b56034b4`;
the Phase-K report correctly remains bound to its execution-time hash above.
The formatted source reran the full offline regression at 390 passed, four
skipped, and 90.26% coverage.

### Phase L - complete v5-plan development evaluation

- Authorization: the owner explicitly authorized all remaining Point-5 steps,
  with candidate freeze and holdout strictly conditional on development gates.
- Split: all 70 development cases from immutable `stage-7-v1`; holdout cases
  remain unscored and are not selected or inspected during this phase.
- Maximum provider requests: exactly 136. The `v5-plan` runtime reserves at
  most two calls for each of 68 LLM-invoking cases; valid first plans consume
  only one call.
- Minimum interval between actual requests: 6 seconds.
- Frozen runtime: Gemini `gemma-4-31b-it`, prompt `v5-plan`, 8,192 output
  tokens, thinking `minimal`, temperature 0, semantic version `v1`, comparison
  policy `semantic-v2`, and source hash
  `eb467958f5eea831f0a2e5628925a7a06243bfc87c481c25b140d677b56034b4`.
- Output identity: `stage-7-gemini-31b-v5-plan-development-v1`, with a unique
  checkpoint and no replacement without an explicit new version.
- Frozen gates: structured validity >= 99%, development execution accuracy >=
  85%, known-unsafe blocking 100%, clarification accuracy >= 90%, schema
  hallucination <= 5%, and zero security bypass.
- Stop condition: if any development gate fails, do not freeze a candidate,
  calculate or run holdout, or begin points 6-7. Record the failed result and
  keep Point 5 blocked.
- Success condition: only a passing report may be frozen. After freeze, compute
  the aggregate holdout request cap without exposing case content, then run the
  sealed holdout exactly once under the frozen candidate.

Pre-live gates on the exact source passed: 390 tests passed, four PostgreSQL
tests skipped, 90.26% coverage, Ruff/format, strict Mypy on 164 files, and
`git diff --check`. Local Gemini configuration is present; paid budget remains
USD 0 and FakeLLM is unavailable on the live `v5-plan` path.

Phase L completed all 70 development cases using 74/136 maximum requests. It
passed 52/70 cases overall. Structured-output validity was 64/68 (94.12%),
valid SQL and read-only execution were each 58/61 (95.08%), and execution
accuracy was 44/61 (72.13%). Clarification accuracy was 2/2, schema
hallucination was 0/61, false blocking was zero, and no security bypass
occurred. Known-unsafe blocking was only 6/7 because `UNS-007` failed closed at
strict plan validation instead of returning the required unsupported result;
no SQL was compiled or executed for that failure.

The run used 156,921 input and 29,517 output tokens, with P50/P95 latency of
12,937.98/31,259.27 ms and measured cost USD 0. Five repairs had a 20% success
rate. `semantic-v2` accepted 22 presentation-equivalent passes and rejected 14
substantive result mismatches. Source hash stayed frozen and holdout calls
remained zero.

The formal gate failed structured validity, execution accuracy, and known-
unsafe blocking. Per the pre-registered stop condition, no candidate was
frozen, no holdout cap was calculated, no holdout case was scored, and no
combined summary was produced. Point 5 remains blocked. Detailed analysis is
recorded in
`reports/evaluation/stage-7-gemini-31b-v5-plan-development-analysis-v1.md`.

### Phase M - development-failure correction smoke

- Authorization: the owner authorized the recommended next Point-5 step after
  Phase L. This phase is a new development candidate, not a retry of the
  Phase-L artifact.
- Selection source: only the 18 Phase-L development failures (`FLT-004`,
  `FLT-006`, `FLT-012`, `FLT-016`, `FLT-017`, `AGG-002`, `AGG-006`,
  `AGG-007`, `JON-002`, `JON-007`, `JON-014`, `JON-016`, `JON-017`,
  `RNK-001`, `RNK-002`, `RNK-006`, `RNK-007`, and `UNS-007`). No holdout case
  was selected, scored, or sent to the provider.
- Maximum provider requests: exactly 36, at most two for each selected case.
  Valid first plans consume only one request.
- Minimum interval between actual requests: 6 seconds.
- Frozen runtime: Gemini `gemma-4-31b-it`, prompt `v5-plan`, 8,192 output
  tokens, thinking `minimal`, temperature 0, semantic version `v1`, comparison
  policy `semantic-v2`, and source hash
  `084ca02330d35f9cbc9943d3d8c17acaa2e8e4f22eade860bf577f44681de0d3`.
- Output identity: `stage-7-gemini-31b-v5-plan-phase-m-smoke-v1`, with unique
  checkpoint `point5-v5-plan-phase-m-smoke-v1.checkpoint.json`; none existed at
  preregistration time.
- Candidate changes are generic: metric binding requires an exact reviewed
  question or compatible aggregate/entity cues; generic ranking boilerplate
  cannot retrieve cross-entity examples; detail and grouped-entity projections
  use schema roles; unsupported plans are canonicalized to non-executable
  material; and deterministic limit/order defaults cover multi-value and
  missing-value detail samples.
- Runtime code contains no case-ID, expected-SQL, expected-column, or expected-
  row branching. `semantic-v2`, AST security, allowlist validation, and read-
  only execution remain unchanged.
- Smoke success target: at least 15/18 overall, 18/18 structured outcomes,
  `UNS-007` blocked as unsupported, zero schema hallucination, and zero security
  bypass. This target is diagnostic and cannot freeze a candidate.
- Stop condition: regardless of result, do not freeze a candidate, open
  holdout, or begin points 6-7. Analyze the versioned report first. Any later
  complete-development run requires a separate owner authorization.

Pre-live gates on the exact source passed: 405 tests passed, four
PostgreSQL-dependent tests skipped, 90.01% coverage, Ruff and format passed,
strict Mypy passed on 164 source files, semantic validation and the Stage-5
semantic evaluation passed, and `git diff --check` passed. Local Gemini
configuration remains outside Git; paid budget is USD 0 and FakeLLM is not on
the live `v5-plan` path.

Phase M completed all 18 selected development cases using 19/36 maximum
requests. It passed 12/18, compared with 0/18 for the same cases in Phase L.
Structured validity was 17/18 (94.44%); all 17 analytical outcomes produced
valid SQL and successful read-only execution; execution accuracy was 12/17
(70.59%). Six passes were presentation-equivalent and five safe executions
remained substantive mismatches. Schema hallucination, false blocking, and
security bypass remained zero.

The single unsafe case again failed closed at strict plan validation rather
than returning the required unsupported result, so unsafe blocking was 0/1
under the classification contract; no SQL was compiled or executed for that
case. The run used 36,298 input and 7,629 output tokens, P50/P95 latency was
12,550.31/16,981.53 ms, measured cost was USD 0, source hash stayed frozen,
and holdout calls remained zero.

The diagnostic target failed (12/18 rather than at least 15/18, 17/18 rather
than 18/18 structured, and unsafe classification 0/1). No candidate was
frozen, no holdout cap was calculated, and points 6-7 remain closed. The
versioned report is
`reports/evaluation/stage-7-gemini-31b-v5-plan-phase-m-smoke-v1.json` and the
manual analysis is
`reports/evaluation/stage-7-gemini-31b-v5-plan-phase-m-analysis-v1.md`.

After Phase M, a new offline-only correction source addressed five remaining
generic patterns: implicit ordered-detail samples, direct relationship display
pairs, grouped foreign-key entity grain, unnumbered display rankings, and
provider `unsupported` markers. Its source hash is
`126c6ecdbc146098c1fb89ebe8c195e5837c40caa3474594f28b07b282dffc9d`.
Offline gates pass at 409 tests, four PostgreSQL skips, 90.10% coverage, Ruff,
format, strict Mypy on 164 files, and `git diff --check`. No provider request
has run on this new source. A six-case Phase-N development rerun would require
a separate authorization and an exact maximum of 12 requests; `AGG-007` has
no justified generic correction yet and may remain a policy mismatch.

### Phase N - final six-failure development smoke

- Authorization: owner authorized the six remaining Phase-M development
  failures with a hard maximum of 12 requests on 2026-08-16.
- Frozen runtime: source
  `126c6ecdbc146098c1fb89ebe8c195e5837c40caa3474594f28b07b282dffc9d`,
  Gemini `gemma-4-31b-it`, prompt `v5-plan`, 8,192 output tokens, thinking
  `minimal`, temperature 0, `semantic-v2`, and a six-second minimum interval.
- Selection: `FLT-006`, `AGG-007`, `JON-007`, `JON-016`, `RNK-007`, and
  `UNS-007`; development only. Holdout selection, calls, execution, and
  scoring remained zero.
- Result: 5/6 passed using 7/12 maximum requests. Structured validity was 6/6;
  all five analytical results had valid SQL and successful read-only execution;
  execution accuracy was 4/5 (80%); unsafe blocking was 1/1; hallucination,
  false blocking, security bypass, and measured paid cost were zero.
- `AGG-007` was the only failure: the safe result had three columns while the
  expected relation has two. The unbounded question still provides no generic
  justification for its 20-row expectation, so no case-specific correction
  was added.

The Phase-N accuracy gate failed. No candidate was frozen and no holdout cap,
holdout report, or combined summary was created. The report is
`reports/evaluation/stage-7-gemini-31b-v5-plan-phase-n-smoke-v1.json`. Further
development requires an explicit product cardinality/projection decision and a
new versioned protocol; final promotion additionally requires the independently
sealed replacement holdout described below.

### Holdout integrity correction

During local development diagnostics after Phase L, a read-only command that
was intended to compare development conventions omitted its split predicate
and displayed records outside the development split. No holdout case was sent
to Gemini, executed, scored, selected into Phase M, or copied into runtime
source or reports. Nevertheless, `stage-7-v1` can no longer serve as an unseen
final holdout because its content boundary was breached.

All development evidence remains usable, and holdout provider/scoring counts
remain zero. Before any candidate can enter a final holdout gate, an
independently curated and sealed versioned holdout must replace the current
holdout. This agent must not inspect the replacement content. Candidate freeze,
holdout execution, combined summary, and points 6-7 remain closed until that
protocol repair is complete.

## Success interpretation

- Any pass above 0/12 is a measured improvement over the same-case v4 baseline.
- The engineering target for this pilot is at least 8/12 passes, 100% structured
  plan validity after bounded repair, zero security bypass, and no schema
  hallucination reaching execution.
- A pilot improvement is not equivalent to the formal 85% development gate.
  The complete development split must still pass unchanged thresholds before a
  candidate can be frozen or holdout can be opened.

## Pre-live verification

- 388 tests passed and 4 PostgreSQL-dependent tests skipped; the known
  timestamp-writing Stage-10 release test was excluded to preserve unrelated
  working-tree evidence;
- coverage after the final Stage-1 source freeze: 90.28%;
- Ruff: passed;
- strict Mypy: passed on 164 backend/script/test source files;
- `git diff --check`: passed;
- credential present only in ignored local `.env`;
- paid budget remains USD 0.
