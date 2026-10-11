"""KPI calculations over the curated ShopSphere gold model.

The functions intentionally use the gold tables rather than rereading raw files. This keeps KPI
logic reproducible, makes every assumption testable, and allows the same calculations to run over
SQLite locally or over an equivalent warehouse model later.
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from collections import Counter, defaultdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from hackathon.config import DEFAULT_CONFIG, load_config

OUTPUT_NAMES = {
    "net_revenue_by_category_month": "kpi_01_net_revenue_by_category_month.csv",
    "top_customers_by_ltv": "kpi_02_top_customers_by_ltv.csv",
    "customer_segment_profile": "kpi_03_customer_segment_profile.csv",
    "mom_channel_growth": "kpi_04_mom_channel_growth.csv",
    "product_return_rate": "kpi_05_product_return_rate.csv",
    "supplier_scorecard": "kpi_06_supplier_scorecard.csv",
    "repeat_purchase_rate": "kpi_07_repeat_purchase_rate.csv",
    "payment_reconciliation": "kpi_08_payment_reconciliation.csv",
    "margin_risk": "kpi_09_margin_risk.csv",
}

ASSUMPTIONS = {
    "revenue": (
        "Completed orders only; line_total is the discounted sale amount; approved refunds "
        "are capped at the line amount and allocated to the sale month."
    ),
    "ltv": (
        "Completed orders with a known customer only; net lifetime value is discounted line "
        "revenue less approved refunds."
    ),
    "segment": (
        "Customer count uses the current cleansed customer dimension; average order value uses "
        "completed orders and discounted line totals."
    ),
    "channel_growth": (
        "Completed orders only; revenue is discounted line revenue and growth is compared with "
        "the immediately preceding calendar month."
    ),
    "return_rate": (
        "Approved returned quantity divided by ordered quantity; products must meet the "
        "configured minimum ordered-unit threshold."
    ),
    "supplier_score": (
        "Composite score = 50% revenue share + 30% inverse average return rate + 20% "
        "normalized supplier rating."
    ),
    "repeat_rate": (
        "A repeat customer has a second distinct completed order within the configured window "
        "after the first completed order."
    ),
    "payments": (
        "Successful payment rows are summed; the configured tolerance determines match, "
        "underpayment, and overpayment. Every cleansed order is reported."
    ),
    "margin": (
        "Effective selling price is unit_price after line discount; products are reported when "
        "cost_price exceeds that effective price."
    ),
}


def _decimal(value: Any) -> Decimal:
    return Decimal("0") if value is None else Decimal(str(value))


def _money(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _date(value: Any) -> date | None:
    return date.fromisoformat(value) if value else None


def _month(value: Any) -> str:
    parsed = _date(value)
    return parsed.strftime("%Y-%m") if parsed else "Unknown"


def _percent(numerator: Decimal, denominator: Decimal) -> float | None:
    if not denominator:
        return None
    return round(float(numerator / denominator * 100), 2)


def _read_tables(db_path: str | Path) -> dict[str, list[dict[str, Any]]]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        names = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'fact_%' "
                "OR name LIKE 'dim_%' OR name LIKE 'quarantine_%'"
            )
        ]
        return {
            name: [dict(row) for row in conn.execute(f'SELECT * FROM "{name}"')] for name in names
        }
    finally:
        conn.close()


def calculate_kpis(
    db_path: str | Path,
    return_rate_min_volume: int = 10,
    payment_tolerance: float = 1.0,
    repeat_window_days: int = 90,
    include_margin: bool = True,
) -> dict[str, list[dict[str, Any]]]:
    tables = _read_tables(db_path)
    orders = tables["fact_orders"]
    items = tables["fact_order_items"]
    returns = tables["fact_returns"]
    payments = tables["fact_payments"]
    customers = tables["dim_customer"]
    products = tables["dim_product"]
    suppliers = tables["dim_supplier"]

    order_by_id = {r["order_id"]: r for r in orders}
    item_by_id = {r["order_item_id"]: r for r in items}
    product_by_id = {r.get("product_id"): r for r in products if r.get("product_id")}
    customer_by_id = {
        r.get("customer_id"): r for r in customers if r.get("customer_id") != "UNKNOWN"
    }
    supplier_by_id = {
        r.get("supplier_id"): r for r in suppliers if r.get("supplier_id") != "UNKNOWN"
    }

    approved_returns_by_item: dict[str, Decimal] = defaultdict(Decimal)
    returned_qty_by_item: dict[str, Decimal] = defaultdict(Decimal)
    for row in returns:
        if row.get("return_status") != "Approved":
            continue
        item_id = row.get("order_item_id")
        if item_id not in item_by_id:
            continue
        line = _decimal(item_by_id[item_id].get("line_total"))
        approved_returns_by_item[item_id] += min(_decimal(row.get("refund_amount")), line)
        returned_qty_by_item[item_id] += _decimal(row.get("returned_quantity"))

    completed = {row["order_id"]: row for row in orders if row.get("order_status") == "Completed"}
    item_revenue: dict[str, Decimal] = {}
    for row in items:
        if row.get("order_id") in completed and not row.get("is_orphan_order"):
            item_revenue[row["order_item_id"]] = _decimal(row.get("line_total"))

    # 1. Net revenue by category and month.
    revenue = defaultdict(lambda: {"gross_revenue": Decimal("0"), "refunds": Decimal("0")})
    for row in items:
        if row["order_item_id"] not in item_revenue:
            continue
        product = product_by_id.get(row.get("product_id_source"), {})
        category = product.get("category") or "Unknown"
        key = (category, _month(order_by_id[row["order_id"]].get("order_date")))
        revenue[key]["gross_revenue"] += item_revenue[row["order_item_id"]]
        revenue[key]["refunds"] += approved_returns_by_item[row["order_item_id"]]
    net_revenue = [
        {
            "category": category,
            "month": month,
            "gross_revenue": _money(values["gross_revenue"]),
            "refunds": _money(values["refunds"]),
            "net_revenue": _money(values["gross_revenue"] - values["refunds"]),
        }
        for (category, month), values in sorted(revenue.items())
    ]

    # 2. Top 10 customer lifetime value.
    ltv = defaultdict(Decimal)
    for row in items:
        order = completed.get(row.get("order_id"))
        customer_id = order.get("customer_id_source") if order else None
        if not order or order.get("is_orphan_customer") or customer_id not in customer_by_id:
            continue
        ltv[customer_id] += (
            _decimal(row.get("line_total")) - approved_returns_by_item[row["order_item_id"]]
        )
    top_ltv = []
    for rank, (customer_id, value) in enumerate(
        sorted(ltv.items(), key=lambda pair: (-pair[1], pair[0]))[:10], 1
    ):
        customer = customer_by_id[customer_id]
        top_ltv.append(
            {
                "rank": rank,
                "customer_id": customer_id,
                "customer_name": (
                    f"{customer.get('first_name') or ''} {customer.get('last_name') or ''}"
                ).strip(),
                "customer_segment": customer.get("customer_segment"),
                "net_lifetime_value": _money(value),
            }
        )

    # 3. Customer segment profile.
    segment_customers = Counter(
        r.get("customer_segment") or "Unknown" for r in customer_by_id.values()
    )
    segment_orders: dict[str, dict[str, Decimal | set]] = defaultdict(
        lambda: {"value": Decimal("0"), "orders": set()}
    )
    for row in items:
        order = completed.get(row.get("order_id"))
        customer = customer_by_id.get(order.get("customer_id_source")) if order else None
        if not order or order.get("is_orphan_customer") or not customer:
            continue
        segment = customer.get("customer_segment") or "Unknown"
        segment_orders[segment]["value"] += _decimal(row.get("line_total"))
        segment_orders[segment]["orders"].add(order["order_id"])
    segments = sorted(set(segment_customers) | set(segment_orders))
    segment_profile = []
    for segment in segments:
        values = segment_orders[segment]
        segment_profile.append(
            {
                "customer_segment": segment,
                "customer_count": segment_customers[segment],
                "completed_order_count": len(values["orders"]),
                "average_order_value": _money(values["value"] / len(values["orders"]))
                if values["orders"]
                else None,
            }
        )

    # 4. Month-over-month volume and revenue by channel.
    channel_month: dict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {"orders": set(), "revenue": Decimal("0")}
    )
    for row in items:
        order = completed.get(row.get("order_id"))
        if not order:
            continue
        key = (order.get("channel") or "Unknown", _month(order.get("order_date")))
        channel_month[key]["orders"].add(order["order_id"])
        channel_month[key]["revenue"] += _decimal(row.get("line_total"))
    mom = []
    for channel in sorted({key[0] for key in channel_month}):
        months = sorted(month for ch, month in channel_month if ch == channel)
        by_month = {month: channel_month[(channel, month)] for month in months}
        for month in months:
            year, month_number = map(int, month.split("-"))
            previous_number = month_number - 1 or 12
            previous_year = year if month_number > 1 else year - 1
            previous = by_month.get(f"{previous_year:04d}-{previous_number:02d}")
            current = by_month[month]
            mom.append(
                {
                    "channel": channel,
                    "month": month,
                    "order_count": len(current["orders"]),
                    "revenue": _money(current["revenue"]),
                    "order_volume_growth_pct": _percent(
                        Decimal(len(current["orders"])) - Decimal(len(previous["orders"]))
                        if previous
                        else Decimal("0"),
                        Decimal(len(previous["orders"])) if previous else Decimal("0"),
                    )
                    if previous
                    else None,
                    "revenue_growth_pct": _percent(
                        current["revenue"] - previous["revenue"], previous["revenue"]
                    )
                    if previous
                    else None,
                }
            )

    # 5. Product return rates.
    product_volume: dict[str, Decimal] = defaultdict(Decimal)
    product_returns: dict[str, Decimal] = defaultdict(Decimal)
    for row in items:
        product_id = row.get("product_id_source")
        if not product_id or row.get("is_orphan_product"):
            continue
        product_volume[product_id] += _decimal(row.get("quantity"))
        product_returns[product_id] += returned_qty_by_item[row["order_item_id"]]
    return_rates = []
    for product_id, volume in product_volume.items():
        if volume < return_rate_min_volume:
            continue
        product = product_by_id.get(product_id, {})
        returned = product_returns[product_id]
        return_rates.append(
            {
                "product_id": product_id,
                "product_name": product.get("product_name"),
                "ordered_quantity": int(volume),
                "returned_quantity": float(returned),
                "return_rate_pct": _percent(returned, volume),
            }
        )
    return_rates.sort(key=lambda row: (-row["return_rate_pct"], row["product_id"]))
    for rank, row in enumerate(return_rates, 1):
        row["rank_high_to_low"] = rank
    selected = return_rates[:10]
    selected_ids = {row["product_id"] for row in selected}
    selected += [row for row in return_rates[-10:] if row["product_id"] not in selected_ids]
    product_return_output = [
        {**row, "ranking": "TOP_10" if index < 10 else "BOTTOM_10"}
        for index, row in enumerate(selected)
    ]

    # 6. Supplier scorecard.
    supplier_revenue = defaultdict(Decimal)
    supplier_product_stats: dict[str, dict[str, dict[str, Decimal]]] = defaultdict(
        lambda: defaultdict(lambda: {"volume": Decimal("0"), "returned": Decimal("0")})
    )
    for row in items:
        product_id = row.get("product_id_source")
        product = product_by_id.get(product_id)
        order = completed.get(row.get("order_id"))
        if not product or not order or row.get("is_orphan_product"):
            continue
        supplier_id = product.get("supplier_id")
        if supplier_id not in supplier_by_id:
            continue
        supplier_revenue[supplier_id] += _decimal(row.get("line_total"))
        supplier_product_stats[supplier_id][product_id]["volume"] += _decimal(row.get("quantity"))
        supplier_product_stats[supplier_id][product_id]["returned"] += returned_qty_by_item[
            row["order_item_id"]
        ]
    revenue_total = sum(supplier_revenue.values(), Decimal("0"))
    scorecard = []
    for supplier_id, supplier in supplier_by_id.items():
        rates = [
            stats["returned"] / stats["volume"]
            for stats in supplier_product_stats[supplier_id].values()
            if stats["volume"]
        ]
        average_rate = sum(rates, Decimal("0")) / len(rates) if rates else Decimal("0")
        revenue_share = (
            supplier_revenue[supplier_id] / revenue_total if revenue_total else Decimal("0")
        )
        quality = _decimal(supplier.get("rating_norm"))
        composite = (
            Decimal("0.5") * revenue_share
            + Decimal("0.3") * (Decimal("1") - min(average_rate, Decimal("1")))
            + Decimal("0.2") * quality
        ) * 100
        scorecard.append(
            {
                "supplier_id": supplier_id,
                "supplier_name": supplier.get("supplier_name"),
                "revenue": _money(supplier_revenue[supplier_id]),
                "revenue_share_pct": round(float(revenue_share * 100), 2),
                "average_product_return_rate_pct": round(float(average_rate * 100), 2),
                "rating_norm": float(quality),
                "composite_score": round(float(composite), 2),
            }
        )
    scorecard.sort(key=lambda row: (-row["composite_score"], row["supplier_id"]))

    # 7. Repeat purchase rate.
    customer_orders: dict[str, list[date]] = defaultdict(list)
    for order in completed.values():
        customer_id = order.get("customer_id_source")
        if order.get("is_orphan_customer") or customer_id not in customer_by_id:
            continue
        order_date = _date(order.get("order_date"))
        if order_date:
            customer_orders[customer_id].append(order_date)
    repeat_customers = 0
    for dates in customer_orders.values():
        dates.sort()
        repeat_customers += int(
            any(0 < (candidate - dates[0]).days <= repeat_window_days for candidate in dates[1:])
        )
    first_order_customers = len(customer_orders)
    repeat = [
        {
            "first_order_customers": first_order_customers,
            "repeat_customers_within_window": repeat_customers,
            "window_days": repeat_window_days,
            "repeat_purchase_rate_pct": _percent(
                Decimal(repeat_customers), Decimal(first_order_customers)
            ),
        }
    ]

    # 8. Payment reconciliation.
    order_totals = defaultdict(Decimal)
    for row in items:
        if row.get("order_id") in order_by_id:
            order_totals[row["order_id"]] += _decimal(row.get("line_total"))
    payments_by_order: dict[str, list[dict]] = defaultdict(list)
    for row in payments:
        payments_by_order[row.get("order_id")].append(row)
    duplicate_payment_rows: dict[str, int] = defaultdict(int)
    conflicting_payment_rows: dict[str, int] = defaultdict(int)
    for row in tables.get("quarantine_payments", []):
        try:
            raw = json.loads(row.get("raw_payload") or "{}")
        except json.JSONDecodeError:
            raw = {}
        order_id = raw.get("order_id")
        if row.get("reason_code") == "DUPLICATE_EXACT":
            duplicate_payment_rows[order_id] += 1
        elif row.get("reason_code") == "DUPLICATE_CONFLICT":
            conflicting_payment_rows[order_id] += 1
    reconciliation = []
    tolerance = Decimal(str(payment_tolerance))
    for order in sorted(orders, key=lambda row: row["order_id"]):
        order_id = order["order_id"]
        rows = payments_by_order[order_id]
        successful = [row for row in rows if row.get("payment_status") == "Success"]
        paid = sum((_decimal(row.get("amount")) for row in successful), Decimal("0"))
        expected = order_totals[order_id]
        difference = paid - expected
        if not successful:
            status = "NO_SUCCESSFUL_PAYMENT"
        elif abs(difference) <= tolerance:
            status = "MATCH"
        elif difference < 0:
            status = "UNDERPAID"
        else:
            status = "OVERPAID"
        payment_ids = Counter(row.get("payment_id") for row in rows)
        reconciliation.append(
            {
                "order_id": order_id,
                "order_status": order.get("order_status"),
                "computed_order_total": _money(expected),
                "successful_payment_amount": _money(paid),
                "difference": _money(difference),
                "payment_row_count": len(rows),
                "successful_payment_count": len(successful),
                "duplicate_payment_id_count": sum(
                    max(count - 1, 0) for count in payment_ids.values()
                ),
                "quarantined_duplicate_payment_rows": duplicate_payment_rows[order_id],
                "quarantined_conflicting_payment_rows": conflicting_payment_rows[order_id],
                "multiple_payment_rows": int(len(rows) > 1),
                "status": status,
            }
        )

    result = {
        "net_revenue_by_category_month": net_revenue,
        "top_customers_by_ltv": top_ltv,
        "customer_segment_profile": segment_profile,
        "mom_channel_growth": mom,
        "product_return_rate": product_return_output,
        "supplier_scorecard": scorecard,
        "repeat_purchase_rate": repeat,
        "payment_reconciliation": reconciliation,
    }
    if include_margin:
        margin = defaultdict(lambda: {"quantity": Decimal("0"), "revenue_exposed": Decimal("0")})
        for row in items:
            product = product_by_id.get(row.get("product_id_source"))
            if not product or product.get("is_orphan_product"):
                continue
            effective_price = _decimal(row.get("unit_price")) * (
                Decimal("1") - _decimal(row.get("discount_pct")) / 100
            )
            cost = _decimal(product.get("cost_price"))
            if cost > effective_price:
                product_id = product["product_id"]
                margin[product_id]["quantity"] += _decimal(row.get("quantity"))
                margin[product_id]["revenue_exposed"] += (cost - effective_price) * _decimal(
                    row.get("quantity")
                )
        result["margin_risk"] = [
            {
                "product_id": product_id,
                "product_name": product_by_id[product_id].get("product_name"),
                "quantity_exposed": int(values["quantity"]),
                "revenue_exposed": _money(values["revenue_exposed"]),
            }
            for product_id, values in sorted(margin.items())
        ]
    return result


def write_outputs(
    results: dict[str, list[dict[str, Any]]], output_dir: str | Path
) -> dict[str, int]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    counts = {}
    for key, rows in results.items():
        path = output_dir / OUTPUT_NAMES[key]
        fields = sorted({field for row in rows for field in row})
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            if fields:
                writer.writeheader()
                writer.writerows(rows)
        counts[key] = len(rows)
    (output_dir / "kpi_manifest.json").write_text(
        json.dumps({"row_counts": counts, "assumptions": ASSUMPTIONS}, indent=2), encoding="utf-8"
    )
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Calculate ShopSphere KPIs from the gold database")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--db-path")
    parser.add_argument("--output-dir")
    parser.add_argument("--return-rate-min-volume", type=int)
    parser.add_argument("--payment-tolerance", type=float)
    parser.add_argument("--repeat-window-days", type=int)
    parser.add_argument("--no-margin-risk", action="store_true")
    args = parser.parse_args(argv)
    config = load_config(args.config)
    medallion = config.get("medallion", {})
    kpi_config = config.get("kpis", {})
    db_path = (
        args.db_path
        or kpi_config.get("db_path")
        or medallion.get("db_path", "data/processed/shopsphere.db")
    )
    output_dir = args.output_dir or kpi_config.get("output_dir", "reports/kpi_outputs")
    results = calculate_kpis(
        db_path,
        return_rate_min_volume=(
            args.return_rate_min_volume
            if args.return_rate_min_volume is not None
            else medallion.get("return_rate_min_volume", 10)
        ),
        payment_tolerance=args.payment_tolerance
        if args.payment_tolerance is not None
        else medallion.get("payment_tolerance", 1.0),
        repeat_window_days=(
            args.repeat_window_days
            if args.repeat_window_days is not None
            else medallion.get("repeat_window_days", 90)
        ),
        include_margin=not args.no_margin_risk,
    )
    counts = write_outputs(results, output_dir)
    print(json.dumps(counts, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
