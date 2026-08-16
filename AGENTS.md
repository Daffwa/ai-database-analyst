# Repository Agent Instructions

These instructions apply to the entire `ai-database-analyst` repository.

## Required startup context

Before making material changes:

1. Read `project-memory/00-START-HERE.md` completely.
2. Read `project-memory/02-CURRENT-STATE.md` completely.
3. Read every active plan linked from the current-state file.
4. Run `git status --short` and preserve unrelated user changes.
5. Verify important memory claims against the current source before relying on
   them; memory files are orientation and handoff artifacts, not a substitute
   for repository evidence.

## Required continuity updates

After material implementation, decisions, test results, or a change of next
step:

1. Update `project-memory/02-CURRENT-STATE.md`.
2. Append a concise entry to `project-memory/03-WORK-LOG.md`.
3. Update the status/checklists in the active implementation plan.
4. Record durable architecture decisions in `DECISIONS.md` rather than only in
   the memory files.

## Safety and scope

- Preserve the deterministic SQL security boundary and read-only execution.
- Treat all LLM output as untrusted.
- Never store API keys, credentials, raw authorization headers, or private data
  in memory files.
- Do not create paid resources or make paid live-provider calls without explicit
  user authorization.
- Keep fake-provider tests offline and deterministic.
