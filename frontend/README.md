# Streamlit UI

`streamlit_api_app.py` is the Tahap 9 containerized frontend and communicates only with the
versioned FastAPI API through `api_client.py`. `streamlit_app.py` remains the
Tahap 6 in-process fixture so earlier deterministic UI evidence stays
reproducible.

## Tahap 6 fixture

Run from the repository root after data setup:

```powershell
uv run python scripts/dev.py ui-stage6
```

The UI supports arbitrary Indonesian or English text input, but the fake adapter
only recognizes the 20 exact closed-catalog questions. Recognized SQL is parsed,
validated, limit-rewritten, and executed through the read-only database path.
Blocked proposals show safe violation codes, and unknown questions remain
unsupported. Generated SQL, executed SQL, validation metadata, and database
results are displayed separately.

Before generation, the Tahap 5 runtime resolves the versioned semantic layer.
Known ambiguous requests such as `Siapa pelanggan terbaik?` return localized
clarification options without calling the adapter or producing SQL. Explicitly
resolved requests carry canonical metric IDs, visible assumptions, semantic
version/content hash, and bounded verified-query provenance in the audit panel.

After execution, the Tahap 6 runtime preserves raw rows, creates a formatted
display view, selects a deterministic KPI/bar/line/scatter/table presentation,
and creates cell-grounded explanations. The four tabs provide AI Analyst,
schema-only Database Explorer, bounded metadata-only Query History, and
allowlisted System Info. CSV downloads are byte-bounded and spreadsheet formula
prefixes are neutralized. Feedback is restricted to correct, partially correct,
or incorrect.

## Tahap 9 API client

After PostgreSQL bootstrap and metadata migration, run the API and UI in
separate terminals:

```powershell
uv run python scripts/dev.py api
uv run python scripts/dev.py ui
```

The browser-facing process holds only `API_BASE_URL`; analytics and metadata
credentials stay in the FastAPI process.

The sidebar also accepts a SQLite database (`.db`, `.sqlite`, `.sqlite3`) or a
SQLite dump/schema (`.sql`). A successful upload activates an expiring,
server-owned workspace and switches both Database Explorer and prompt queries
to that workspace. Delete the workspace from the sidebar to return to Chinook.

SQL dumps are intentionally narrower than the full SQLite language. They may
contain `CREATE TABLE`, `CREATE INDEX`, and literal `INSERT ... VALUES`
statements plus transaction markers. Views, triggers, virtual tables,
`ATTACH`, computed imports, and other statements fail closed. With the fake
provider, arbitrary uploaded-schema prompts return unsupported; configure the
approved Gemini provider for open-ended prompt-to-query behavior. Relevant
schema metadata is sent to that provider, so do not upload private schemas or
data until the provider and deployment data policy are approved.
