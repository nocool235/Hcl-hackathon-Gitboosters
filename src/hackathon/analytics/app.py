"""Streamlit app: RAG-status scorecards and grounded Q&A for Finance, Marketing, Supply Chain.

Run: streamlit run src/hackathon/analytics/app.py
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from hackathon.analytics import qa, source
from hackathon.analytics.rag_status import TEAMS, build_scorecards
from hackathon.config import DEFAULT_CONFIG, load_config

TEAM_KPIS = {
    "Finance": ["kpi_01", "kpi_08", "stretch_margin_risk"],
    "Marketing": ["kpi_02", "kpi_02b", "kpi_03", "kpi_04", "kpi_07"],
    "Supply Chain": ["kpi_05", "kpi_06", "stretch_margin_risk"],
}

CONFIG = load_config(DEFAULT_CONFIG)
MEDALLION = CONFIG.get("medallion", {})
ANALYTICS = CONFIG.get("analytics", {})


@st.cache_data(ttl=900, show_spinner="Running KPI queries...")
def load_kpis(origin: str, dataset: str, project: str, db_path: str):
    if origin == "BigQuery":
        results, notes = source.run_kpis_bigquery(
            dataset,
            MEDALLION,
            project or None,
            CONFIG.get("kpis"),
            CONFIG.get("bigquery", {}).get("max_bytes_billed"),
        )
    else:
        results, notes = source.run_kpis_sqlite(db_path, MEDALLION, CONFIG.get("kpis"))
    return source.row_counts(results), results, notes


def render_scorecard(metrics) -> None:
    columns = st.columns(len(metrics))
    for col, m in zip(columns, metrics, strict=True):
        value = "n/a" if m.value is None else f"{m.value:,.2f}{m.unit}"
        with col, st.container(border=True):
            st.metric(m.label, value)


def render_qa(team: str, chunks) -> None:
    st.subheader("Ask the data")
    history = st.session_state.setdefault(f"chat_{team}", [])
    for role, text in history:
        st.chat_message(role).write(text)
    question = st.chat_input(f"Ask a {team} question", key=f"input_{team}")
    if not question:
        return
    st.chat_message("user").write(question)
    try:
        answer = qa.answer_question(
            question, team, chunks, model=ANALYTICS.get("model", qa.DEFAULT_MODEL)
        )
    except Exception as exc:  # missing key / network: show it, keep the app alive
        st.error(f"Could not answer: {exc}")
        return
    st.chat_message("assistant").write(answer.text)
    with st.expander("Sources used"):
        for c in answer.sources:
            st.markdown(f"**[{c.id}] {c.source}**")
            st.text(c.text)
    history += [("user", question), ("assistant", answer.text)]


def main() -> None:
    st.set_page_config(page_title="ShopSphere Analytics", layout="wide")
    st.title("ShopSphere team analytics")

    with st.sidebar:
        team = st.radio("Team", TEAMS)
        db_path = MEDALLION.get("db_path", "data/processed/shopsphere.db")
        options = ["BigQuery", "SQLite"]
        origin = st.radio("Data source", options, index=0 if MEDALLION.get("bq_dataset") else 1)
        dataset = st.text_input(
            "BigQuery dataset", MEDALLION.get("bq_dataset") or "shopsphere_gold"
        )
        project = st.text_input(
            "GCP project (blank = GCP_PROJECT_ID)", source.default_project() or ""
        )
        if st.button("Refresh data"):
            st.cache_data.clear()

    if origin == "BigQuery" and not dataset:
        st.info("Enter the BigQuery dataset in the sidebar, or switch the source to SQLite.")
        return
    if origin == "SQLite" and not source.sqlite_available(db_path):
        st.error(f"{db_path} not found. Run `python -m hackathon.medallion` first.")
        return
    try:
        counts, kpis, notes = load_kpis(origin, dataset, project, db_path)
    except Exception as exc:
        st.error(f"Could not load data from {origin}: {exc}")
        return

    scorecards = build_scorecards(kpis, ANALYTICS.get("thresholds"))
    metrics = scorecards[team]
    st.markdown(f"### {team}")
    render_scorecard(metrics)

    tab_data, tab_qa = st.tabs(["KPI detail", "Ask the data"])
    with tab_data:
        for name in TEAM_KPIS[team]:
            note = notes.get(name, "")
            st.subheader(note.split("\n", 1)[0] or name)
            st.dataframe(pd.DataFrame(kpis.get(name, [])), width="stretch", hide_index=True)
            if "\n" in note:
                with st.expander("Definition, inclusions and exclusions"):
                    st.text(note.split("\n", 1)[1])
        st.caption("Row counts: " + ", ".join(f"{k}={v}" for k, v in counts.items()))
    with tab_qa:
        model_text = Path("docs/data_model.md")
        chunks = qa.build_corpus(
            kpis,
            scorecards,
            model_text.read_text(encoding="utf-8") if model_text.exists() else "",
            notes,
        )
        render_qa(team, chunks)


main()
