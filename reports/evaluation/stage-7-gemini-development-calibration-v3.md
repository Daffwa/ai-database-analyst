# Real-Model Evaluation: Development

- Gate: failed
- Provider/model: `gemini` / `gemma-4-26b-a4b-it`
- Dataset: `stage-7-v1` / `34002b865f657bf12401627b91b88f09ed07d5ffe53b08683015b384960b6542`
- Prompt/semantic: `v3` / `v1`
- Schema hash: `58c6c16d147308c44996f88c3b893c0baa264a9b0ca6d06418f1ba3f199def7c`
- Requests: 4/4
- Temperature/thinking: 0 / `minimal`
- Paid budget and measured cost: USD 0 / USD 0.00

## Metrics

| Metric | Result |
|---|---:|
| Passed cases | 1/4 (25.00%) |
| Structured-output validity | 2/4 (50.00%) |
| Valid SQL | 2/4 (50.00%) |
| Execution success | 2/4 (50.00%) |
| Execution accuracy | 1/4 (25.00%) |
| Schema hallucination | 0/4 (0.00%) |
| Unsafe protection | 0/0 (100.00%) |
| False blocking | 0/4 (0.00%) |
| Clarification accuracy | 0/0 (100.00%) |
| Latency P50/P95 | 9885.60 / 88553.18 ms |
| Input/output tokens | 1761 / 343 |

## Failure Categories

- `filtering`: FLT-001, FLT-003, FLT-004

## Gate Failures

structured_output_validity, execution_accuracy

## Boundaries

- The corpus is synthetic Chinook and does not represent private production data.
- A single temperature-zero run does not measure provider variance.
- Free-tier capacity and model behavior may change after this dated run.
- Unsafe protection on this finite corpus does not prove absence of unknown bypasses.
- Repair is not wired into the primary runtime, so repair metrics remain zero.
