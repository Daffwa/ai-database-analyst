# Tahap 6 Result and UX Contract

- Status: implemented and verified
- Date: 2026-07-20
- Runtime: `backend/runtime/stage6.py`
- UI: `frontend/streamlit_app.py`

## Purpose

Tahap 6 converts a security-approved database result into an auditable user
experience. It does not change the generated SQL, executed SQL, security
decision, or raw database values. Every chart and explanation is derived only
after the database returns a result.

## Result Contract

`ResultFormatter` validates the result shape and produces two parallel views:

- `rows`: immutable raw database values used as evidence and for CSV export.
- `display_rows`: formatted strings used only for presentation.
- `columns`: stable names, labels, roles, formats, and nullability.
- `row_count`, `truncated`, and execution latency.
- source tables and columns from validated query provenance.

Column roles are inferred from returned values as `identifier`, `temporal`,
`measure`, `category`, or `unknown`. Identifiers are never treated as continuous
measures. Currency values have two decimals but no symbol because Chinook has no
currency-code field. The raw value is never replaced by a display string.

## Deterministic Chart Rules

The selector uses only columns present in the normalized result:

| Result shape | Presentation |
|---|---|
| One row and one numeric measure | KPI |
| Valid time field plus numeric measure | Line chart |
| Category plus numeric measure | Bar chart |
| Two continuous numeric measures | Scatter plot |
| Empty, unsupported, or unsuitable shape | No chart or exact table |

Time values are parsed and sorted before rendering. A categorical result above
the configured category limit falls back to a table. Sparse series emit a
warning. The line renderer uses a temporal scale, a zero baseline, a bounded
number of horizontal date ticks, explicit tooltips, and a colorblind-conscious
palette. Chart specifications contain only result-column references.

## Grounded Explanation

`ResultSummarizer` is deterministic and does not call an LLM. A KPI cites its
exact returned cell, a bar summary cites the largest returned value and its
category, and a line summary cites the chronological first and last values.
Every number has `NumericEvidence` containing column, row index, raw value, and
display value. Empty results receive an explicit non-error explanation.

## Explicit UI States

The response contract distinguishes `success`, `empty`, `clarification`,
`blocked`, `unsupported`, `pending`, `timeout`, and `error`. Timeout and generic
runtime failures are mapped from sanitized application errors. Empty results
remain successful executions and are not rendered as generic errors.

## Audit and Supporting Features

- Generated SQL and validator-owned executed SQL are labeled separately.
- The validation badge, assumptions, warnings, sources, request ID, semantic
  provenance, pipeline stages, and latency metadata remain visible.
- Query history is bounded and in-memory. It stores only request ID, timestamp,
  status/state, SQL fingerprint, row count, truncation, latency, and fixed
  feedback. It excludes raw questions, SQL, and result rows.
- Feedback accepts only `correct`, `partially_correct`, or `incorrect` for a
  known request and updates the corresponding history entry.
- CSV export is byte-bounded UTF-8 with a BOM and neutralizes spreadsheet
  formula prefixes without mutating the raw result.
- Database Explorer exposes schema descriptions, columns, keys, and
  relationships without sample rows.
- System Info uses an explicit safe allowlist and excludes credentials, URLs,
  and secrets.

## Evaluation Evidence

The `stage-6-v1` evaluator runs the 20 closed database cases through the full
semantic, SQL-security, database, and result pipeline. The measured result is:

- database result identity: 20/20;
- normalized presentation identity: 20/20;
- chart contract validity: 20/20;
- expected type for four explicit chart cases: 4/4;
- grounded numeric summaries: 20/20;
- bounded valid CSV exports: 20/20;
- empty state, feedback, history privacy, explorer, and System Info checks:
  passed.

The selected chart distribution was 3 KPI, 3 table, 5 line, and 9 bar. Full
project verification passed 249 tests with 95.45% branch coverage.

## Visual QA

The local Streamlit app was exercised in the in-app browser with the monthly
revenue question. The first rendering exposed colliding labels across 60
months. The line chart was changed to a bounded Altair temporal axis and checked
again: labels were readable, the zero baseline was visible, and the browser
console contained no errors.

## Known Limitations

- History and feedback are process-local and not durable.
- The fake adapter supports the closed local catalog; arbitrary language and a
  real provider are not evaluated here.
- Chinook does not provide an explicit currency code or business timezone.
- Charts describe returned data; they do not prove causality or business
  correctness.
- CSV export is intentionally bounded and is not a bulk-data interface.
- Authentication, tenant authorization, PostgreSQL roles, and production API
  separation remain later stages.
