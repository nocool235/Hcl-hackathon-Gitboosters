"""Bronze layer: copy each source file exactly as received, plus lineage columns."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from hackathon.medallion import db

SOURCES = {
    "customers": ("customers.csv", [
        "customer_id", "first_name", "last_name", "email", "phone", "address_line1", "city",
        "state", "zip_code", "country", "signup_date", "customer_segment", "is_active"]),
    "suppliers": ("suppliers.json", [
        "supplier_id", "supplier_name", "country", "rating", "contract_start_date",
        "is_preferred"]),
    "products": ("products.csv", [
        "product_id", "product_name", "category", "sub_category", "unit_price", "cost_price",
        "supplier_id", "is_active", "launch_date"]),
    "orders": ("orders.csv", [
        "order_id", "customer_id", "order_date", "order_status", "payment_method", "channel",
        "promo_code", "shipping_city"]),
    "order_items": ("order_items.csv", [
        "order_item_id", "order_id", "product_id", "quantity", "unit_price", "discount_pct",
        "line_total"]),
    "payments": ("payments.csv", [
        "payment_id", "order_id", "payment_date", "amount", "payment_status", "payment_method"]),
    "returns": ("returns.csv", [
        "return_id", "order_item_id", "return_date", "return_reason", "refund_amount",
        "return_status"]),
}
LINEAGE = ["_source_file", "_row_number", "_batch_id", "_loaded_at"]


def _read_csv(path: Path) -> tuple[list[str], list[dict]]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        columns = list(reader.fieldnames or [])
        rows = [{c: (r.get(c) or "") for c in columns} for r in reader]
    return columns, rows


def _read_json(path: Path) -> tuple[list[str], list[dict]]:
    with open(path, encoding="utf-8-sig") as f:
        records = json.load(f)
    columns: list[str] = []
    for rec in records:
        columns += [k for k in rec if k not in columns]
    rows = [{c: ("" if rec.get(c) is None else str(rec[c])) for c in columns} for rec in records]
    return columns, rows


def read_sources(input_dir: str | Path) -> dict[str, tuple[list[str], list[dict]]]:
    """Read every source file as text. Returns {entity: (columns, rows)}; nothing is cleaned."""
    out = {}
    for entity, (filename, _required) in SOURCES.items():
        path = Path(input_dir) / filename
        reader = _read_json if path.suffix == ".json" else _read_csv
        out[entity] = reader(path)
    return out


def add_lineage(entity: str, rows: list[dict], batch_id: str, loaded_at: str) -> list[dict]:
    filename = SOURCES[entity][0]
    return [
        {**r, "_source_file": filename, "_row_number": i, "_batch_id": batch_id,
         "_loaded_at": loaded_at}
        for i, r in enumerate(rows, start=1)
    ]


def write_bronze(conn, sources: dict, batch_id: str) -> dict[str, list[dict]]:
    loaded_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    bronze, log = {}, []
    for entity, (columns, rows) in sources.items():
        bronze[entity] = add_lineage(entity, rows, batch_id, loaded_at)
        db.write_table(conn, f"bronze_{entity}", columns + LINEAGE, bronze[entity])
        log.append({"entity": entity, "source_file": SOURCES[entity][0], "row_count": len(rows),
                    "batch_id": batch_id, "loaded_at": loaded_at})
    db.write_table(
        conn, "bronze_load_log",
        ["entity", "source_file", "row_count", "batch_id", "loaded_at"], log,
    )
    return bronze
