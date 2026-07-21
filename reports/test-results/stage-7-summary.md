# Tahap 7 Verification Summary

- Date: 2026-07-20 (Asia/Bangkok)
- Runtime: CPython 3.12.13 on Windows
- Dataset: `stage-7-v1`
- Result: passed

## Formal Evaluation Evidence

| Metric | Result |
|---|---:|
| Cases | 100/100 passed |
| Analytical execution accuracy | 85/85 (100%) |
| Valid SQL | 85/85 (100%) |
| Execution success | 85/85 (100%) |
| Schema hallucination | 0/85 (0%) |
| Known unsafe blocking | 10/10 (100%) |
| False blocking | 0/85 (0%) |
| Clarification accuracy | 5/5 (100%) |
| Clarification precision | 100% |
| Repair rate | 0%; success not applicable |
| Baseline regression gate | Passed |

The corpus contains exactly 20 filtering, 20 aggregation, 20 multi-table join,
10 time analysis, 10 ranking/top-N, 5 subquery, 5 ambiguity, and 10 unsafe
cases. Seventy cases are labelled development and thirty holdout. The dataset
SHA-256 is
`79b51079324c42b375f7b1df5c2062d3b0780c5601698017e591650ef8f082c3`.

## Comparison and Provenance

- Results are compared by executed columns and rows, not exact SQL alone.
- Order, NULL, empty result, numeric tolerance, and type behavior have focused
  tests.
- Reports record dataset, Chinook, schema, prompt, semantic, provider/model,
  runtime, Python, SQLGlot, Git, timestamp, and configuration provenance.
- Known-unsafe blocking must stay at 100%; accuracy, valid SQL, clarification,
  and false blocking allow no regression from this baseline.
- P95 latency has a 50% non-security warning threshold.
- Token usage and cost are not applicable to the offline fake-provider run.

## Automated Verification

- `uv run python scripts/dev.py evaluate-stage7`: passed.
- Ruff formatting and lint: passed.
- Mypy strict: 109 source files, no issues.
- Pytest: 266 passed.
- Branch coverage: 94.80%, required minimum 90%.
- Network calls: 0.
- Credentials used: none.

## Interpretation Boundary

This baseline proves deterministic pipeline regression over pinned Chinook. It
does not claim real-model natural-language generalization, production security,
or named analyst approval of the `project_verified` semantic definitions.
