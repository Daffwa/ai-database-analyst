# Session Handoff Template

Copy the structure below into the top of `03-WORK-LOG.md` when pausing or ending
material work. Update `02-CURRENT-STATE.md` at the same time.

```markdown
## YYYY-MM-DD - Short work-session title

### Goal

- What this session intended to complete.

### Completed

- Concrete implementation or documentation changes.

### Files changed

- `path/to/file`

### Decisions

- Decision and its reason.
- Durable architecture decisions were also recorded in `DECISIONS.md`.

### Verification

- Exact command: result.

### Remaining work

- Work that is not complete.

### Blockers/user decisions

- Specific decision or authority required, or `None`.

### Exact next action

- The first concrete step for the next session.
```

## Handoff quality checklist

- [ ] `git status --short` was checked.
- [ ] Changed files are listed.
- [ ] Tests are recorded with exact commands and results.
- [ ] Incomplete work is not described as complete.
- [ ] The active plan status was updated.
- [ ] `02-CURRENT-STATE.md` matches the handoff.
- [ ] No secret or sensitive payload was stored.
