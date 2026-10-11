"""Gold layer: star schema built from silver. Built in memory first; written only if gates pass."""

from __future__ import annotations

import calendar
import hashlib
from datetime import date, timedelta

UNKNOWN_KEY = -1
OPEN_START, OPEN_END = "1900-01-01", "9999-12-31"

GOLD_COLUMNS = {
    "dim_customer": ["customer_key", "customer_id", "first_name", "last_name", "email", "phone",
                     "address_line1", "city", "state", "zip_code", "country", "signup_date",
                     "customer_segment", "is_active", "dup_group_id", "valid_from", "valid_to",
                     "is_current"],
    "dim_supplier": ["supplier_key", "supplier_id", "supplier_name", "country", "rating_raw",
                     "rating_scale_max", "rating_norm", "contract_start_date", "is_preferred"],
    "dim_product": ["product_key", "product_id", "product_name", "category", "sub_category",
                    "unit_price", "cost_price", "supplier_key", "supplier_id", "is_active",
                    "launch_date", "price_issue"],
    "dim_date": ["date_key", "date", "year", "quarter", "month", "month_name", "year_month",
                 "day", "day_of_week", "is_weekend"],
    "fact_orders": ["order_id", "customer_key", "customer_id_source", "order_date_key",
                    "order_date", "order_status", "channel", "payment_method", "promo_code",
                    "shipping_city", "is_orphan_customer"],
    "fact_order_items": ["order_item_id", "order_id", "product_key", "product_id_source",
                         "order_date_key", "quantity", "unit_price", "discount_pct",
                         "line_total", "source_line_total", "line_total_mismatch",
                         "is_orphan_order", "is_orphan_product"],
    "fact_payments": ["payment_id", "order_id", "payment_date_key", "payment_date", "amount",
                      "payment_status", "payment_method", "is_orphan_order"],
    "fact_returns": ["return_id", "order_item_id", "order_id", "product_key", "return_date_key",
                     "return_date", "return_reason", "return_status", "refund_amount",
                     "returned_quantity", "returned_quantity_basis", "refund_exceeds_line",
                     "return_before_order", "is_orphan_item"],
}


def surrogate_key(kind: str, natural: str) -> int:
    """Same input -> same key on every run (a hash, not a counter)."""
    return int(hashlib.sha1(f"{kind}|{natural}".encode()).hexdigest()[:12], 16)


def date_key(iso: str | None) -> int | None:
    return int(iso.replace("-", "")) if iso else None


def _pick(row: dict, columns: list[str]) -> dict:
    return {c: row.get(c) for c in columns}


def build_dim_date(silver: dict) -> list[dict]:
    days = [r["order_date"] for r in silver["orders"]]
    days += [r["payment_date"] for r in silver["payments"] if r["payment_date"]]
    days += [r["return_date"] for r in silver["returns"]]
    if not days:
        return []
    first, last = date.fromisoformat(min(days)), date.fromisoformat(max(days))
    first = first.replace(day=1)
    last = last.replace(day=calendar.monthrange(last.year, last.month)[1])
    rows, d = [], first
    while d <= last:
        rows.append({"date_key": int(d.strftime("%Y%m%d")), "date": d.isoformat(),
                     "year": d.year, "quarter": (d.month - 1) // 3 + 1, "month": d.month,
                     "month_name": d.strftime("%B"), "year_month": d.strftime("%Y-%m"),
                     "day": d.day, "day_of_week": d.strftime("%A"),
                     "is_weekend": int(d.weekday() >= 5)})
        d += timedelta(days=1)
    return rows


def build_gold(silver: dict[str, list[dict]]) -> dict[str, list[dict]]:
    gold: dict[str, list[dict]] = {}

    # Dimensions. Each has an 'Unknown' member (key -1) so orphans can be kept and flagged.
    customers = []
    for r in silver["customers"]:
        key = surrogate_key("customer", f"{r['customer_id']}|{OPEN_START}")
        customers.append({**_pick(r, GOLD_COLUMNS["dim_customer"]), "customer_key": key,
                          "valid_from": OPEN_START, "valid_to": OPEN_END, "is_current": 1})
    customers.append({"customer_key": UNKNOWN_KEY, "customer_id": "UNKNOWN",
                      "customer_segment": "Unknown", "valid_from": OPEN_START,
                      "valid_to": OPEN_END, "is_current": 1})
    gold["dim_customer"] = customers

    suppliers = [{**_pick(r, GOLD_COLUMNS["dim_supplier"]),
                  "supplier_key": surrogate_key("supplier", r["supplier_id"])}
                 for r in silver["suppliers"]]
    suppliers.append({"supplier_key": UNKNOWN_KEY, "supplier_id": "UNKNOWN",
                      "supplier_name": "Unknown"})
    gold["dim_supplier"] = suppliers

    supplier_key = {r["supplier_id"]: r["supplier_key"] for r in suppliers}
    products = [{**_pick(r, GOLD_COLUMNS["dim_product"]),
                 "product_key": surrogate_key("product", r["product_id"]),
                 "supplier_key": supplier_key.get(r["supplier_id"], UNKNOWN_KEY)}
                for r in silver["products"]]
    products.append({"product_key": UNKNOWN_KEY, "product_id": "UNKNOWN",
                     "product_name": "Unknown", "category": "Unknown",
                     "supplier_key": UNKNOWN_KEY})
    gold["dim_product"] = products
    gold["dim_date"] = build_dim_date(silver)

    for name in ("dim_customer", "dim_supplier", "dim_product"):
        keys = [r[f"{name[4:]}_key"] for r in gold[name]]
        if len(keys) != len(set(keys)):
            raise RuntimeError(f"surrogate key collision in {name}")

    customer_key = {r["customer_id"]: r["customer_key"] for r in customers if r["is_current"]}
    product_key = {r["product_id"]: r["product_key"] for r in products}
    order_date = {r["order_id"]: r["order_date"] for r in silver["orders"]}
    items = {r["order_item_id"]: r for r in silver["order_items"]}

    # Facts
    gold["fact_orders"] = [
        {**_pick(r, GOLD_COLUMNS["fact_orders"]),
         "customer_key": customer_key.get(r["customer_id"], UNKNOWN_KEY),
         "customer_id_source": r["customer_id"], "order_date_key": date_key(r["order_date"])}
        for r in silver["orders"]]

    gold["fact_order_items"] = [
        {**_pick(r, GOLD_COLUMNS["fact_order_items"]),
         "product_key": product_key.get(r["product_id"], UNKNOWN_KEY),
         "product_id_source": r["product_id"],
         "order_date_key": date_key(order_date.get(r["order_id"]))}
        for r in silver["order_items"]]

    gold["fact_payments"] = [
        {**_pick(r, GOLD_COLUMNS["fact_payments"]),
         "payment_date_key": date_key(r["payment_date"])}
        for r in silver["payments"]]

    returns = []
    for r in silver["returns"]:
        item = items.get(r["order_item_id"])
        qty, basis = None, "UNKNOWN"
        if item and r["refund_amount"] is not None and item["line_total"] > 0:
            if r["refund_amount"] >= item["line_total"] - 0.01:
                qty, basis = float(item["quantity"]), "FULL"
            else:
                qty = round(item["quantity"] * r["refund_amount"] / item["line_total"], 4)
                basis = "PROPORTIONAL"
        returns.append({
            **_pick(r, GOLD_COLUMNS["fact_returns"]),
            "order_id": item["order_id"] if item else None,
            "product_key": product_key.get(item["product_id"], UNKNOWN_KEY) if item else None,
            "return_date_key": date_key(r["return_date"]),
            "returned_quantity": qty, "returned_quantity_basis": basis})
    gold["fact_returns"] = returns
    return gold
