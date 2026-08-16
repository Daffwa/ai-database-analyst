# Gemma 31B v5-plan Complete Development Analysis

## Decision

The complete 70-case development evaluation failed the frozen Point-5 gates.
Do not freeze this candidate, open holdout, create a combined development/
holdout summary, or begin points 6-7 from this result.

The candidate materially improved analytical execution accuracy and safe SQL
completion compared with the prior prompt-v4/semantic-v2 run, but it did not
reach the required accuracy and regressed structured-output and known-unsafe
reliability.

## Frozen Run Identity

- Provider/model: `gemini` / `gemma-4-31b-it`
- Runtime/prompt: `v5-plan`
- Semantic layer: `v1`, definitions `project_verified`
- Comparison policy: `semantic-v2`
- Development corpus: immutable `stage-7-v1`, 70 cases
- Source hash:
  `eb467958f5eea831f0a2e5628925a7a06243bfc87c481c25b140d677b56034b4`
- Requests: 74 used / 136 maximum
- Paid budget and measured cost: USD 0 / USD 0
- Holdout cases scored: 0

## Gate Results

| Metric | Result | Required | Gate |
|---|---:|---:|---|
| Structured-output validity | 64/68 (94.12%) | >= 99% | Failed |
| Development execution accuracy | 44/61 (72.13%) | >= 85% | Failed |
| Known-unsafe blocking | 6/7 (85.71%) | 100% | Failed |
| Clarification accuracy | 2/2 (100%) | >= 90% | Passed |
| Schema hallucination | 0/61 (0%) | <= 5% | Passed |
| Security bypass | 0 | 0 | Passed |

Additional evidence:

- total passed cases: 52/70 (74.29%);
- valid SQL: 58/61 (95.08%);
- successful read-only execution: 58/61 (95.08%);
- false blocking: 0;
- repairs: 5 attempts, 20% success;
- presentation-equivalent passes: 22;
- substantive result mismatches: 14;
- input/output tokens: 156,921 / 29,517;
- latency P50/P95: 12,937.98 / 31,259.27 ms.

## Comparison With the Prior Complete Development Run

| Metric | prompt-v4 + semantic-v2 | v5-plan Phase L | Change |
|---|---:|---:|---:|
| Passed cases | 37/70 | 52/70 | +15 cases |
| Structured validity | 97.06% | 94.12% | -2.94 pp |
| Valid SQL | 86.89% | 95.08% | +8.19 pp |
| Execution success | 86.89% | 95.08% | +8.19 pp |
| Execution accuracy | 45.90% | 72.13% | +26.23 pp |
| Known-unsafe blocking | 100% | 85.71% | -14.29 pp |
| Presentation-equivalent passes | 10 | 22 | +12 cases |

The plan/compiler architecture therefore improves SQL completion and result
accuracy substantially, but the candidate is not yet reliable enough for
promotion.

## Failure Analysis

Eighteen cases failed:

- filtering: 5;
- aggregation: 3;
- multi-table join: 5;
- ranking/top-N: 4;
- known-unsafe: 1.

Failure shapes were:

- eight column-count mismatches;
- four fail-closed invalid-plan outcomes;
- three row-value or required-order mismatches;
- two row-count mismatches;
- one column-identity/value mismatch.

The four invalid-plan outcomes used sanitized codes only. They covered one
missing named projection, one invalid output value, one declared-schema
mismatch, and one unsupported-plan extra field. The known-unsafe failure did
not execute SQL; it failed closed at strict plan validation, but did not return
the required unsupported classification and therefore failed the 100%
known-unsafe gate.

## Boundary and Next State

- No candidate manifest was created.
- No holdout case was scored or used for tuning.
- No combined final summary was generated because it requires a frozen passing
  candidate and a completed holdout report.
- FakeLLM was not used on the live `v5-plan` path.
- Existing deterministic AST validation and read-only execution remained
  mandatory for every compiled candidate.
- Point 5 remains `Terblokir`. Any continuation must be a new, explicitly
  versioned development-only candidate; thresholds and `semantic-v2` must not
  be loosened to manufacture a pass.
