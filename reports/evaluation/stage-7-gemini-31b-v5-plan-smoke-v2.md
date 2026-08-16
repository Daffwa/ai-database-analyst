# Real-Model Evaluation: Development

- Gate: failed
- Provider/model: `gemini` / `gemma-4-31b-it`
- Dataset: `stage-7-v1` / `34002b865f657bf12401627b91b88f09ed07d5ffe53b08683015b384960b6542`
- Prompt/semantic: `v5-plan` / `v1`
- Result comparison: `semantic-v2`
- Schema hash: `58c6c16d147308c44996f88c3b893c0baa264a9b0ca6d06418f1ba3f199def7c`
- Requests: 2/2
- Temperature/thinking: 0 / `minimal`
- Paid budget and measured cost: USD 0 / USD 0.00

## Metrics

| Metric | Result |
|---|---:|
| Passed cases | 0/1 (0.00%) |
| Structured-output validity | 0/1 (0.00%) |
| Valid SQL | 0/1 (0.00%) |
| Execution success | 0/1 (0.00%) |
| Execution accuracy | 0/1 (0.00%) |
| Schema hallucination | 0/1 (0.00%) |
| Unsafe protection | 0/0 (100.00%) |
| False blocking | 0/1 (0.00%) |
| Clarification accuracy | 0/0 (100.00%) |
| Latency P50/P95 | 11975.59 / 11975.59 ms |
| Input/output tokens | 0 / 0 |
| Presentation-equivalent passes | 0 |
| Substantive result mismatches | 0 |

## Failure Categories

- `filtering`: FLT-003

## Gate Failures

structured_output_validity, execution_accuracy

## Boundaries

- The corpus is synthetic Chinook and does not represent private production data.
- A single temperature-zero run does not measure provider variance.
- Free-tier capacity and model behavior may change after this dated run.
- Unsafe protection on this finite corpus does not prove absence of unknown bypasses.
- For v5-plan, requests_planned is a hard maximum because valid first plans do not consume the optional repair call.
