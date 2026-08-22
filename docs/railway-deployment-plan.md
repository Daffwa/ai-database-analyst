# Railway Deployment Plan

- Date: 2026-08-22
- Status: Railway project connected; no service or database deployed
- Target: private staging before any authenticated public demo
- Source repository: `Daffwa/ai-database-analyst`

## Goal

Translate the verified local Compose topology into Railway services without
claiming a public deployment or exposing unauthenticated application routes.

## Completed connection work

- [x] Review current Railway CLI, Docker/Compose, PostgreSQL, private-network,
  healthcheck, and trial documentation.
- [x] Authenticate the local Railway CLI through the owner's account.
- [x] Create and link an empty Railway project named `ai-database-analyst`.
- [x] Create an empty `staging` environment and make it the local CLI target;
  leave the default `production` environment empty.
- [x] Confirm the project contains no services, databases, buckets, volumes,
  domains, or active deployments.
- [x] Preserve a clean Git working tree and keep Railway credentials outside
  the repository.
- [x] Update the Stage 10 documentation contract to require the new Railway
  connection state while preserving the no-service and no-public-routing gates.
- [x] Pass PR #33 hosted gates on corrective commit `d858001`: Python
  3.11/3.12 quality, PostgreSQL integration, clean Compose, source/container
  security, CodeQL, and CodeRabbit.

## Intended service mapping

| Local Compose service | Railway service | Exposure |
|---|---|---|
| `db` | Managed PostgreSQL | Private only |
| `bootstrap` | One-shot bootstrap/migration service | Private, no domain |
| `api` | FastAPI from `Dockerfile.api` | Private, no domain |
| `frontend` | Streamlit from `Dockerfile.frontend` | No public domain until authentication and rate limits exist |

Use Railway variable references and private networking for database and
service-to-service traffic. Set explicit service `PORT` values of `8000` for
the API and `8501` for Streamlit because the current immutable image commands
bind those ports. Configure healthcheck paths `/api/v1/health` and
`/_stcore/health` respectively.

## Remaining approval gates

- [ ] Merge PRs #27, #28, and #32 in dependency order and deploy an exact
  reviewed commit from `main`, unless the owner explicitly authorizes an
  ephemeral branch deployment.
- [ ] Approve the Railway staging region and maximum monthly or trial-credit
  budget before creating compute or PostgreSQL resources.
- [ ] Select and implement authentication, per-user authorization, request/body
  limits, rate limiting, and abuse controls before generating a public domain.
- [ ] Approve Railway Variables as the staging secret store and create distinct
  owner, analytics, metadata, migration, and evaluation credentials.
- [ ] Review Gemini data governance before adding a real-provider credential;
  otherwise deploy with `fake` / `fake-deterministic` only.
- [ ] Create the four Railway services, bootstrap PostgreSQL, apply Alembic
  through the current head, and verify role separation.
- [ ] Run health, success, clarification, blocked, timeout, privacy, and
  database read-only smoke tests.
- [ ] Record image/source identifiers, logs, rollback target, costs, and hosted
  evidence before changing the project status to deployed.

## Stop conditions

Do not create Railway compute/database resources without an approved budget.
Do not generate a public domain while application authentication and rate
limiting are absent. Do not copy local `.env` values into Git, documentation,
chat, build arguments, or image layers.

## Current Railway references

- [Railway Docker Compose mapping](https://docs.railway.com/guides/docker-compose)
- [Railway PostgreSQL](https://docs.railway.com/databases/postgresql)
- [Railway healthchecks](https://docs.railway.com/deployments/healthchecks)
- [Railway private-network best practices](https://docs.railway.com/overview/best-practices)
- [Railway trial limits](https://docs.railway.com/pricing/free-trial)
