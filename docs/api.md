# API Reference

The versioned FastAPI surface uses the `/api/v1` prefix. In non-production
mode, interactive OpenAPI documentation is available at `/api/v1/docs` and the
schema at `/api/v1/openapi.json`. Production disables the interactive docs.

| Method | Path | Purpose | Protection |
|---|---|---|---|
| `GET` | `/health` | readiness of API and database runtime | public health probe |
| `POST` | `/query` | process one bounded natural-language question | deployment auth required before public use |
| `POST` | `/agent/query` | start a bounded typed-tool run | deployment auth required before public use |
| `POST` | `/agent/continue` | resume an issued clarification using a canonical option ID | deployment auth and continuation claim |
| `POST` | `/agent/cancel` | consume an unused clarification continuation | deployment auth and continuation claim |
| `GET` | `/schema` | schema-only Database Explorer snapshot | deployment auth required |
| `POST` | `/workspaces` | create an expiring workspace from raw SQLite/SQL bytes and `X-Upload-Filename` | loopback only; deployment auth and upload quota required before public use |
| `GET` | `/workspaces/{id}/schema` | inspect the uploaded workspace schema | possession of ID is not authorization; deployment auth required |
| `POST` | `/workspaces/{id}/query` | generate, validate, and execute against only that uploaded SQLite workspace | deployment auth and per-user workspace ownership required before public use |
| `DELETE` | `/workspaces/{id}` | destroy the workspace and temporary database | deployment auth and per-user workspace ownership required before public use |
| `GET` | `/history` | privacy-minimized query metadata | deployment auth and per-user authorization required |
| `POST` | `/feedback` | fixed-category feedback for a known request | deployment auth required |
| `GET` | `/evaluation/baseline` | tracked evaluation summary | `EVALUATION_API_TOKEN` |
| `GET` | `/operations/metrics` | payload-free process aggregates | `EVALUATION_API_TOKEN` |

The table paths are relative to `/api/v1`. Request models reject extra fields,
question length is bounded by configuration, and exceptions map to stable safe
contracts with a request ID. The current local implementation has no end-user
authentication; loopback binding is therefore mandatory until the deployment
controls in [`deployment.md`](deployment.md) are implemented.

Example health check:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
```

Example query:

```powershell
$body = @{ question = "Berapa jumlah pelanggan?" } | ConvertTo-Json
Invoke-RestMethod -Method Post -ContentType application/json `
  -Uri http://127.0.0.1:8000/api/v1/query -Body $body
```

Responses may represent success, empty result, clarification, blocked,
unsupported, timeout, or error. Generated SQL is never interchangeable with
the separately validated and limit-rewritten executed SQL.

Example bounded-agent start:

```powershell
$body = @{ question = "Siapa pelanggan terbaik?" } | ConvertTo-Json
$response = Invoke-RestMethod -Method Post -ContentType application/json `
  -Uri http://127.0.0.1:8000/api/v1/agent/query -Body $body
```

When `status` is `clarification_required`, resume with the issued opaque ID,
one exact `option_id`, and the original question. The server verifies the
question digest and active semantic version before consuming the continuation:

```powershell
$resume = @{
  continuation_id = $response.clarification.continuation_id
  option_id = "total_spend"
  question = "Siapa pelanggan terbaik?"
} | ConvertTo-Json
Invoke-RestMethod -Method Post -ContentType application/json `
  -Uri http://127.0.0.1:8000/api/v1/agent/continue -Body $resume
```

See [`bounded-agent.md`](bounded-agent.md) for tool authority, budgets,
durable continuation fields, and the model-qualification boundary.

## Uploaded SQLite workspace

The upload body is raw `application/octet-stream`; the percent-encoded UTF-8
filename is carried in the bounded `X-Upload-Filename` header so filenames do
not enter ordinary access-log URLs. Multipart parsing is intentionally not required. The
API accepts SQLite `.db`, `.sqlite`, `.sqlite3`, and restricted SQLite `.sql`
files. Example:

```powershell
$path = Resolve-Path .\sample.sql
$name = [Uri]::EscapeDataString((Get-Item $path).Name)
$workspace = Invoke-RestMethod -Method Post -ContentType application/octet-stream `
  -Headers @{ "X-Upload-Filename" = $name } -InFile $path `
  -Uri "http://127.0.0.1:8000/api/v1/workspaces"

$body = @{ question = "Berapa jumlah pengguna?" } | ConvertTo-Json
Invoke-RestMethod -Method Post -ContentType application/json `
  -Uri "http://127.0.0.1:8000/api/v1/workspaces/$($workspace.workspace_id)/query" `
  -Body $body

Invoke-RestMethod -Method Delete `
  -Uri "http://127.0.0.1:8000/api/v1/workspaces/$($workspace.workspace_id)"
```

Each response exposes only an opaque workspace ID, content hash, counts,
expiry, provider readiness, warnings, and schema metadata. It never exposes a
server path. Workspaces are process-local, expire after 30 minutes by default,
and are deleted on API shutdown or explicit `DELETE`. Queries are never stored
in the PostgreSQL metadata history through this route.

SQL dumps allow only ordinary `CREATE TABLE`, `CREATE INDEX`, literal
`INSERT ... VALUES`, and transaction markers. The importer rejects views,
triggers, virtual tables, attached databases, computed inserts/indexes, DML
other than literal inserts, malformed encodings, and budget overruns. The
resulting file is integrity-checked, opened with SQLite `mode=ro`,
`query_only=ON`, and `trusted_schema=OFF`, and queried only after the normal
SQLGlot allowlist policy passes.
