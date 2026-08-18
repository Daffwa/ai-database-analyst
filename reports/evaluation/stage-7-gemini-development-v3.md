# Real-Model Evaluation: Development

- Gate: passed
- Provider/model: `gemini` / `gemma-4-31b-it`
- Dataset: `stage-7-development-v2` / `5988509b1f0248a41df85fb11da9796348994d0036d278adbd3b987f2dba94b6`
- Prompt/semantic: `v5-plan` / `v1`
- Result comparison: `semantic-v2`
- Schema hash: `58c6c16d147308c44996f88c3b893c0baa264a9b0ca6d06418f1ba3f199def7c`
- Requests: 69/136
- Temperature/thinking: 0 / `minimal`
- Paid budget and measured cost: USD 0 / USD 0.00

## Metrics

| Metric | Result |
|---|---:|
| Passed cases | 67/70 (95.71%) |
| Structured-output validity | 68/68 (100.00%) |
| Valid SQL | 61/61 (100.00%) |
| Execution success | 61/61 (100.00%) |
| Execution accuracy | 58/61 (95.08%) |
| Schema hallucination | 0/61 (0.00%) |
| Unsafe protection | 7/7 (100.00%) |
| False blocking | 0/61 (0.00%) |
| Clarification accuracy | 2/2 (100.00%) |
| Latency P50/P95 | 13742.86 / 24958.51 ms |
| Input/output tokens | 135259 / 27377 |
| Presentation-equivalent passes | 30 |
| Substantive result mismatches | 3 |

## Failure Categories

- `aggregation`: AGG-006, AGG-007, AGG-017

## Gate Failures

None.

## Boundaries

- The corpus is synthetic Chinook and does not represent private production data.
- A single temperature-zero run does not measure provider variance.
- Free-tier capacity and model behavior may change after this dated run.
- Unsafe protection on this finite corpus does not prove absence of unknown bypasses.
- For v5-plan, requests_planned is a hard maximum because valid first plans do not consume the optional repair call.
