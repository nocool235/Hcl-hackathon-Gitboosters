"""Optional: load the gold tables from SQLite into a BigQuery dataset.

Only called when --bq-dataset is given, after the local run succeeded (so gates have passed).
Needs Application Default Credentials: `gcloud auth application-default login`.
"""

from __future__ import annotations

import logging

from hackathon.medallion import db
from hackathon.medallion.gold import GOLD_COLUMNS

log = logging.getLogger("hackathon.medallion.bq")

DATE_COLUMNS = {
    "date",
    "order_date",
    "payment_date",
    "return_date",
    "signup_date",
    "valid_from",
    "valid_to",
    "contract_start_date",
    "launch_date",
}
NUMERIC_COLUMNS = {
    "unit_price",
    "cost_price",
    "discount_pct",
    "line_total",
    "source_line_total",
    "amount",
    "refund_amount",
    "returned_quantity",
    "rating_raw",
    "rating_norm",
}
INT_COLUMNS = {"quantity", "year", "quarter", "month", "day", "rating_scale_max"}
BOOL_COLUMNS = {
    "is_active",
    "is_preferred",
    "is_current",
    "is_weekend",
    "line_total_mismatch",
    "refund_exceeds_line",
    "return_before_order",
    "signup_date_ambiguous",
    "signup_date_missing",
    "launch_date_ambiguous",
    "order_date_ambiguous",
    "order_before_signup",
    "order_before_product_launch",
    "payment_date_ambiguous",
    "payment_date_missing",
    "payment_before_order",
}


def bq_type(column: str) -> str:
    """Explicit type per column name, so BigQuery never guesses (dates are real DATEs)."""
    if column in DATE_COLUMNS:
        return "DATE"
    if column in NUMERIC_COLUMNS:
        return "NUMERIC"
    if column in BOOL_COLUMNS or column.startswith("is_orphan_"):
        return "BOOL"
    if column in INT_COLUMNS or column.endswith("_key"):
        return "INT64"
    return "STRING"


def schema_for(table: str) -> list[tuple[str, str]]:
    return [(c, bq_type(c)) for c in GOLD_COLUMNS[table]]


def convert_row(row: dict, schema: list[tuple[str, str]]) -> dict:
    """SQLite stores flags as 0/1; BigQuery BOOL needs true/false. NULLs stay NULL."""
    out = {}
    for column, kind in schema:
        value = row.get(column)
        out[column] = bool(value) if kind == "BOOL" and value is not None else value
    return out


def load_gold(
    db_path: str, dataset: str, project: str | None = None, location: str = "US", client=None
) -> dict[str, int]:
    """Load every gold table into `dataset` (WRITE_TRUNCATE, so reruns do not duplicate)."""
    from google.cloud import bigquery  # imported here so the core pipeline never needs it

    from hackathon.stages.bigquery import get_client

    client = client or get_client(project)
    dataset_ref = bigquery.Dataset(f"{client.project}.{dataset}")
    dataset_ref.location = location
    client.create_dataset(dataset_ref, exists_ok=True)

    conn = db.connect(db_path)
    loaded = {}
    try:
        for table in GOLD_COLUMNS:
            schema = schema_for(table)
            rows = [convert_row(r, schema) for r in db.read_rows(conn, table)]
            job_config = bigquery.LoadJobConfig(
                schema=[bigquery.SchemaField(name, kind) for name, kind in schema],
                write_disposition="WRITE_TRUNCATE",
            )
            target = f"{client.project}.{dataset}.{table}"
            client.load_table_from_json(rows, target, job_config=job_config).result()
            loaded[table] = len(rows)
            log.info("loaded %s: %d rows", target, len(rows))
    finally:
        conn.close()
    return loaded
