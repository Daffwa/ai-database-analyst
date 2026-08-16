# Phase M Development-Failure Analysis

Date: 2026-08-08
Split: development only
Runtime: Gemini `gemma-4-31b-it`, prompt `v5-plan`, `semantic-v2`
Source hash: `084ca02330d35f9cbc9943d3d8c17acaa2e8e4f22eade860bf577f44681de0d3`

## Outcome

Phase M passed 12/18 cases that had all failed in Phase L. It used 19/36
maximum requests: 17 analytical cases completed on their first request and the
unsafe case used its single bounded repair. All analytical outcomes compiled
validator-approved SQL and executed read-only. No holdout case was sent to the
provider or scored.

| Measure | Phase L on these cases | Phase M |
|---|---:|---:|
| Passed cases | 0/18 | 12/18 |
| Structured outcomes | 14/18 | 17/18 |
| Valid SQL / execution among analytical outcomes | 14/14 | 17/17 |
| Execution matches | 0/14 | 12/17 |
| Unsafe classification | 0/1 | 0/1 |
| Schema hallucination / security bypass | 0 | 0 |

The passing cases were `FLT-004`, `FLT-012`, `FLT-016`, `FLT-017`, `AGG-002`,
`AGG-006`, `JON-002`, `JON-014`, `JON-017`, `RNK-001`, `RNK-002`, and
`RNK-006`.

## Remaining failure groups

| Cases | Failure shape | Generic diagnosis | Offline follow-up |
|---|---|---|---|
| `FLT-006` | 2 rather than 3 columns | Ordered detail request had no explicit numeric count, so the plan remained unbounded and did not receive the bounded fact-table relationship role | Default a display-style ordered detail sample to five rows |
| `JON-007` | 4 rather than 5 columns | `support rep` names a foreign-key role, not the physical `Employee` table; only one related display field survived | Complete the target entity's display pair from the named FK role |
| `JON-016` | 2 rather than 4 columns | The model grouped `Invoice.CustomerId` at invoice grain instead of lifting it to the requested bounded Customer entity | Lift an approved grouped FK to the related entity PK, then add its display fields |
| `RNK-007` | Row count differs | The model invented top-one for a display-style ranking that did not request a numeric N | Remove an invented limit for unnumbered display/rank requests |
| `UNS-007` | Strict extra-field validation | The provider expressed unsupported state through an extra `unsupported` marker | Treat a truthy marker as unsupported and discard all query material before validation |
| `AGG-007` | Row count differs | Expected output applies a 20-row presentation cap not stated by the question | No generic source change; needs an explicit product cardinality policy rather than benchmark-specific logic |

The first five follow-ups are implemented and covered by offline tests on the
new source hash `126c6ecdbc146098c1fb89ebe8c195e5837c40caa3474594f28b07b282dffc9d`.
`AGG-007` is deliberately not hard-coded. A live rerun has not been authorized
or performed on the new source.

## Boundary

Phase M failed its diagnostic target and cannot freeze a candidate. No holdout
case was selected into the run or scored, and no candidate manifest or combined
report was created. A separate local diagnostic accidentally displayed records
outside the development split, so the current `stage-7-v1` holdout is no longer
eligible as an unseen final holdout despite zero provider calls. The next safe
live action, if separately authorized, is a six-case development rerun with a
hard maximum of 12 requests. Any later final holdout requires an independently
curated, sealed replacement that this agent does not inspect.
