# Stage 7 Gemini 31B Development Analysis

- Date: 2026-08-08
- Provider/model: Gemini Developer API / `gemma-4-31b-it`
- Dataset/split: immutable `stage-7-v1` / development only
- Prompt/semantic version: `v4` / `v1`
- Temperature/thinking: `0` / `minimal`
- Automatic retries: 0
- Paid budget and measured cost: USD 0 / USD 0.00
- Formal provider requests: 68/68 for 70 development cases
- Holdout provider requests: 0

## Outcome

The formal development candidate failed the frozen quality gate. It was not
frozen, and the holdout runner remains locked. Known unsafe protection,
clarification, and schema-grounding metrics passed, but structured-output
validity and execution accuracy did not meet their thresholds.

| Metric | Result | Frozen threshold | Gate |
|---|---:|---:|---|
| Overall passed cases | 27/70 (38.57%) | Informational | - |
| Structured-output validity | 66/68 (97.06%) | >= 99% | Fail |
| Valid SQL | 53/61 (86.89%) | Informational | - |
| Execution success | 53/61 (86.89%) | Informational | - |
| Execution accuracy | 18/61 (29.51%) | >= 85% | Fail |
| Schema hallucination | 0/61 (0.00%) | <= 5% | Pass |
| Known-unsafe protection | 7/7 (100.00%) | 100% | Pass |
| Security bypass | 0 | 0 | Pass |
| False blocking | 6/61 (9.84%) | Informational | - |
| Clarification accuracy | 2/2 (100.00%) | >= 90% | Pass |
| Latency P50/P95 | 5,038.28 / 9,347.81 ms | Informational | - |
| Input/output tokens | 66,561 / 9,895 | Informational | - |

## Category Results

| Category | Passed | Notes |
|---|---:|---|
| Filtering | 7/14 | Most failures were result-shape differences. |
| Aggregation | 7/14 | SQL often executed but returned a different shape/result. |
| Multi-table join | 0/14 | Largest weakness; validation and result mismatches both occurred. |
| Time analysis | 1/7 | Most results differed in columns, rows, or ordering. |
| Ranking/top-N | 3/7 | Included one parse failure. |
| Subquery | 0/5 | Included result mismatches and one parse failure. |
| Ambiguity | 2/2 | Both clarification cases passed without SQL execution. |
| Unsafe | 7/7 | All known-unsafe requests were stopped. |

Across failed cases, the privacy-safe comparator recorded 29 column-shape
differences, five row-value/order differences, one row-count difference, six
status/validation/execution differences, and two sanitized pipeline errors.
The validator also recorded three declared-source mismatches, two parse
failures, and one disallowed function. No raw question, generated SQL, executed
SQL, database row, prompt, response, or credential is stored in this report.

## Calibration and Request Accounting

The 31B candidate used eight development-only calibration calls: four with v3
and four with the development-derived v4 output-shape rule. The v3 prefix
reached 50% execution accuracy; v4 improved the same prefix to 75%. The formal
v4 development run then used 68 provider requests. Total 31B provider usage was
76 requests, and total point-5 usage including the prior 26B calibration was 87
requests. No holdout request was made for either model.

## Comparison Boundary

The deterministic fake baseline remains 100/100, with 100% execution accuracy
and known-unsafe protection. It proves regression mechanics for exact supported
cases; it is not statistically equivalent to this real-model development run
and must not be presented as real-model generalization evidence.

## Decision

`gemma-4-31b-it` with prompt v4 is rejected as the point-5 qualified baseline
under the frozen protocol. Point 5 is `Terblokir`; points 6 and 7 must not treat
this candidate as evaluated and ready. Unblocking requires an explicitly
versioned next candidate or a development-derived change to the output contract
and evaluation protocol. Thresholds and holdout data remain unchanged.
