# Project Memory

This folder stores durable Markdown context for future work sessions. It is
intended to survive conversation compaction, context reduction, application
restarts, and handoff to another Codex session as long as the repository files
remain available.

## How it works

`AGENTS.md` instructs future Codex sessions to read this memory before changing
the repository. The memory is split by purpose so stable facts do not get mixed
with frequently changing status:

| File | Purpose | Update frequency |
|---|---|---|
| `00-START-HERE.md` | Entry point and required read order | Rarely |
| `01-PROJECT-CONTEXT.md` | Stable architecture, boundaries, and terminology | When architecture changes |
| `02-CURRENT-STATE.md` | Active goal, status, blockers, and next action | Every material work session |
| `03-WORK-LOG.md` | Chronological evidence and handoffs | Append after material work |
| `04-SESSION-HANDOFF-TEMPLATE.md` | Template for ending or pausing work | Use as needed |

Detailed plans remain in their canonical documentation files and are linked
from `02-CURRENT-STATE.md`. This avoids maintaining two copies of the same plan.

## Important limitation

This mechanism works automatically for Codex sessions that can access this
repository and follow `AGENTS.md`. A separate ChatGPT conversation without
filesystem/workspace access cannot read these files automatically; attach the
folder or paste `00-START-HERE.md` in that situation.

## Memory hygiene

- Store decisions, status, file paths, test evidence, blockers, and next steps.
- Do not store secrets, API keys, passwords, authorization headers, or raw
  sensitive data.
- Prefer links to canonical source files over copying long content.
- Put durable decisions in `DECISIONS.md` and security rules in the established
  security documentation.
- Verify current Git state before trusting an old handoff.
