"""Typed wrappers around existing deterministic and read-only services."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel

from backend.agent.contracts import AgentTool, SQLRepairProvider
from backend.agent.session import AgentSession, SQLCandidate
from backend.schemas.agent import (
    AgentToolName,
    ClarificationOptionView,
    ExecuteValidatedSQLInput,
    ExecuteValidatedSQLOutput,
    FinishInput,
    FinishOutput,
    FormatResultInput,
    FormatResultOutput,
    RepairSQLInput,
    RequestClarificationInput,
    RequestClarificationOutput,
    ResolveSemanticsInput,
    ResolveSemanticsOutput,
    RetrieveSchemaContextInput,
    RetrieveSchemaContextOutput,
    ValidateSQLInput,
    ValidationObservation,
)
from backend.schemas.sql_security import SQLViolationCode
from backend.services.sql_repair import REPAIRABLE_CODES, SQLRepairCoordinator


def _validation_observation(
    session: AgentSession,
    candidate: SQLCandidate,
) -> ValidationObservation:
    validation = candidate.validation
    repairable = bool(validation.violations) and all(
        violation.code in REPAIRABLE_CODES for violation in validation.violations
    )
    handle = session.issue_validation_capability(candidate) if validation.safe else None
    return ValidationObservation(
        candidate_id=candidate.candidate_id,
        safe=validation.safe,
        validation_handle=handle,
        fingerprint=validation.fingerprint,
        violation_codes=tuple(item.code.value for item in validation.violations),
        repairable=repairable,
        table_ids=validation.tables,
        column_ids=validation.columns,
        limit_applied=validation.limit_applied,
    )


class ResolveSemanticsTool:
    name = AgentToolName.RESOLVE_SEMANTICS
    version = "1.0.0"
    description = "Resolve versioned business terms without database or model access."
    input_model: type[BaseModel] = ResolveSemanticsInput
    output_model: type[BaseModel] = ResolveSemanticsOutput

    async def run(self, session: AgentSession, payload: BaseModel) -> BaseModel:
        ResolveSemanticsInput.model_validate(payload)
        resolution = session.services.semantic_service.resolve(session.question)
        session.semantic_resolution = resolution
        session.language = resolution.language
        return ResolveSemanticsOutput(
            language=resolution.language,
            semantic_version=resolution.semantic_version,
            term_ids=tuple(item.term_id for item in resolution.matched_terms),
            metric_ids=tuple(item.metric_id for item in resolution.matched_metrics),
            clarification_rule_id=(
                resolution.clarification.rule_id if resolution.clarification else None
            ),
        )


class RetrieveSchemaContextTool:
    name = AgentToolName.RETRIEVE_SCHEMA_CONTEXT
    version = "1.0.0"
    description = "Retrieve a bounded allowlisted schema context without database execution."
    input_model: type[BaseModel] = RetrieveSchemaContextInput
    output_model: type[BaseModel] = RetrieveSchemaContextOutput

    async def run(self, session: AgentSession, payload: BaseModel) -> BaseModel:
        RetrieveSchemaContextInput.model_validate(payload)
        context = session.services.schema_retriever.retrieve(
            session.question, session.services.snapshot
        )
        session.schema_context = context
        return RetrieveSchemaContextOutput(
            schema_hash=context.schema_hash,
            table_ids=context.table_names,
            truncated=context.truncated,
        )


class ValidateSQLTool:
    name = AgentToolName.VALIDATE_SQL
    version = "1.0.0"
    description = "Validate untrusted SQL and issue a request-bound one-use handle when safe."
    input_model: type[BaseModel] = ValidateSQLInput
    output_model: type[BaseModel] = ValidationObservation

    async def run(self, session: AgentSession, payload: BaseModel) -> BaseModel:
        typed = ValidateSQLInput.model_validate(payload)
        validation = session.services.validator.validate(
            typed.sql,
            declared_tables=typed.declared_tables,
            declared_columns=typed.declared_columns,
        )
        candidate = SQLCandidate(
            candidate_id=f"sqlc_{secrets.token_urlsafe(18)}",
            sql=typed.sql,
            declared_tables=typed.declared_tables,
            declared_columns=typed.declared_columns,
            validation=validation,
        )
        session.candidates[candidate.candidate_id] = candidate
        session.current_candidate_id = candidate.candidate_id
        return _validation_observation(session, candidate)


class RepairSQLTool:
    name = AgentToolName.REPAIR_SQL
    version = "1.0.0"
    description = "Ask the configured model for one bounded repair of repairable SQL only."
    input_model: type[BaseModel] = RepairSQLInput
    output_model: type[BaseModel] = ValidationObservation

    def __init__(self, provider: SQLRepairProvider) -> None:
        self._provider = provider

    async def run(self, session: AgentSession, payload: BaseModel) -> BaseModel:
        typed = RepairSQLInput.model_validate(payload)
        previous = session.candidates.get(typed.candidate_id)
        if previous is None:
            raise ValueError("repair candidate is unavailable")
        if previous.validation.safe:
            raise ValueError("safe SQL must not enter repair")
        repairable = bool(previous.validation.violations) and all(
            violation.code in REPAIRABLE_CODES for violation in previous.validation.violations
        )
        if not repairable:
            raise ValueError("security-policy violations must not enter repair")
        if session.repairs_used >= session.limits.max_repairs:
            raise ValueError("SQL repair budget is exhausted")

        proposed = await self._provider.propose(session, typed.candidate_id)
        session.repairs_used += 1
        session.add_usage(proposed.token_usage, proposed.cost_usd)
        coordinator = SQLRepairCoordinator(session.services.validator, max_attempts=1)

        async def supplied_candidate(
            attempt_number: int,
            violation_codes: tuple[SQLViolationCode, ...],
        ) -> str:
            _ = attempt_number, violation_codes
            return proposed.sql

        outcome = await coordinator.repair(
            previous.validation,
            supplied_candidate,
            declared_tables=proposed.declared_tables,
            declared_columns=proposed.declared_columns,
        )
        validation = outcome.final_validation
        candidate = SQLCandidate(
            candidate_id=f"sqlc_{secrets.token_urlsafe(18)}",
            sql=proposed.sql,
            declared_tables=proposed.declared_tables,
            declared_columns=proposed.declared_columns,
            validation=validation,
        )
        session.candidates[candidate.candidate_id] = candidate
        session.current_candidate_id = candidate.candidate_id
        return _validation_observation(session, candidate)


class ExecuteValidatedSQLTool:
    name = AgentToolName.EXECUTE_VALIDATED_SQL
    version = "1.0.0"
    description = "Execute only SQL recovered from a validator-owned one-use capability."
    input_model: type[BaseModel] = ExecuteValidatedSQLInput
    output_model: type[BaseModel] = ExecuteValidatedSQLOutput

    async def run(self, session: AgentSession, payload: BaseModel) -> BaseModel:
        typed = ExecuteValidatedSQLInput.model_validate(payload)
        capability = session.consume_validation_capability(typed.validation_handle)
        result = session.services.executor.execute(capability.executed_sql)
        result_handle = session.issue_result_capability(capability.fingerprint, result)
        session.current_result_handle = result_handle
        session.result = result
        return ExecuteValidatedSQLOutput(
            result_handle=result_handle,
            fingerprint=capability.fingerprint,
            row_count=result.row_count,
            truncated=result.truncated,
            execution_time_ms=result.execution_time_ms,
        )


class FormatResultTool:
    name = AgentToolName.FORMAT_RESULT
    version = "1.0.0"
    description = "Deterministically format a bounded query result and grounded summary."
    input_model: type[BaseModel] = FormatResultInput
    output_model: type[BaseModel] = FormatResultOutput

    async def run(self, session: AgentSession, payload: BaseModel) -> BaseModel:
        typed = FormatResultInput.model_validate(payload)
        capability = session.consume_result_capability(typed.result_handle)
        candidate = (
            session.candidates.get(session.current_candidate_id)
            if session.current_candidate_id
            else None
        )
        tables = candidate.validation.tables if candidate else ()
        columns = candidate.validation.columns if candidate else ()
        presentation = session.services.formatter.format(
            capability.result,
            source_tables=tables,
            source_columns=columns,
        )
        chart = session.services.chart_selector.select(presentation)
        if session.language is None:
            raise RuntimeError("result formatting requires a resolved language")
        summary = session.services.summarizer.summarize(
            presentation, chart, language=session.language
        )
        session.presentation = presentation
        session.chart = chart
        session.summary = summary
        return FormatResultOutput(
            row_count=presentation.row_count,
            chart_type=chart.type.value if chart else None,
            explanation=summary.text,
        )


class RequestClarificationTool:
    name = AgentToolName.REQUEST_CLARIFICATION
    version = "1.0.0"
    description = "Create a canonical, expiring continuation without database access."
    input_model: type[BaseModel] = RequestClarificationInput
    output_model: type[BaseModel] = RequestClarificationOutput

    async def run(self, session: AgentSession, payload: BaseModel) -> BaseModel:
        typed = RequestClarificationInput.model_validate(payload)
        resolution = session.semantic_resolution
        if resolution is None or resolution.clarification is None:
            raise ValueError("no deterministic clarification is pending")
        if resolution.clarification.rule_id != typed.rule_id:
            raise ValueError("clarification rule does not match the resolved ambiguity")
        rule = next(
            (
                term.ambiguity
                for term in resolution.matched_terms
                if term.ambiguity is not None and term.ambiguity.rule_id == typed.rule_id
            ),
            None,
        )
        if rule is None:
            raise ValueError("clarification rule is unavailable")
        if session.clarification_rounds >= session.limits.max_clarification_rounds:
            raise ValueError("clarification budget is exhausted")
        session.clarification_rounds += 1
        expires = datetime.now(UTC) + timedelta(seconds=session.limits.continuation_ttl_seconds)
        output = RequestClarificationOutput(
            continuation_id=session.session_id,
            question=rule.question.for_language(resolution.language),
            options=tuple(
                ClarificationOptionView(
                    option_id=option.option_id,
                    label=option.label.for_language(resolution.language),
                )
                for option in rule.options
            ),
            expires_at=expires.isoformat(),
        )
        session.clarification = output
        return output


class FinishTool:
    name = AgentToolName.FINISH
    version = "1.0.0"
    description = "Finish the bounded run with an explicit terminal status."
    input_model: type[BaseModel] = FinishInput
    output_model: type[BaseModel] = FinishOutput

    async def run(self, session: AgentSession, payload: BaseModel) -> BaseModel:
        typed = FinishInput.model_validate(payload)
        return FinishOutput(status=typed.status)


def default_tools(repair_provider: SQLRepairProvider) -> tuple[AgentTool, ...]:
    """Return the complete explicit registry set in a stable order."""

    return (
        ResolveSemanticsTool(),
        RetrieveSchemaContextTool(),
        ValidateSQLTool(),
        RepairSQLTool(repair_provider),
        ExecuteValidatedSQLTool(),
        FormatResultTool(),
        RequestClarificationTool(),
        FinishTool(),
    )
