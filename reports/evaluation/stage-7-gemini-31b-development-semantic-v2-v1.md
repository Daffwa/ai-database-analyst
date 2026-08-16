# Real-Model Evaluation: Development

- Gate: failed
- Provider/model: `gemini` / `gemma-4-31b-it`
- Dataset: `stage-7-v1` / `34002b865f657bf12401627b91b88f09ed07d5ffe53b08683015b384960b6542`
- Prompt/semantic: `v4` / `v1`
- Result comparison: `semantic-v2`
- Schema hash: `58c6c16d147308c44996f88c3b893c0baa264a9b0ca6d06418f1ba3f199def7c`
- Requests: 68/68
- Temperature/thinking: 0 / `minimal`
- Paid budget and measured cost: USD 0 / USD 0.00

## Metrics

| Metric | Result |
|---|---:|
| Passed cases | 37/70 (52.86%) |
| Structured-output validity | 66/68 (97.06%) |
| Valid SQL | 53/61 (86.89%) |
| Execution success | 53/61 (86.89%) |
| Execution accuracy | 28/61 (45.90%) |
| Schema hallucination | 0/61 (0.00%) |
| Unsafe protection | 7/7 (100.00%) |
| False blocking | 6/61 (9.84%) |
| Clarification accuracy | 2/2 (100.00%) |
| Latency P50/P95 | 5018.12 / 8257.60 ms |
| Input/output tokens | 66561 / 9895 |
| Presentation-equivalent passes | 10 |
| Substantive result mismatches | 25 |

## Failure Categories

- `aggregation`: AGG-007
- `filtering`: FLT-003, FLT-005, FLT-006, FLT-011, FLT-012, FLT-016, FLT-017
- `multi_table_join`: JON-001, JON-002, JON-003, JON-004, JON-005, JON-006, JON-007, JON-011, JON-012, JON-013, JON-014, JON-015, JON-016, JON-017
- `ranking_top_n`: RNK-003, RNK-004, RNK-005, RNK-007
- `subquery`: SUB-001, SUB-002, SUB-003, SUB-004, SUB-005
- `time_analysis`: TIM-001, TIM-006

## Gate Failures

structured_output_validity, execution_accuracy

## Boundaries

- The corpus is synthetic Chinook and does not represent private production data.
- A single temperature-zero run does not measure provider variance.
- Free-tier capacity and model behavior may change after this dated run.
- Unsafe protection on this finite corpus does not prove absence of unknown bypasses.
- Repair is not wired into the primary runtime, so repair metrics remain zero.
