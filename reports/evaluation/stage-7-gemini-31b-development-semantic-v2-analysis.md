# Gemma 4 31B Development Analysis — Semantic-v2

- Date: 2026-08-08
- Decision: **development gate failed; do not freeze; do not open holdout**
- Provider/model: Gemini Developer API / `gemma-4-31b-it`
- Prompt/comparison policy: `v4` / `semantic-v2`
- Dataset: immutable `stage-7-v1` development split
- Requests: 68/68 across 70 cases
- Paid cost: USD 0
- Holdout cases scored: 0

## Gate result

| Metric | Result | Required | Gate |
|---|---:|---:|---|
| Structured-output validity | 66/68 (97.06%) | >= 99% | Failed |
| Execution accuracy | 28/61 (45.90%) | >= 85% | Failed |
| Clarification accuracy | 2/2 (100.00%) | >= 90% | Passed |
| Schema hallucination | 0/61 (0.00%) | <= 5% | Passed |
| Known-unsafe protection | 7/7 (100.00%) | 100% | Passed |
| Security bypass | 0 | 0 | Passed |

Other observed metrics were 53/61 (86.89%) valid SQL and execution success,
6/61 (9.84%) false blocking, 66,561 input tokens, 9,895 output tokens, and
latency P50/P95 of 5,018.12/8,257.60 ms. Overall, 37/70 cases passed.

## What semantic-v2 changed

The fail-closed comparator accepted 10 cases through a unique value-aligned
column mapping. They were recorded as presentation-equivalent passes. The
remaining 25 executed-result failures were substantive and stayed rejected.
Compared with the preceding strict-v1 run of the same model and prompt,
observed execution accuracy increased from 18/61 (29.51%) to 28/61 (45.90%),
and overall passes increased from 27/70 to 37/70.

This is an observed comparison between two independent provider runs, not a
controlled retrospective rescore. Privacy-safe reports retain neither raw
provider output nor result rows, so they cannot prove that every provider
response was byte-identical. The 10 presentation-equivalent cases in the new
report are the direct evidence attributable to semantic-v2.

## Remaining failure shape

The 33 failed cases are concentrated in model-quality categories:

- multi-table joins: 14;
- filtering: 7;
- subqueries: 5;
- ranking/top-N: 4;
- time analysis: 2;
- aggregation: 1.

The comparator continued to reject different column counts, different row
counts or values, required-order changes, blocked/invalid SQL, and sanitized
pipeline errors. These failures cannot be fixed by further relaxing result
equivalence without weakening correctness.

## Decision and next gate

Do not create a candidate manifest and do not run the holdout split. Point 5
remains blocked even though all known unsafe cases were protected, because both
frozen quality thresholds must pass. The next attempt requires an explicitly
versioned candidate decision, such as a stronger model or a development-only
prompt/runtime improvement. Thresholds and holdout isolation remain unchanged.

Machine-readable evidence:
`reports/evaluation/stage-7-gemini-31b-development-semantic-v2-v1.json`.
