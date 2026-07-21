"""Final Streamlit frontend that communicates only through FastAPI."""

from __future__ import annotations

from typing import Any

import streamlit as st

from backend.core.config import get_settings
from backend.schemas.llm import QueryResponse, QueryStatus
from backend.schemas.result import ChartType, FeedbackRating, UXState
from backend.services.chart_selector import sorted_chart_records
from backend.services.csv_export import CSVExportService
from frontend.api_client import AnalystAPIClient, APIClientError


@st.cache_resource
def _client() -> AnalystAPIClient:
    settings = get_settings()
    return AnalystAPIClient(settings.api_base_url, timeout_seconds=settings.api_timeout_seconds)


def _records(columns: tuple[str, ...], rows: tuple[tuple[Any, ...], ...]) -> list[dict[str, Any]]:
    return [dict(zip(columns, row, strict=True)) for row in rows]


def _render_api_error(exc: APIClientError) -> None:
    suffix = f" Request ID: {exc.request_id}" if exc.request_id else ""
    st.error(f"{exc.error_code}: {exc.public_message}{suffix}")


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

    presentation = response.presentation
    if presentation is not None and presentation.row_count > 0:
        st.subheader("Hasil database")
        st.dataframe(
            _records(
                tuple(column.label for column in presentation.columns),
                presentation.display_rows,
            ),
            width="stretch",
        )
        _render_chart(response)
        if response.result is not None:
            export = CSVExportService(max_bytes=get_settings().csv_max_bytes).export(
                response.request_id, response.result
            )
            st.download_button(
                "Unduh CSV terbatas",
                data=export.data,
                file_name=export.filename,
                mime=export.media_type,
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
            "tables": presentation.source_tables if presentation else (),
            "columns": presentation.source_columns if presentation else (),
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
                "provider": response.provider,
                "model": response.model,
                "llm_latency_ms": response.llm_latency_ms,
                "database_latency_ms": response.database_latency_ms,
                "pipeline": [event.model_dump(mode="json") for event in response.pipeline],
            }
        )


def _render_chart(response: QueryResponse) -> None:
    chart = response.chart
    presentation = response.presentation
    if chart is None or presentation is None or chart.type is ChartType.TABLE:
        st.caption("Tabel dipertahankan ketika visualisasi lain tidak menambah kejelasan.")
        return
    st.subheader(f"Visualisasi — {chart.title}")
    if chart.type is ChartType.KPI:
        y_index = tuple(column.name for column in presentation.columns).index(chart.y[0])
        st.metric(chart.title, presentation.display_rows[0][y_index], border=True)
        return
    records = sorted_chart_records(presentation, chart)
    if chart.type is ChartType.BAR:
        st.bar_chart(records, x=chart.x, y=list(chart.y), horizontal=True)
    elif chart.type is ChartType.LINE:
        st.line_chart(records, x=chart.x, y=list(chart.y))
    elif chart.type is ChartType.SCATTER:
        st.scatter_chart(records, x=chart.x, y=chart.y[0])


def _render_feedback(response: QueryResponse) -> None:
    if response.status not in {QueryStatus.SUCCESS, QueryStatus.EMPTY_RESULT}:
        return
    choices = {
        "Benar": FeedbackRating.CORRECT,
        "Sebagian benar": FeedbackRating.PARTIALLY_CORRECT,
        "Salah": FeedbackRating.INCORRECT,
    }
    selected = st.radio(
        "Nilai jawaban", tuple(choices), horizontal=True, key=f"rating-{response.request_id}"
    )
    if st.button("Simpan feedback", key=f"feedback-{response.request_id}"):
        try:
            saved = _client().feedback(response.request_id, choices[selected])
        except APIClientError as exc:
            _render_api_error(exc)
        else:
            st.success(f"Feedback tersimpan: {saved.rating.value}.")


def _render_schema() -> None:
    try:
        explorer = _client().schema()
    except APIClientError as exc:
        _render_api_error(exc)
        return
    st.caption(f"{explorer.source_name} · {explorer.dialect} · {explorer.schema_version}")
    table_name = st.selectbox("Tabel", tuple(table.name for table in explorer.tables))
    table = next(item for item in explorer.tables if item.name == table_name)
    st.write(table.business_description)
    st.dataframe([column.model_dump(mode="json") for column in table.columns], width="stretch")


def _render_history() -> None:
    try:
        response = _client().history()
    except APIClientError as exc:
        _render_api_error(exc)
        return
    st.caption("Metadata durable; pertanyaan, SQL mentah, dan result rows tidak disimpan.")
    if not response.items:
        st.info("Belum ada riwayat.")
    else:
        st.dataframe([item.model_dump(mode="json") for item in response.items], width="stretch")


st.set_page_config(page_title="AI Database Analyst — Tahap 9", layout="wide")
st.title("AI Database Analyst")
st.caption("Tahap 9 · Streamlit → FastAPI → PostgreSQL · observable and containerized")
analyst_tab, explorer_tab, history_tab, system_tab = st.tabs(
    ("AI Analyst", "Database Explorer", "Query History", "System Info")
)
with analyst_tab:
    question = st.text_area(
        "Pertanyaan",
        value="Berapa jumlah pelanggan?",
        height=100,
        max_chars=get_settings().question_max_characters,
    )
    if st.button("Kirim", type="primary"):
        try:
            with st.spinner("FastAPI sedang memproses permintaan..."):
                st.session_state["last_response"] = _client().query(question)
        except APIClientError as exc:
            _render_api_error(exc)
    last_response = st.session_state.get("last_response")
    if isinstance(last_response, QueryResponse):
        _render_response(last_response)
with explorer_tab:
    _render_schema()
with history_tab:
    _render_history()
with system_tab:
    try:
        health = _client().health()
    except APIClientError as exc:
        _render_api_error(exc)
    else:
        st.json(health.model_dump(mode="json"))
