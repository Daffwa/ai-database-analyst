# Real-Model Evaluation Protocol v3

- Status: development rerun completed and failed; candidate not frozen
- Provider/model: Gemini Developer API / `gemma-4-31b-it`
- Corpus: immutable `stage-7-v1`
- Candidate prompt: `v4`
- Result-comparison policy: `semantic-v2`
- Semantic/schema: `v1` / pinned Chinook v1.4.5 snapshot
- Temperature/thinking: `0` / `minimal`
- Paid budget: USD 0
- Automatic retries: 0
- Date versioned: 2026-08-08
- Supersedes for future runs: `real-model-evaluation-protocol-v2.md`

## Purpose

The v2 run showed 29 column-shape mismatches, but its privacy-safe evidence did
not retain raw SQL, result rows, or provider responses. Protocol v3 therefore
does not retrospectively change the 29.51% v2 execution-accuracy result. It
introduced an explicit, frozen comparison policy and required a fresh
development rerun while preserving the original report and untouched holdout
split. That rerun is recorded below.

## Semantic-v2 acceptance rules

The policy accepts a result only when all business values can be proven
equivalent:

1. expected and actual results have the same number of columns and rows;
2. exact column names pass unchanged;
3. case/spacing/punctuation variants and column reordering may be normalized;
4. otherwise, aliases may be aligned only through a unique one-to-one value
   mapping;
5. any shared normalized name is locked to that semantic column and cannot be
   remapped to hide a mislabeled value;
6. numeric tolerance, NULL/type rules, and each case's `order_sensitive` flag
   remain authoritative.

The policy rejects extra or missing columns, ambiguous mappings, changed
values, changed row counts, internally inconsistent result shapes, and row-
order changes where order is required. `strict-v1` remains available for
legacy reproducibility; semantic-v2 must be selected explicitly.

## Frozen thresholds

| Metric | Required threshold |
|---|---:|
| Known-unsafe protection | 100% |
| Structured-output validity | >= 99% |
| Execution accuracy | >= 85% |
| Holdout execution accuracy | >= 85% |
| Clarification accuracy | >= 90% |
| Schema hallucination | <= 5% |
| Security bypass | 0 cases |

No quality or security threshold changed. The comparison-policy identifier is
recorded in the report, checkpoint identity, evaluator provenance, frozen
candidate, and combined summary. A holdout run is rejected if its policy does
not match the frozen development candidate.

## Offline audit

The deterministic development-only audit passed:

| Invariant | Result |
|---|---:|
| Exact expected results accepted | 61/61 |
| Presentation-only variants accepted | 61/61 |
| Same variants rejected by strict-v1 | 61/61 |
| Changed-value/extra-column variants rejected | 122/122 |
| Required-order changes rejected | 47/47 |
| Irrelevant-order changes accepted | 1/1 |
| Holdout cases scored | 0 |

Evidence:
`reports/evaluation/stage-7-comparison-policy-v2-audit.json` and
`reports/evaluation/stage-7-comparison-policy-v2-audit.md`.

## Completed live development run

The owner authorized this command, and it completed on 2026-08-08:

```powershell
uv run python scripts/dev.py evaluate-real-model run --split development --model gemma-4-31b-it --prompt-version v4 --comparison-policy semantic-v2 --confirm-live --max-requests 68 --request-interval-seconds 6 --development-output reports/evaluation/stage-7-gemini-31b-development-semantic-v2-v1.json --development-markdown reports/evaluation/stage-7-gemini-31b-development-semantic-v2-v1.md --checkpoint logs/point5-31b-semantic-v2-development.checkpoint.json
```

The run used all 68 authorized requests across 70 cases. It passed 37/70 cases,
including 10 presentation-equivalent passes. Structured-output validity was
66/68 (97.06%) against the 99% threshold, while execution accuracy was 28/61
(45.90%) against the 85% threshold. Clarification was 2/2, schema hallucination
was 0/61, and known-unsafe protection was 7/7. Paid cost was USD 0 and holdout
cases scored remained zero.

Because the complete development report failed two frozen gates, no candidate
manifest was created. The holdout cap remains 27 but is inaccessible for this
candidate. See
`reports/evaluation/stage-7-gemini-31b-development-semantic-v2-analysis.md`.
Old v1 checkpoints cannot be resumed because comparison-policy identity was
not recorded in them.
