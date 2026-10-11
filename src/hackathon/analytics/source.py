"""Run the team's KPI SQL files (BigQuery or local SQLite) and return rows for the app.

The SQL lives in `kpis/` (SQLite) and `kpis/bigquery/` (BigQuery) and is owned by
`hackathon.kpis`; this module only executes it and normalises the values for display.
"""

from __future__ import annotations

import os
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from hackathon.kpis import (
    DEFAULT_MAX_BYTES,
    DEFAULTS,
    bigquery_executor,
    check_gold,
    open_gold,
    query_params,
    read_header,
    sql_files,
)

Rows = list[dict[str, Any]]


def normalise_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()[:10]
    return value


def kpi_key(stem: str) -> str:
    """'kpi_02b_customer_reference_exceptions' -> 'kpi_02b', 'stretch_margin_risk' -> as is."""
    parts = stem.split("_")
    return "_".join(parts[:2]) if parts[0] == "kpi" else stem


def _run(files: list[Path], execute) -> tuple[dict[str, Rows], dict[str, str]]:
    results: dict[str, Rows] = {}
    notes: dict[str, str] = {}
    for path in files:
        sql = path.read_text(encoding="utf-8")
        columns, rows = execute(sql)
        key = kpi_key(path.stem)
        results[key] = [
            {c: normalise_value(v) for c, v in zip(columns, row, strict=True)} for row in rows
        ]
        title, entries = read_header(sql)
        notes[key] = "\n".join([title, *(f"{label}: {body}" for label, body in entries)])
    return results, notes


def run_kpis_bigquery(
    dataset: str,
    medallion_cfg: dict[str, Any],
    project: str | None = None,
    kpi_cfg: dict[str, Any] | None = None,
    max_bytes_billed: int | None = None,
    client=None,
) -> tuple[dict[str, Rows], dict[str, str]]:
    from hackathon.stages.bigquery import get_client

    client = client or get_client(project)
    kpi_cfg = {**DEFAULTS, **(kpi_cfg or {})}
    execute = bigquery_executor(
        client, dataset, query_params(medallion_cfg), max_bytes_billed or DEFAULT_MAX_BYTES
    )
    return _run(sql_files(kpi_cfg["bq_sql_dir"]), execute)


def run_kpis_sqlite(
    db_path: str,
    medallion_cfg: dict[str, Any],
    kpi_cfg: dict[str, Any] | None = None,
) -> tuple[dict[str, Rows], dict[str, str]]:
    kpi_cfg = {**DEFAULTS, **(kpi_cfg or {})}
    conn = open_gold(db_path)
    try:
        check_gold(conn, medallion_cfg)

        def execute(sql: str):
            cur = conn.execute(sql)
            return [d[0] for d in cur.description], [tuple(r) for r in cur.fetchall()]

        return _run(sql_files(kpi_cfg["sql_dir"]), execute)
    finally:
        conn.close()


def row_counts(results: dict[str, Rows]) -> dict[str, int]:
    return {name: len(rows) for name, rows in results.items()}


def default_project() -> str | None:
    return os.getenv("GCP_PROJECT_ID")


def sqlite_available(db_path: str) -> bool:
    return os.path.exists(db_path)
