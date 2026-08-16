# Stage 7 Semantic Comparison Policy v2 Audit

- Gate: passed
- Dataset: `stage-7-v1` / `34002b865f657bf12401627b91b88f09ed07d5ffe53b08683015b384960b6542`
- Split scored: `development`
- Policy: `semantic-v2`
- Holdout cases scored: 0

| Invariant | Result |
|---|---:|
| Exact self matches | 61/61 |
| Presentation variants accepted | 61/61 |
| Same variants rejected by strict-v1 | 61/61 |
| Substantive variants rejected | 122/122 |
| Required-order changes rejected | 47/47 |
| Irrelevant-order changes accepted | 1/1 |

## Gate failures

None.

## Boundaries

- The audit uses deterministic transformations of development expectations, not new provider outputs.
- Value-aligned aliases pass only when a unique one-to-one mapping is provable.
- Extra or missing columns, ambiguous mappings, changed values, changed row counts, and required-order changes remain failures.
- The audit does not estimate how many prior provider failures semantic-v2 will fix because privacy-safe reports do not retain raw SQL or result rows.
