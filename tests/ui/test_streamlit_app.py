"""Headless interaction tests for all major Tahap 6 Streamlit surfaces."""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[2]
APP_PATH = ROOT / "frontend" / "streamlit_app.py"
DATABASE_PATH = ROOT / "data" / "processed" / "chinook.sqlite"


def _app() -> AppTest:
    if not DATABASE_PATH.is_file():
        pytest.skip("Run `python scripts/bootstrap_data.py` before UI tests.")
    return AppTest.from_file(str(APP_PATH)).run(timeout=20)


@pytest.mark.ui
def test_streamlit_success_shows_sql_validation_result_kpi_sources_and_safe_info() -> None:
    app = _app()

    assert not app.exception
    assert app.title[0].value == "AI Database Analyst"
    assert "Tahap 6" in app.warning[0].value
    assert [tab.label for tab in app.tabs] == [
        "AI Analyst",
        "Database Explorer",
        "Query History",
        "System Info",
    ]

    app.button[0].click().run(timeout=20)

    assert not app.exception
    assert app.code[0].value == "SELECT COUNT(CustomerId) AS customer_count FROM Customer"
    assert app.code[1].value == (
        "SELECT COUNT(CustomerId) AS customer_count FROM Customer LIMIT 500"
    )
    assert app.metric[0].label == "Customer Count"
    assert app.metric[0].value == "59"
    assert any("Validation badge" in item.value for item in app.success)
    assert len(app.download_button) == 1
    assert app.download_button[0].label == "Unduh CSV terbatas"
    assert len(app.radio) == 1
    audit = app.json[1].value
    system_info = app.json[-1].value
    assert '"summary_evidence"' in audit
    assert '"result_summarized"' in audit
    assert "api_key" not in system_info.casefold()
    assert "database_url" not in system_info.casefold()
    assert len(app.dataframe) >= 4


@pytest.mark.ui
@pytest.mark.parametrize(
    ("question", "title_fragment"),
    [
        ("Berapa jumlah pelanggan per negara?", "Customer Count by Country"),
        ("Bagaimana tren pendapatan setiap bulan?", "Revenue by Month"),
    ],
)
def test_streamlit_renders_deterministic_bar_and_line_charts(
    question: str,
    title_fragment: str,
) -> None:
    app = _app()
    app.selectbox[0].select(question)
    app.text_area[0].set_value(question)

    app.button[0].click().run(timeout=20)

    assert not app.exception
    assert len(app.get("vega_lite_chart")) == 1
    assert any(title_fragment in item.value for item in app.subheader)
    assert any(item.value == "Penjelasan berbasis hasil" for item in app.subheader)


@pytest.mark.ui
def test_streamlit_clarification_state_has_no_sql_result_chart_or_feedback() -> None:
    app = _app()
    question = "Siapa pelanggan terbaik?"
    app.selectbox[0].select(question)
    app.text_area[0].set_value(question)

    app.button[0].click().run(timeout=20)

    assert not app.exception
    assert any("total belanja" in item.value.casefold() for item in app.info)
    assert app.code[0].value == "—"
    assert app.code[1].value == "Belum dieksekusi"
    assert len(app.metric) == 0
    assert len(app.get("vega_lite_chart")) == 0
    assert len(app.radio) == 0
    assert len(app.download_button) == 0


@pytest.mark.ui
def test_streamlit_feedback_is_saved_and_visible_in_history() -> None:
    app = _app()
    app.button[0].click().run(timeout=20)
    app.radio[0].set_value("Sebagian benar")

    app.button[1].click().run(timeout=20)

    assert not app.exception
    assert any("partially_correct" in item.value for item in app.success)
    history_frame = app.dataframe[-1].value
    assert "partially_correct" in history_frame.to_string()
