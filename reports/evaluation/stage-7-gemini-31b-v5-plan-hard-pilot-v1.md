# Real-Model Evaluation: Development

- Gate: failed
- Provider/model: `gemini` / `gemma-4-31b-it`
- Dataset: `stage-7-v1` / `34002b865f657bf12401627b91b88f09ed07d5ffe53b08683015b384960b6542`
- Prompt/semantic: `v5-plan` / `v1`
- Result comparison: `semantic-v2`
- Schema hash: `58c6c16d147308c44996f88c3b893c0baa264a9b0ca6d06418f1ba3f199def7c`
- Requests: 20/24
- Temperature/thinking: 0 / `minimal`
- Paid budget and measured cost: USD 0 / USD 0.00

## Metrics

| Metric | Result |
|---|---:|
| Passed cases | 2/12 (16.67%) |
| Structured-output validity | 5/12 (41.67%) |
| Valid SQL | 5/12 (41.67%) |
| Execution success | 5/12 (41.67%) |
| Execution accuracy | 2/12 (16.67%) |
| Schema hallucination | 0/12 (0.00%) |
| Unsafe protection | 0/0 (100.00%) |
| False blocking | 0/12 (0.00%) |
| Clarification accuracy | 0/0 (100.00%) |
| Latency P50/P95 | 23296.79 / 37198.46 ms |
| Input/output tokens | 40616 / 8551 |
| Presentation-equivalent passes | 1 |
| Substantive result mismatches | 3 |

## Failure Categories

- `filtering`: FLT-005
- `multi_table_join`: JON-001, JON-003, JON-004, JON-011
- `ranking_top_n`: RNK-003, RNK-004
- `subquery`: SUB-001, SUB-004, SUB-005

## Gate Failures

structured_output_validity, execution_accuracy

## Boundaries

- The corpus is synthetic Chinook and does not represent private production data.
- A single temperature-zero run does not measure provider variance.
- Free-tier capacity and model behavior may change after this dated run.
- Unsafe protection on this finite corpus does not prove absence of unknown bypasses.
- For v5-plan, requests_planned is a hard maximum because valid first plans do not consume the optional repair call.
