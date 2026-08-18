# Start Here

- Project: AI Database Analyst
- Memory version: `v1`
- Last updated: 2026-08-18

## Required reading order

Read these files before resuming work:

1. `AGENTS.md`
2. `project-memory/01-PROJECT-CONTEXT.md`
3. `project-memory/02-CURRENT-STATE.md`
4. The active plan linked from `02-CURRENT-STATE.md`
5. The newest entries in `project-memory/03-WORK-LOG.md`

Then run:

```powershell
git status --short
git log -1 --oneline
```

Do not assume the last session committed its changes. Do not overwrite unrelated
working-tree changes.

## Fast briefing

The project is a security-first conversational analytics system over Chinook.
It turns Indonesian or English questions into proposed SQL, validates the full
SQL AST, executes only rewritten read-only SQL, and presents database-grounded
results.

The production-shaped local stack, PostgreSQL roles, FastAPI, Streamlit, Docker,
CI/CD, semantic layer, evaluation corpus, and security controls already exist.
The currently verified LLM implementation is still `fake` /
`fake-deterministic`.

The active product goal is to implement points 1-7 in the real-LLM/agent plan:

1. choose a provider and model;
2. implement the real API adapter;
3. connect configuration securely;
4. test adapter and pipeline failure modes;
5. evaluate the real model;
6. expose bounded typed tools;
7. implement a bounded agent loop.

## Canonical links

- Active plan: `docs/real-llm-agent-implementation-plan.md`
- Overall project status: `PROJECT_STATUS.md`
- Architecture: `docs/architecture.md`
- Requirements: `docs/requirements.md`
- Security boundary: `docs/security.md`
- Threat model: `docs/threat-model.md`
- Evaluation methodology: `docs/evaluation.md`
- Durable decisions: `DECISIONS.md`

## Current decision gate

Point 1 is complete: the owner selected Google Gemini Developer API with hosted
`gemma-4-26b-a4b-it`. ADR-0035 is Accepted and the paid budget is USD 0 because
hosted Gemma 4 is currently free-only. The Gemini adapter and environment/
Compose wiring are implemented and live validated with a replacement local key.

The original keys exposed in chat or a tracked example remain compromised and
must never be reused. The owner completed a second rotation on 2026-08-08; the
active credential has no exact match in any tracked file, is stored only in
ignored `.env`, and passed one bounded live smoke. Points 2 and 3 are complete.
Point 4 is also complete: 12 offline mocked-Gemini pipeline/security cases and
the combined regression passed. Points 6-7 are complete as bounded authority,
loop, continuation, API, and UI work; this does not qualify the model.

Point 5 remains blocked. Phase N passed 5/6 and failed only `AGG-007`, whose old
20-row/two-column expectation was not justified by its unbounded question.
ADR-0048 now defines a generic policy: universal grouped requests return all
groups under the existing 500-row execution ceiling; model-invented limits are
removed unless the user requested a quantity; identifier-only groupings omit
an unrequested display field. Runtime contains no case-specific branch.

The new `stage-7-development-v2` corpus contains exactly 70 development cases,
no holdout, and a corrected complete 204-group `AGG-007` relation. The final
holdout must be an independently curated private 30-case replacement covering
all eight categories. Candidate freeze binds its public payload/attestation
manifest; the runner rejects version, hash, count, distribution, or split drift
before provider setup. Private JSONL and attestation text stay outside Git and
must not be inspected by the development agent.

Full offline verification passes 460 tests with four unavailable PostgreSQL
skips and 90.56% coverage. The owner-authorized complete v5 development run on
commit `23efdea` then passed 67/70 using 69/136 requests: structured 68/68,
valid SQL/read-only execution 61/61, execution accuracy 58/61 (95.08%),
clarification 2/2, and unsafe blocking 7/7. Hallucination, false blocking,
security bypass, measured paid cost, and holdout calls were zero.

The candidate is not frozen because the independent curator manifest is still
absent. This is the only current Point-5 blocker. After a valid manifest is
supplied, freeze may proceed; the one-time holdout has an exact maximum of 54
requests and requires separate owner authorization.
