# Gemini/Gemma Development Calibration Analysis

- Date: 2026-08-08
- Provider/model: `gemini` / `gemma-4-26b-a4b-it`
- Dataset: immutable `stage-7-v1`, development split only
- Holdout provider calls: 0
- Temperature/thinking: 0 / `minimal`
- Paid spend: USD 0
- Formal candidate status: not frozen

## Outcome

The selected model did not qualify for the formal 68-request development
baseline. Holdout remained locked.

Two v2 prefixes used seven development-only calls. The first four exposed that
the progress evidence was insufficient for safe diagnosis and were stopped
without a report. The next three produced two SQL-valid executions with column
contract mismatches and one invalid structured response. At that point the best
possible structured validity for a 68-call run was 67/68 (98.53%), below the
frozen 99% threshold, so the run stopped early.

Prompt v3 was derived only from those development failure classes. It added
strict rules for output keys, empty arrays versus null, physical source
metadata, computed aliases, listing shape, and unsupported fallback. A bounded
four-case v3 calibration then produced:

| Metric | v3 calibration | Frozen threshold |
|---|---:|---:|
| Passed cases | 1/4 (25%) | diagnostic only |
| Structured-output validity | 2/4 (50%) | >= 99% |
| Valid SQL | 2/4 (50%) | diagnostic |
| Execution success | 2/4 (50%) | diagnostic |
| Execution accuracy | 1/4 (25%) | >= 85% |
| Schema hallucination | 0/4 (0%) | <= 5% |
| False blocking | 0/4 (0%) | diagnostic |
| Input/output tokens | 1,761 / 343 | recorded |
| Latency P50/P95 | 9,886 / 88,553 ms | recorded |
| Estimated paid cost | USD 0 | USD 0 maximum |

The three failed IDs were `FLT-001`, `FLT-003`, and `FLT-004`. Privacy-safe
failure classes were one invalid structured response, one sanitized provider
error, and one executed-result column mismatch. No raw question, prompt,
provider response, SQL, result row, credential, or authorization header is
stored in the reports.

## Comparison boundary

The existing fake baseline is 100/100 because it uses exact deterministic
mappings. It proves orchestration, validation, execution, and regression
mechanics; it is not a language-generalization peer. The real calibration's
25% execution accuracy therefore does not degrade or replace the fake baseline.

## Blocker and options

Point 5 is blocked under the frozen thresholds. Continuing to the holdout would
violate the evaluation protocol because the development candidate did not pass
and cannot be frozen.

Unblocking requires a new owner-approved decision:

1. evaluate a different supported model, such as hosted `gemma-4-31b-it`;
2. change the quality protocol by lowering thresholds or allowing bounded
   structured-output retries, then rerun development from a new version; or
3. retain `gemma-4-26b-a4b-it` and accept that points 6-7 cannot use it as a
   qualified real-model baseline yet.

The machine-readable v3 evidence is
`reports/evaluation/stage-7-gemini-development-calibration-v3.json`.
