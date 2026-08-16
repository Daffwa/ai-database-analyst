"""Deterministic grounding, compilation, and alignment checks for analysis plans."""

from __future__ import annotations

import re
from collections import deque
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Final

from sqlglot import exp, parse_one
from sqlglot.errors import ParseError

from backend.schemas.analysis_plan import (
    AnalysisPlan,
    PlanAggregate,
    PlanBenchmark,
    PlanBenchmarkKind,
    PlanFilter,
    PlanFilterOperator,
    PlanFilterScope,
    PlanOrder,
    PlanOutput,
    PlanOutputKind,
    PlanRelatedFilter,
    PlanSortDirection,
    PlanTimeGrain,
)
from backend.schemas.database import SchemaSnapshot
from backend.schemas.llm import LLMIntent, StructuredSQLProposal
from backend.schemas.semantic import (
    ApprovalStatus,
    JoinDefinition,
    MetricDefinition,
    MetricFormat,
    SemanticLayerBundle,
)

_ALIAS_PATTERN: Final = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
_COLUMN_REFERENCE_PATTERN: Final = re.compile(
    r"\b([A-Za-z][A-Za-z0-9_]*)\.([A-Za-z][A-Za-z0-9_]*)\b"
)


class AnalysisPlanError(ValueError):
    """Sanitized plan failure safe to return as bounded repair feedback."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class CompiledAnalysisPlan:
    """Compiler output passed to the existing untrusted SQL security boundary."""

    sql: str
    tables: tuple[str, ...]
    columns: tuple[str, ...]
    output_aliases: tuple[str, ...]


class AnalysisPlanNormalizer:
    """Canonicalize bounded presentation fields before strict plan validation."""

    @classmethod
    def normalize(cls, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = deepcopy(payload)
        intent = normalized.get("intent")
        unsupported_marker = normalized.pop("unsupported", None)
        if (
            unsupported_marker is not None
            and unsupported_marker is not False
            and unsupported_marker != ""
            and unsupported_marker != 0
        ):
            normalized["intent"] = "unsupported"
            intent = "unsupported"
        if intent in {"clarification", "unsupported"}:
            allowed = set(AnalysisPlan.model_fields)
            normalized = {key: value for key, value in normalized.items() if key in allowed}
            for field_name, empty_value in (
                ("base_table", None),
                ("tables", []),
                ("join_ids", []),
                ("outputs", []),
                ("filters", []),
                ("related_filters", []),
                ("order_by", []),
                ("limit", None),
            ):
                normalized[field_name] = empty_value
            if intent == "unsupported":
                normalized["needs_clarification"] = False
                normalized["clarification_question"] = None

        aliases: dict[str, str] = {}
        outputs = normalized.get("outputs")
        if isinstance(outputs, list):
            for output in outputs:
                if not isinstance(output, dict):
                    continue
                cls._normalize_output_fields(output)
                raw_alias = output.get("alias")
                safe_alias = cls._alias(raw_alias)
                if isinstance(raw_alias, str) and isinstance(safe_alias, str):
                    aliases[raw_alias.casefold()] = safe_alias
                    output["alias"] = safe_alias

        orders = normalized.get("order_by")
        if isinstance(orders, list):
            for order in orders:
                if not isinstance(order, dict):
                    continue
                target = order.get("target_alias")
                if isinstance(target, str):
                    order["target_alias"] = aliases.get(target.casefold(), cls._alias(target))

        filters = normalized.get("filters")
        if isinstance(filters, list):
            cls._normalize_filters(filters, aliases)
        related_filters = normalized.get("related_filters")
        if isinstance(related_filters, list):
            for related in related_filters:
                if isinstance(related, dict) and isinstance(related.get("filters"), list):
                    cls._normalize_filters(related["filters"], {})
        return normalized

    @staticmethod
    def _normalize_output_fields(output: dict[str, Any]) -> None:
        """Drop incompatible residue according to the provider's chosen kind."""

        kind = output.get("kind")
        if kind == "column":
            for field_name in (
                "second_column",
                "aggregate",
                "metric_id",
                "time_grain",
                "round_digits",
            ):
                output[field_name] = None
        elif kind == "aggregate":
            output["metric_id"] = None
            output["time_grain"] = None
            output["group_by"] = False
            if output.get("aggregate") != "sum_product":
                output["second_column"] = None
        elif kind == "metric":
            for field_name in ("column", "second_column", "aggregate", "time_grain"):
                output[field_name] = None
            output["group_by"] = False
        elif kind == "time_bucket":
            for field_name in ("second_column", "aggregate", "metric_id", "round_digits"):
                output[field_name] = None
            output["group_by"] = True

    @staticmethod
    def _alias(value: object) -> object:
        if not isinstance(value, str) or len(value) > 200:
            return value
        if _ALIAS_PATTERN.fullmatch(value):
            return value
        if re.match(r"^[A-Za-z]", value) is None:
            return value
        candidate = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_")
        return candidate if _ALIAS_PATTERN.fullmatch(candidate) else value

    @classmethod
    def _normalize_filters(
        cls,
        filters: list[object],
        aliases: dict[str, str],
    ) -> None:
        for item in filters:
            if not isinstance(item, dict):
                continue
            if item.get("scope") == "having":
                target = item.get("target")
                if isinstance(target, str):
                    item["target"] = aliases.get(target.casefold(), cls._alias(target))
            benchmark = item.get("benchmark")
            if item.get("values") is None and (
                isinstance(benchmark, dict) or item.get("operator") in {"is_null", "is_not_null"}
            ):
                item["values"] = []
            if not isinstance(benchmark, dict):
                continue
            group_by = benchmark.get("group_by")
            if isinstance(group_by, list) and len(group_by) == 1 and isinstance(group_by[0], str):
                benchmark["group_by"] = group_by[0]
            if isinstance(benchmark.get("group_by"), str) and benchmark.get("kind") in {
                "global_average",
                "group_average",
            }:
                benchmark["kind"] = "group_average"
            table = benchmark.get("table")
            if not isinstance(table, str) or re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", table) is None:
                continue
            for field in ("column", "group_by"):
                column = benchmark.get(field)
                if isinstance(column, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", column):
                    benchmark[field] = f"{table}.{column}"


class AnalysisPlanGrounder:
    """Canonicalize physical identifiers and derive unique approved join paths."""

    def __init__(self, snapshot: SchemaSnapshot, bundle: SemanticLayerBundle) -> None:
        self._table_names = {table.name.casefold(): table.name for table in snapshot.tables}
        self._column_names = {
            table.name: {column.name.casefold(): column.name for column in table.columns}
            for table in snapshot.tables
        }
        self._primary_keys = {table.name: table.primary_key for table in snapshot.tables}
        self._display_columns = {
            table.name: next(
                (
                    column.name
                    for preferred in ("name", "firstname", "title")
                    for column in table.columns
                    if column.name.casefold() == preferred
                ),
                None,
            )
            for table in snapshot.tables
        }
        self._display_column_sets = {
            table.name: self._display_set(tuple(column.name for column in table.columns))
            for table in snapshot.tables
        }
        self._foreign_key_columns = {
            table.name: tuple(
                dict.fromkeys(
                    column
                    for foreign_key in table.foreign_keys
                    for column in foreign_key.constrained_columns
                )
            )
            for table in snapshot.tables
        }
        self._foreign_key_targets = {
            table.name: tuple(
                (
                    foreign_key.constrained_columns[0],
                    foreign_key.referred_table,
                    foreign_key.referred_columns[0],
                )
                for foreign_key in table.foreign_keys
                if len(foreign_key.constrained_columns) == 1
                and len(foreign_key.referred_columns) == 1
            )
            for table in snapshot.tables
        }
        self._numeric_value_columns = {
            table.name: tuple(
                column.name
                for column in table.columns
                if not column.name.casefold().endswith("id")
                and re.search(
                    r"INT|REAL|NUMERIC|DECIMAL|DOUBLE|FLOAT",
                    column.data_type,
                    re.IGNORECASE,
                )
            )
            for table in snapshot.tables
        }
        self._core_value_columns = {
            table.name: next(
                (
                    column.name
                    for preferred in ("total", "unitprice", "milliseconds")
                    for column in table.columns
                    if column.name.casefold() == preferred
                ),
                None,
            )
            for table in snapshot.tables
        }
        self._joins = {
            join.join_id: join
            for join in bundle.joins.joins
            if join.approval_status is ApprovalStatus.APPROVED
        }
        self._metrics = {metric.metric_id: metric for metric in bundle.metrics.metrics}
        self._graph: dict[str, list[tuple[str, str]]] = {table: [] for table in self._column_names}
        for join in self._joins.values():
            if join.left_table == join.right_table:
                continue
            self._graph[join.left_table].append((join.right_table, join.join_id))
            self._graph[join.right_table].append((join.left_table, join.join_id))
        for edges in self._graph.values():
            edges.sort(key=lambda item: (item[0].casefold(), item[1]))

    @property
    def metrics(self) -> dict[str, MetricDefinition]:
        return dict(self._metrics)

    @property
    def joins(self) -> dict[str, JoinDefinition]:
        return dict(self._joins)

    def ground(
        self,
        plan: AnalysisPlan,
        *,
        question: str | None = None,
        selected_metric_ids: tuple[str, ...] = (),
    ) -> AnalysisPlan:
        if plan.intent is not LLMIntent.ANALYSIS:
            return plan
        if plan.base_table is None:
            raise AnalysisPlanError("missing_base_table")

        base_table = self._table(plan.base_table)
        outputs = tuple(self._ground_output(output) for output in plan.outputs)
        outputs = self._align_reviewed_metric(outputs, selected_metric_ids)
        if question is not None:
            base_table = self._requested_plan_base_table(plan, base_table, outputs, question)
            outputs = self._align_grouped_entity_key(outputs, base_table)
            plan = self._normalize_display_ranking_limit(plan, outputs, question)
            plan = self._with_default_limit(plan, base_table, outputs, question)
            outputs = self._complete_base_projection(plan, base_table, outputs, question)
            outputs = self._complete_related_display_projection(
                outputs,
                base_table,
                question,
            )
        aliases = {output.alias.casefold(): output.alias for output in outputs}
        filters = tuple(self._ground_filter(item, aliases) for item in plan.filters)
        if question is not None:
            outputs = self._prune_filter_only_projection(
                plan,
                base_table,
                outputs,
                filters,
                question,
            )
            aliases = {output.alias.casefold(): output.alias for output in outputs}
        self._validate_filtered_detail_projection(plan, base_table, outputs, filters)
        if question is not None:
            self._validate_bounded_detail_projection(
                plan,
                base_table,
                outputs,
                filters,
                question,
            )
        related = tuple(self._ground_related(item) for item in plan.related_filters)
        orders = tuple(
            PlanOrder(
                target_alias=aliases.get(item.target_alias.casefold(), item.target_alias),
                direction=item.direction,
            )
            for item in plan.order_by
        )
        if any(order.target_alias.casefold() not in aliases for order in orders):
            raise AnalysisPlanError("unknown_order_alias")
        if question is not None:
            orders = self._canonical_ordering(
                plan,
                base_table,
                outputs,
                filters,
                orders,
                question,
            )

        required_tables = {base_table}
        for output in outputs:
            required_tables.update(self._output_tables(output))
        for item in filters:
            required_tables.update(self._filter_tables(item))
        for related_item in related:
            required_tables.add(self._qualified(related_item.outer_column)[0])

        join_ids, grounded_tables = self._paths_from(base_table, required_tables)
        return plan.model_copy(
            update={
                "base_table": base_table,
                "tables": grounded_tables,
                "join_ids": join_ids,
                "outputs": outputs,
                "filters": filters,
                "related_filters": related,
                "order_by": orders,
            }
        )

    def _requested_base_table(self, question: str) -> str | None:
        """Resolve the first explicitly named entity for bounded list grain."""

        normalized = " ".join(re.sub(r"[^a-z0-9]+", " ", question.casefold()).split())
        mentions: list[tuple[int, int, str]] = []
        for table in self._column_names:
            spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", table).casefold()
            aliases = {spaced, spaced.replace(" ", "")}
            aliases.update(_plural_forms(alias) for alias in tuple(aliases))
            for alias in aliases:
                match = re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", normalized)
                if match is not None:
                    mentions.append((match.start(), -len(alias), table))
        return min(mentions)[2] if mentions else None

    def _requested_plan_base_table(
        self,
        plan: AnalysisPlan,
        current: str,
        outputs: tuple[PlanOutput, ...],
        question: str,
    ) -> str:
        """Use grouping identity for aggregate grain and wording for details."""

        measures = tuple(
            output
            for output in outputs
            if output.kind in {PlanOutputKind.AGGREGATE, PlanOutputKind.METRIC}
        )
        if measures:
            candidates: set[str] = set()
            for output in outputs:
                if not output.group_by or output.column is None:
                    continue
                table, column = self._qualified(output.column)
                identity = set(self._primary_keys.get(table, ())) | set(
                    self._display_column_sets.get(table, ())
                )
                if column in identity:
                    candidates.add(table)
            if len(candidates) == 1:
                return next(iter(candidates))
            if plan.limit is not None:
                return self._bounded_entity_table(question) or current
            return current
        if plan.limit is not None:
            return self._requested_base_table(question) or current
        return current

    def _bounded_entity_table(self, question: str) -> str | None:
        normalized = " ".join(re.sub(r"[^a-z0-9]+", " ", question.casefold()).split())
        quantity = (
            r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|"
            r"satu|dua|tiga|empat|lima|enam|tujuh|delapan|sembilan|sepuluh)"
        )
        for table in sorted(self._column_names, key=str.casefold):
            spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", table).casefold()
            aliases = {spaced, spaced.replace(" ", ""), _plural_forms(spaced)}
            if any(
                re.search(
                    rf"\b{quantity}\s+(?:[a-z0-9]+\s+)?{re.escape(alias)}\b",
                    normalized,
                )
                for alias in aliases
            ):
                return table
        return None

    def _align_grouped_entity_key(
        self,
        outputs: tuple[PlanOutput, ...],
        base_table: str,
    ) -> tuple[PlanOutput, ...]:
        """Lift a grouped foreign key to the requested related entity key."""

        updated: list[PlanOutput] = []
        for output in outputs:
            if not output.group_by or output.column is None:
                updated.append(output)
                continue
            table, column = self._qualified(output.column)
            replacement = next(
                (
                    referred
                    for constrained, target, referred in self._foreign_key_targets.get(table, ())
                    if constrained == column and target == base_table
                ),
                None,
            )
            if replacement is None:
                updated.append(output)
            else:
                updated.append(output.model_copy(update={"column": f"{base_table}.{replacement}"}))
        return tuple(updated)

    def _normalize_display_ranking_limit(
        self,
        plan: AnalysisPlan,
        outputs: tuple[PlanOutput, ...],
        question: str,
    ) -> AnalysisPlan:
        """Do not invent top-one for an unbounded display-style ranking."""

        if (
            plan.limit is None
            or not any(
                output.kind in {PlanOutputKind.AGGREGATE, PlanOutputKind.METRIC}
                for output in outputs
            )
            or not _is_display_request(question)
            or not _has_explicit_order(question)
            or _has_requested_quantity(question)
        ):
            return plan
        return plan.model_copy(update={"limit": None})

    def _with_default_limit(
        self,
        plan: AnalysisPlan,
        base_table: str,
        outputs: tuple[PlanOutput, ...],
        question: str,
    ) -> AnalysisPlan:
        """Apply small, explainable display bounds for implicit detail samples."""

        if plan.limit is not None or any(
            output.kind is not PlanOutputKind.COLUMN or output.group_by for output in outputs
        ):
            return plan
        if _is_display_request(question) and _has_explicit_order(question):
            return plan.model_copy(update={"limit": 5})
        for item in plan.filters:
            if item.scope is not PlanFilterScope.WHERE or item.benchmark is not None:
                continue
            try:
                table, column = self._qualified(item.target)
            except AnalysisPlanError:
                continue
            if table != base_table:
                continue
            if item.operator is PlanFilterOperator.IN and len(item.values) > 1:
                return plan.model_copy(update={"limit": 10})
            if item.operator is PlanFilterOperator.IS_NULL and self._missing_value_is_focus(
                question, column
            ):
                return plan.model_copy(update={"limit": 5})
        return plan

    def _align_reviewed_metric(
        self,
        outputs: tuple[PlanOutput, ...],
        selected_metric_ids: tuple[str, ...],
    ) -> tuple[PlanOutput, ...]:
        """Bind one unambiguous semantic metric to the model's sole measure."""

        unique_ids = tuple(dict.fromkeys(metric_id.casefold() for metric_id in selected_metric_ids))
        if len(unique_ids) != 1 or unique_ids[0] not in self._metrics:
            return outputs
        measure_indexes = tuple(
            index
            for index, output in enumerate(outputs)
            if output.kind in {PlanOutputKind.AGGREGATE, PlanOutputKind.METRIC}
        )
        if len(measure_indexes) != 1:
            return outputs
        index = measure_indexes[0]
        existing = outputs[index]
        metric = self._metrics[unique_ids[0]]
        replacement = PlanOutput(
            kind=PlanOutputKind.METRIC,
            alias=existing.alias,
            metric_id=metric.metric_id,
            round_digits=(2 if metric.format is MetricFormat.CURRENCY else existing.round_digits),
        )
        updated = list(outputs)
        updated[index] = replacement
        return tuple(updated)

    def _canonical_ordering(
        self,
        plan: AnalysisPlan,
        base_table: str,
        outputs: tuple[PlanOutput, ...],
        filters: tuple[PlanFilter, ...],
        current: tuple[PlanOrder, ...],
        question: str,
    ) -> tuple[PlanOrder, ...]:
        """Preserve explicit rankings and apply stable project ordering defaults."""

        if _has_explicit_order(question):
            return self._with_primary_key_tiebreaker(base_table, outputs, current)
        grouped = tuple(output for output in outputs if output.group_by)
        measures = tuple(
            output
            for output in outputs
            if output.kind in {PlanOutputKind.AGGREGATE, PlanOutputKind.METRIC}
        )
        if (
            grouped
            and measures
            and not any(output.kind is PlanOutputKind.TIME_BUCKET for output in grouped)
        ):
            benchmark_filters = tuple(
                item
                for item in filters
                if item.scope is PlanFilterScope.HAVING and item.benchmark is not None
            )
            if not benchmark_filters and self._prefer_grouped_dimension_order(grouped, measures):
                return tuple(
                    PlanOrder(
                        target_alias=output.alias,
                        direction=PlanSortDirection.ASCENDING,
                    )
                    for output in grouped
                )
            measure_alias = benchmark_filters[0].target if benchmark_filters else measures[0].alias
            direction = PlanSortDirection.DESCENDING
            if benchmark_filters and benchmark_filters[0].operator in {
                PlanFilterOperator.LESS_THAN,
                PlanFilterOperator.LESS_OR_EQUAL,
            }:
                direction = PlanSortDirection.ASCENDING
            ordered_aliases = [measure_alias]
            primary_key = self._primary_keys.get(base_table, ())
            if len(primary_key) == 1:
                primary_reference = f"{base_table}.{primary_key[0]}".casefold()
                ordered_aliases.extend(
                    output.alias
                    for output in grouped
                    if output.column is not None and output.column.casefold() == primary_reference
                )
            ordered_aliases.extend(output.alias for output in grouped)
            unique_aliases = tuple(dict.fromkeys(ordered_aliases))
            return tuple(
                PlanOrder(
                    target_alias=alias,
                    direction=(direction if index == 0 else PlanSortDirection.ASCENDING),
                )
                for index, alias in enumerate(unique_aliases)
            )

        detail_outputs = tuple(
            output
            for output in outputs
            if output.kind is PlanOutputKind.COLUMN and not output.group_by
        )
        if plan.limit is None or len(detail_outputs) != len(outputs):
            return current
        benchmark_order = self._bounded_benchmark_ordering(
            base_table,
            detail_outputs,
            filters,
        )
        if benchmark_order is not None:
            return benchmark_order
        filter_order = self._bounded_filter_ordering(base_table, detail_outputs, filters)
        if filter_order is not None:
            return filter_order
        primary_key = self._primary_keys.get(base_table, ())
        if len(primary_key) != 1:
            return current
        primary_reference = f"{base_table}.{primary_key[0]}".casefold()
        primary_alias = next(
            (
                output.alias
                for output in detail_outputs
                if output.column is not None and output.column.casefold() == primary_reference
            ),
            None,
        )
        if primary_alias is None:
            return current
        return (
            PlanOrder(
                target_alias=primary_alias,
                direction=PlanSortDirection.ASCENDING,
            ),
        )

    def _prefer_grouped_dimension_order(
        self,
        grouped: tuple[PlanOutput, ...],
        measures: tuple[PlanOutput, ...],
    ) -> bool:
        if any(
            output.column is not None
            and self._qualified(output.column)[1].casefold().endswith("id")
            for output in grouped
        ):
            return True
        for output in measures:
            if output.kind is PlanOutputKind.AGGREGATE and output.aggregate not in {
                PlanAggregate.COUNT,
                PlanAggregate.COUNT_DISTINCT,
            }:
                return False
            if output.kind is PlanOutputKind.METRIC:
                if output.metric_id is None:
                    return False
                metric = self._metrics[output.metric_id]
                if metric.aggregation.casefold() not in {"count", "count_distinct"}:
                    return False
        return True

    def _bounded_filter_ordering(
        self,
        base_table: str,
        outputs: tuple[PlanOutput, ...],
        filters: tuple[PlanFilter, ...],
    ) -> tuple[PlanOrder, ...] | None:
        multi_value = tuple(
            item
            for item in filters
            if item.scope is PlanFilterScope.WHERE
            and item.operator is PlanFilterOperator.IN
            and len(item.values) > 1
        )
        if len(multi_value) != 1:
            return None
        target_alias = next(
            (
                output.alias
                for output in outputs
                if output.column is not None
                and output.column.casefold() == multi_value[0].target.casefold()
            ),
            None,
        )
        if target_alias is None:
            return None
        return self._with_primary_key_tiebreaker(
            base_table,
            outputs,
            (PlanOrder(target_alias=target_alias, direction=PlanSortDirection.ASCENDING),),
        )

    def _bounded_benchmark_ordering(
        self,
        base_table: str,
        outputs: tuple[PlanOutput, ...],
        filters: tuple[PlanFilter, ...],
    ) -> tuple[PlanOrder, ...] | None:
        """Rank bounded detail rows by their sole global-average comparison."""

        benchmark_filters = tuple(
            item
            for item in filters
            if item.scope is PlanFilterScope.WHERE and item.benchmark is not None
        )
        if len(benchmark_filters) != 1:
            return None
        benchmark_filter = benchmark_filters[0]
        directions = {
            PlanFilterOperator.GREATER_THAN: PlanSortDirection.DESCENDING,
            PlanFilterOperator.GREATER_OR_EQUAL: PlanSortDirection.DESCENDING,
            PlanFilterOperator.LESS_THAN: PlanSortDirection.ASCENDING,
            PlanFilterOperator.LESS_OR_EQUAL: PlanSortDirection.ASCENDING,
        }
        direction = directions.get(benchmark_filter.operator)
        if direction is None:
            return None
        target_alias = next(
            (
                output.alias
                for output in outputs
                if output.column is not None
                and output.column.casefold() == benchmark_filter.target.casefold()
            ),
            None,
        )
        if target_alias is None:
            return None
        return self._with_primary_key_tiebreaker(
            base_table,
            outputs,
            (PlanOrder(target_alias=target_alias, direction=direction),),
        )

    def _with_primary_key_tiebreaker(
        self,
        base_table: str,
        outputs: tuple[PlanOutput, ...],
        current: tuple[PlanOrder, ...],
    ) -> tuple[PlanOrder, ...]:
        if not current:
            return current
        primary_key = self._primary_keys.get(base_table, ())
        if len(primary_key) != 1:
            return current
        primary_reference = f"{base_table}.{primary_key[0]}".casefold()
        primary_alias = next(
            (
                output.alias
                for output in outputs
                if output.column is not None and output.column.casefold() == primary_reference
            ),
            None,
        )
        if primary_alias is None or any(
            order.target_alias.casefold() == primary_alias.casefold() for order in current
        ):
            return current
        return (
            *current,
            PlanOrder(
                target_alias=primary_alias,
                direction=PlanSortDirection.ASCENDING,
            ),
        )

    @staticmethod
    def _display_set(columns: tuple[str, ...]) -> tuple[str, ...]:
        by_name = {column.casefold(): column for column in columns}
        if "name" in by_name:
            return (by_name["name"],)
        if "firstname" in by_name and "lastname" in by_name:
            return (by_name["firstname"], by_name["lastname"])
        if "title" in by_name:
            return (by_name["title"],)
        return ()

    def _complete_base_projection(
        self,
        plan: AnalysisPlan,
        base_table: str,
        outputs: tuple[PlanOutput, ...],
        question: str,
    ) -> tuple[PlanOutput, ...]:
        """Complete trusted detail roles and entity-group identities."""

        detail_mode = all(
            output.kind is PlanOutputKind.COLUMN
            and not output.group_by
            and output.column is not None
            for output in outputs
        )
        aggregate_mode = any(
            output.kind in {PlanOutputKind.AGGREGATE, PlanOutputKind.METRIC} for output in outputs
        ) and all(
            output.kind in {PlanOutputKind.COLUMN, PlanOutputKind.AGGREGATE, PlanOutputKind.METRIC}
            and (output.kind is not PlanOutputKind.COLUMN or output.group_by)
            for output in outputs
        )
        if plan.related_filters or not outputs or not (detail_mode or aggregate_mode):
            return outputs
        primary_key = self._primary_keys.get(base_table, ())
        if len(primary_key) != 1:
            return outputs
        base_display = self._display_column_sets.get(base_table, ())
        required_columns: list[str]
        if aggregate_mode:
            selected_group_columns = {
                self._qualified(output.column)[1]
                for output in outputs
                if output.kind is PlanOutputKind.COLUMN
                and output.group_by
                and output.column is not None
                and self._qualified(output.column)[0] == base_table
            }
            entity_signature = set(primary_key) | set(base_display)
            if not selected_group_columns & entity_signature:
                return outputs
            required_columns = [primary_key[0], *base_display]
        else:
            required_columns = [primary_key[0], *base_display]
            if not base_display:
                foreign_keys = self._relevant_foreign_keys(base_table, question)
                if plan.limit is not None:
                    required_columns.extend(foreign_keys)
                required_columns.extend(self._numeric_value_columns.get(base_table, ()))
            required_columns.extend(
                self._requested_filter_projection_columns(plan, base_table, question)
            )
        required_columns = list(dict.fromkeys(required_columns))

        by_reference = {
            output.column.casefold(): output for output in outputs if output.column is not None
        }
        aliases = {output.alias.casefold() for output in outputs}
        completed: list[PlanOutput] = []
        used_references: set[str] = set()
        for column in required_columns:
            reference = f"{base_table}.{column}"
            key = reference.casefold()
            existing = by_reference.get(key)
            if existing is not None:
                if aggregate_mode and not existing.group_by:
                    existing = existing.model_copy(update={"group_by": True})
                completed.append(existing)
            else:
                alias = column
                if alias.casefold() in aliases:
                    alias = f"{base_table}_{column}"
                if not _ALIAS_PATTERN.fullmatch(alias):
                    raise AnalysisPlanError("invalid_completed_output_alias")
                aliases.add(alias.casefold())
                completed.append(
                    PlanOutput(
                        kind=PlanOutputKind.COLUMN,
                        alias=alias,
                        column=reference,
                        group_by=aggregate_mode,
                    )
                )
            used_references.add(key)
        completed.extend(
            output
            for output in outputs
            if output.column is None or output.column.casefold() not in used_references
        )
        return tuple(completed)

    def _relevant_foreign_keys(self, base_table: str, question: str) -> tuple[str, ...]:
        foreign_keys = self._foreign_key_targets.get(base_table, ())
        if len(foreign_keys) <= 1:
            return tuple(column for column, _target, _referred in foreign_keys)
        mentioned = tuple(
            column
            for column, target, _referred in foreign_keys
            if self._question_mentions_table(question, target)
        )
        return mentioned or tuple(column for column, _target, _referred in foreign_keys)

    def _complete_related_display_projection(
        self,
        outputs: tuple[PlanOutput, ...],
        base_table: str,
        question: str,
    ) -> tuple[PlanOutput, ...]:
        """Complete display pairs for a named direct relationship role."""

        selected = {output.column.casefold() for output in outputs if output.column is not None}
        aliases = {output.alias.casefold() for output in outputs}
        completed = list(outputs)
        normalized = " ".join(re.sub(r"[^a-z0-9]+", " ", question.casefold()).split())
        for constrained, target, _referred in self._foreign_key_targets.get(base_table, ()):
            role = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", constrained[:-2]).casefold()
            if not role or re.search(rf"\b{re.escape(role)}\b", normalized) is None:
                continue
            prefix = role.split()[-1]
            for column in self._display_column_sets.get(target, ()):
                reference = f"{target}.{column}"
                if reference.casefold() in selected:
                    continue
                snake_column = re.sub(
                    r"(?<=[a-z0-9])(?=[A-Z])",
                    "_",
                    column,
                ).casefold()
                alias = f"{prefix}_{snake_column}"
                if alias.casefold() in aliases or not _ALIAS_PATTERN.fullmatch(alias):
                    alias = f"{target}_{column}"
                aliases.add(alias.casefold())
                selected.add(reference.casefold())
                completed.append(
                    PlanOutput(
                        kind=PlanOutputKind.COLUMN,
                        alias=alias,
                        column=reference,
                    )
                )
        return tuple(completed)

    def _question_mentions_table(self, question: str, table: str) -> bool:
        normalized = " ".join(re.sub(r"[^a-z0-9]+", " ", question.casefold()).split())
        spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", table).casefold()
        aliases = {spaced, spaced.replace(" ", ""), _plural_forms(spaced)}
        return any(
            re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", normalized)
            for alias in aliases
        )

    def _requested_filter_projection_columns(
        self,
        plan: AnalysisPlan,
        base_table: str,
        question: str,
    ) -> tuple[str, ...]:
        requested: list[str] = []
        numeric = {column.casefold() for column in self._numeric_value_columns.get(base_table, ())}
        for item in plan.filters:
            if item.scope is not PlanFilterScope.WHERE or item.benchmark is not None:
                continue
            try:
                table, column = self._qualified(item.target)
            except AnalysisPlanError:
                continue
            if table != base_table:
                continue
            if (
                column.casefold().endswith("id")
                or column.casefold() in numeric
                or (item.operator is PlanFilterOperator.IN and len(item.values) > 1)
            ):
                requested.append(column)
            elif item.operator is PlanFilterOperator.IS_NULL:
                if self._missing_value_is_focus(question, column):
                    requested.append(column)
            elif self._column_is_named(question, column):
                requested.append(column)
        return tuple(dict.fromkeys(requested))

    @staticmethod
    def _column_tokens(column: str) -> tuple[str, ...]:
        spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", column).casefold()
        values = list(spaced.split())
        if values and values[-1].endswith("s") and len(values[-1]) > 3:
            values.append(values[-1][:-1])
        return tuple(dict.fromkeys(values))

    def _column_is_named(self, question: str, column: str) -> bool:
        tokens = set(re.sub(r"[^a-z0-9]+", " ", question.casefold()).split())
        return any(token in tokens for token in self._column_tokens(column))

    def _missing_value_is_focus(self, question: str, column: str) -> bool:
        normalized = " ".join(re.sub(r"[^a-z0-9]+", " ", question.casefold()).split())
        column_tokens = self._column_tokens(column)
        for token in column_tokens:
            if re.search(
                rf"\b(?:missing|null|kosong)\b(?:\s+[a-z0-9]+){{0,2}}\s+{re.escape(token)}\b",
                normalized,
            ):
                return True
        return False

    def _prune_filter_only_projection(
        self,
        plan: AnalysisPlan,
        base_table: str,
        outputs: tuple[PlanOutput, ...],
        filters: tuple[PlanFilter, ...],
        question: str,
    ) -> tuple[PlanOutput, ...]:
        """Remove only unrequested non-ID filter fields from detail presentation."""

        if (
            plan.limit is None
            or plan.related_filters
            or any(
                output.kind is not PlanOutputKind.COLUMN or output.group_by or output.column is None
                for output in outputs
            )
        ):
            return outputs
        candidates: set[str] = set()
        for item in filters:
            if item.scope is not PlanFilterScope.WHERE or item.benchmark is not None:
                continue
            table, column = self._qualified(item.target)
            if table == base_table and not column.casefold().endswith("id"):
                candidates.add(item.target.casefold())
        if not candidates:
            return outputs

        protected_columns = set(self._primary_keys.get(base_table, ()))
        display_columns = self._display_column_sets.get(base_table, ())
        if display_columns:
            protected_columns.update(display_columns)
        else:
            protected_columns.update(self._foreign_key_columns.get(base_table, ()))
            core_value = self._core_value_columns.get(base_table)
            if core_value is not None:
                protected_columns.add(core_value)
        protected_references = {f"{base_table}.{column}".casefold() for column in protected_columns}
        protected_references.update(
            f"{base_table}.{column}".casefold()
            for column in self._requested_filter_projection_columns(plan, base_table, question)
        )
        ordered_aliases = {order.target_alias.casefold() for order in plan.order_by}

        def keep(output: PlanOutput) -> bool:
            if output.column is None:
                return True
            reference = output.column.casefold()
            if reference not in candidates or reference in protected_references:
                return True
            return output.alias.casefold() in ordered_aliases

        return tuple(output for output in outputs if keep(output))

    def _validate_bounded_detail_projection(
        self,
        plan: AnalysisPlan,
        base_table: str,
        outputs: tuple[PlanOutput, ...],
        filters: tuple[PlanFilter, ...],
        question: str,
    ) -> None:
        if (
            plan.limit is None
            or plan.related_filters
            or not outputs
            or any(
                output.kind is not PlanOutputKind.COLUMN or output.group_by or output.column is None
                for output in outputs
            )
        ):
            return
        selected = {output.column.casefold() for output in outputs if output.column is not None}

        def require(table: str, column: str, code: str) -> None:
            if f"{table}.{column}".casefold() not in selected:
                raise AnalysisPlanError(code)

        compact_question = re.sub(r"[^a-z0-9]+", "", question.casefold())
        filter_targets = {
            item.target.casefold()
            for item in filters
            if item.scope is PlanFilterScope.WHERE and item.benchmark is None
        }
        identifier_entities = {
            column[:-2].casefold()
            for item in filters
            if item.scope is PlanFilterScope.WHERE and item.benchmark is None
            for table, column in (self._qualified(item.target),)
            if table == base_table and column.casefold().endswith("id")
        }
        for table in sorted(self._column_names, key=str.casefold):
            if table == base_table or table.casefold() not in compact_question:
                continue
            if table.casefold() in identifier_entities:
                continue
            displays = self._display_column_sets.get(table, ())
            if not displays:
                continue
            try:
                self._unique_shortest_path(base_table, table)
            except AnalysisPlanError:
                continue
            for column in displays:
                require(table, column, "missing_related_display_projection")

        for column in self._column_names[base_table].values():
            compact_column = re.sub(r"[^a-z0-9]+", "", column.casefold())
            reference = f"{base_table}.{column}".casefold()
            if (
                reference not in filter_targets
                and len(compact_column) >= 5
                and compact_column in compact_question
            ):
                require(base_table, column, "missing_named_attribute_projection")

    def _validate_filtered_detail_projection(
        self,
        plan: AnalysisPlan,
        base_table: str,
        outputs: tuple[PlanOutput, ...],
        filters: tuple[PlanFilter, ...],
    ) -> None:
        """Require a complete display shape for bounded foreign-ID entity lists."""

        if (
            plan.limit is None
            or plan.related_filters
            or not outputs
            or any(
                output.kind is not PlanOutputKind.COLUMN
                or output.group_by
                or output.column is None
                or self._qualified(output.column)[0] != base_table
                for output in outputs
            )
        ):
            return
        primary_key = self._primary_keys.get(base_table, ())
        display_column = self._display_columns.get(base_table)
        if len(primary_key) != 1 or display_column is None:
            return
        identifier_filters: list[str] = []
        for item in filters:
            if (
                item.scope is not PlanFilterScope.WHERE
                or item.benchmark is not None
                or item.operator not in {PlanFilterOperator.EQUALS, PlanFilterOperator.IN}
            ):
                continue
            table, column = self._qualified(item.target)
            if (
                table == base_table
                and column.casefold().endswith("id")
                and column.casefold() != primary_key[0].casefold()
            ):
                identifier_filters.append(column)
        if len(identifier_filters) != 1:
            return
        required_roles = (
            (
                f"{base_table}.{primary_key[0]}".casefold(),
                "missing_primary_identifier_projection",
            ),
            (
                f"{base_table}.{display_column}".casefold(),
                "missing_display_projection",
            ),
            (
                f"{base_table}.{identifier_filters[0]}".casefold(),
                "missing_filter_identifier_projection",
            ),
        )
        selected = {output.column.casefold() for output in outputs if output.column is not None}
        for required, error_code in required_roles:
            if required not in selected:
                raise AnalysisPlanError(error_code)

    def _ground_output(self, output: PlanOutput) -> PlanOutput:
        if not _ALIAS_PATTERN.fullmatch(output.alias):
            raise AnalysisPlanError("invalid_output_alias")
        updates: dict[str, object] = {}
        if output.column is not None:
            updates["column"] = self._reference(output.column)
        if output.second_column is not None:
            updates["second_column"] = self._reference(output.second_column)
        if output.metric_id is not None:
            metric_id = output.metric_id.casefold()
            if metric_id not in self._metrics:
                raise AnalysisPlanError("unknown_metric")
            updates["metric_id"] = metric_id
        return output.model_copy(update=updates)

    def _ground_filter(
        self,
        item: PlanFilter,
        aliases: dict[str, str],
    ) -> PlanFilter:
        if item.scope is PlanFilterScope.HAVING:
            target = aliases.get(item.target.casefold())
            if target is None:
                raise AnalysisPlanError("unknown_having_alias")
        else:
            target = self._reference(item.target)
        benchmark = self._ground_benchmark(item.benchmark) if item.benchmark else None
        return item.model_copy(update={"target": target, "benchmark": benchmark})

    def _ground_benchmark(self, benchmark: PlanBenchmark) -> PlanBenchmark:
        updates: dict[str, object] = {
            "table": self._table(benchmark.table),
            "column": self._reference(benchmark.column),
        }
        if benchmark.group_by is not None:
            updates["group_by"] = self._reference(benchmark.group_by)
        grounded = benchmark.model_copy(update=updates)
        if self._qualified(grounded.column)[0] != grounded.table:
            raise AnalysisPlanError("benchmark_table_mismatch")
        if grounded.group_by and self._qualified(grounded.group_by)[0] != grounded.table:
            raise AnalysisPlanError("benchmark_group_table_mismatch")
        return grounded

    def _ground_related(self, item: PlanRelatedFilter) -> PlanRelatedFilter:
        base = self._table(item.base_table)
        select_column = self._reference(item.subquery_select_column)
        outer_column = self._reference(item.outer_column)
        provisional_filters = tuple(
            self._ground_filter(filter_item, {}) for filter_item in item.filters
        )
        required = {base, self._qualified(select_column)[0]}
        required.update(
            self._qualified(filter_item.target)[0] for filter_item in provisional_filters
        )
        joins, tables = self._paths_from(base, required)
        return item.model_copy(
            update={
                "outer_column": outer_column,
                "subquery_select_column": select_column,
                "base_table": base,
                "tables": tables,
                "join_ids": joins,
                "filters": provisional_filters,
            }
        )

    def _paths_from(
        self,
        base_table: str,
        required_tables: set[str],
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        join_ids: list[str] = []
        included = {base_table}
        for target in sorted(required_tables - {base_table}, key=str.casefold):
            path_tables, path_joins = self._unique_shortest_path(base_table, target)
            included.update(path_tables)
            for join_id in path_joins:
                if join_id not in join_ids:
                    join_ids.append(join_id)
        ordered_tables = (base_table, *sorted(included - {base_table}, key=str.casefold))
        return tuple(join_ids), ordered_tables

    def _unique_shortest_path(
        self,
        start: str,
        end: str,
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        queue: deque[tuple[str, tuple[str, ...], tuple[str, ...]]] = deque([(start, (start,), ())])
        best_length: int | None = None
        solutions: list[tuple[tuple[str, ...], tuple[str, ...]]] = []
        while queue:
            node, tables, joins = queue.popleft()
            if best_length is not None and len(joins) > best_length:
                continue
            if node == end:
                best_length = len(joins)
                solutions.append((tables, joins))
                continue
            for neighbor, join_id in self._graph.get(node, []):
                if neighbor not in tables:
                    queue.append((neighbor, (*tables, neighbor), (*joins, join_id)))
        unique = {(tables, joins) for tables, joins in solutions}
        if not unique:
            raise AnalysisPlanError("no_approved_join_path")
        if len(unique) != 1:
            raise AnalysisPlanError("ambiguous_join_path")
        return next(iter(unique))

    def _output_tables(self, output: PlanOutput) -> set[str]:
        tables: set[str] = set()
        if output.column:
            tables.add(self._qualified(output.column)[0])
        if output.second_column:
            tables.add(self._qualified(output.second_column)[0])
        if output.metric_id:
            metric = self._metrics[output.metric_id]
            tables.add(metric.source_table)
        return tables

    def _filter_tables(self, item: PlanFilter) -> set[str]:
        tables: set[str] = set()
        if item.scope is PlanFilterScope.WHERE:
            tables.add(self._qualified(item.target)[0])
        if item.benchmark:
            tables.add(item.benchmark.table)
        return tables

    def _table(self, value: str) -> str:
        canonical = self._table_names.get(value.casefold())
        if canonical is None:
            raise AnalysisPlanError("unknown_table")
        return canonical

    def _reference(self, value: str) -> str:
        table_name, column_name = self._qualified(value)
        return f"{table_name}.{column_name}"

    def _qualified(self, value: str) -> tuple[str, str]:
        table_value, separator, column_value = value.partition(".")
        if not separator:
            raise AnalysisPlanError("unqualified_column")
        table_name = self._table(table_value)
        column_name = self._column_names[table_name].get(column_value.casefold())
        if column_name is None:
            raise AnalysisPlanError("unknown_column")
        return table_name, column_name


class AnalysisPlanCompiler:
    """Compile only validated plan primitives into one read-only SELECT."""

    _TIME_FORMATS: Final = {
        PlanTimeGrain.YEAR: "%Y",
        PlanTimeGrain.MONTH: "%Y-%m",
        PlanTimeGrain.MONTH_NUMBER: "%m",
        PlanTimeGrain.WEEKDAY_NUMBER: "%w",
    }

    def __init__(
        self,
        metrics: dict[str, MetricDefinition],
        joins: dict[str, JoinDefinition],
    ) -> None:
        self._metrics = metrics
        self._joins = joins

    def compile(self, plan: AnalysisPlan) -> CompiledAnalysisPlan:
        if plan.intent is not LLMIntent.ANALYSIS or plan.base_table is None:
            raise AnalysisPlanError("analysis_plan_required")
        expressions = {output.alias: self._output_expression(output) for output in plan.outputs}
        select_items = tuple(
            f"{expressions[output.alias]} AS {output.alias}" for output in plan.outputs
        )
        from_clause = self._from_clause(plan.base_table, plan.tables, plan.join_ids)
        where_items = [
            self._filter_expression(item, expressions)
            for item in plan.filters
            if item.scope is PlanFilterScope.WHERE
        ]
        where_items.extend(self._related_expression(item) for item in plan.related_filters)
        group_items = [expressions[output.alias] for output in plan.outputs if output.group_by]
        having_items = [
            self._filter_expression(item, expressions)
            for item in plan.filters
            if item.scope is PlanFilterScope.HAVING
        ]
        order_items = [
            f"{order.target_alias} "
            f"{'ASC' if order.direction is PlanSortDirection.ASCENDING else 'DESC'}"
            for order in plan.order_by
        ]
        pieces = [f"SELECT {', '.join(select_items)}", from_clause]
        if where_items:
            pieces.append("WHERE " + " AND ".join(where_items))
        if group_items:
            pieces.append("GROUP BY " + ", ".join(group_items))
        if having_items:
            pieces.append("HAVING " + " AND ".join(having_items))
        if order_items:
            pieces.append("ORDER BY " + ", ".join(order_items))
        if plan.limit is not None:
            pieces.append(f"LIMIT {plan.limit}")
        sql = " ".join(pieces)
        columns = self._declared_columns(plan)
        all_tables = tuple(
            dict.fromkeys(
                (
                    *plan.tables,
                    *(table for item in plan.related_filters for table in item.tables),
                )
            )
        )
        return CompiledAnalysisPlan(
            sql=sql,
            tables=all_tables,
            columns=columns,
            output_aliases=tuple(output.alias for output in plan.outputs),
        )

    def proposal(self, plan: AnalysisPlan, compiled: CompiledAnalysisPlan) -> StructuredSQLProposal:
        return StructuredSQLProposal(
            intent=plan.intent,
            language=plan.language,
            needs_clarification=plan.needs_clarification,
            clarification_question=plan.clarification_question,
            assumptions=plan.assumptions,
            sql=compiled.sql,
            tables=compiled.tables,
            columns=compiled.columns,
            confidence=plan.confidence,
            reasoning_summary=plan.reasoning_summary,
        )

    def _output_expression(self, output: PlanOutput) -> str:
        if output.kind is PlanOutputKind.COLUMN:
            expression = output.column
        elif output.kind is PlanOutputKind.TIME_BUCKET:
            if output.time_grain is None or output.column is None:
                raise AnalysisPlanError("invalid_time_output")
            expression = f"strftime('{self._TIME_FORMATS[output.time_grain]}', {output.column})"
        elif output.kind is PlanOutputKind.METRIC:
            if output.metric_id is None or output.metric_id not in self._metrics:
                raise AnalysisPlanError("unknown_metric")
            expression = self._metrics[output.metric_id].expression
        else:
            expression = self._aggregate_expression(
                output.aggregate, output.column, output.second_column
            )
        if expression is None:
            raise AnalysisPlanError("invalid_output_expression")
        if output.round_digits is not None:
            expression = f"ROUND({expression}, {output.round_digits})"
        return expression

    def _aggregate_expression(
        self,
        aggregate: PlanAggregate | None,
        column: str | None,
        second_column: str | None = None,
    ) -> str:
        if aggregate is None or column is None:
            raise AnalysisPlanError("invalid_aggregate")
        if aggregate is PlanAggregate.COUNT:
            return f"COUNT({column})"
        if aggregate is PlanAggregate.COUNT_DISTINCT:
            return f"COUNT(DISTINCT {column})"
        if aggregate is PlanAggregate.SUM:
            return f"SUM({column})"
        if aggregate is PlanAggregate.AVERAGE:
            return f"AVG({column})"
        if aggregate is PlanAggregate.MINIMUM:
            return f"MIN({column})"
        if aggregate is PlanAggregate.MAXIMUM:
            return f"MAX({column})"
        if second_column is None:
            raise AnalysisPlanError("sum_product_missing_column")
        return f"SUM({column} * {second_column})"

    def _from_clause(
        self,
        base_table: str,
        tables: tuple[str, ...],
        join_ids: tuple[str, ...],
    ) -> str:
        visited = {base_table}
        clauses = [f"FROM {base_table}"]
        pending = list(join_ids)
        while pending:
            progressed = False
            for join_id in tuple(pending):
                join = self._joins.get(join_id)
                if join is None or join.left_table == join.right_table:
                    raise AnalysisPlanError("unsupported_join")
                left_seen = join.left_table in visited
                right_seen = join.right_table in visited
                if left_seen == right_seen:
                    continue
                new_table = join.right_table if left_seen else join.left_table
                conditions = " AND ".join(
                    f"{join.left_table}.{left} = {join.right_table}.{right}"
                    for left, right in zip(
                        join.left_columns,
                        join.right_columns,
                        strict=True,
                    )
                )
                clauses.append(f"JOIN {new_table} ON {conditions}")
                visited.add(new_table)
                pending.remove(join_id)
                progressed = True
            if not progressed:
                raise AnalysisPlanError("disconnected_join_plan")
        if visited != set(tables):
            raise AnalysisPlanError("join_table_mismatch")
        return " ".join(clauses)

    def _filter_expression(
        self,
        item: PlanFilter,
        outputs: dict[str, str],
    ) -> str:
        target = outputs[item.target] if item.scope is PlanFilterScope.HAVING else item.target
        operator = item.operator
        if operator is PlanFilterOperator.IS_NULL:
            return f"{target} IS NULL"
        if operator is PlanFilterOperator.IS_NOT_NULL:
            return f"{target} IS NOT NULL"
        if item.benchmark is not None:
            right = self._benchmark_expression(item.benchmark)
        elif operator is PlanFilterOperator.BETWEEN:
            right = f"{_literal(item.values[0])} AND {_literal(item.values[1])}"
        elif operator is PlanFilterOperator.IN:
            right = "(" + ", ".join(_literal(value) for value in item.values) + ")"
        elif operator in {
            PlanFilterOperator.CONTAINS,
            PlanFilterOperator.STARTS_WITH,
            PlanFilterOperator.ENDS_WITH,
        }:
            raw = str(item.values[0])
            pattern = {
                PlanFilterOperator.CONTAINS: f"%{raw}%",
                PlanFilterOperator.STARTS_WITH: f"{raw}%",
                PlanFilterOperator.ENDS_WITH: f"%{raw}",
            }[operator]
            return f"{target} LIKE {_literal(pattern)}"
        else:
            right = _literal(item.values[0])
        sql_operator = {
            PlanFilterOperator.EQUALS: "=",
            PlanFilterOperator.NOT_EQUALS: "!=",
            PlanFilterOperator.GREATER_THAN: ">",
            PlanFilterOperator.GREATER_OR_EQUAL: ">=",
            PlanFilterOperator.LESS_THAN: "<",
            PlanFilterOperator.LESS_OR_EQUAL: "<=",
            PlanFilterOperator.BETWEEN: "BETWEEN",
            PlanFilterOperator.IN: "IN",
        }.get(operator)
        if sql_operator is None:
            raise AnalysisPlanError("unsupported_filter_operator")
        return f"{target} {sql_operator} {right}"

    def _benchmark_expression(self, benchmark: PlanBenchmark) -> str:
        if benchmark.kind is PlanBenchmarkKind.GLOBAL_AVERAGE:
            return f"(SELECT AVG({benchmark.column}) FROM {benchmark.table})"
        if benchmark.aggregate is None or benchmark.group_by is None:
            raise AnalysisPlanError("invalid_group_benchmark")
        grouped = self._aggregate_expression(benchmark.aggregate, benchmark.column)
        return (
            "(SELECT AVG(group_value) FROM "
            f"(SELECT {grouped} AS group_value FROM {benchmark.table} "
            f"GROUP BY {benchmark.group_by}))"
        )

    def _related_expression(self, item: PlanRelatedFilter) -> str:
        from_clause = self._from_clause(item.base_table, item.tables, item.join_ids)
        filters = " AND ".join(self._filter_expression(value, {}) for value in item.filters)
        return (
            f"{item.outer_column} IN (SELECT {item.subquery_select_column} "
            f"{from_clause} WHERE {filters})"
        )

    def _declared_columns(self, plan: AnalysisPlan) -> tuple[str, ...]:
        values: list[str] = []

        def add(value: str | None) -> None:
            if value and value not in values:
                values.append(value)

        for output in plan.outputs:
            add(output.column)
            add(output.second_column)
            if output.metric_id:
                metric = self._metrics[output.metric_id]
                for table, column in _COLUMN_REFERENCE_PATTERN.findall(metric.expression):
                    add(f"{table}.{column}")
        for item in plan.filters:
            if item.scope is PlanFilterScope.WHERE:
                add(item.target)
            if item.benchmark:
                add(item.benchmark.column)
                add(item.benchmark.group_by)
        for related_item in plan.related_filters:
            add(related_item.outer_column)
            add(related_item.subquery_select_column)
            for filter_item in related_item.filters:
                add(filter_item.target)
            for join_id in related_item.join_ids:
                self._add_join_columns(join_id, add)
        for join_id in plan.join_ids:
            self._add_join_columns(join_id, add)
        return tuple(values)

    def _add_join_columns(
        self,
        join_id: str,
        add: Callable[[str | None], None],
    ) -> None:
        join = self._joins[join_id]
        for column in join.left_columns:
            add(f"{join.left_table}.{column}")
        for column in join.right_columns:
            add(f"{join.right_table}.{column}")


class PlanSQLAlignmentValidator:
    """Independently parse compiler output and reject plan/SQL drift."""

    def validate(
        self,
        plan: AnalysisPlan,
        compiled: CompiledAnalysisPlan,
        *,
        dialect: str,
    ) -> None:
        try:
            tree = parse_one(compiled.sql, read=dialect)
        except ParseError as exc:
            raise AnalysisPlanError("compiled_sql_parse_failed") from exc
        if not isinstance(tree, exp.Select):
            raise AnalysisPlanError("compiled_sql_not_select")
        aliases = tuple(expression.alias_or_name for expression in tree.expressions)
        if aliases != compiled.output_aliases:
            raise AnalysisPlanError("compiled_output_mismatch")
        observed_tables = {table.name for table in tree.find_all(exp.Table)}
        if observed_tables != set(compiled.tables):
            raise AnalysisPlanError("compiled_table_mismatch")
        limit = tree.args.get("limit")
        observed_limit = (
            int(limit.expression.this)
            if limit is not None and limit.expression is not None
            else None
        )
        if observed_limit != plan.limit:
            raise AnalysisPlanError("compiled_limit_mismatch")


def _plural_forms(value: str) -> str:
    if value.endswith("y") and len(value) > 1 and value[-2] not in "aeiou":
        return value[:-1] + "ies"
    if value.endswith(("s", "x", "z", "ch", "sh")):
        return value + "es"
    return value + "s"


def _has_explicit_order(question: str) -> bool:
    normalized = " ".join(re.sub(r"[^a-z0-9]+", " ", question.casefold()).split())
    markers = (
        "berdasarkan",
        "diurutkan",
        "pertama",
        "terakhir",
        "teratas",
        "terbanyak",
        "terbesar",
        "terendah",
        "terkecil",
        "tertinggi",
        "terbaru",
        "terlama",
        "terpanjang",
        "terpendek",
        "tersingkat",
        "biggest",
        "first",
        "highest",
        "last",
        "largest",
        "latest",
        "least",
        "longest",
        "lowest",
        "most",
        "order",
        "peringkat",
        "rank",
        "ranking",
        "shortest",
        "smallest",
        "top",
    )
    padded = f" {normalized} "
    return any(f" {marker}" in padded for marker in markers)


def _is_display_request(question: str) -> bool:
    normalized = " ".join(re.sub(r"[^a-z0-9]+", " ", question.casefold()).split())
    return bool(re.match(r"^(?:list|rank|ranking|show|tampilkan|urutkan)\b", normalized))


def _has_requested_quantity(question: str) -> bool:
    normalized = " ".join(re.sub(r"[^a-z0-9]+", " ", question.casefold()).split())
    quantity = {
        "dua",
        "eight",
        "empat",
        "enam",
        "five",
        "four",
        "lima",
        "nine",
        "one",
        "satu",
        "sembilan",
        "sepuluh",
        "seven",
        "six",
        "ten",
        "three",
        "tiga",
        "tujuh",
        "two",
    }
    return any(token.isdigit() or token in quantity for token in normalized.split())


def _literal(value: str | int | float) -> str:
    if isinstance(value, bool):
        raise AnalysisPlanError("unsupported_literal")
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    return str(value)
