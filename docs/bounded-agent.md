# Bounded Agent Runtime

- Architecture version: `bounded-agent-v1`
- Roadmap scope: Points 6 and 7
- Security posture: model output is untrusted; PostgreSQL remains read-only
- Model qualification: Point 5 remains blocked

## What was added

The `/api/v1/agent/*` path wraps the existing semantic, schema, SQL security,
execution, and result services in a typed tool registry and a bounded
`decide -> act -> observe` state machine. The existing `/api/v1/query` path is
retained for compatibility and regression evidence.

The production policy uses the configured model to choose between an
analytical proposal and a terminal unsupported result, and to provide the SQL
proposal that becomes the typed `validate_sql` action. Deterministic control
selects mandatory semantic, schema, validation, execution, formatting, and
finish steps. The `AgentPolicy` boundary permits other model action policies,
but every policy is subordinate to the same registry and state allowlist.

This is a bounded agent, not an autonomous or general-purpose agent. It has no
filesystem, shell, network, credential, dynamic-import, or arbitrary database
tool.

## Tool authority

| Tool | Allowed effect | Important boundary |
|---|---|---|
| `resolve_semantics` | Deterministic read-only resolution | No model or database call |
| `retrieve_schema_context` | Bounded schema selection | Allowlisted identifiers only |
| `validate_sql` | AST authorization and limit rewrite | Issues a random request-bound handle only when safe |
| `repair_sql` | One model repair proposal per step | Repairable codes only; full validation via `SQLRepairCoordinator` |
| `execute_validated_sql` | Read-only database query | Accepts one-use validation handle, never raw SQL |
| `format_result` | Deterministic presentation/chart/summary | Accepts one-use result handle |
| `request_clarification` | Pause with canonical options | No database call; answer is an option ID, not an instruction |
| `finish` | Terminal state transition | No external side effect |

Tool input and output use extra-forbidding Pydantic contracts. Tool name,
description, and contract version are registered statically. Unknown tools,
invalid arguments, calls outside the state allowlist, forged handles, and
reused handles fail closed.

## State and budgets

The state path is:

```text
RECEIVED -> SEMANTICS_RESOLVED -> CLARIFICATION_REQUIRED | SCHEMA_READY
SCHEMA_READY -> SQL_PROPOSED -> SQL_VALIDATED | REPAIR_ALLOWED | BLOCKED
SQL_VALIDATED -> QUERY_EXECUTED -> RESULT_FORMATTED -> COMPLETED
```

Defaults are eight tool steps, two SQL repairs, one tool call per step, one
execution per validation handle, 30 seconds of active runtime, and two
clarification rounds. Optional total-token and cost ceilings can stop a run
before its next tool call. Provider timeout, query timeout, agent deadline,
maximum steps, unsupported input, empty result, policy block, and sanitized
internal error remain distinct terminal outcomes.

Environment settings:

```text
AGENT_MAX_STEPS=8
AGENT_MAX_RUNTIME_SECONDS=30
AGENT_MAX_CLARIFICATION_ROUNDS=2
AGENT_CONTINUATION_TTL_SECONDS=900
AGENT_MAX_TOTAL_TOKENS=
AGENT_MAX_COST_USD=
```

An unset token or cost ceiling means that dimension is observed but not used
as a stop gate. A real deployment should set ceilings only after provider
usage and price accounting are approved.

## Clarification continuation

`POST /api/v1/agent/query` may return `clarification_required` with an opaque
continuation ID and canonical option IDs. Resume with:

```json
{
  "continuation_id": "opaque-issued-value",
  "option_id": "total_spend",
  "question": "Who is the best customer?"
}
```

`POST /api/v1/agent/continue` verifies that the re-supplied question matches
the persisted digest, re-resolves the active semantic layer, checks its
version/hash/rule/options, and consumes the selected canonical ID. PostgreSQL
stores only the digest, safe IDs, version/hash, counters, and expiry. It does
not store raw question text, SQL, prompts, or result rows. Claiming uses a row
lock so concurrent processes cannot execute the same continuation twice.
`POST /api/v1/agent/cancel` deletes an unused continuation.

Alembic revision `20260816_0002` adds the privacy-minimized
`app_metadata.agent_continuations` table. Deployments must migrate metadata to
`head` before enabling agent routes.

## Audit and evidence

Agent audit events contain only step number, registered tool name/version,
status, latency, candidate ID, and SQL fingerprint. They exclude question,
prompt, SQL, result rows, credentials, and internal exception detail.

The local gate for this implementation passed 447 tests with four unavailable
PostgreSQL/Docker tests skipped, 90.69% coverage, Ruff format/lint, strict Mypy,
and `git diff --check`. These are architecture and offline regression results;
they do not qualify Gemma or close the blocked Point-5 quality/holdout gate.
