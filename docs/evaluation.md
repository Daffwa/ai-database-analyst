# Evaluation — Deterministic Baselines

- Version: `stage3-mini-v1`
- Date: 2026-07-19
- Dataset: Chinook v1.4.5 SQLite
- Dataset SHA-256:
  `bdf635be69850bd3be09c9a2dbeef7ddfb80036bd3ef3381383cd03b61e4a61a`
- Schema hash:
  `58c6c16d147308c44996f88c3b893c0baa264a9b0ca6d06418f1ba3f199def7c`
- Prompt version: `v1`
- Provider/model: `fake` / `fake-deterministic`

## Purpose and Boundary

The 20 cases cover simple filtering, aggregation, joins, ranking, and time
analysis in Indonesian and English. The catalog verifies deterministic pipeline
mechanics, SQL/result separation, and database-grounded values. It is not the
formal Tahap 7 evaluation set and does not support claims about real-model
generalization.

The cases are not used as prompt examples. Each exact question maps to a strict
structured fake response. Before execution, the proposal SQL, tables, and
columns must exactly match the trusted case. The executor then receives the
case's baseline SQL constant, not the adapter output string. The normalized
columns and rows must match a tracked SHA-256 result identity.

Any unknown question, malformed proposal, metadata mismatch, or result drift
fails closed or returns without execution.

## Metrics

| Metric | Result |
|---|---:|
| Case count | 20 |
| Structured-output valid | 20/20 |
| Generated SQL exact baseline match | 20/20 |
| Execution success | 20/20 |
| Normalized result baseline match | 20/20 |
| API credentials used | 0 |
| Network calls used by evaluation | 0 |

The full case definitions and result hashes live in
`backend/evaluation/mini_cases.py`. The runner is
`backend/evaluation/runner.py`. Run the evidence again with:

```powershell
uv run python scripts/dev.py evaluate-stage3
```

## Known Limitations

- Exact fake mappings do not measure natural-language generalization.
- This 20-case set alone does not measure SQL security; the separate Tahap 4
  corpus below measures blocking and false blocking.
- Result hashes are tied to the pinned dataset and normalized output contract.
- A real provider requires a separate opt-in evaluation with credentials and
  provider/model/version provenance.

## Tahap 4 Security Baseline

- Version: `stage-4-v1`
- Parser: SQLGlot 30.12.0
- Dialect: SQLite
- Unsafe corpus: 30 versioned SQL cases
- Safe comparison set: the 20 Tahap 3 database baselines

| Metric | Result |
|---|---:|
| Known unsafe statements blocked as expected | 30/30 |
| Known unsafe blocking rate | 100% |
| Safe baselines allowed | 20/20 |
| False-block count | 0 |
| False-blocking rate | 0% |

The unsafe corpus covers DML, DDL, privilege and administrative statements,
multiple statements, `SELECT INTO`, DML inside a CTE, forbidden tables inside a
set operation, recursive CTEs, cartesian joins, schema/catalog escape,
parameters, parse failure, and direct or nested dangerous functions. Separate
tests cover quoted identifiers, comments, unusual whitespace, case changes,
nested subqueries, timeout, response budgets, read-only database enforcement,
repair revalidation, and Indonesian/English prompt injection.

Re-run the measured security baseline with:

```powershell
uv run python scripts/dev.py evaluate-stage4
```

The tracked result is `reports/evaluation/stage-4-security.json`. A 100% result
on a finite known corpus is regression evidence, not proof that unknown bypasses
or semantic authorization risks do not exist.

## Tahap 5 Semantic Baseline

- Version: `stage-5-v1`
- Semantic version: `v1`
- Semantic content hash:
  `3dc2a621c4eab93d8685a075569a65dfafed43c76eb082de511313f16f4ee3be`
- Ambiguity corpus: 10 Indonesian/English cases across five business terms
- Explicit-resolution corpus: 10 cases
- Clear Tahap 3 comparison set: 20 cases
- Verified-query exact retrieval set: 10 cases

| Metric | Result |
|---|---:|
| Ambiguous questions correctly clarified | 10/10 |
| Clarification recall | 100% |
| Explicit resolutions accepted without re-clarification | 10/10 |
| Clear baselines accepted without false clarification | 20/20 |
| False-clarification rate on clear baselines | 0% |
| Exact verified-query retrieval | 10/10 |
| Semantic validation issues | 0 |

The clarification set covers “best customer,” “best product,” “active
customer,” “latest revenue,” and “largest sales” in both languages. The
explicit cases select a measurable interpretation such as spend, transaction
count, unit count, or latest complete calendar period. No ambiguity rule has a
silent default.

Verified-query retrieval admits only `valid`, non-draft entries, applies a
relevance threshold, and returns at most the configured count. These examples
are separate from the evaluation corpus and still pass the full SQL security
boundary before execution.

Re-run the semantic baseline with:

```powershell
uv run python scripts/dev.py semantic-validate
uv run python scripts/dev.py evaluate-stage5
```

The tracked result is `reports/evaluation/stage-5-semantic.json`. This baseline
tests deterministic term resolution and retrieval on the pinned Chinook domain;
it does not replace analyst sign-off, real-model evaluation, or future
authorization-specific tests.

## Tahap 6 Result and UX Baseline

- Version: `stage-6-v1`
- Closed database cases: 20
- Explicit expected chart cases: 4
- UI interaction cases: 5

| Metric | Result |
|---|---:|
| Database result identity | 20/20 |
| Normalized presentation identity | 20/20 |
| Valid result-only chart contracts | 20/20 |
| Explicit expected chart type | 4/4 |
| Cell-grounded numeric summaries | 20/20 |
| Valid bounded CSV exports | 20/20 |
| Empty result state | Passed |
| Feedback persistence | Passed |
| History metadata privacy | Passed |
| Database Explorer table coverage | 11/11 |
| Safe System Info | Passed |

The chart distribution was 3 KPI, 3 table, 5 line, and 9 bar. The evaluator
compares database and presentation values, checks that chart fields belong to
the returned result, verifies evidence cells, and exercises supporting UX
contracts. It remains a deterministic closed-domain regression baseline, not a
claim about real-model generalization or causal validity.

Run it with:

```powershell
uv run python scripts/dev.py evaluate-stage6
```

The tracked result is `reports/evaluation/stage-6-result-ux.json`; the complete
design and limitations are in `docs/result-experience.md`.

## Tahap 7 Formal Evaluation

The canonical corpus is `data/evaluation/stage-7-v1.jsonl`. Its loader uses a
strict extra-forbidden schema, rejects duplicate IDs/questions and mixed
versions, hashes the exact source bytes, and enforces this distribution:

| Category | Cases |
|---|---:|
| Filtering | 20 |
| Aggregation | 20 |
| Multi-table join | 20 |
| Time analysis | 10 |
| Ranking/top-N | 10 |
| Subquery | 5 |
| Ambiguity | 5 |
| Unsafe/adversarial | 10 |

Seventy cases are labelled `development` and thirty `holdout`. These labels
prepare a future real-provider evaluation; the current fake adapter still uses
exact deterministic mappings for all generated cases. Evaluation questions are
not inserted into verified-query prompt examples.

### Result comparison

Analytical accuracy is based on executed database results, not exact SQL text.
The comparator checks column identity and row count, distinguishes NULL from an
empty string, preserves non-numeric type identity, normalizes numeric types,
applies each case's explicit tolerance, and either preserves or ignores row
order according to the case contract. Empty results are compared as a valid
zero-row result.

### Metric denominators

- Structured-output validity: 95 generated cases; semantic clarification cases
  stop before the model and are excluded.
- Valid SQL, execution success, accuracy, hallucination, and false blocking: 85
  analytical cases.
- Unsafe blocking: 10 known adversarial cases.
- Clarification accuracy: 5 expected ambiguity cases.
- Clarification precision: correct expected clarifications divided by every
  clarification returned across the full corpus.
- Repair rate: cases using at least one repair divided by all cases. Repair
  success is `null` when no repair was attempted.
- P50/P95: nearest-rank total pipeline latency across all 100 cases.
- Token/cost: `null` for the offline fake provider.

### Baseline and thresholds

The initial baseline passed 100/100 cases. All 85 analytical results matched,
schema hallucination and false blocking were 0%, all 10 unsafe cases were
blocked, and all 5 ambiguity cases returned the required rule. The machine
baseline is `reports/evaluation/stage-7-baseline.json`; the readable version is
`stage-7-baseline.md`.

Regression comparison requires identical dataset, schema, prompt, semantic,
provider, and model provenance. The gate permits no decrease in execution
accuracy, valid-SQL rate, clarification accuracy, or increase in false blocking.
Known-unsafe blocking must remain exactly 100%. P95 latency may increase by 50%
before a warning check fails, but latency alone is not a security gate.

Run:

```powershell
uv run python scripts/dev.py evaluate-stage7
```

The baseline is offline deterministic evidence. It does not measure real-model
generalization, token usage, cost, or organizational approval of the
`project_verified` business definitions.

### Opt-in real-model candidate evaluation

The point-5 evaluator is separate from the fake baseline and from `verify`. It
enforces exact development/holdout request caps, explicit live confirmation,
sequential calls, privacy-minimized reports, checkpoint identity, source drift
detection, and a candidate hash that must be frozen before holdout can run.

The first Gemini/Gemma 4 26B development calibration did not qualify. Prompt v3
scored 1/4 cases, 50% structured-output validity, and 25% execution accuracy.
The owner then authorized the 31B candidate under an unchanged protocol. Its
formal v4 development run processed 70 cases using 68 provider requests and
reached 66/68 (97.06%) structured-output validity, 18/61 (29.51%) execution
accuracy, 2/2 clarification accuracy, 0% schema hallucination, and 7/7 known-
unsafe protection. Latency P50/P95 was 5,038.28/9,347.81 ms, token usage was
66,561/9,895 input/output, and measured paid cost was USD 0.

The frozen quality thresholds require at least 99% structured validity and 85%
execution accuracy. Therefore the 31B candidate was not frozen, holdout
provider calls remained zero, and the fake 100/100 baseline remains separate.
See `reports/evaluation/stage-7-gemini-calibration-analysis.md`,
`reports/evaluation/stage-7-gemini-31b-development-analysis.md`, and
`docs/real-model-evaluation-protocol-v2.md`.

The commands below are historical v1 examples and must not be used for a new
qualification because `stage-7-v1` is no longer an eligible unseen holdout:

```powershell
uv run python scripts/dev.py evaluate-real-model run --split development --confirm-live --max-requests 68 --request-interval-seconds 6
uv run python scripts/dev.py evaluate-real-model freeze --holdout-max-requests 27
uv run python scripts/dev.py evaluate-real-model run --split holdout --confirm-live --max-requests 27 --request-interval-seconds 6
uv run python scripts/dev.py evaluate-real-model summarize
```

The replacement v5 workflow uses a development-only v2 corpus and a private
holdout payload bound to an independently produced manifest. See
`docs/real-model-evaluation-protocol-v5.md` for the current commands.

#### Semantic comparison policy v2

The owner selected option 3: revise the output/comparison contract without
lowering any threshold. `semantic-v2` accepts case/spacing/punctuation aliases,
column reordering, or otherwise provable unique one-to-one value alignment. It
still rejects extra/missing columns, ambiguous alignments, changed values or row
counts, internally inconsistent result shapes, and required-order changes. The
policy ID is frozen in checkpoints, provenance, candidates, and summaries so a
holdout cannot silently use different rules.

The development-only offline audit passed 61/61 presentation variants, rejected
122/122 substantive variants and 47/47 required-order changes, and scored zero
holdout cases. It does not rescore the old 31B report because raw provider rows
were intentionally not retained. See
`reports/evaluation/stage-7-comparison-policy-v2-audit.md` and
`docs/real-model-evaluation-protocol-v3.md`.

The authorized protocol-v3 development rerun completed all 70 cases with 68
requests. Semantic-v2 accepted 10 presentation-equivalent results, raising the
new run to 28/61 (45.90%) execution accuracy and 37/70 total passes. Structured
validity was still 66/68 (97.06%). These miss the unchanged 85% and 99% gates,
so no candidate was frozen, holdout cases scored remained zero, and point 5 is
blocked. The complete interpretation is in
`reports/evaluation/stage-7-gemini-31b-development-semantic-v2-analysis.md`.

Run the offline audit with:

```powershell
uv run python scripts/dev.py audit-comparison-policy
```

#### Gemma-only plan-compiled candidate

Runtime `v5-plan` keeps Gemma but removes direct SQL authorship. Gemma returns a
strict AnalysisPlan; deterministic code normalizes presentation aliases,
grounds allowlisted identifiers, derives unique approved join paths, completes
trusted base projection roles, compiles SQL, validates plan/SQL alignment, and
then uses the existing AST policy and read-only executor. The new runtime path
requires the real Gemini adapter and has no FakeLLM fallback. Legacy FakeLLM
remains only for offline regression.

On the same 12 development cases that prompt-v4 passed 0/12, successive frozen
pilots passed 2/12, 6/12, and finally 8/12. Pilot v3 used 14/24 maximum requests;
structured validity, valid SQL, and execution success were 10/12, schema
hallucination/security bypass were zero, and paid cost was USD 0. This meets the
subset engineering target but not the formal 99% structured-validity and 85%
execution-accuracy thresholds. No candidate is frozen and holdout cases scored
remain zero. See `docs/real-model-evaluation-protocol-v4.md` and
`reports/evaluation/stage-7-gemini-31b-v5-plan-hard-pilot-v3.md`.

The next targeted correction retained that request/security boundary and added
one shared-slot provider retry, unambiguous reviewed-metric binding, stable
schema-derived entity grain/order defaults, and structurally equivalent grouped
benchmark normalization. Phase G passed three of the four pilot-v3 failures
with 5 requests; after one fail-closed 2-request diagnostic, Phase I passed the
remaining grouped-benchmark case exactly in 1 request. Hallucination, bypass,
paid cost, and holdout calls remained zero. Because these were successive
source freezes, they are not reported as a 12/12 same-source result. The next
quality step at that historical point was a separately authorized hard pilot.

Phase N later passed 5/6 but exposed an inconsistent development contract: an
unbounded universal grouping expected an unexplained 20 rows and omitted an
unrequested-versus-requested projection policy. Protocol v5 now defines the
generic behavior: universal groupings return every group within the 500-row
execution ceiling, model-invented limits are removed unless the user requested
a quantity, and ID-only grouping omits an unrequested display field. Explicit
quantities and display names remain honored.

The new `stage-7-development-v2` corpus contains only 70 development cases and
records the corrected 204-row `ArtistId, album_count` expectation. Runtime code
contains no `AGG-007` branch. The replacement final holdout must be curated
independently, kept outside Git, committed by a content/attestation manifest,
and supplied to the runner only after a passing development report is frozen.
Missing, altered, partial, or mixed-split payloads fail before provider setup.

This repairs the policy and isolation mechanisms, not the model qualification.
No v5 provider call has been made. Point 5 remains blocked until the owner
authorizes the exact 136-request complete development run, that run passes,
and an independent curator supplies a valid sealed holdout manifest. Current
details and commands are in `docs/real-model-evaluation-protocol-v5.md`.

## Tahap 8 Readiness Evaluation

`scripts/evaluate_stage8.py` records deterministic implementation evidence and
external-infrastructure state separately. It checks the pinned PostgreSQL asset,
snapshot/semantic overlay, role and URL separation, ten metadata models,
Alembic revision, API contracts, frontend isolation, privacy-safe metadata, and
focused tests. Passing these checks sets `implementation_gate_passed`; it cannot
set `stage_gate_passed` unless the separately generated PostgreSQL integration
report confirms a live container run.

The current report is `reports/evaluation/stage-8-readiness.json`: all nine
implementation checks pass, `postgresql_integration_verified` is true, and the
stage gate passes. The separate ephemeral-container run passed 4/4 tests on
2026-07-21. Reproduce the evidence with:

```powershell
uv run python scripts/dev.py test-postgres
uv run python scripts/dev.py evaluate-stage8
uv run python scripts/dev.py verify
```

## Tahap 9 Delivery Readiness

The deterministic `stage-9-readiness-v1` evaluator verifies image pinning and
non-root contracts, Compose services/readiness/required secrets/named volume,
least-privilege immutable workflows, and end-to-end observability fields. It
then consumes two independently produced external reports:

- `reports/test-results/stage-9-compose.json` from a clean no-cache stack run;
- `reports/security/stage-9-security.json` from dependency, SAST, secret, SQL,
  image, and configuration scans.

The local Tahap 9 stage gate is false if either external report is absent or
failed. Reproduce it with:

```powershell
uv run python scripts/dev.py docker-smoke
uv run python scripts/dev.py security-stage9
uv run python scripts/dev.py evaluate-stage9
```

GitHub-hosted execution is verified for the authorized public repository. The
exact commit, workflow run IDs, conclusions, and URLs for CI, Docker, Security,
and the manually dispatched Evaluation workflow are recorded in
`reports/evaluation/stage-10-external-evidence.json`. The Tahap 10 evaluator
validates that offline attestation; it does not infer hosted success from
workflow-file inspection.
