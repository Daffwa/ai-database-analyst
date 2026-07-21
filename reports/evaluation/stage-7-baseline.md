# Tahap 7 Baseline Report

- Result: passed
- Dataset: `stage-7-v1` (100 cases)
- Dataset SHA-256: `79b51079324c42b375f7b1df5c2062d3b0780c5601698017e591650ef8f082c3`
- Development / holdout: 70 / 30
- Chinook: `v1.4.5`
- Schema hash: `58c6c16d147308c44996f88c3b893c0baa264a9b0ca6d06418f1ba3f199def7c`
- Prompt / semantic: `v1` / `v1`
- Semantic content hash: `3dc2a621c4eab93d8685a075569a65dfafed43c76eb082de511313f16f4ee3be`
- Provider / model: `fake` / `fake-deterministic`
- Git commit: `uncommitted`; dirty at run: `true`

## Metrics

| Metric | Result |
|---|---:|
| All cases | 100/100 (100.00%) |
| Structured-output validity | 95/95 (100.00%) |
| Valid SQL | 85/85 (100.00%) |
| Execution success | 85/85 (100.00%) |
| Execution accuracy | 85/85 (100.00%) |
| Schema hallucination | 0/85 (0.00%) |
| Unsafe blocking | 10/10 (100.00%) |
| False blocking | 0/85 (0.00%) |
| Clarification accuracy | 5/5 (100.00%) |
| Clarification precision | 100.00% |
| Repair rate | 0.00% |
| Latency P50 / P95 | 16.13 ms / 52.91 ms |
| Token usage / cost | not available (offline fake provider) |

## Category Distribution

- `aggregation`: 20
- `ambiguity`: 5
- `filtering`: 20
- `multi_table_join`: 20
- `ranking_top_n`: 10
- `subquery`: 5
- `time_analysis`: 10
- `unsafe`: 10

## Interpretation Boundary

This is a reproducible offline regression baseline. The fake adapter validates
the complete deterministic pipeline but does not measure real-model language
generalization. The holdout labels are reserved for a future opt-in provider
evaluation and the evaluation cases are never inserted as verified prompt
examples.
