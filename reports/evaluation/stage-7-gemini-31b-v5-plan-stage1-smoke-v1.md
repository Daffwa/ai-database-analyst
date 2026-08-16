# Real-Model Evaluation: Development

- Gate: failed
- Provider/model: `gemini` / `gemma-4-31b-it`
- Dataset: `stage-7-v1` / `34002b865f657bf12401627b91b88f09ed07d5ffe53b08683015b384960b6542`
- Prompt/semantic: `v5-plan` / `v1`
- Result comparison: `semantic-v2`
- Schema hash: `58c6c16d147308c44996f88c3b893c0baa264a9b0ca6d06418f1ba3f199def7c`
- Requests: 5/8
- Temperature/thinking: 0 / `minimal`
- Paid budget and measured cost: USD 0 / USD 0.00

## Metrics

| Metric | Result |
|---|---:|
| Passed cases | 3/4 (75.00%) |
| Structured-output validity | 3/4 (75.00%) |
| Valid SQL | 3/4 (75.00%) |
| Execution success | 3/4 (75.00%) |
| Execution accuracy | 3/4 (75.00%) |
| Schema hallucination | 0/4 (0.00%) |
| Unsafe protection | 0/0 (100.00%) |
| False blocking | 0/4 (0.00%) |
| Clarification accuracy | 0/0 (100.00%) |
| Latency P50/P95 | 14398.45 / 36772.88 ms |
| Input/output tokens | 11058 / 2601 |
| Presentation-equivalent passes | 2 |
| Substantive result mismatches | 0 |

## Failure Categories

- `subquery`: SUB-004

## Gate Failures

structured_output_validity, execution_accuracy

## Boundaries

- The corpus is synthetic Chinook and does not represent private production data.
- A single temperature-zero run does not measure provider variance.
- Free-tier capacity and model behavior may change after this dated run.
- Unsafe protection on this finite corpus does not prove absence of unknown bypasses.
- For v5-plan, requests_planned is a hard maximum because valid first plans do not consume the optional repair call.
