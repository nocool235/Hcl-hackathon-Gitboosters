import csv
import json
import sqlite3
from decimal import Decimal
from pathlib import Path

from hackathon.kpis import run_sqlite_kpis
from hackathon.medallion.common import parse_amount, parse_date
from hackathon.medallion.gold import UNKNOWN_KEY, build_gold
from hackathon.medallion.run import run_pipeline
from hackathon.medallion.silver import infer_categories

SQL_DIR = Path(__file__).resolve().parents[1] / "kpis"


def _write_csv(path, columns, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        writer.writerows(rows)


def test_common_parsers_handle_source_formats():
    assert parse_amount("₹210,054.96") == Decimal("210054.96")
    assert parse_date("26/11/2022") == "2022-11-26"
    assert parse_date("11/26/2022") == "2022-11-26"
    assert parse_date("not-a-date") is None


def test_blank_category_inferred_only_when_sub_category_is_unambiguous():
    products = [
        {"product_id": "P1", "category": "Sports", "sub_category": "Fitness"},
        {"product_id": "P2", "category": "Unknown", "sub_category": "Fitness"},
        {"product_id": "P3", "category": "Fashion", "sub_category": "Shoes"},
        {"product_id": "P4", "category": "Sports", "sub_category": "Shoes"},
        {"product_id": "P5", "category": "Unknown", "sub_category": "Shoes"},
        {"product_id": "P6", "category": "Unknown", "sub_category": None},
    ]
    infer_categories(products)
    assert [(p["category"], p["category_inferred"]) for p in products] == [
        ("Sports", 0), ("Sports", 1), ("Fashion", 0), ("Sports", 0), ("Unknown", 0),
        ("Unknown", 0)]


def test_gold_uses_unknown_product_for_orphan_return():
    silver = {
        "customers": [],
        "suppliers": [],
        "products": [],
        "orders": [],
        "order_items": [],
        "payments": [],
        "returns": [
            {
                "return_id": "R1",
                "order_item_id": "MISSING",
                "return_date": "2024-01-02",
                "return_reason": "wrong item",
                "return_status": "Approved",
                "refund_amount": 4.0,
                "returned_quantity": None,
                "returned_quantity_basis": "UNKNOWN",
                "refund_exceeds_line": 0,
                "return_before_order": 0,
                "is_orphan_item": 1,
            }
        ],
    }
    result = build_gold(silver)
    assert result["fact_returns"][0]["product_key"] == UNKNOWN_KEY


def test_medallion_pipeline_and_kpis(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    _write_csv(
        source / "customers.csv",
        [
            "customer_id",
            "first_name",
            "last_name",
            "email",
            "phone",
            "address_line1",
            "city",
            "state",
            "zip_code",
            "country",
            "signup_date",
            "customer_segment",
            "is_active",
        ],
        [
            [
                "C1",
                "Ada",
                "Patel",
                "ada@example.com",
                "9999999999",
                "1 Main",
                "Pune",
                "MH",
                "411001",
                "India",
                "2023-01-01",
                "Gold",
                "true",
            ]
        ],
    )
    (source / "suppliers.json").write_text(
        json.dumps(
            [
                {
                    "supplier_id": "S1",
                    "supplier_name": "Supplier One",
                    "country": "India",
                    "rating": "8",
                    "contract_start_date": "2020-01-01",
                    "is_preferred": "yes",
                }
            ]
        ),
        encoding="utf-8",
    )
    _write_csv(
        source / "products.csv",
        [
            "product_id",
            "product_name",
            "category",
            "sub_category",
            "unit_price",
            "cost_price",
            "supplier_id",
            "is_active",
            "launch_date",
        ],
        [["P1", "Widget", "Electronics", "Accessories", "10", "6", "S1", "1", "2020-01-01"]],
    )
    _write_csv(
        source / "orders.csv",
        [
            "order_id",
            "customer_id",
            "order_date",
            "order_status",
            "payment_method",
            "channel",
            "promo_code",
            "shipping_city",
        ],
        [
            ["O1", "C1", "2024-01-01", "Completed", "Card", "Web", "", "Pune"],
            ["O2", "C1", "2024-02-01", "Completed", "Card", "Web", "", "Pune"],
        ],
    )
    _write_csv(
        source / "order_items.csv",
        [
            "order_item_id",
            "order_id",
            "product_id",
            "quantity",
            "unit_price",
            "discount_pct",
            "line_total",
        ],
        [["I1", "O1", "P1", "2", "10", "0", "20"], ["I2", "O2", "P1", "1", "10", "0", "10"]],
    )
    _write_csv(
        source / "payments.csv",
        [
            "payment_id",
            "order_id",
            "payment_date",
            "amount",
            "payment_status",
            "payment_method",
        ],
        [
            ["PAY1", "O1", "2024-01-01", "20", "Success", "Card"],
            ["PAY2", "O2", "2024-02-01", "10", "Success", "Card"],
        ],
    )
    _write_csv(
        source / "returns.csv",
        [
            "return_id",
            "order_item_id",
            "return_date",
            "return_reason",
            "refund_amount",
            "return_status",
        ],
        [["R1", "I1", "2024-01-05", "wrong item", "10", "Approved"]],
    )

    db_path = tmp_path / "shopsphere.db"
    first_run = run_pipeline(input_dir=source, db_path=db_path, batch_id="test_batch")
    second_run = run_pipeline(input_dir=source, db_path=db_path, batch_id="test_batch")
    assert first_run["counts"] == second_run["counts"]
    # The real pipeline stores money as TEXT in SQLite, so this also guards the SQL casts.
    out = tmp_path / "kpis"
    run_sqlite_kpis(db_path, SQL_DIR, out, tmp_path / "kpi_report.md")

    def read(name):
        with open(out / f"{name}.csv", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    revenue = [(r["order_month"], r["category"], float(r["gross_revenue"]), float(r["refunds"]),
                float(r["net_revenue"])) for r in read("kpi_01_net_revenue_category_month")]
    assert revenue == [("2024-01", "Electronics", 20.0, 10.0, 10.0),
                       ("2024-02", "Electronics", 10.0, 0.0, 10.0)]
    assert float(read("kpi_02_top_customers_net_ltv")[0]["net_lifetime_value"]) == 20.0
    full_window, all_customers = read("kpi_07_repeat_purchase_rate")
    assert (full_window["cohort"], full_window["customers_denominator"]) == ("FULL_WINDOW", "0")
    assert float(all_customers["repeat_rate_pct"]) == 100.0
    assert {r["reconciliation_status"] for r in read("kpi_08_payment_reconciliation")} == {
        "MATCHED"}
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("select count(*) from quality_issues").fetchone()[0] == 0
