"""Quality gates. Each gate returns result dicts; `enforce` stops the run if any failed."""

from __future__ import annotations


class GateFailure(Exception):
    """Raised when a quality gate fails; the run stops and no gold is built."""


ISSUE_COLUMNS = ["entity", "record_key", "source_row", "issue_code", "severity", "detail"]
ROW_FLAGS = {
    "signup_date_ambiguous", "signup_date_missing", "dup_group_id", "launch_date_ambiguous",
    "category_inferred",
    "is_orphan_supplier", "order_date_ambiguous", "is_orphan_customer", "order_before_signup",
    "line_total_mismatch", "is_orphan_order", "is_orphan_product",
    "order_before_product_launch", "payment_date_ambiguous", "payment_date_missing",
    "payment_before_order", "is_orphan_item", "refund_exceeds_line", "return_before_order",
}


def _result(gate: str, entity: str, passed: bool, detail: str = "") -> dict:
    return {"gate": gate, "entity": entity, "passed": int(passed), "detail": detail}


def schema_gate(entity: str, columns: list[str], required: list[str]) -> dict:
    missing = [c for c in required if c not in columns]
    extra = [c for c in columns if c not in required]
    if missing:
        return _result("schema_drift", entity, False, f"missing columns: {missing}")
    detail = f"extra columns ignored: {extra}" if extra else "ok"
    return _result("schema_drift", entity, True, detail)


def reconciliation_gates(stats: dict) -> list[dict]:
    out = []
    for entity, s in stats.items():
        ok = s["bronze"] == s["silver"] + s["quarantine"]
        detail = f"bronze={s['bronze']} silver={s['silver']} quarantine={s['quarantine']}"
        out.append(_result("reconciliation", entity, ok, detail))
    return out


def unique_key_gates(silver: dict[str, list[dict]], keys: dict[str, str]) -> list[dict]:
    out = []
    for entity, key in keys.items():
        values = [r[key] for r in silver[entity]]
        dupes = len(values) - len(set(values))
        out.append(_result("unique_key", entity, dupes == 0, f"{key}: {dupes} duplicates"))
    return out


def positive_quantity_gate(silver: dict[str, list[dict]]) -> dict:
    bad = sum(1 for r in silver["order_items"] if r["quantity"] <= 0)
    return _result("positive_quantity", "order_items", bad == 0, f"{bad} non-positive rows")


def issue_rows(silver: dict[str, list[dict]], quarantine: dict[str, list[dict]]) -> list[dict]:
    """Flatten row-level flags and quarantine reasons into an auditable issue table."""
    key_by_entity = {
        "customers": "customer_id", "suppliers": "supplier_id", "products": "product_id",
        "orders": "order_id", "order_items": "order_item_id", "payments": "payment_id",
        "returns": "return_id",
    }
    issues = []
    for entity, rows in quarantine.items():
        for row in rows:
            issues.append({
                "entity": entity,
                "record_key": row.get("record_key"),
                "source_row": row.get("_row_number"),
                "issue_code": row.get("reason_code"),
                "severity": "ERROR",
                "detail": row.get("reason_detail"),
            })
    for entity, rows in silver.items():
        key = key_by_entity[entity]
        for row in rows:
            for flag, value in row.items():
                if flag not in ROW_FLAGS or not value:
                    continue
                issues.append({
                    "entity": entity,
                    "record_key": row.get(key),
                    "source_row": row.get("_row_number"),
                    "issue_code": flag.upper(),
                    "severity": "WARNING",
                    "detail": f"{flag}={value}",
                })
    return issues


def _fk_gate(child: str, col: str, rows: list[dict], parent_keys: set,
             allow_null: bool = False) -> dict:
    bad = sum(1 for r in rows if (r[col] is None and not allow_null) or
              (r[col] is not None and r[col] not in parent_keys))
    return _result("referential_integrity", f"{child}.{col}", bad == 0, f"{bad} unresolved")


def gold_gates(gold: dict[str, list[dict]], silver: dict[str, list[dict]]) -> list[dict]:
    out = []
    customer_keys = {r["customer_key"] for r in gold["dim_customer"]}
    product_keys = {r["product_key"] for r in gold["dim_product"]}
    supplier_keys = {r["supplier_key"] for r in gold["dim_supplier"]}
    date_keys = {r["date_key"] for r in gold["dim_date"]}
    order_ids = {r["order_id"] for r in gold["fact_orders"]}
    item_ids = {r["order_item_id"] for r in gold["fact_order_items"]}

    out.append(_fk_gate("fact_orders", "customer_key", gold["fact_orders"], customer_keys))
    out.append(_fk_gate("fact_orders", "order_date_key", gold["fact_orders"], date_keys))
    out.append(_fk_gate("fact_order_items", "product_key", gold["fact_order_items"], product_keys))
    out.append(_fk_gate(
        "fact_order_items", "order_date_key",
        [r for r in gold["fact_order_items"] if not r["is_orphan_order"]], date_keys,
    ))
    out.append(_fk_gate("fact_payments", "payment_date_key", gold["fact_payments"], date_keys,
                        allow_null=True))
    out.append(_fk_gate("fact_returns", "product_key", gold["fact_returns"], product_keys))
    out.append(_fk_gate("fact_returns", "return_date_key", gold["fact_returns"], date_keys))
    out.append(_fk_gate("dim_product", "supplier_key", gold["dim_product"], supplier_keys))

    # Orphans are flagged, not dropped: only non-orphan rows must resolve to a parent.
    for table, col, parents, flag in [
        ("fact_order_items", "order_id", order_ids, "is_orphan_order"),
        ("fact_payments", "order_id", order_ids, "is_orphan_order"),
        ("fact_returns", "order_item_id", item_ids, "is_orphan_item"),
    ]:
        rows = [r for r in gold[table] if not r[flag]]
        out.append(_fk_gate(table, col, rows, parents))

    pairs = [
        ("fact_orders", "orders", 0),
        ("fact_order_items", "order_items", 0),
        ("fact_payments", "payments", 0),
        ("fact_returns", "returns", 0),
        ("dim_customer", "customers", 1),
        ("dim_product", "products", 1),
        ("dim_supplier", "suppliers", 1),
    ]
    for gold_name, silver_name, extra in pairs:
        expected = len(silver[silver_name]) + extra
        actual = len(gold[gold_name])
        detail = f"{gold_name}={actual} expected={expected}"
        out.append(_result("row_count_match", gold_name, actual == expected, detail))
    return out


def enforce(results: list[dict]) -> None:
    failed = [r for r in results if not r["passed"]]
    if failed:
        msg = "; ".join(f"{r['gate']}[{r['entity']}]: {r['detail']}" for r in failed)
        raise GateFailure(msg)
