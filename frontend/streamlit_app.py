"""Auditable Streamlit UI for result processing and UX in Tahap 6."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import altair as alt
import streamlit as st

from backend.core.config import get_settings
from backend.core.errors import AppError
from backend.evaluation.mini_cases import MINI_EVALUATION_CASES
from backend.runtime.stage6 import Stage6Runtime, create_stage6_runtime
from backend.schemas.llm import QueryResponse, QueryStatus
from backend.schemas.result import ChartSpec, ChartType, FeedbackRating, UXState
from backend.services.chart_selector import sorted_chart_records
from backend.services.result_experience import ux_state_for_error

ROOT = Path(__file__).resolve().parents[1]


@st.cache_resource
def _runtime() -> Stage6Runtime:
    return create_stage6_runtime(ROOT, get_settings())


def _records(columns: tuple[str, ...], rows: tuple[tuple[Any, ...], ...]) -> list[dict[str, Any]]:
    return [dict(zip(columns, row, strict=True)) for row in rows]


def _render_response(response: QueryResponse) -> None:
    st.caption(f"Request ID: {response.request_id}")
    state = response.ui_state or UXState.PENDING
    st.write(f"Status: `{state.value}`")

    if state is UXState.CLARIFICATION:
        st.info(response.clarification_question or response.explanation)
    elif state is UXState.BLOCKED:
        st.error(response.explanation or "SQL diblokir oleh kebijakan keamanan.")
    elif state is UXState.UNSUPPORTED:
        st.warning(response.explanation or "Pertanyaan belum didukung.")
    elif state is UXState.EMPTY:
        st.info(response.explanation or "Kueri berhasil tanpa baris hasil.")
    elif response.explanation:
        st.subheader("Penjelasan berbasis hasil")
        st.write(response.explanation)

    generated, executed = st.columns(2)
    with generated:
        st.subheader("Generated SQL")
        st.code(response.generated_sql or "—", language="sql")
    with executed:
        st.subheader("Executed SQL")
        st.code(response.executed_sql or "Belum dieksekusi", language="sql")

    if response.validation is not None:
        if response.validation.safe:
            st.success("Validation badge: SQL diizinkan oleh kebijakan AST.")
        else:
            st.error("Validation badge: SQL diblokir.")
            st.json(
                {
                    "violations": [
                        violation.model_dump(mode="json")
                        for violation in response.validation.violations
                    ]
                }
            )

    if response.presentation is not None and response.presentation.row_count > 0:
        presentation = response.presentation
        st.subheader("Hasil database")
        st.dataframe(
            _records(
                tuple(column.label for column in presentation.columns),
                presentation.display_rows,
            ),
            width="stretch",
        )
        _render_chart(response)
        try:
            export = _runtime().csv_export.export(response.request_id, response.result)
        except AppError as exc:
            st.warning(exc.public_message)
        else:
            st.download_button(
                "Unduh CSV terbatas",
                data=export.data,
                file_name=export.filename,
                mime=export.media_type,
                help=(
                    f"{export.size_bytes:,} byte; {export.formula_cells_escaped} sel formula "
                    "dinetralkan."
                ),
                on_click="ignore",
            )

    if response.assumptions:
        st.subheader("Asumsi")
        for assumption in response.assumptions:
            st.markdown(f"- {assumption}")
    if response.warnings:
        st.subheader("Peringatan")
        for warning in response.warnings:
            st.warning(warning)

    st.subheader("Sumber")
    st.write(
        {
            "tables": response.presentation.source_tables if response.presentation else (),
            "columns": response.presentation.source_columns if response.presentation else (),
        }
    )
    _render_feedback(response)

    with st.expander("Audit metadata"):
        st.json(
            {
                "prompt_version": response.prompt_version,
                "schema_hash": response.schema_hash,
                "semantic_version": response.semantic_version,
                "semantic_context_hash": response.semantic_context_hash,
                "matched_term_ids": response.matched_term_ids,
                "matched_metric_ids": response.matched_metric_ids,
                "verified_query_ids": response.verified_query_ids,
                "provider": response.provider,
                "model": response.model,
                "tables": response.tables,
                "columns": response.columns,
                "summary_evidence": [
                    evidence.model_dump(mode="json") for evidence in response.summary_evidence
                ],
                "llm_latency_ms": response.llm_latency_ms,
                "database_latency_ms": response.database_latency_ms,
                "validation": (
                    response.validation.model_dump(mode="json") if response.validation else None
                ),
                "pipeline": [event.model_dump(mode="json") for event in response.pipeline],
            }
        )


def _render_chart(response: QueryResponse) -> None:
    chart = response.chart
    presentation = response.presentation
    if chart is None or presentation is None or chart.type is ChartType.TABLE:
        st.caption("Visualisasi tambahan tidak dipaksakan; tabel adalah bentuk paling jujur.")
        return
    st.subheader(f"Visualisasi — {chart.title}")
    st.caption(chart.subtitle)
    for warning in chart.warnings:
        st.caption(f"Catatan: {warning}")
    if chart.type is ChartType.KPI:
        y_index = tuple(column.name for column in presentation.columns).index(chart.y[0])
        st.metric(chart.title, presentation.display_rows[0][y_index], border=True)
        return

    records = sorted_chart_records(presentation, chart)
    color: str | list[str] = chart.palette[0] if len(chart.palette) == 1 else list(chart.palette)
    if chart.type is ChartType.BAR:
        st.bar_chart(
            records,
            x=chart.x,
            y=list(chart.y),
            x_label=chart.x_label,
            y_label=chart.y_label,
            color=color,
            horizontal=chart.orientation.value == "horizontal",
            sort=True,
        )
    elif chart.type is ChartType.LINE:
        _render_line_chart(records, chart)
    elif chart.type is ChartType.SCATTER:
        st.scatter_chart(
            records,
            x=chart.x,
            y=chart.y[0],
            x_label=chart.x_label,
            y_label=chart.y_label,
            color=color,
        )


def _render_line_chart(records: list[dict[str, Any]], chart: ChartSpec) -> None:
    """Render time axes with bounded, horizontal labels and exact tooltips."""

    if chart.x is None or not chart.y:
        return
    x_encoding = alt.X(
        f"{chart.x}:T",
        title=chart.x_label,
        axis=alt.Axis(
            format="%b %Y",
            labelAngle=0,
            labelOverlap="greedy",
            tickCount=10,
        ),
    )
    if len(chart.y) == 1:
        y_name = chart.y[0]
        visual = (
            alt.Chart(alt.Data(values=records))
            .mark_line(color=chart.palette[0], strokeWidth=2)
            .encode(
                x=x_encoding,
                y=alt.Y(f"{y_name}:Q", title=chart.y_label, scale=alt.Scale(zero=True)),
                tooltip=(
                    alt.Tooltip(f"{chart.x}:T", title=chart.x_label, format="%b %Y"),
                    alt.Tooltip(f"{y_name}:Q", title=chart.y_label, format=",.2f"),
                ),
            )
        )
    else:
        visual = (
            alt.Chart(alt.Data(values=records))
            .transform_fold(list(chart.y), as_=("Series", "Value"))
            .mark_line(strokeWidth=2)
            .encode(
                x=x_encoding,
                y=alt.Y("Value:Q", title=chart.y_label, scale=alt.Scale(zero=True)),
                color=alt.Color(
                    "Series:N",
                    scale=alt.Scale(domain=list(chart.y), range=list(chart.palette)),
                    legend=alt.Legend(orient="top"),
                ),
                tooltip=(
                    alt.Tooltip(f"{chart.x}:T", title=chart.x_label, format="%b %Y"),
                    alt.Tooltip("Series:N"),
                    alt.Tooltip("Value:Q", title=chart.y_label, format=",.2f"),
                ),
            )
        )
    st.altair_chart(visual.properties(height=360), width="stretch")


def _render_feedback(response: QueryResponse) -> None:
    if response.status not in {
        QueryStatus.SUCCESS,
        QueryStatus.TRUSTED_DEMO_SUCCESS,
        QueryStatus.EMPTY_RESULT,
    }:
        return
    st.subheader("Feedback")
    choices = {
        "Benar": FeedbackRating.CORRECT,
        "Sebagian benar": FeedbackRating.PARTIALLY_CORRECT,
        "Salah": FeedbackRating.INCORRECT,
    }
    selected = st.radio(
        "Nilai jawaban",
        tuple(choices),
        horizontal=True,
        key=f"feedback-rating-{response.request_id}",
    )
    if st.button("Simpan feedback", key=f"feedback-save-{response.request_id}"):
        try:
            record = _runtime().feedback.submit(response.request_id, choices[selected])
        except AppError as exc:
            st.error(exc.public_message)
        else:
            st.success(f"Feedback tersimpan: {record.rating.value}.")


def _render_database_explorer(runtime: Stage6Runtime) -> None:
    explorer = runtime.database_explorer
    st.subheader("Database Explorer")
    st.caption(
        f"{explorer.source_name} · {explorer.dialect} · schema {explorer.schema_version} · "
        f"refresh {explorer.refreshed_at}"
    )
    table_name = st.selectbox(
        "Tabel",
        tuple(table.name for table in explorer.tables),
        key="database-explorer-table",
    )
    table = next(item for item in explorer.tables if item.name == table_name)
    st.write(table.business_description)
    st.caption(f"Review status: {table.review_status}")
    st.dataframe(
        [column.model_dump(mode="json") for column in table.columns],
        width="stretch",
    )
    if table.relationships:
        st.write("Foreign-key relationships")
        st.dataframe(
            [relationship.model_dump(mode="json") for relationship in table.relationships],
            width="stretch",
        )
    else:
        st.caption("Tabel ini tidak memiliki foreign key keluar.")


def _render_history(runtime: Stage6Runtime) -> None:
    st.subheader("Query History")
    st.caption("Metadata in-memory saja; pertanyaan, SQL, dan result rows tidak disimpan.")
    entries = runtime.history.list()
    if not entries:
        st.info("Belum ada riwayat pada proses aplikasi ini.")
        return
    st.dataframe(
        [entry.model_dump(mode="json") for entry in entries],
        width="stretch",
    )


st.set_page_config(page_title="AI Database Analyst — Tahap 6", layout="wide")
st.title("AI Database Analyst")
st.warning(
    "MVP Tahap 6 — belum production-ready. Result, chart, summary, history, dan feedback "
    "tetap berada di belakang semantic layer, validator AST, dan database read-only."
)

runtime = _runtime()
analyst_tab, explorer_tab, history_tab, system_tab = st.tabs(
    ("AI Analyst", "Database Explorer", "Query History", "System Info")
)

with analyst_tab:
    example = st.selectbox(
        "Contoh terverifikasi",
        options=[
            *[case.question for case in MINI_EVALUATION_CASES],
            "Siapa pelanggan terbaik?",
            "Berapa pelanggan aktif?",
            "Apa produk terbaik?",
            "Berapa pendapatan terbaru?",
        ],
    )
    question = st.text_area(
        "Pertanyaan",
        value=example,
        height=100,
        help="Masukkan pertanyaan analitik dalam Bahasa Indonesia atau English.",
    )

    if st.button("Kirim", type="primary"):
        try:
            with st.spinner("Memuat semantic context, memvalidasi SQL, dan menyusun hasil..."):
                response = asyncio.run(runtime.demo_runner.run(question))
        except AppError as exc:
            state = ux_state_for_error(exc)
            st.session_state["last_error"] = exc.to_public_dict()
            st.error(f"State `{state.value}`: {exc.public_message}")
        else:
            st.session_state["last_response"] = response
            st.session_state.pop("last_error", None)

    last_response = st.session_state.get("last_response")
    if isinstance(last_response, QueryResponse):
        _render_response(last_response)

with explorer_tab:
    _render_database_explorer(runtime)

with history_tab:
    _render_history(runtime)

with system_tab:
    st.subheader("System Info")
    st.caption("Hanya field yang diizinkan; URL database dan credential tidak diserialisasi.")
    st.json(runtime.system_info.model_dump(mode="json"))
