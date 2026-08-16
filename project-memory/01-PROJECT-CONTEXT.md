# Stable Project Context

- Project name: AI Database Analyst
- Repository package version: `0.1.0`
- Primary language: Python 3.11-3.12
- User-facing languages: Indonesian and English
- Dataset: pinned synthetic Chinook v1.4.5
- Local release shape: Streamlit -> FastAPI -> PostgreSQL

## What the system does

The system accepts a natural-language analytical question, resolves relevant
business semantics, supplies a bounded schema context to an LLM adapter,
validates the resulting structured proposal, parses and authorizes the complete
SQL AST, executes only approved read-only SQL, and presents grounded results,
charts, sources, and audit metadata.

## Current classification

At the current baseline, the most accurate description is:

> A security-first, orchestrated conversational text-to-SQL application with
> limited agentic characteristics.

It should not yet be described as a full AI agent because the default provider
uses exact fake mappings, the request path is predominantly fixed, and there is
no model-directed bounded plan-act-observe tool loop.

After points 1-7 are completed and evaluated, the intended description is:

> A bounded AI Database Analyst Agent with deterministic security guardrails.

## Primary request path

```text
User question
  -> semantic resolution and ambiguity check
  -> bounded schema/semantic prompt context
  -> LLM structured SQL proposal
  -> structured-output validation
  -> deterministic SQL AST security policy
  -> rewritten read-only SQL
  -> read-only database executor
  -> deterministic result formatting/chart/summary
  -> auditable response
```

## Existing major components

- `backend/llm/`: provider-neutral fake and Gemini/Gemma implementations.
- `backend/services/orchestrator.py`: generation orchestration.
- `backend/services/secure_orchestrator.py`: mandatory SQL validation and
  execution boundary.
- `backend/services/sql_security.py`: SQLGlot AST policy.
- `backend/services/sql_repair.py`: bounded repair coordinator.
- `backend/services/semantic_*`: versioned semantic layer and clarification.
- `backend/services/result_*`: grounded result experience.
- `backend/runtime/stage8.py`: PostgreSQL/FastAPI composition root.
- `backend/api/`: versioned backend API.
- `frontend/`: Streamlit clients.
- `data/evaluation/stage-7-v1.jsonl`: 100-case evaluation corpus.
- `semantic/`: glossary, metrics, joins, and verified queries.

## Non-negotiable security invariants

- LLM output is untrusted.
- The LLM has no database credentials or direct database access.
- Only validator-owned `executed_sql` reaches the executor.
- Analytics execution uses `analytics_readonly` and a read-only transaction.
- Unknown tables, columns, catalogs, functions, multiple statements, DML, DDL,
  and administrative SQL fail closed.
- Security-policy violations are never automatically repaired.
- Agent steps, retries, time, token usage, result size, and cost are bounded.
- Logs exclude raw questions, SQL, result rows, credentials, and URLs by default.
- The fake provider remains the offline CI/regression default.

## Current real-LLM gaps

- `create_llm_adapter` constructs both the offline fake adapter and the opt-in
  Gemini/Gemma adapter.
- The Gemini API HTTP adapter is live validated with structured output and safe
  aggregate token metadata.
- Provider token usage is propagated through generation and query responses.
- The real-provider evaluator exists. Both the initial 26B calibration and the
  authorized 31B/v4 formal development run failed frozen quality thresholds.
  The explicit `semantic-v2` comparator was then implemented, offline audited,
  and used in a complete authorized rerun. It improved observed execution
  accuracy to 45.90% through 10 presentation-equivalent passes, but still
  failed the 85% execution and 99% structured-output gates. Holdout remains
  locked despite 100% known-unsafe protection.
- The subsequent Gemma-only `v5-plan` candidate moves SQL authorship into a
  deterministic grounder/compiler. On the same 12 hard development failures,
  frozen pilots improved 0/12 -> 2/12 -> 6/12 -> 8/12 with zero schema
  hallucination/security bypass. The subset target passed, but formal full-
  development and holdout gates remain closed.
- Model-directed typed tools and the bounded agent loop remain unimplemented.

## Current agent gaps

- No typed agent tool registry.
- No state-based tool authority table.
- No model-directed plan-act-observe loop.
- SQL repair exists as a service but is not wired into the primary runtime.
- Durable multi-turn clarification continuation remains unimplemented.

## Verification philosophy

The deterministic fake baseline proves pipeline mechanics and security
regression; it does not prove real-model generalization. Real-provider results
must receive a separate versioned baseline with development/holdout separation,
execution-based accuracy, unsafe blocking, latency, token, and cost metrics.
