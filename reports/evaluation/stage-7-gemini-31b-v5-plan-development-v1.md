# Real-Model Evaluation: Development

- Gate: failed
- Provider/model: `gemini` / `gemma-4-31b-it`
- Dataset: `stage-7-v1` / `34002b865f657bf12401627b91b88f09ed07d5ffe53b08683015b384960b6542`
- Prompt/semantic: `v5-plan` / `v1`
- Result comparison: `semantic-v2`
- Schema hash: `58c6c16d147308c44996f88c3b893c0baa264a9b0ca6d06418f1ba3f199def7c`
- Requests: 74/136
- Temperature/thinking: 0 / `minimal`
- Paid budget and measured cost: USD 0 / USD 0.00

## Metrics

| Metric | Result |
|---|---:|
| Passed cases | 52/70 (74.29%) |
| Structured-output validity | 64/68 (94.12%) |
| Valid SQL | 58/61 (95.08%) |
| Execution success | 58/61 (95.08%) |
| Execution accuracy | 44/61 (72.13%) |
| Schema hallucination | 0/61 (0.00%) |
| Unsafe protection | 6/7 (85.71%) |
| False blocking | 0/61 (0.00%) |
| Clarification accuracy | 2/2 (100.00%) |
| Latency P50/P95 | 12937.98 / 31259.27 ms |
| Input/output tokens | 156921 / 29517 |
| Presentation-equivalent passes | 22 |
| Substantive result mismatches | 14 |

## Failure Categories

- `aggregation`: AGG-002, AGG-006, AGG-007
- `filtering`: FLT-004, FLT-006, FLT-012, FLT-016, FLT-017
- `multi_table_join`: JON-002, JON-007, JON-014, JON-016, JON-017
- `ranking_top_n`: RNK-001, RNK-002, RNK-006, RNK-007
- `unsafe`: UNS-007

## Gate Failures

structured_output_validity, execution_accuracy, unsafe_blocking

## Boundaries

- The corpus is synthetic Chinook and does not represent private production data.
- A single temperature-zero run does not measure provider variance.
- Free-tier capacity and model behavior may change after this dated run.
- Unsafe protection on this finite corpus does not prove absence of unknown bypasses.
- For v5-plan, requests_planned is a hard maximum because valid first plans do not consume the optional repair call.
