# API Reference

The versioned FastAPI surface uses the `/api/v1` prefix. In non-production
mode, interactive OpenAPI documentation is available at `/api/v1/docs` and the
schema at `/api/v1/openapi.json`. Production disables the interactive docs.

| Method | Path | Purpose | Protection |
|---|---|---|---|
| `GET` | `/health` | readiness of API and database runtime | public health probe |
| `POST` | `/query` | process one bounded natural-language question | deployment auth required before public use |
| `GET` | `/schema` | schema-only Database Explorer snapshot | deployment auth required |
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

