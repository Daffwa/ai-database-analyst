# Tahap 9 Verification Summary

- Status: passed locally
- Date: 2026-07-21
- Readiness checks: 14/14 passed
- Preserved live PostgreSQL gate: 4/4 passed
- Offline suite: 298 passed, 4 environment-gated PostgreSQL tests skipped
- Branch coverage: 91.59% (minimum 90%)
- Mypy strict: 142 source files

## Container and Compose evidence

`uv run python scripts/dev.py docker-smoke` rebuilt both application images
without cache and passed the complete stack gate:

- PostgreSQL, FastAPI, and Streamlit became healthy after the one-shot
  bootstrap/migration service completed.
- API and frontend ran as `10001:10001` with no generated credential in image
  configuration or history.
- A real Indonesian query crossed frontend/API/PostgreSQL boundaries and its
  canonical request ID matched response body, response header, and structured
  analytics log.
- The required structured fields and protected operational rates were present.
- Logs contained no raw question, connection URL, or generated credential.
- The named gate containers and volume were removed after verification.

Machine evidence: `stage-9-compose.json`.

## Security evidence

`uv run python scripts/dev.py security-stage9` passed:

- frozen runtime dependency audit with pip-audit 2.10.1;
- Bandit 1.9.4 medium/high SAST gate;
- Gitleaks 8.30.1 source/config secret scan;
- the complete SQL security regression suite;
- Trivy 0.70.0 HIGH/CRITICAL fixed-vulnerability and secret scans for the API
  and frontend images;
- Trivy HIGH/CRITICAL Dockerfile configuration scanning with zero findings.

Gitleaks and Trivy ran from exact image digests. The report stores only boolean
outcomes and tool provenance; it contains no matched value, source snippet,
question, SQL, result row, URL, or credential.

Machine evidence: `../security/stage-9-security.json`.

## Clean-checkout CI evidence

`uv run python scripts/dev.py test-clean-checkout` inventoried only
Git-trackable files, created an isolated temporary commit, cloned it, verified
the initial checkout was clean, bootstrapped the pinned SQLite fixture, and ran
the exact deterministic quality sequence on Python 3.11 and 3.12. Both matrix
entries passed. The temporary repository and environments were removed; the
project repository was not committed.

The first run exposed and led to correction of a real workflow defect: a clean
checkout lacked the intentionally ignored SQLite runtime database. `ci.yml` and
`evaluation.yml` now run the pinned, checksum-verified data bootstrap before
evaluation.

Machine evidence: `stage-9-clean-checkout.json`.

## CI/CD and observability contracts

Four workflows cover quality/live integration, source and container security,
manual/scheduled evaluation, and no-cache Compose smoke. Workflow permissions
are least-privilege, checkout credentials are not persisted, third-party
actions use full commit SHAs, and no workflow references a repository secret.
Image push is intentionally absent until an authorized tag/release registry is
configured.

The API accepts only a canonical UUID correlation ID or generates one, binds it
to the request context, and propagates it through orchestration, SQL security,
and database execution. Privacy-safe logs use fingerprints rather than SQL.
The protected metrics endpoint reports request/outcome/timeout/repair rates,
latency, status/errors, and nullable fake-provider token usage.

## Boundary and remaining external evidence

The local Tahap 9 quality gate passes. GitHub-hosted workflow runs do not yet
exist because the repository has no authorized commit or publication; that is
a Tahap 10 release action, not a claim made by this report. Public deployment
also remains blocked on license, hosting, TLS, authentication/rate limiting,
and managed-secret decisions.
