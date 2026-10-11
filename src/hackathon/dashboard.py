"""Streamlit KPI explorer: pick a KPI, read its definition, run its BigQuery SQL live.

Run from the project root: streamlit run src/hackathon/dashboard.py
"""

from __future__ import annotations

import re
from collections import defaultdict

import streamlit as st

from hackathon.config import load_config
from hackathon.kpis import (
    DEFAULT_MAX_BYTES,
    DEFAULTS,
    md_escape,
    query_params,
    read_header,
    run_bigquery,
    sql_files,
)
from hackathon.stages.bigquery import get_client

st.set_page_config(page_title="ShopSphere KPIs", layout="wide")

cfg = load_config()
kpi_cfg = {**DEFAULTS, **(cfg.get("kpis") or {})}
max_bytes = int((cfg.get("bigquery") or {}).get("max_bytes_billed") or DEFAULT_MAX_BYTES)
defaults = query_params(cfg.get("medallion", {}))


@st.cache_resource
def bq_client():
    return get_client()


@st.cache_data(ttl=600, show_spinner="Running on BigQuery...")
def run_query(sql: str, dataset: str, params: tuple, max_bytes_billed: int):
    job = run_bigquery(bq_client(), sql, dataset, dict(params), max_bytes_billed)
    return job.to_dataframe(), job.total_bytes_processed, job.cache_hit


@st.cache_data(ttl=600)
def gold_loaded_at(dataset: str):
    client = bq_client()
    return client.get_table(f"{client.project}.{dataset}.fact_orders").modified


def describe(entries: list[tuple[str, str]]) -> str:
    return "\n".join(f"- **{label}:** {md_escape(body)}" if label else f"- {md_escape(body)}"
                     for label, body in entries)


# kpi_02b_*.sql is shown inside kpi_02_*.sql's page, not as a KPI of its own.
COMPANION = re.compile(r"^(kpi_\d+)[a-z]_")
kpis, companions = {}, defaultdict(list)
for path in sql_files(kpi_cfg["bq_sql_dir"]):
    match = COMPANION.match(path.stem)
    if match:
        companions[f"{match.group(1)}_"].append(path)
    else:
        kpis[read_header(path.read_text(encoding="utf-8"))[0] or path.stem] = path

with st.sidebar:
    dataset = st.text_input("BigQuery dataset", kpi_cfg["bq_dataset"])
    st.subheader("Parameters")
    params = {
        "return_rate_min_volume": int(st.number_input(
            "Return-rate minimum volume (units)", min_value=1, step=1,
            value=int(defaults["return_rate_min_volume"]))),
        "payment_tolerance": float(st.number_input(
            "Payment tolerance", min_value=0.0, step=0.5,
            value=float(defaults["payment_tolerance"]))),
        "repeat_window_days": int(st.number_input(
            "Repeat-purchase window (days)", min_value=1, step=1,
            value=int(defaults["repeat_window_days"]))),
        "reference_date": st.date_input(
            "Reference date (empty = latest order date)", value=defaults["reference_date"]),
    }
    if st.button("Clear cached results"):
        st.cache_data.clear()

st.title("ShopSphere KPIs")
choice = st.selectbox("KPI", list(kpis))
path = kpis[choice]
sql = path.read_text(encoding="utf-8")
title, entries = read_header(sql)
st.header(title)

try:
    client = bq_client()
    st.caption(f"`{client.project}.{dataset}` · gold loaded "
               f"{gold_loaded_at(dataset):%Y-%m-%d %H:%M} UTC · `{path.as_posix()}`")
except Exception as exc:
    st.error(f"Cannot reach BigQuery: {exc}\n\nCheck `GCP_PROJECT_ID` in `.env` and run "
             "`gcloud auth application-default login`.")
    st.stop()

with st.expander("Definition, inclusions and exclusions", expanded=True):
    st.markdown(describe(entries))

used = [name for name in params if f"@{name}" in sql]
if used:
    st.caption("Parameters used: " + ", ".join(f"`{n}` = {params[n]}" for n in used))

try:
    df, scanned, cache_hit = run_query(sql, dataset, tuple(sorted(params.items())), max_bytes)
except Exception as exc:
    st.error(f"Query failed: {exc}")
    st.stop()

rows_col, scanned_col = st.columns(2)
rows_col.metric("Rows", len(df))
scanned_col.metric("Data scanned",
                   "0 KB (BigQuery cache)" if cache_hit else f"{(scanned or 0) / 1024:,.0f} KB")
st.dataframe(df, hide_index=True)
st.download_button("Download CSV", df.to_csv(index=False).encode("utf-8"),
                   file_name=f"{path.stem}.csv", mime="text/csv")

with st.expander("SQL"):
    st.code(sql, language="sql")

for extra in [p for prefix, paths in companions.items() if path.stem.startswith(prefix)
              for p in paths]:
    extra_sql = extra.read_text(encoding="utf-8")
    extra_title, extra_entries = read_header(extra_sql)
    st.subheader(extra_title.split(": ", 1)[-1])
    with st.expander("Definition"):
        st.markdown(describe(extra_entries))
    try:
        extra_df = run_query(extra_sql, dataset, tuple(sorted(params.items())), max_bytes)[0]
    except Exception as exc:
        st.error(f"Query failed: {exc}")
        continue
    st.dataframe(extra_df, hide_index=True)
    st.download_button("Download CSV", extra_df.to_csv(index=False).encode("utf-8"),
                       file_name=f"{extra.stem}.csv", mime="text/csv", key=extra.stem)
    with st.expander("SQL"):
        st.code(extra_sql, language="sql")
