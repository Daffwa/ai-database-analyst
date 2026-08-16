"""Strict contracts for Gemma-planned, deterministically compiled analytics."""

from __future__ import annotations

from enum import StrEnum
from typing import Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictFloat,
    StrictInt,
    StrictStr,
    model_validator,
)

from backend.schemas.llm import LanguageCode, LLMIntent


class StrictPlanModel(BaseModel):
    """Immutable, extra-forbidding base for every plan component."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)


class PlanOutputKind(StrEnum):
    COLUMN = "column"
    AGGREGATE = "aggregate"
    METRIC = "metric"
    TIME_BUCKET = "time_bucket"


class PlanAggregate(StrEnum):
    COUNT = "count"
    COUNT_DISTINCT = "count_distinct"
    SUM = "sum"
    AVERAGE = "average"
    MINIMUM = "minimum"
    MAXIMUM = "maximum"
    SUM_PRODUCT = "sum_product"


class PlanTimeGrain(StrEnum):
    YEAR = "year"
    MONTH = "month"
    MONTH_NUMBER = "month_number"
    WEEKDAY_NUMBER = "weekday_number"


class PlanFilterScope(StrEnum):
    WHERE = "where"
    HAVING = "having"


class PlanFilterOperator(StrEnum):
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    GREATER_THAN = "greater_than"
    GREATER_OR_EQUAL = "greater_or_equal"
    LESS_THAN = "less_than"
    LESS_OR_EQUAL = "less_or_equal"
    BETWEEN = "between"
    IN = "in"
    CONTAINS = "contains"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    IS_NULL = "is_null"
    IS_NOT_NULL = "is_not_null"


class PlanBenchmarkKind(StrEnum):
    GLOBAL_AVERAGE = "global_average"
    GROUP_AVERAGE = "group_average"


class PlanSortDirection(StrEnum):
    ASCENDING = "ascending"
    DESCENDING = "descending"


PlanScalar = StrictStr | StrictInt | StrictFloat


class PlanOutput(StrictPlanModel):
    """One selected dimension or measure with an explicit result label."""

    kind: PlanOutputKind
    alias: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
    column: str | None = Field(
        default=None, pattern=r"^[A-Za-z][A-Za-z0-9_]*\.[A-Za-z][A-Za-z0-9_]*$"
    )
    second_column: str | None = Field(
        default=None,
        pattern=r"^[A-Za-z][A-Za-z0-9_]*\.[A-Za-z][A-Za-z0-9_]*$",
    )
    aggregate: PlanAggregate | None = None
    metric_id: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]*$")
    time_grain: PlanTimeGrain | None = None
    round_digits: int | None = Field(default=None, ge=0, le=6)
    group_by: bool = False

    @model_validator(mode="after")
    def validate_kind_fields(self) -> Self:
        if self.kind is PlanOutputKind.COLUMN:
            if self.column is None or any(
                value is not None
                for value in (self.second_column, self.aggregate, self.metric_id, self.time_grain)
            ):
                raise ValueError("column output requires only column")
            if self.round_digits is not None:
                raise ValueError("column output cannot be rounded")
        elif self.kind is PlanOutputKind.AGGREGATE:
            if self.aggregate is None or self.column is None:
                raise ValueError("aggregate output requires aggregate and column")
            if self.metric_id is not None or self.time_grain is not None or self.group_by:
                raise ValueError("aggregate output has incompatible fields")
            if self.aggregate is PlanAggregate.SUM_PRODUCT:
                if self.second_column is None:
                    raise ValueError("sum_product requires second_column")
            elif self.second_column is not None:
                raise ValueError("second_column is only valid for sum_product")
        elif self.kind is PlanOutputKind.METRIC:
            if self.metric_id is None or any(
                value is not None
                for value in (self.column, self.second_column, self.aggregate, self.time_grain)
            ):
                raise ValueError("metric output requires only metric_id")
            if self.group_by:
                raise ValueError("metric output cannot be a grouping dimension")
        else:
            if self.column is None or self.time_grain is None:
                raise ValueError("time_bucket requires column and time_grain")
            if any(
                value is not None
                for value in (self.second_column, self.aggregate, self.metric_id, self.round_digits)
            ):
                raise ValueError("time_bucket has incompatible fields")
            if not self.group_by:
                raise ValueError("time_bucket must be grouped")
        return self


class PlanBenchmark(StrictPlanModel):
    """A deterministic average subquery used by a filter or HAVING clause."""

    kind: PlanBenchmarkKind
    table: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]*$")
    column: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]*\.[A-Za-z][A-Za-z0-9_]*$")
    aggregate: PlanAggregate | None = None
    group_by: str | None = Field(
        default=None,
        pattern=r"^[A-Za-z][A-Za-z0-9_]*\.[A-Za-z][A-Za-z0-9_]*$",
    )

    @model_validator(mode="after")
    def validate_benchmark(self) -> Self:
        if self.kind is PlanBenchmarkKind.GLOBAL_AVERAGE:
            if self.aggregate not in {None, PlanAggregate.AVERAGE} or self.group_by is not None:
                raise ValueError("global_average accepts only an optional average aggregate")
        elif self.aggregate is None or self.group_by is None:
            raise ValueError("group_average requires aggregate and group_by")
        elif self.aggregate not in {
            PlanAggregate.COUNT,
            PlanAggregate.COUNT_DISTINCT,
            PlanAggregate.SUM,
            PlanAggregate.AVERAGE,
        }:
            raise ValueError("unsupported grouped benchmark aggregate")
        return self


class PlanFilter(StrictPlanModel):
    """One typed predicate; targets are physical columns or output aliases."""

    scope: PlanFilterScope = PlanFilterScope.WHERE
    target: str = Field(min_length=1, max_length=257)
    operator: PlanFilterOperator
    values: tuple[PlanScalar, ...] = Field(default=(), max_length=20)
    benchmark: PlanBenchmark | None = None

    @model_validator(mode="after")
    def validate_operator_values(self) -> Self:
        if any(isinstance(value, bool) for value in self.values):
            raise ValueError("boolean filter values are not supported")
        null_operators = {PlanFilterOperator.IS_NULL, PlanFilterOperator.IS_NOT_NULL}
        if self.operator in null_operators:
            if self.values or self.benchmark is not None:
                raise ValueError("null filters accept no values or benchmark")
        elif self.benchmark is not None:
            if self.values or self.operator not in {
                PlanFilterOperator.GREATER_THAN,
                PlanFilterOperator.GREATER_OR_EQUAL,
                PlanFilterOperator.LESS_THAN,
                PlanFilterOperator.LESS_OR_EQUAL,
            }:
                raise ValueError("benchmark filters require one comparison operator")
        elif self.operator is PlanFilterOperator.BETWEEN:
            if len(self.values) != 2:
                raise ValueError("between requires exactly two values")
        elif self.operator is PlanFilterOperator.IN:
            if not self.values:
                raise ValueError("in requires one or more values")
        elif len(self.values) != 1:
            raise ValueError("filter requires exactly one value")
        if self.scope is PlanFilterScope.HAVING and self.benchmark is None:
            raise ValueError("HAVING is reserved for benchmark comparisons")
        return self


class PlanRelatedFilter(StrictPlanModel):
    """A bounded IN-subquery over an approved relationship path."""

    outer_column: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]*\.[A-Za-z][A-Za-z0-9_]*$")
    subquery_select_column: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]*\.[A-Za-z][A-Za-z0-9_]*$")
    base_table: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]*$")
    tables: tuple[str, ...] = Field(min_length=1, max_length=8)
    join_ids: tuple[str, ...] = Field(default=(), max_length=8)
    filters: tuple[PlanFilter, ...] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def validate_related_filter(self) -> Self:
        if self.base_table.casefold() not in {table.casefold() for table in self.tables}:
            raise ValueError("related filter base_table must be listed")
        if len(set(self.tables)) != len(self.tables) or len(set(self.join_ids)) != len(
            self.join_ids
        ):
            raise ValueError("related filter tables and joins must be unique")
        if any(item.scope is not PlanFilterScope.WHERE for item in self.filters):
            raise ValueError("related filters only support WHERE predicates")
        return self


class PlanOrder(StrictPlanModel):
    target_alias: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
    direction: PlanSortDirection


class AnalysisPlan(StrictPlanModel):
    """Gemma output contract consumed by deterministic grounding and compilation."""

    intent: LLMIntent
    language: LanguageCode
    needs_clarification: bool
    clarification_question: str | None = Field(default=None, min_length=1, max_length=500)
    assumptions: tuple[str, ...] = Field(default=(), max_length=10)
    base_table: str | None = Field(default=None, pattern=r"^[A-Za-z][A-Za-z0-9_]*$")
    tables: tuple[str, ...] = Field(default=(), max_length=12)
    join_ids: tuple[str, ...] = Field(default=(), max_length=12)
    outputs: tuple[PlanOutput, ...] = Field(default=(), max_length=20)
    filters: tuple[PlanFilter, ...] = Field(default=(), max_length=20)
    related_filters: tuple[PlanRelatedFilter, ...] = Field(default=(), max_length=5)
    order_by: tuple[PlanOrder, ...] = Field(default=(), max_length=10)
    limit: int | None = Field(default=None, ge=1, le=500)
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning_summary: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_intent_contract(self) -> Self:
        if any(not assumption for assumption in self.assumptions):
            raise ValueError("assumptions must not contain empty values")
        if len(set(self.tables)) != len(self.tables) or len(set(self.join_ids)) != len(
            self.join_ids
        ):
            raise ValueError("tables and joins must be unique")
        aliases = tuple(output.alias.casefold() for output in self.outputs)
        if len(set(aliases)) != len(aliases):
            raise ValueError("output aliases must be unique")
        output_aliases = set(aliases)
        if any(order.target_alias.casefold() not in output_aliases for order in self.order_by):
            raise ValueError("order_by must reference an output alias")

        has_query_material = bool(
            self.base_table
            or self.tables
            or self.join_ids
            or self.outputs
            or self.filters
            or self.related_filters
            or self.order_by
            or self.limit
        )
        if self.intent is LLMIntent.ANALYSIS:
            if self.needs_clarification or self.clarification_question is not None:
                raise ValueError("analysis must not request clarification")
            if (
                self.base_table is None
                or self.base_table.casefold() not in {table.casefold() for table in self.tables}
                or not self.outputs
            ):
                raise ValueError("analysis requires base_table, tables, and outputs")
        elif self.intent is LLMIntent.CLARIFICATION:
            if not self.needs_clarification or self.clarification_question is None:
                raise ValueError("clarification requires a question")
            if has_query_material:
                raise ValueError("clarification must not contain query material")
        else:
            if self.needs_clarification or self.clarification_question is not None:
                raise ValueError("unsupported intent cannot request clarification")
            if has_query_material:
                raise ValueError("unsupported intent must not contain query material")
        return self
