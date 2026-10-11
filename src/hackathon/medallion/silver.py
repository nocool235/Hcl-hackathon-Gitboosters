"""Silver layer: one cleansing function per entity. Rejected rows go to quarantine.

Every bronze row ends up in exactly one place, so bronze = silver + quarantine.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal
from functools import partial

from hackathon.medallion.common import (
    clean_phone,
    clean_text,
    is_ambiguous_date,
    map_value,
    money,
    parse_amount,
    parse_date,
    to_bool,
)

STATUS = {"completed": "Completed", "complete": "Completed", "complted": "Completed",
          "pending": "Pending", "cancelled": "Cancelled", "canceled": "Cancelled",
          "cancled": "Cancelled", "returned": "Returned"}
CHANNEL = {"web": "Web", "app": "App", "store": "Store", "instore": "Store"}
SEGMENT = {"platinum": "Platinum", "gold": "Gold", "glod": "Gold", "silver": "Silver",
           "silverr": "Silver", "bronze": "Bronze", "broze": "Bronze"}
CATEGORY = {"fashion": "Fashion", "grocery": "Grocery", "electronics": "Electronics",
            "electornics": "Electronics", "sports": "Sports",
            "homeandkitchen": "Home & Kitchen"}
PAYMENT_STATUS = {"success": "Success", "succeded": "Success", "succeeded": "Success",
                  "failed": "Failed", "pending": "Pending", "refunded": "Refunded"}
RETURN_STATUS = {"approved": "Approved", "rejected": "Rejected", "pending": "Pending"}
RETURN_REASON = {"damged": "damaged"}

# Business columns (used for completeness and duplicate comparison) per entity.
COLUMNS = {
    "customers": ["customer_id", "first_name", "last_name", "email", "phone", "address_line1",
                  "city", "state", "zip_code", "country", "signup_date", "customer_segment",
                  "is_active"],
    "suppliers": ["supplier_id", "supplier_name", "country", "rating_raw", "rating_scale_max",
                  "rating_norm", "contract_start_date", "is_preferred"],
    "products": ["product_id", "product_name", "category", "sub_category", "unit_price",
                 "cost_price", "supplier_id", "is_active", "launch_date", "price_issue"],
    "orders": ["order_id", "customer_id", "order_date", "order_status", "payment_method",
               "channel", "promo_code", "shipping_city"],
    "order_items": ["order_item_id", "order_id", "product_id", "quantity", "unit_price",
                    "discount_pct", "line_total", "source_line_total"],
    "payments": ["payment_id", "order_id", "payment_date", "amount", "payment_status",
                 "payment_method"],
    "returns": ["return_id", "order_item_id", "return_date", "return_reason", "refund_amount",
                "return_status"],
}
# Columns added after cleansing (cross-entity checks); not used to pick duplicate winners.
FLAGS = {
    "customers": ["dup_group_id"],
    "suppliers": [],
    "products": ["is_orphan_supplier"],
    "orders": ["order_date_ambiguous", "is_orphan_customer"],
    "order_items": ["line_total_mismatch", "is_orphan_order", "is_orphan_product"],
    "payments": ["payment_date_ambiguous", "is_orphan_order"],
    "returns": ["return_date_ambiguous", "is_orphan_item", "refund_exceeds_line",
                "return_before_order"],
}
KEYS = {"customers": "customer_id", "suppliers": "supplier_id", "products": "product_id",
        "orders": "order_id", "order_items": "order_item_id", "payments": "payment_id",
        "returns": "return_id"}
SILVER_COLUMNS = {e: COLUMNS[e] + FLAGS[e] + ["_row_number"] for e in COLUMNS}
QUARANTINE_COLUMNS = ["_row_number", "record_key", "reason_code", "reason_detail", "raw_payload",
                      "_batch_id"]


def silver_columns(entity: str) -> list[str]:
    return SILVER_COLUMNS[entity]


# ---------- cleansing functions: raw bronze row -> (clean row, None) or (None, (code, detail)) --

def clean_customer(raw: dict):
    customer_id = clean_text(raw["customer_id"])
    if customer_id is None:
        return None, ("MISSING_KEY", "customer_id is blank")
    email = clean_text(raw["email"])
    email = email.lower() if email and "@" in email else None
    city, state = clean_text(raw["city"]), clean_text(raw["state"])
    return {
        "customer_id": customer_id,
        "first_name": clean_text(raw["first_name"]),
        "last_name": clean_text(raw["last_name"]),
        "email": email,
        "phone": clean_phone(raw["phone"]),
        "address_line1": clean_text(raw["address_line1"]),
        "city": city.title() if city else None,
        "state": state.title() if state else None,
        "zip_code": clean_text(raw["zip_code"]),
        "country": clean_text(raw["country"]),
        "signup_date": parse_date(raw["signup_date"]),
        "customer_segment": map_value(raw["customer_segment"], SEGMENT) or "Unknown",
        "is_active": to_bool(raw["is_active"]),
        "_row_number": raw["_row_number"],
    }, None


def detect_rating_scale(raw_ratings: list) -> int | None:
    """Smallest of 5 / 10 / 100 that contains the highest rating seen in the file."""
    values = [parse_amount(v) for v in raw_ratings]
    top = max((v for v in values if v is not None), default=None)
    if top is None:
        return None
    return next((s for s in (5, 10, 100) if top <= s), None)


def clean_supplier(raw: dict, scale: int | None):
    supplier_id = clean_text(raw["supplier_id"])
    if supplier_id is None:
        return None, ("MISSING_KEY", "supplier_id is blank")
    rating = parse_amount(raw["rating"])
    if rating is not None and (rating < 0 or scale is None or rating > scale):
        rating = None
    return {
        "supplier_id": supplier_id,
        "supplier_name": clean_text(raw["supplier_name"]),
        "country": clean_text(raw["country"]) or "Unknown",
        "rating_raw": None if rating is None else float(rating),
        "rating_scale_max": scale,
        "rating_norm": None if rating is None else round(float(rating) / scale, 4),
        "contract_start_date": parse_date(raw["contract_start_date"]),
        "is_preferred": to_bool(raw["is_preferred"]),
        "_row_number": raw["_row_number"],
    }, None


def clean_product(raw: dict):
    product_id = clean_text(raw["product_id"])
    if product_id is None:
        return None, ("MISSING_KEY", "product_id is blank")
    price, cost = parse_amount(raw["unit_price"]), parse_amount(raw["cost_price"])
    issues = []
    if price is None or price <= 0:
        price, issues = None, issues + ["INVALID_LIST_PRICE"]
    if cost is None or cost < 0:
        cost, issues = None, issues + ["INVALID_COST"]
    sub_category = clean_text(raw["sub_category"])
    return {
        "product_id": product_id,
        "product_name": clean_text(raw["product_name"]),
        "category": map_value(raw["category"], CATEGORY) or "Unknown",
        "sub_category": sub_category.title() if sub_category else None,
        "unit_price": money(price),
        "cost_price": money(cost),
        "supplier_id": clean_text(raw["supplier_id"]),
        "is_active": to_bool(raw["is_active"]),
        "launch_date": parse_date(raw["launch_date"]),
        "price_issue": ",".join(issues) or None,
        "_row_number": raw["_row_number"],
    }, None


def clean_order(raw: dict):
    order_id = clean_text(raw["order_id"])
    if order_id is None:
        return None, ("MISSING_KEY", "order_id is blank")
    order_date = parse_date(raw["order_date"])
    if order_date is None:
        return None, ("INVALID_DATE", f"order_date={raw['order_date']!r}")
    status = map_value(raw["order_status"], STATUS)
    if status is None:
        return None, ("INVALID_STATUS", f"order_status={raw['order_status']!r}")
    channel = map_value(raw["channel"], CHANNEL)
    if channel is None:
        return None, ("INVALID_CHANNEL", f"channel={raw['channel']!r}")
    city = clean_text(raw["shipping_city"])
    return {
        "order_id": order_id,
        "customer_id": clean_text(raw["customer_id"]),
        "order_date": order_date,
        "order_status": status,
        "payment_method": clean_text(raw["payment_method"]),
        "channel": channel,
        "promo_code": clean_text(raw["promo_code"]),
        "shipping_city": city.title() if city else None,
        "order_date_ambiguous": int(is_ambiguous_date(raw["order_date"])),
        "_row_number": raw["_row_number"],
    }, None


def calc_line_total(quantity: int, unit_price: Decimal, discount_pct: Decimal) -> Decimal:
    gross = Decimal(quantity) * unit_price * (Decimal(1) - discount_pct / Decimal(100))
    return gross.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def clean_order_item(raw: dict):
    item_id = clean_text(raw["order_item_id"])
    if item_id is None:
        return None, ("MISSING_KEY", "order_item_id is blank")
    qty = parse_amount(raw["quantity"])
    if qty is None or qty != qty.to_integral_value():
        return None, ("INVALID_QUANTITY", f"quantity={raw['quantity']!r}")
    if qty <= 0:
        return None, ("NON_POSITIVE_QUANTITY", f"quantity={qty}")
    price = parse_amount(raw["unit_price"])
    if price is None:
        return None, ("MISSING_UNIT_PRICE", f"unit_price={raw['unit_price']!r}")
    if price < 0:
        return None, ("NEGATIVE_UNIT_PRICE", f"unit_price={price}")
    discount = parse_amount(raw["discount_pct"])
    if discount is None or not (0 <= discount <= 100):
        return None, ("INVALID_DISCOUNT", f"discount_pct={raw['discount_pct']!r}")
    line_total = calc_line_total(int(qty), price, discount)
    source_total = parse_amount(raw["line_total"])
    mismatch = source_total is None or abs(source_total - line_total) > Decimal("0.01")
    return {
        "order_item_id": item_id,
        "order_id": clean_text(raw["order_id"]),
        "product_id": clean_text(raw["product_id"]),
        "quantity": int(qty),
        "unit_price": money(price),
        "discount_pct": float(discount),
        "line_total": money(line_total),
        "source_line_total": money(source_total),
        "line_total_mismatch": int(mismatch),
        "_row_number": raw["_row_number"],
    }, None


def clean_payment(raw: dict):
    payment_id = clean_text(raw["payment_id"])
    if payment_id is None:
        return None, ("MISSING_KEY", "payment_id is blank")
    amount = parse_amount(raw["amount"])
    if amount is None:
        return None, ("INVALID_AMOUNT", f"amount={raw['amount']!r}")
    if amount < 0:
        return None, ("NEGATIVE_AMOUNT", f"amount={amount}")
    status = map_value(raw["payment_status"], PAYMENT_STATUS)
    if status is None:
        return None, ("INVALID_STATUS", f"payment_status={raw['payment_status']!r}")
    return {
        "payment_id": payment_id,
        "order_id": clean_text(raw["order_id"]),
        "payment_date": parse_date(raw["payment_date"]),
        "amount": money(amount),
        "payment_status": status,
        "payment_method": clean_text(raw["payment_method"]),
        "payment_date_ambiguous": int(is_ambiguous_date(raw["payment_date"])),
        "_row_number": raw["_row_number"],
    }, None


def clean_return(raw: dict):
    return_id = clean_text(raw["return_id"])
    if return_id is None:
        return None, ("MISSING_KEY", "return_id is blank")
    return_date = parse_date(raw["return_date"])
    if return_date is None:
        return None, ("INVALID_DATE", f"return_date={raw['return_date']!r}")
    status = map_value(raw["return_status"], RETURN_STATUS)
    if status is None:
        return None, ("INVALID_STATUS", f"return_status={raw['return_status']!r}")
    refund = parse_amount(raw["refund_amount"])
    if refund is not None and refund < 0:
        return None, ("NEGATIVE_REFUND", f"refund_amount={refund}")
    reason = clean_text(raw["return_reason"])
    reason = RETURN_REASON.get(reason.lower(), reason.lower()) if reason else None
    return {
        "return_id": return_id,
        "order_item_id": clean_text(raw["order_item_id"]),
        "return_date": return_date,
        "return_reason": reason,
        "refund_amount": money(refund),
        "return_status": status,
        "return_date_ambiguous": int(is_ambiguous_date(raw["return_date"])),
        "_row_number": raw["_row_number"],
    }, None


# ---------- the engine: validate, then pick one winner per key ----------

def completeness(row: dict, columns: list[str]) -> int:
    return sum(1 for c in columns if row.get(c) is not None)


def content_hash(row: dict, columns: list[str]) -> str:
    payload = json.dumps({c: row.get(c) for c in columns}, sort_keys=True, default=str)
    return hashlib.sha1(payload.encode()).hexdigest()


def _quarantine_row(raw: dict, key: str, code: str, detail: str) -> dict:
    payload = {k: v for k, v in raw.items() if not k.startswith("_")}
    return {"_row_number": raw["_row_number"], "record_key": clean_text(raw.get(key)),
            "reason_code": code, "reason_detail": detail,
            "raw_payload": json.dumps(payload, sort_keys=True), "_batch_id": raw["_batch_id"]}


def process_entity(entity: str, bronze_rows: list[dict], cleaner):
    """Winner rule for duplicate keys: most complete record, then the smallest content hash
    (independent of file order), then the lowest source row number. Reruns are identical."""
    key, columns = KEYS[entity], COLUMNS[entity]
    raw_by_row = {r["_row_number"]: r for r in bronze_rows}
    valid, quarantine = [], []
    for raw in bronze_rows:
        row, problem = cleaner(raw)
        if problem:
            quarantine.append(_quarantine_row(raw, key, *problem))
        else:
            valid.append(row)

    groups = defaultdict(list)
    for row in valid:
        groups[row[key]].append(row)
    silver = []
    for k in sorted(groups):
        ranked = sorted(groups[k], key=lambda r: (-completeness(r, columns),
                                                  content_hash(r, columns), r["_row_number"]))
        winner = ranked[0]
        silver.append(winner)
        for loser in ranked[1:]:
            same = content_hash(loser, columns) == content_hash(winner, columns)
            code = "DUPLICATE_EXACT" if same else "DUPLICATE_CONFLICT"
            detail = f"lost to source row {winner['_row_number']}"
            quarantine.append(_quarantine_row(raw_by_row[loser["_row_number"]], key, code, detail))
    quarantine.sort(key=lambda q: q["_row_number"])
    return silver, quarantine


def add_flags(silver: dict[str, list[dict]]) -> None:
    """Cross-entity checks. Orphans are kept and flagged, never dropped."""
    supplier_ids = {r["supplier_id"] for r in silver["suppliers"]}
    product_ids = {r["product_id"] for r in silver["products"]}
    customer_ids = {r["customer_id"] for r in silver["customers"]}
    order_date = {r["order_id"]: r["order_date"] for r in silver["orders"]}
    items = {r["order_item_id"]: r for r in silver["order_items"]}

    for r in silver["products"]:
        r["is_orphan_supplier"] = int(r["supplier_id"] not in supplier_ids)
    for r in silver["orders"]:
        r["is_orphan_customer"] = int(r["customer_id"] not in customer_ids)
    for r in silver["order_items"]:
        r["is_orphan_order"] = int(r["order_id"] not in order_date)
        r["is_orphan_product"] = int(r["product_id"] not in product_ids)
    for r in silver["payments"]:
        r["is_orphan_order"] = int(r["order_id"] not in order_date)
    for r in silver["returns"]:
        item = items.get(r["order_item_id"])
        r["is_orphan_item"] = int(item is None)
        refund = r["refund_amount"]
        r["refund_exceeds_line"] = int(
            item is not None and refund is not None and refund > item["line_total"] + 0.01)
        placed = order_date.get(item["order_id"]) if item else None
        r["return_before_order"] = int(placed is not None and r["return_date"] < placed)

    # Same person under different ids: identical email AND phone. Flagged only, never merged.
    by_contact = defaultdict(list)
    for r in silver["customers"]:
        if r["email"] and r["phone"]:
            by_contact[(r["email"], r["phone"])].append(r["customer_id"])
    for r in silver["customers"]:
        group = by_contact.get((r["email"], r["phone"]), []) if r["email"] and r["phone"] else []
        r["dup_group_id"] = min(group) if len(group) > 1 else None


def build_silver(bronze: dict[str, list[dict]]):
    scale = detect_rating_scale([r["rating"] for r in bronze["suppliers"]])
    cleaners = {
        "customers": clean_customer, "suppliers": partial(clean_supplier, scale=scale),
        "products": clean_product, "orders": clean_order, "order_items": clean_order_item,
        "payments": clean_payment, "returns": clean_return,
    }
    silver, quarantine, stats = {}, {}, {}
    for entity, cleaner in cleaners.items():
        silver[entity], quarantine[entity] = process_entity(entity, bronze[entity], cleaner)
    add_flags(silver)
    for entity in cleaners:
        reasons = defaultdict(int)
        for q in quarantine[entity]:
            reasons[q["reason_code"]] += 1
        stats[entity] = {"bronze": len(bronze[entity]), "silver": len(silver[entity]),
                         "quarantine": len(quarantine[entity]), "reasons": dict(reasons)}
    return silver, quarantine, stats
