# Security Policy

## Supported version

This repository is a local portfolio pre-release. Security fixes are applied to
the current `main` branch only; no long-term support release exists yet.

## Reporting a vulnerability

Do not open a public issue for a suspected vulnerability, leaked credential, or
private data exposure. Until an authorized GitHub repository and private
security-advisory channel exist, contact the repository owner privately and
include only:

- the affected component and version or commit;
- reproduction steps using synthetic data;
- expected and observed behavior;
- impact and any safe mitigation.

Never include real credentials, connection strings, raw questions, generated
SQL, database rows, or personal data in a report. A public reporting address
will be added only after the owner and publication workflow are chosen.

## Security boundary

LLM output is untrusted. The prompt and model are not authorization controls.
Before execution, one complete SQL statement is parsed with SQLGlot and checked
recursively against statement, schema, table, column, function, catalog,
complexity, and result-budget policies. The policy emits separate generated and
limit-rewritten executed SQL. PostgreSQL execution then requires the exact
`analytics_readonly` role and a read-only transaction.

The browser-facing Streamlit process has no database credential. FastAPI owns
the analytics and metadata connections, which use separate least-privilege
roles. Metadata and logs exclude raw questions, SQL, result rows, credentials,
authorization headers, and database URLs by default.

These controls reduce risk; they do not prove that all unknown bypasses,
semantic errors, denial-of-service cases, or provider-side data risks are
eliminated. The full model and residual risks are in
[`docs/threat-model.md`](docs/threat-model.md).

## Public-deployment requirements

The local Compose stack binds published ports to loopback and is not a public
deployment template. Before any internet exposure, the operator must provide:

1. HTTPS termination and a private backend network.
2. Authentication, per-user authorization, and rate limiting.
3. Managed secrets with rotation and no plaintext values in source or images.
4. Managed PostgreSQL with separate analytics and metadata credentials.
5. Safe migrations, backups, monitoring, and a tested rollback.
6. A reviewed LLM provider data-retention policy when a real provider is used.
7. Post-deployment success, clarification, blocked, timeout, health, and log
   smoke tests.

See [`docs/deployment.md`](docs/deployment.md) for the release procedure.

## Verification

Run the local release checks from a clean environment:

```powershell
uv sync --extra dev
uv run python scripts/dev.py verify
uv run python scripts/dev.py test-postgres
uv run python scripts/dev.py docker-smoke
uv run python scripts/dev.py security-stage9
uv run python scripts/dev.py test-clean-checkout
```

The security runner covers dependency audit, Bandit, Gitleaks, SQL adversarial
tests, container image vulnerability/secret scans, and Dockerfile
configuration checks. Passing a finite scanner set is regression evidence, not
a vulnerability-free guarantee.

