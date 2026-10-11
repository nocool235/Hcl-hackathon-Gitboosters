"""Run the whole medallion pipeline: bronze -> silver -> gates -> gold, with an audit log."""

from __future__ import annotations

import argparse
import json
import logging
import uuid
from datetime import datetime, timezone

from hackathon.config import DEFAULT_CONFIG, load_config
from hackathon.logging_setup import setup_logging
from hackathon.medallion import bronze, db, gold, quality, silver

log = logging.getLogger("hackathon.medallion")

DEFAULTS = {
    "input_dir": "data/raw/Ecommerce_Analytics_SourceData/Ecommerce_Analytics_SourceData",
    "db_path": "data/processed/shopsphere.db",
    "batch_id": "batch_001",
    "reference_date": None,
    "return_rate_min_volume": 10,
    "payment_tolerance": 1.00,
    "repeat_window_days": 90,
}
RUN_COLUMNS = ["run_id", "batch_id", "status", "started_at", "finished_at", "row_counts", "error"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _start_run(conn, run_id: str, batch_id: str) -> None:
    conn.execute(
        'CREATE TABLE IF NOT EXISTS pipeline_runs (run_id TEXT, batch_id TEXT, status TEXT, '
        'started_at TEXT, finished_at TEXT, row_counts TEXT, error TEXT)')
    conn.execute("INSERT INTO pipeline_runs VALUES (?,?,?,?,?,?,?)",
                 (run_id, batch_id, "RUNNING", _now(), None, None, None))
    conn.commit()


def _finish_run(conn, run_id: str, status: str, counts: dict, error: str | None) -> None:
    conn.execute(
        "UPDATE pipeline_runs SET status=?, finished_at=?, row_counts=?, error=? WHERE run_id=?",
        (status, _now(), json.dumps(counts, sort_keys=True), error, run_id))
    conn.commit()


def run_pipeline(**overrides) -> dict:
    """Run end to end. Raises GateFailure if a gate fails (no gold is built in that case)."""
    params = {**DEFAULTS, **{k: v for k, v in overrides.items() if v is not None}}
    conn = db.connect(params["db_path"])
    run_id = uuid.uuid4().hex[:12]
    _start_run(conn, run_id, params["batch_id"])
    counts: dict = {}
    gate_results: list[dict] = []
    try:
        db.reset_database(conn)  # drops gold too, so a failed run can never leave stale gold

        sources = bronze.read_sources(params["input_dir"])
        gate_results += [quality.schema_gate(e, cols, bronze.SOURCES[e][1])
                         for e, (cols, _rows) in sources.items()]
        _write_gates(conn, run_id, gate_results)
        quality.enforce(gate_results)

        bronze_rows = bronze.write_bronze(conn, sources, params["batch_id"])
        silver_rows, quarantine_rows, stats = silver.build_silver(bronze_rows)
        for entity in silver_rows:
            db.write_table(conn, f"silver_{entity}", silver.silver_columns(entity),
                           silver_rows[entity], primary_key=silver.KEYS[entity])
            db.write_table(conn, f"quarantine_{entity}", silver.QUARANTINE_COLUMNS,
                           quarantine_rows[entity])
        counts["entities"] = stats
        db.write_table(
            conn,
            "quality_issues",
            ["run_id", *quality.ISSUE_COLUMNS],
            [{"run_id": run_id, **row}
             for row in quality.issue_rows(silver_rows, quarantine_rows)],
        )

        gate_results += quality.reconciliation_gates(stats)
        gate_results += quality.unique_key_gates(silver_rows, silver.KEYS)
        gate_results.append(quality.positive_quantity_gate(silver_rows))
        _write_gates(conn, run_id, gate_results)
        quality.enforce(gate_results)

        gold_rows = gold.build_gold(silver_rows)
        gate_results += quality.gold_gates(gold_rows, silver_rows)
        _write_gates(conn, run_id, gate_results)
        quality.enforce(gate_results)

        for name, rows in gold_rows.items():
            primary_keys = {
                "dim_customer": "customer_key", "dim_supplier": "supplier_key",
                "dim_product": "product_key", "dim_date": "date_key",
                "fact_orders": "order_id", "fact_order_items": "order_item_id",
                "fact_payments": "payment_id", "fact_returns": "return_id",
            }
            foreign_keys = {
                "dim_product": [("supplier_key", "dim_supplier", "supplier_key")],
                "fact_orders": [("customer_key", "dim_customer", "customer_key"),
                                ("order_date_key", "dim_date", "date_key")],
                "fact_order_items": [("product_key", "dim_product", "product_key"),
                                     ("order_date_key", "dim_date", "date_key")],
                "fact_payments": [("payment_date_key", "dim_date", "date_key")],
                "fact_returns": [("product_key", "dim_product", "product_key"),
                                 ("return_date_key", "dim_date", "date_key")],
            }
            db.write_table(
                conn, name, gold.GOLD_COLUMNS[name], rows,
                primary_key=primary_keys[name], foreign_keys=foreign_keys.get(name),
            )
        counts["gold"] = {name: len(rows) for name, rows in gold_rows.items()}
        _write_params(conn, params, silver_rows)
        _finish_run(conn, run_id, "SUCCESS", counts, None)
        return {"run_id": run_id, "counts": counts, "gates": gate_results}
    except Exception as exc:
        _finish_run(conn, run_id, "FAILED", counts, f"{type(exc).__name__}: {exc}")
        raise
    finally:
        conn.close()


def _write_gates(conn, run_id: str, results: list[dict]) -> None:
    rows = [{"run_id": run_id, **r} for r in results]
    db.write_table(conn, "quality_gate_results",
                   ["run_id", "gate", "entity", "passed", "detail"], rows)


def _write_params(conn, params: dict, silver_rows: dict) -> None:
    reference = params["reference_date"] or max(r["order_date"] for r in silver_rows["orders"])
    values = {**params, "reference_date": reference}
    db.write_table(conn, "run_params", ["param", "value"],
                   [{"param": k, "value": str(v)} for k, v in sorted(values.items())])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the ShopSphere medallion pipeline")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--input-dir")
    parser.add_argument("--db-path")
    parser.add_argument("--batch-id")
    parser.add_argument("--reference-date", help="YYYY-MM-DD; default = latest order date")
    parser.add_argument("--return-rate-min-volume", type=int)
    parser.add_argument("--payment-tolerance", type=float)
    parser.add_argument("--repeat-window-days", type=int)
    parser.add_argument("--bq-dataset", help="Also load gold into this BigQuery dataset")
    parser.add_argument("--bq-location", help="BigQuery dataset location (default US)")
    args = parser.parse_args(argv)

    setup_logging()
    cfg = load_config(args.config).get("medallion", {})
    cli = {k: v for k, v in vars(args).items() if k != "config" and v is not None}
    merged = {**cfg, **cli}
    bq_dataset = merged.pop("bq_dataset", None)
    bq_location = merged.pop("bq_location", None) or "US"
    try:
        result = run_pipeline(**merged)
    except quality.GateFailure as exc:
        log.error("quality gate failed, gold not built: %s", exc)
        return 1
    for entity, s in result["counts"]["entities"].items():
        print(f"{entity:12} bronze={s['bronze']:4} silver={s['silver']:4} "
              f"quarantine={s['quarantine']:3} {s['reasons']}")
    print("gold:", result["counts"]["gold"])

    if bq_dataset:
        from hackathon.medallion.bq_load import load_gold

        db_path = merged.get("db_path", DEFAULTS["db_path"])
        try:
            loaded = load_gold(db_path, bq_dataset, location=bq_location)
        except Exception as exc:
            log.error("BigQuery load failed (local run is fine): %s", exc)
            return 2
        print("bigquery:", loaded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
