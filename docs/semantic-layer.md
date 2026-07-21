# Semantic Layer and Clarification — Tahap 5

- Status: implemented and validated for the Chinook SQLite MVP
- Semantic version: `v1`
- Semantic content hash:
  `3dc2a621c4eab93d8685a075569a65dfafed43c76eb082de511313f16f4ee3be`
- Compatible schema hash:
  `58c6c16d147308c44996f88c3b893c0baa264a9b0ca6d06418f1ba3f199def7c`
- Review status: `project_verified`; no named business analyst approval yet

## Canonical Artifacts

- `semantic/glossary.yaml`: nine bilingual terms and five ambiguity policies.
- `semantic/metrics.yaml`: ten metric definitions with source table, expression,
  grain, format, dimensions, period requirement, review status, and
  double-counting guidance.
- `semantic/joins.yaml`: eleven approved relationships tied to physical foreign
  keys, cardinality, and duplication risk.
- `semantic/verified_queries.yaml`: ten status-aware question/SQL definitions
  with metric/join references and result hashes where available.

All four files repeat `semantic_version` and `schema_hash`. The loader computes a
canonical SHA-256 over their validated models. Startup fails if YAML is missing
or malformed, versions disagree, or the active schema hash changes.

## Validation Contract

`SemanticLayerValidator` checks:

- unique IDs and conflict-free synonyms per language;
- every table and qualified dimension/time column against the schema snapshot;
- every metric as one safe parsed SQL expression over its declared source table;
- every join key for arity, existing columns, and a matching physical foreign
  key in either direction;
- every clarification option's referenced metric IDs;
- every verified query's metric/join IDs and complete SQL through the Tahap 4
  AST security policy;
- compatibility with the configured `SEMANTIC_VERSION` and active schema hash.

Validation issues use stable safe codes and do not expose parser paths or raw
database errors. The active bundle contains 9 terms, 10 metrics, 11 joins, and
10 valid verified queries with zero validation issues.

## Business Definitions

The key grain distinction is:

- transaction: one `Invoice`;
- product line: one `InvoiceLine`;
- product: one `Track` for this MVP;
- invoice revenue: `SUM(Invoice.Total)` at invoice grain;
- product sales value:
  `SUM(InvoiceLine.UnitPrice * InvoiceLine.Quantity)` at line grain.

`Invoice.Total` must not be summed after a one-to-many join to `InvoiceLine`
unless invoices are deduplicated. Playlist membership can also duplicate tracks
because a track may appear in multiple playlists.

Metric formats such as `currency` describe display intent only. Chinook does not
store a currency code, so the application must not claim a specific currency
until a project convention is approved. The dataset also contains no timezone
metadata.

## Clarification Policy

The deterministic engine runs before prompt construction and LLM invocation.
It requests clarification for:

- best customer: total spend, transaction count, or latest transaction;
- active customer: transacted in a stated period or ever transacted;
- best product: sales value, units sold, or distinct transaction count;
- latest revenue: latest invoice, month, or year;
- largest sales: monetary value or units sold.

If a resolution phrase is explicit, the selected option's metric IDs and
localized assumption are attached to `QueryResponse`. If no option is explicit,
no prompt is built, no model is called, and no SQL is generated. Semantic audit
logs keep version/hash, matched IDs, clarification rule, verified query IDs, and
assumption count without raw question or assumption text.

## Verified Query Retrieval

Retrieval is deterministic, bilingual, lexical, and bounded to three examples by
default. Exact matches rank first; approximate matches use content-token overlap
plus matched metric IDs. Only queries with `status: valid` and a non-draft
review status are eligible. Retrieved examples enter the prompt as reference
patterns and never bypass structured output validation, AST policy, limit
rewriting, or database read-only enforcement.

## Evaluation and Change Gate

`python scripts/dev.py verify` now runs semantic validation and the Stage 5
evaluation before the complete test suite. Therefore a semantic or schema change
cannot pass the standard gate without rerunning clarification and retrieval
regressions.

Measured `stage-5-v1` results:

| Metric | Result |
|---|---:|
| Ambiguous cases correctly clarified | 10/10 |
| Explicitly resolved cases not clarified | 10/10 |
| Existing baseline false clarifications | 0/20 |
| Exact valid verified-query retrieval | 10/10 |
| Existing database baseline execution/result match | 20/20 |

Run the focused checks with:

```powershell
uv run python scripts/dev.py semantic-validate
uv run python scripts/dev.py evaluate-stage5
uv run python scripts/dev.py test-semantic
```

## Remaining Decisions

- A qualified business analyst or owner must review definitions before any
  `analyst_verified` status is used.
- Currency, timezone, and an optional default active-customer window remain
  explicitly unresolved.
- The deterministic lexical corpus is finite and does not establish natural
  language generalization for a real model.
- Persisted multi-turn clarification context and a metadata database remain
  later API/persistence work; approved assumptions are currently preserved in
  response and safe audit metadata.
