# Tahap 10 Repository Release Audit

- Audit date: 2026-07-28 (Asia/Bangkok)
- Outcome: **repository release gate passed**
- Public application deployment: **pending platform and security decisions**
- Machine report: `reports/evaluation/stage-10-readiness.json`
- Hosted evidence: `reports/evaluation/stage-10-external-evidence.json`

## Release work completed

- Reworked README around the actual problem, implemented features, safe setup,
  fake-provider boundary, example outcomes, limitations, roadmap, screenshots,
  and evidence.
- Added `SECURITY.md`, API reference, deployment/rollback guide, and a reviewed
  demo script.
- Finalized architecture and threat-model sections for the local release
  candidate while explicitly rejecting any public-deployment claim.
- Added a deterministic Tahap 10 evaluator for required documents, README
  commands, local links, screenshots, prior gates, and external decisions.
- Added the Tahap 7 adversarial fake mappings to the final API runtime so a
  destructive UI question crosses the same structured-model boundary and is
  blocked by the PostgreSQL AST policy. The API image now includes the
  content-addressed corpus required by that demo path.
- Restricted the Gitleaks local allowlist to exact ignored `.env` and
  `.env.compose` files; `.example` files remain scanned.
- Published the MIT-licensed repository publicly under `Daffwa`, verified CI,
  Docker, Security, and Evaluation on GitHub-hosted runners, and recorded their
  immutable run IDs against one commit.
- Patched the transitive GitPython vulnerability, refreshed Streamlit, NumPy,
  sqlglot, setuptools, CodeQL, setup-uv, and checkout, and closed every
  Dependabot pull request only after its relevant hosted gates passed.

## Browser QA

Journey: open Streamlit → submit “Berapa jumlah pelanggan?” → inspect the value
`59`, generated/executed SQL, AST badge, result, source, and audit metadata.

| Check | Result |
|---|---|
| URL/title and nonblank DOM | Passed at `http://127.0.0.1:8501/` |
| Framework exception overlay | Absent |
| Success interaction | Passed; status `success`, Customer Count `59` |
| Clarification interaction | Passed; no generated/executed SQL |
| Destructive interaction | Passed after fix; status `blocked`, AST badge blocked, no execution |
| Database Explorer | Passed; PostgreSQL schema selector rendered |
| Query History privacy notice | Passed |
| System Info health | Passed |
| Console warnings/errors | 0 |
| Screenshot sensitive-data review | Passed; synthetic Chinook data only, no credential visible |
| Desktop viewport | 1280 × 720 |
| Mobile viewport | Not run; viewport control was unavailable in the in-app browser |

Evidence:

- `reports/screenshots/stage-9-ui-result.jpg`
- `reports/screenshots/stage-9-ui-details.jpg`

## Final audit evidence

| Gate | Command/evidence | Result |
|---|---|---|
| Format and lint | `uv run python scripts/dev.py verify` | Passed; 150 files formatted, Ruff clean |
| Strict typing | same | Passed; Mypy 144 source files |
| Offline unit/integration/security/UI/evaluation | same | Passed; 305 collected, 301 passed, 4 PostgreSQL-gated skipped |
| Branch coverage | same | Passed; 92%, minimum 90% |
| Full deterministic evaluation | `evaluate-stage7` inside verify | 100/100; unsafe 10/10, ambiguity 5/5 |
| Live PostgreSQL/API | `uv run python scripts/dev.py test-postgres` | 4/4 passed, including destructive blocked state |
| Clean no-cache Compose | `uv run python scripts/dev.py docker-smoke` | Passed; healthy db/API/frontend and cleanup |
| Security toolchain | `uv run python scripts/dev.py security-stage9` | Passed; dependency, SAST, Gitleaks, SQL, Trivy image/config |
| Clean checkout | `uv run python scripts/dev.py test-clean-checkout` | Passed on Python 3.11 and 3.12 |
| README commands/links/screenshots | `evaluate-stage10` | All local checks passed; no broken local links |

The complete project-owned security gate and GitHub-hosted Security workflow
both pass. Gitleaks scans the complete current checkout with the reviewed
allowlist; no Git-history scan is claimed. Pip-audit reports no known
installed-package vulnerabilities, and the hosted container/configuration scans
pass on the recorded release commit.

## Definition of Done

- [x] Clean-checkout local reproduction passes.
- [x] Docker Compose is healthy from a no-cache build.
- [x] Required tests, evaluation, and destructive blocking pass.
- [x] Dataset provenance, README, threat model, and `SECURITY.md` are present.
- [x] Local links and reviewed screenshots pass the machine gate.
- [x] Current source, examples, reports, images, and containers pass secret and
  vulnerability checks.
- [x] Project license selected: MIT.
- [x] Git identity, authorized GitHub owner/name/visibility, public remote, and
  hosted Actions verified.
- [ ] Public platform, cost approval, authentication/rate limiting, managed
  PostgreSQL/secrets, HTTPS, smoke tests, logs, and rollback verified if a
  public demo is requested.

No paid resource, public application URL, cloud secret, managed production
database, or real LLM credential was created during this audit.
