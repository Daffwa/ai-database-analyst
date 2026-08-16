"""Final Streamlit frontend that communicates only through FastAPI."""

from __future__ import annotations

from typing import Any

import streamlit as st

from backend.core.config import get_settings
from backend.schemas.agent import AgentRunResponse, AgentTerminalStatus
from backend.schemas.database import QueryResult
from backend.schemas.result import ChartType
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


def _render_agent_response(response: AgentRunResponse) -> None:
    """Render bounded-agent states, including canonical clarification controls."""

    st.caption(f"Request ID: {response.request_id} · Session: {response.session_id}")
    st.write(f"Status: `{response.status.value}` · State: `{response.state.value}`")
    if response.status is AgentTerminalStatus.CLARIFICATION_REQUIRED:
        clarification = response.clarification
        if clarification is None:
            st.error("Continuation tidak memiliki pilihan klarifikasi yang valid.")
            return
        st.info(clarification.question)
        labels = {option.label: option.option_id for option in clarification.options}
        selected = st.selectbox(
            "Pilih interpretasi",
            tuple(labels),
            key=f"clarification-{response.session_id}",
        )
        continue_col, cancel_col = st.columns(2)
        with continue_col:
            if st.button("Lanjutkan", type="primary", key=f"continue-{response.session_id}"):
                original_question = st.session_state.get("agent_question")
                if not isinstance(original_question, str) or not original_question.strip():
                    st.error("Pertanyaan awal tidak tersedia; mulai sesi baru.")
                    return
                try:
                    with st.spinner("Agent melanjutkan dari pilihan kanonis..."):
                        st.session_state["last_agent_response"] = _client().agent_continue(
                            clarification.continuation_id,
                            labels[selected],
                            original_question,
                        )
                    st.rerun()
                except APIClientError as exc:
                    _render_api_error(exc)
        with cancel_col:
            if st.button("Batalkan", key=f"cancel-{response.session_id}"):
                try:
                    _client().agent_cancel(clarification.continuation_id)
                except APIClientError as exc:
                    _render_api_error(exc)
                else:
                    st.session_state.pop("last_agent_response", None)
                    st.rerun()
        return
    if response.status is AgentTerminalStatus.BLOCKED:
        st.error("Permintaan dihentikan oleh boundary otoritas atau kebijakan keamanan.")
    elif response.status is AgentTerminalStatus.UNSUPPORTED:
        st.warning("Tujuan analitik belum didukung oleh model/schema aktif.")
    elif response.status is AgentTerminalStatus.EMPTY_RESULT:
        st.info("Kueri aman berhasil tetapi tidak mengembalikan baris.")
    elif response.status in {
        AgentTerminalStatus.TIMEOUT,
        AgentTerminalStatus.MAX_STEPS_REACHED,
        AgentTerminalStatus.ERROR,
    }:
        st.error(f"Agent berhenti aman: {response.stop_reason}.")

    result = response.result
    if result is not None:
        generated, executed = st.columns(2)
        with generated:
            st.subheader("Generated SQL")
            st.code(result.generated_sql or "—", language="sql")
        with executed:
            st.subheader("Executed SQL")
            st.code(result.executed_sql or "Belum dieksekusi", language="sql")
        if result.explanation:
            st.subheader("Penjelasan berbasis hasil")
            st.write(result.explanation)
        if result.presentation is not None and result.presentation.row_count > 0:
            st.subheader("Hasil database")
            st.dataframe(
                _records(
                    tuple(column.label for column in result.presentation.columns),
                    result.presentation.display_rows,
                ),
                width="stretch",
            )
            _render_agent_chart(response)
            query_result = QueryResult(
                columns=tuple(column.name for column in result.presentation.columns),
                rows=result.presentation.rows,
                row_count=result.presentation.row_count,
                truncated=result.presentation.truncated,
                execution_time_ms=result.presentation.execution_time_ms,
                response_bytes=0,
            )
            export = CSVExportService(max_bytes=get_settings().csv_max_bytes).export(
                response.request_id,
                query_result,
            )
            st.download_button(
                "Unduh CSV terbatas",
                data=export.data,
                file_name=export.filename,
                mime=export.media_type,
                on_click="ignore",
            )
        st.subheader("Sumber")
        st.write({"tables": result.tables, "columns": result.columns})
    with st.expander("Bounded-agent audit"):
        st.json(
            {
                "architecture_version": response.architecture_version,
                "provider": response.provider,
                "model": response.model,
                "budget": response.budget.model_dump(mode="json"),
                "events": [event.model_dump(mode="json") for event in response.audit],
            }
        )


def _render_agent_chart(response: AgentRunResponse) -> None:
    result = response.result
    if result is None or result.presentation is None or result.chart is None:
        return
    chart = result.chart
    presentation = result.presentation
    if chart.type is ChartType.TABLE:
        st.caption("Tabel dipertahankan ketika chart tidak menambah kejelasan.")
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


st.set_page_config(page_title="AI Database Analyst — Bounded Agent", layout="wide")
st.title("AI Database Analyst")
st.caption("Bounded Agent v1 · typed tools · deterministic validation · read-only execution")
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
                st.session_state["agent_question"] = question
                st.session_state["last_agent_response"] = _client().agent_query(question)
        except APIClientError as exc:
            _render_api_error(exc)
    last_response = st.session_state.get("last_agent_response")
    if isinstance(last_response, AgentRunResponse):
        _render_agent_response(last_response)
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
