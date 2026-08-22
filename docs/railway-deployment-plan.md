# Railway Deployment Plan

- Date: 2026-08-22
- Status: private staging health-gated in Singapore; no public domain
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
- [x] Accept the owner's Railway Hobby-plan authorization. Keep the CLI-reported
  USD 5 agent/account limit unchanged, add a USD 5 workspace soft alert, and do
  not create a workspace hard limit because Railway requires at least USD 10.
- [x] Provision a private managed PostgreSQL service in Singapore
  (`asia-southeast1-eqsg3a`) with no public TCP proxy or domain.
- [x] Create private `bootstrap`, `api`, and `frontend` service placeholders,
  configure Railway Variables without printing or persisting generated
  credentials, and keep `fake` / `fake-deterministic` as the provider.
- [x] Remove the first empty PostgreSQL deployment and volume after its initial
  generated credential appeared in CLI configuration output; replace it with a
  fresh healthy service and leave no registered temporary SSH key.
- [x] Pass every hosted PR #33 gate on deployment commit `eb90de0`, including
  the dedicated bootstrap image build and Trivy container/config scan.
- [x] Run bootstrap deployment `4f75d32d-ff44-4731-b24e-2412bb8fdb25`, seed
  the pinned Chinook counts, create separated roles/databases, and apply Alembic
  through `20260816_0002`/head; then remove privileged bootstrap variables and
  delete the completed ephemeral service.
- [x] Deploy healthcheck-gated private API deployment
  `b21897c1-abc0-4490-bbe7-3285ce04be71` and frontend deployment
  `2caf7c74-bc68-4087-9951-5bca31943c46` from clean commit `eb90de0`.
- [x] Verify all three retained services report `SUCCESS`, use one Singapore
  replica each, and expose zero custom or Railway service domains. Production
  remains empty.

## Intended service mapping

| Local Compose service | Railway service | Exposure |
|---|---|---|
| `db` | Managed PostgreSQL | Private only |
| `bootstrap` | Ephemeral `Dockerfile.bootstrap` job, deleted after success | None retained |
| `api` | FastAPI from `Dockerfile.api` | Private, no domain |
| `frontend` | Streamlit from `Dockerfile.frontend` | No public domain until authentication and rate limits exist |

Use Railway variable references and private networking for database and
service-to-service traffic. Set explicit service `PORT` values of `8000` for
the API and `8501` for Streamlit because the current immutable image commands
bind those ports. Configure healthcheck paths `/api/v1/health` and
`/_stcore/health` respectively.

## Remaining approval gates

- [ ] Merge PRs #27, #28, and #32 in dependency order and deploy an exact
  reviewed commit from `main`; the current owner-authorized staging attempt is
  an ephemeral deployment from the clean `agent/railway-staging` branch.
- [ ] Select and implement authentication, per-user authorization, request/body
  limits, rate limiting, and abuse controls before generating a public domain.
- [ ] Review Gemini data governance before adding a real-provider credential;
  otherwise deploy with `fake` / `fake-deterministic` only.
- [x] Pass hosted checks for the dedicated one-shot `Dockerfile.bootstrap`,
  bootstrap PostgreSQL, apply Alembic through the current head, and verify the
  runtime starts only with separated analytics/metadata identities.
- [x] Deploy the private API and frontend in Singapore after bootstrap succeeds.
- [x] Pass Railway deployment healthchecks for `/api/v1/health` and
  `/_stcore/health` and confirm the Streamlit-reported raw external IP is not
  reachable without Railway public networking.
- [ ] Run success, clarification, blocked, timeout, privacy, and explicit
  database read-only functional smoke tests through an authenticated/private
  test channel. Railway SSH was intentionally not trusted because Railway does
  not publish an authoritative host-key fingerprint.
- [x] Record source/deployment/image identifiers, rollback target, cost-limit
  state, and hosted evidence without storing secret values.

## Current deployment evidence

- Source: clean commit `eb90de06c83e3ffadcf23a7b4dae2aaacbe38283`.
- API image: `sha256:2d129b66cabf0597a6bd90b7e9afcbbb25db07aab54bab71573035a90129b81c`.
- Frontend image: `sha256:3d16632da2d933de71e708cdb3d634280e9c0687fca58ba71494d36f08a718e3`.
- Successful bootstrap image:
  `sha256:946e474e2b19b76a1e73768542a74524d1d9cf383a4bac8afa0835d2ac5c2a86`.
- Database image: `sha256:53f2aec0d73373caa91fe493e5d2bb908ee38310c79771cc1ce733dfee8d4545`.
- Provider: `fake` / `fake-deterministic`; no `LLM_API_KEY` is present.
- Cost evidence: USD 5 workspace soft alert, no workspace hard cap, and about
  USD 0.239 workspace usage at final verification (not attributed solely to
  this project). Hobby may bill overage beyond its included USD 5 usage.

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
