# Start Here

- Project: AI Database Analyst
- Memory version: `v1`
- Last updated: 2026-08-08

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
the combined regression passed. Point 5 remains blocked at the formal gate. The
fail-closed `semantic-v2` complete-development rerun reached 45.90% execution
accuracy. The owner then selected Gemma-only runtime `v5-plan`: Gemma emits a
typed AnalysisPlan and deterministic code grounds schema, derives joins,
completes bounded projections, compiles SQL, checks alignment, and retains the
existing AST/read-only boundaries. On 12 previously failed development cases,
frozen pilots progressed from the prompt-v4 baseline 0/12 to 2/12, 6/12, and
8/12. Pilot v3 met its engineering target but not the formal 85%/99% gates.
The four remaining Phase-F failures now pass targeted live correction smokes,
and the exact final Stage-1 12-case hard pilot then reached 10/12 using 12/24
requests. Structured plan validity, valid SQL, and execution success were all
100%, but execution accuracy was 83.33%, below the unchanged 85% gate.
`RNK-004` and `SUB-001` were the remaining substantive mismatches. A generic
ordering correction then passed both cases exactly in a bounded 2/2 smoke using
2/4 requests. No candidate was frozen and holdout cases scored remain zero.
This is staged development evidence; the max-136 complete development split
was then authorized and completed with 52/70 cases passed, 94.12% structured
validity, 72.13% execution accuracy, and 85.71% known-unsafe blocking. Those
results failed the unchanged formal gates. Phase M then targeted its 18
development failures and improved the same-case result from 0/18 to 12/18,
with 17/18 structured outcomes and 17/17 valid SQL/read-only executions, but it
failed its 15/18 diagnostic target and unsafe classification. No candidate was
frozen and holdout remained zero. Five further generic corrections now pass
offline regression at 409 passed, four skipped, and 90.10% coverage on source
hash `126c6ecdbc...`; this source has made zero provider calls. Do not begin
point 6 or open holdout. The next possible action is a separately authorized
six-case Phase-N development rerun capped at 12 requests.
The existing `stage-7-v1` holdout also lost unseen-content eligibility after a
local diagnostic accidentally displayed records outside development. It has
zero provider calls and zero scored cases, but a future final gate requires an
independently curated sealed replacement that this agent does not inspect.
