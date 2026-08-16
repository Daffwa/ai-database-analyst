# Real-Model Evaluation Protocol v2

- Provider/model: Gemini Developer API / `gemma-4-31b-it`
- Corpus: immutable `stage-7-v1`
- Candidate prompt: `v4` (derived only from 31B development calibration)
- Semantic/schema: `v1` / pinned Chinook v1.4.5 snapshot
- Temperature/thinking: `0` / `minimal`
- Paid budget: USD 0
- Automatic retries: 0
- Date frozen: 2026-08-08
- Supersedes for the next candidate: `real-model-evaluation-protocol.md`

## Reason for the new candidate

The first selected model, `gemma-4-26b-a4b-it`, failed development-only
calibration at 50% structured-output validity and 25% execution accuracy. The
owner authorized continuing with the recommended supported 31B variant. The
quality and security thresholds are unchanged; the failed 26B evidence remains
preserved and is not overwritten.

## Split and request budgets

| Scope | Maximum provider requests |
|---|---:|
| 31B development calibration | 8 |
| Formal development | 68 |
| Formal holdout | 27 |
| 31B total | 103 |
| Prior 26B calibration already consumed | 11 |
| Overall point-5 ceiling | 114 |

All inference remains free-tier only with maximum paid spend USD 0. The
calibration uses development cases only. Holdout remains inaccessible until a
complete 68-request development report passes and its candidate manifest is
frozen.

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

The evaluator retains the v1 safeguards: explicit `--confirm-live`, exact
request caps, at least two seconds between request starts, no retry, checkpoint
identity, evaluator-source SHA-256, privacy-minimized reports, deterministic SQL
validation, and read-only execution. The selected run cadence remains six
seconds.

The first four 31B development calibration calls used v3. Structured-output and
valid-SQL rates were 100%, but execution accuracy was 50% because two filtered
entity lists had column-shape mismatches. The remaining four authorized
calibration calls reran the same development-only prefix with v4, which changes
only the development-derived output-shape rule. That prefix reached 75%
execution accuracy. Thresholds and all security controls remained unchanged.

## Calibration command

```powershell
uv run python scripts/dev.py evaluate-real-model run --split development --case-limit 4 --model gemma-4-31b-it --prompt-version v3 --confirm-live --max-requests 4 --request-interval-seconds 6 --development-output reports/evaluation/stage-7-gemini-31b-development-calibration-v1.json --development-markdown reports/evaluation/stage-7-gemini-31b-development-calibration-v1.md --checkpoint logs/point5-31b-calibration.checkpoint.json
```

The localhost application continues using the `.env` model. This command
overrides the model only inside the isolated evaluator.

## Formal development outcome

The complete v4 development run used 68/68 provider requests across 70 cases
(two ambiguity cases did not invoke the model). It failed the frozen gate:

| Metric | Result | Required |
|---|---:|---:|
| Structured-output validity | 66/68 (97.06%) | >= 99% |
| Execution accuracy | 18/61 (29.51%) | >= 85% |
| Clarification accuracy | 2/2 (100.00%) | >= 90% |
| Schema hallucination | 0/61 (0.00%) | <= 5% |
| Known-unsafe protection | 7/7 (100.00%) | 100% |
| Security bypass | 0 | 0 |

The run consumed 66,561 input and 9,895 output tokens, with latency P50/P95 of
5,038.28/9,347.81 ms and measured paid cost USD 0. The candidate was not frozen
and holdout provider requests remained zero. The machine-readable report is
`reports/evaluation/stage-7-gemini-31b-development-v1.json`; the aggregate
analysis is `reports/evaluation/stage-7-gemini-31b-development-analysis.md`.

Point 5 remains blocked. A later candidate must use a new versioned protocol;
this failed evidence and the untouched holdout split must remain preserved.
