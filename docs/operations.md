# Local Operations, Release Gates, and Diagnosis

This guide covers the reproducible local container stack and its automated
quality gates. It is not a public-deployment guide: TLS, authentication, rate
limiting, a managed secret store, and a hosting platform remain external
release decisions documented in `deployment.md`.

## Stack and trust boundaries

```text
browser
  -> frontend (non-root, read-only filesystem)
    -> API (non-root, read-only filesystem)
      -> analytics_readonly -> analytics views
      -> app_metadata_user -> app_metadata tables
bootstrap (one-shot migration/data job)
  -> migration/admin boundary
PostgreSQL -> named development volume
```

PostgreSQL is attached only to the internal backend network. The API and
frontend publish localhost ports. Compose requires generated credentials and
does not provide fixed password defaults. Runtime images use pinned base-image
digests, explicit source copies, health checks, UID/GID `10001:10001`, and no
`.env` file.

## Start the local stack

Requirements: Docker Desktop or another healthy Docker Engine with Compose,
plus the locked Python development environment.

```powershell
uv sync --frozen --extra dev
uv run python scripts/dev.py generate-compose-env
docker compose --env-file .env.compose up --build --wait
```

Open `http://127.0.0.1:8501`. The API health contract is available at
`http://127.0.0.1:8000/api/v1/health`. `.env.compose` is local-only, generated
with random URL-safe values, and must never be committed or pasted into logs.

Stop the services while preserving development data:

```powershell
docker compose --env-file .env.compose down --remove-orphans
```

## Safe development reset

The following command deletes only the named Compose project's local
PostgreSQL development volume. It does not delete source files or unrelated
Docker volumes. Confirm that the command is run from this repository and that
the resolved project is `ai-database-analyst` before proceeding.

```powershell
docker compose --env-file .env.compose config --quiet
docker compose --env-file .env.compose down --volumes --remove-orphans
```

Regenerate credentials only when the old environment file is intentionally
being replaced:

```powershell
uv run python scripts/dev.py generate-compose-env --force
```

## Reproducible gates

```powershell
# Actual PostgreSQL roles, migration, API, and persistence
uv run python scripts/dev.py test-postgres

# Clean no-cache build, whole-stack readiness, query, trace, log, and image checks
uv run python scripts/dev.py docker-smoke

# Dependency, Bandit, Gitleaks, SQL-policy, Trivy image, and config checks
uv run python scripts/dev.py security-stage9

# Deterministic implementation and external-evidence summary
uv run python scripts/dev.py evaluate-stage9

# Offline formatting, lint, typing, evaluation, coverage, and tests
uv run python scripts/dev.py verify
```

`docker-smoke` creates temporary credentials and free localhost ports, builds
without cache, waits for database/API/frontend readiness, issues a real API
query, verifies correlation and operational metrics, checks that image history
contains no generated credential, and removes its containers and volume.

## Observability and diagnosis

The frontend sends a canonical UUID in `X-Request-ID`. FastAPI accepts only a
canonical UUID or replaces it, returns it in the response header/body, binds it
to the orchestration context, and carries it through SQL security and database
execution logs.

Analytics completion logs contain these stable fields:

- `request_id`, `stage`, `status`, `model`, and `prompt_version`;
- `schema_hash` and literal-redacted `sql_fingerprint`;
- `latency_ms`, `row_count`, and `error_code`.

They exclude raw questions, generated/executed SQL, result rows, passwords,
API keys, authorization headers, and connection strings. Use one known request
ID to filter the API logs rather than exporting the entire log stream:

```powershell
docker compose --env-file .env.compose logs --no-color api | Select-String '<request-uuid>'
```

The token-protected `GET /api/v1/operations/metrics` endpoint reports process
uptime, HTTP request rate, success/blocked/clarification/timeout/repair rates,
latency, status counts, errors, and nullable token usage. Fake-provider token
usage is explicitly `null`; it is never fabricated as zero. The endpoint
contains no questions, SQL, rows, URLs, or credentials.

Diagnosis order:

1. Check `docker compose ... ps` and the three health states.
2. Check whether the one-shot `bootstrap` service exited successfully.
3. Correlate a failed request by its response `X-Request-ID`.
4. Compare safe `error_code`, status counters, and latency before viewing logs.
5. Re-run `test-postgres`, then `docker-smoke`, then `security-stage9` to isolate
   database authorization, stack readiness, and security-tool failures.

## GitHub Actions boundaries

- `ci.yml`: Python 3.11/3.12 quality matrix, coverage artifact, and live
  PostgreSQL/API integration.
- `security.yml`: dependency audit, SAST, source secret scan, SQL security
  tests, pinned-digest container scan, and CodeQL.
- `evaluation.yml`: manual/weekly deterministic evaluation artifacts.
- `docker.yml`: clean no-cache Compose smoke artifact.

Workflows declare least-privilege permissions, disable persisted checkout
credentials, reference actions by full commit SHA, and reference no repository
secret. Image publication is intentionally absent; a registry push may be
added only for an authorized tag/release after registry ownership and
credentials are configured.

## Residual risks

- The metrics store is process-local and resets when the API restarts.
- The stack binds only to localhost and has no public authentication, TLS, or
  rate limit; it must not be exposed directly to the internet.
- Compose uses local generated environment values, not a production secret
  manager.
- Trivy, Gitleaks, Bandit, pip-audit, and CodeQL reduce known risk but cannot
  prove the absence of unknown vulnerabilities or semantic data leakage.
- Semantic definitions remain `project_verified`; currency/timezone policy and
  independent analyst approval remain unresolved.

## Tahap 10 release operations

Use `docs/demo-script.md` for the portfolio walkthrough and
`docs/deployment.md` for the production control and rollback sequence. The
local stack is intentionally loopback-only; do not publish its ports through a
router, tunnel, or cloud firewall as a substitute for the missing public
controls.

Before a release candidate is handed off, rerun the exact source through:

```powershell
uv run python scripts/dev.py verify
uv run python scripts/dev.py test-postgres
uv run python scripts/dev.py docker-smoke
uv run python scripts/dev.py security-stage9
uv run python scripts/dev.py test-clean-checkout
```

Then verify local documentation links and screenshots, review the reports for
sensitive data, and record whether GitHub publication and deployment were
performed or are intentionally not applicable. Never mark a hosted workflow or
public smoke test as passed from local workflow-file inspection alone.
