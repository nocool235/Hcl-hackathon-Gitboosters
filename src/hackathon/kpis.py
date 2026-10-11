"""Run every KPI SQL file, export a CSV each and write a Markdown report.

Engines: `bigquery` runs kpis/bigquery/*.sql against the gold dataset in BigQuery;
`sqlite` runs kpis/*.sql against the local gold database (offline, used by the tests).

Usage: python -m hackathon.kpis [--engine bigquery|sqlite]
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import sqlite3
from collections.abc import Callable
from pathlib import Path

from hackathon.config import DEFAULT_CONFIG, load_config
from hackathon.logging_setup import setup_logging

log = logging.getLogger("hackathon.kpis")

DEFAULTS = {
    "engine": "bigquery",
    "sql_dir": "kpis",
    "bq_sql_dir": "kpis/bigquery",
    "bq_dataset": "shopsphere_gold",
    "sql_output_dir": "outputs/kpis",
    "report_path": "reports/kpi_report.md",
    "head_rows": 10,
}
DEFAULT_DB = "data/processed/shopsphere.db"
DEFAULT_MAX_BYTES = 1_000_000_000
CONFIG_PARAMS = ("return_rate_min_volume", "payment_tolerance", "repeat_window_days")
QUERY_PARAM_TYPES = {
    "return_rate_min_volume": "INT64",
    "payment_tolerance": "FLOAT64",
    "repeat_window_days": "INT64",
    "reference_date": "DATE",
}
PARAM_DEFAULTS = {
    "return_rate_min_volume": 10,
    "payment_tolerance": 1.0,
    "repeat_window_days": 90,
    "reference_date": None,
}

Executor = Callable[[str], tuple[list[str], list[tuple]]]


def read_header(sql: str) -> tuple[str, list[tuple[str, str]]]:
    """Leading `--` lines: title first, then `Label: text` entries; indented lines continue one."""
    title, entries = "", []
    for line in sql.splitlines():
        if not line.startswith("--"):
            break
        text = line[2:]
        if not text.strip():
            continue
        if not title:
            title = text.strip()
        elif text.startswith("  ") and entries:
            label, body = entries[-1]
            entries[-1] = (label, f"{body} {text.strip()}")
        else:
            label, _, body = text.strip().partition(": ")
            entries.append((label, body) if body else ("", label))
    return title, entries


def sql_files(sql_dir: str | Path) -> list[Path]:
    files = sorted(Path(sql_dir).glob("*.sql"))
    if not files:
        raise FileNotFoundError(f"no .sql files in {sql_dir}")
    return files


def query_params(medallion_cfg: dict, overrides: dict | None = None) -> dict:
    """KPI thresholds: overrides, then config `medallion:` values, then defaults."""
    params = {k: medallion_cfg.get(k, v) for k, v in PARAM_DEFAULTS.items()}
    params.update({k: v for k, v in (overrides or {}).items() if k in PARAM_DEFAULTS})
    return params


# --- BigQuery -------------------------------------------------------------------------------

def run_bigquery(client, sql: str, dataset: str, params: dict,
                 max_bytes_billed: int = DEFAULT_MAX_BYTES):
    """Run one KPI query; unqualified table names resolve against `dataset`. Returns the job."""
    from google.cloud import bigquery

    job_config = bigquery.QueryJobConfig(
        default_dataset=f"{client.project}.{dataset}",
        query_parameters=[bigquery.ScalarQueryParameter(name, kind, params.get(name))
                          for name, kind in QUERY_PARAM_TYPES.items()],
        maximum_bytes_billed=max_bytes_billed,
    )
    job = client.query(sql, job_config=job_config)
    job.result()
    return job


def bigquery_executor(client, dataset: str, params: dict, max_bytes_billed: int) -> Executor:
    def execute(sql: str) -> tuple[list[str], list[tuple]]:
        result = run_bigquery(client, sql, dataset, params, max_bytes_billed).result()
        return [f.name for f in result.schema], [tuple(row.values()) for row in result]
    return execute


def run_bigquery_kpis(dataset: str, sql_dir: str | Path, output_dir: str | Path,
                      report_path: str | Path, params: dict, head_rows: int = 10,
                      max_bytes_billed: int = DEFAULT_MAX_BYTES, client=None) -> dict[str, int]:
    from hackathon.stages.bigquery import get_client

    client = client or get_client()
    loaded = client.get_table(f"{client.project}.{dataset}.fact_orders").modified
    intro = [
        f"Run on BigQuery dataset `{client.project}.{dataset}` "
        f"(gold last loaded {loaded:%Y-%m-%d %H:%M} UTC).",
        "Parameters: " + ", ".join(f"`{k}` = {params[k]}" for k in QUERY_PARAM_TYPES)
        + " (`reference_date` None = latest order date).",
    ]
    return export_kpis(sql_files(sql_dir), bigquery_executor(client, dataset, params,
                                                             max_bytes_billed),
                       output_dir, report_path, head_rows, intro)


# --- SQLite ---------------------------------------------------------------------------------

def open_gold(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"{path} not found; run `python -m hackathon.medallion` first")
    conn = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def check_gold(conn: sqlite3.Connection, medallion_cfg: dict) -> tuple[dict, dict]:
    """Refuse to run on a failed build; warn when config has changed since gold was built."""
    run = conn.execute(
        "SELECT run_id, batch_id, status, finished_at FROM pipeline_runs "
        "ORDER BY started_at DESC LIMIT 1").fetchone()
    if run is None or run["status"] != "SUCCESS":
        raise RuntimeError("The latest pipeline run did not succeed, so gold is missing or stale; "
                           "run `python -m hackathon.medallion` first")
    params = {r["param"]: r["value"] for r in conn.execute("SELECT param, value FROM run_params")}
    stale = [k for k in CONFIG_PARAMS
             if k in medallion_cfg and float(medallion_cfg[k]) != float(params[k])]
    if medallion_cfg.get("reference_date") and str(medallion_cfg["reference_date"]) != params[
            "reference_date"]:
        stale.append("reference_date")
    if stale:
        log.warning("config differs from the last pipeline run for %s; KPIs use the run's values. "
                    "Rerun `python -m hackathon.medallion` to apply the config.", ", ".join(stale))
    return dict(run), params


def run_sqlite_kpis(db_path: str | Path, sql_dir: str | Path, output_dir: str | Path,
                    report_path: str | Path, head_rows: int = 10,
                    medallion_cfg: dict | None = None) -> dict[str, int]:
    files = sql_files(sql_dir)
    conn = open_gold(db_path)
    try:
        run, params = check_gold(conn, medallion_cfg or {})
        intro = [
            f"Run on the local SQLite gold tables of pipeline run `{run['run_id']}` "
            f"(batch `{run['batch_id']}`, finished {run['finished_at']}).",
            "Parameters from that run: "
            + ", ".join(f"`{k}` = {params[k]}" for k in ("reference_date", *CONFIG_PARAMS)) + ".",
        ]

        def execute(sql: str) -> tuple[list[str], list[tuple]]:
            cur = conn.execute(sql)
            return [d[0] for d in cur.description], [tuple(r) for r in cur.fetchall()]

        return export_kpis(files, execute, output_dir, report_path, head_rows, intro)
    finally:
        conn.close()


# --- Export and report ----------------------------------------------------------------------

def write_csv(path: Path, columns: list[str], rows: list[tuple]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        writer.writerows(rows)


def md_escape(text: str) -> str:
    return text.replace("*", "\\*")


def _cell(value) -> str:
    return "" if value is None else str(value).replace("|", "\\|")


def markdown_table(columns: list[str], rows: list[tuple]) -> str:
    lines = ["| " + " | ".join(columns) + " |", "|" + "---|" * len(columns)]
    lines += ["| " + " | ".join(_cell(v) for v in row) + " |" for row in rows]
    return "\n".join(lines)


def render_section(sql_path: Path, csv_path: Path, report_dir: Path, columns: list[str],
                   rows: list[tuple], head_rows: int) -> str:
    title, entries = read_header(sql_path.read_text(encoding="utf-8"))
    sql_link = Path(os.path.relpath(sql_path, report_dir)).as_posix()
    csv_link = Path(os.path.relpath(csv_path, report_dir)).as_posix()
    parts = [f"## {title or sql_path.stem}", "",
             f"SQL: [{sql_path.name}]({sql_link}) · Output: [{csv_path.name}]({csv_link})"
             f" · Rows: {len(rows)}", ""]
    parts += [f"- **{label}:** {md_escape(body)}" if label else f"- {md_escape(body)}"
              for label, body in entries]
    shown = min(head_rows, len(rows))
    heading = f"**Result (first {shown} of {len(rows)} rows)**" if rows else "**Result: no rows**"
    parts += ["", heading]
    if rows:
        parts += ["", markdown_table(columns, rows[:head_rows])]
    return "\n".join(parts)


def export_kpis(files: list[Path], execute: Executor, output_dir: str | Path,
                report_path: str | Path, head_rows: int, intro: list[str]) -> dict[str, int]:
    output_dir, report_path = Path(output_dir), Path(report_path)
    sections, counts = [], {}
    for sql_path in files:
        try:
            columns, rows = execute(sql_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise RuntimeError(f"{sql_path.name}: {exc}") from exc
        csv_path = output_dir / f"{sql_path.stem}.csv"
        write_csv(csv_path, columns, rows)
        sections.append(render_section(sql_path, csv_path, report_path.parent, columns, rows,
                                       head_rows))
        counts[sql_path.stem] = len(rows)
        log.info("%s: %d rows -> %s", sql_path.stem, len(rows), csv_path)

    header = ["# KPI report", "", *intro, "",
              "Each section's definition, inclusions and exclusions come from the comment "
              "header of its SQL file. Regenerate with `python -m hackathon.kpis`."]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(header) + "\n\n" + "\n\n".join(sections) + "\n",
                           encoding="utf-8")
    log.info("report -> %s", report_path)
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the KPI SQL files against the gold tables")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--engine", choices=["bigquery", "sqlite"], help="Overrides kpis.engine")
    parser.add_argument("--bq-dataset", help="Overrides kpis.bq_dataset")
    parser.add_argument("--db-path", help="Overrides kpis.db_path / medallion.db_path")
    parser.add_argument("--sql-dir", help="Overrides kpis.sql_dir or kpis.bq_sql_dir")
    parser.add_argument("--output-dir", help="Overrides kpis.sql_output_dir")
    parser.add_argument("--report-path", help="Overrides kpis.report_path")
    args = parser.parse_args(argv)

    setup_logging()
    cfg = load_config(args.config)
    medallion_cfg = cfg.get("medallion", {})
    kpi_cfg = {**DEFAULTS, **(cfg.get("kpis") or {})}
    engine = args.engine or kpi_cfg["engine"]
    output_dir = args.output_dir or kpi_cfg["sql_output_dir"]
    report_path = args.report_path or kpi_cfg["report_path"]
    head_rows = int(kpi_cfg["head_rows"])
    if engine == "bigquery":
        counts = run_bigquery_kpis(
            dataset=args.bq_dataset or kpi_cfg["bq_dataset"],
            sql_dir=args.sql_dir or kpi_cfg["bq_sql_dir"],
            output_dir=output_dir,
            report_path=report_path,
            params=query_params(medallion_cfg),
            head_rows=head_rows,
            max_bytes_billed=int((cfg.get("bigquery") or {}).get("max_bytes_billed")
                                 or DEFAULT_MAX_BYTES),
        )
    else:
        counts = run_sqlite_kpis(
            db_path=args.db_path or kpi_cfg.get("db_path")
            or medallion_cfg.get("db_path", DEFAULT_DB),
            sql_dir=args.sql_dir or kpi_cfg["sql_dir"],
            output_dir=output_dir,
            report_path=report_path,
            head_rows=head_rows,
            medallion_cfg=medallion_cfg,
        )
    for name, n in counts.items():
        print(f"{name:42} {n:5} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
