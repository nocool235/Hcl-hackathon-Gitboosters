import csv
import json
from decimal import Decimal as D
from pathlib import Path

import pytest

from hackathon.kpis import query_params, read_header, run_sqlite_kpis
from hackathon.medallion import db
from hackathon.medallion.gold import GOLD_COLUMNS
from hackathon.medallion.silver import QUARANTINE_COLUMNS

SQL_DIR = Path(__file__).resolve().parents[1] / "kpis"

CUSTOMERS = [
    {"customer_key": 1, "customer_id": "C1", "first_name": "A", "last_name": "One",
     "customer_segment": "Gold"},
    {"customer_key": 2, "customer_id": "C2", "first_name": "B", "last_name": "Two",
     "customer_segment": "Gold"},
    {"customer_key": 3, "customer_id": "C3", "first_name": "C", "last_name": "Three",
     "customer_segment": "Silver", "dup_group_id": "C3"},
    {"customer_key": 4, "customer_id": "C4", "first_name": "D", "last_name": "Four",
     "customer_segment": "Silver", "dup_group_id": "C3"},
    {"customer_key": -1, "customer_id": "UNKNOWN", "customer_segment": "Unknown"},
]
# Money is Decimal, which db.write_table stores as TEXT exactly like the real pipeline does,
# so these tests fail if a query compares money columns without casting them.
# (order_id, customer_key, source id, date, status, line_total)
ORDERS = [
    ("O1", 1, "C1", "2024-01-05", "Completed", D("100.00")),
    ("O2", 2, "C2", "2024-01-10", "Completed", D("100.00")),
    ("O3", 2, "C2", "2024-03-01", "Returned", D("100.00")),
    ("O4", 1, "C1", "2024-01-12", "Cancelled", D("100.00")),
    ("O5", -1, "C9", "2024-01-15", "Completed", D("100.00")),
    ("O6", 3, "C3", "2024-01-20", "Completed", D("300.00")),
]
RETURNS = [
    ("R1", "I_O1", "Rejected", D("50.00")),   # rejected: never subtracted
    ("R3", "I_O3", "Approved", D("150.00")),  # exceeds the 100 line: capped, subtracted once
    ("R4", "I_O4", "Approved", D("40.00")),   # on a cancelled order: ignored
]


def build_gold(path: Path, run_status: str = "SUCCESS") -> None:
    conn = db.connect(path)
    tables = {
        "dim_customer": CUSTOMERS,
        "dim_supplier": [{"supplier_key": 100, "supplier_id": "S1", "supplier_name": "Sup",
                          "rating_raw": 4.0, "rating_scale_max": 10, "rating_norm": 0.4},
                         {"supplier_key": -1, "supplier_id": "UNKNOWN"}],
        "dim_product": [{"product_key": 10, "product_id": "P1", "product_name": "Shirt",
                         "category": "Fashion", "cost_price": D("50.00"), "supplier_key": 100},
                        {"product_key": -1, "product_id": "UNKNOWN", "category": "Unknown",
                         "supplier_key": -1}],
        "dim_date": [{"date_key": int(d.replace("-", "")), "date": d, "year_month": d[:7]}
                     for d in ("2024-01-01", "2024-02-01", "2024-03-01")],
        "fact_orders": [{"order_id": o, "customer_key": k, "customer_id_source": src,
                         "order_date": d, "order_status": s, "channel": "Web"}
                        for o, k, src, d, s, _ in ORDERS],
        "fact_order_items": [{"order_item_id": f"I_{o}", "order_id": o, "product_key": 10,
                              "quantity": 1, "unit_price": t, "discount_pct": 0.0,
                              "line_total": t}
                             for o, *_, t in ORDERS],
        "fact_payments": [{"payment_id": "PM1", "order_id": "O1", "amount": D("100.00"),
                           "payment_status": "Success"}],
        "fact_returns": [{"return_id": r, "order_item_id": i, "order_id": f"O{i[-1]}",
                          "product_key": 10, "return_status": s, "refund_amount": amt,
                          "returned_quantity": D("1")}
                         for r, i, s, amt in RETURNS],
    }
    for name, rows in tables.items():
        db.write_table(conn, name, GOLD_COLUMNS[name], rows)
    db.write_table(conn, "quarantine_payments", QUARANTINE_COLUMNS, [
        {"_row_number": 9, "record_key": "PM1", "reason_code": "DUPLICATE_EXACT",
         "raw_payload": json.dumps({"payment_id": "PM1", "order_id": "O1"})}])
    db.write_table(conn, "run_params", ["param", "value"], [
        {"param": "reference_date", "value": "2024-03-01"},
        {"param": "return_rate_min_volume", "value": "1"},
        {"param": "payment_tolerance", "value": "1.0"},
        {"param": "repeat_window_days", "value": "90"},
    ])
    db.write_table(conn, "pipeline_runs",
                   ["run_id", "batch_id", "status", "started_at", "finished_at"],
                   [{"run_id": "r1", "batch_id": "b1", "status": run_status,
                     "started_at": "2024-03-02T00:00:00", "finished_at": "2024-03-02T00:01:00"}])
    conn.close()


def run(tmp_path: Path) -> Path:
    out = tmp_path / "out"
    run_sqlite_kpis(tmp_path / "gold.db", SQL_DIR, out, tmp_path / "report.md")
    return out


def read(out: Path, name: str) -> list[dict]:
    with open(out / f"{name}.csv", encoding="utf-8") as f:
        return list(csv.DictReader(f))


@pytest.fixture
def out(tmp_path):
    build_gold(tmp_path / "gold.db")
    return run(tmp_path)


def test_net_revenue_excludes_cancelled_and_caps_refunds_once(out):
    rows = {r["order_month"]: r for r in read(out, "kpi_01_net_revenue_category_month")}
    assert set(rows) == {"2024-01", "2024-03"}
    assert float(rows["2024-01"]["net_revenue"]) == 600.0  # rejected refund ignored, O4 excluded
    assert float(rows["2024-03"]["refunds"]) == 100.0      # 150 capped at the line
    assert float(rows["2024-03"]["net_revenue"]) == 0.0


def test_top_customers_tie_break_and_exceptions(out):
    ranking = read(out, "kpi_02_top_customers_net_ltv")
    assert [r["customer_id"] for r in ranking] == ["C1", "C2"]  # equal LTV and orders -> key
    rows = read(out, "kpi_02b_customer_reference_exceptions")
    exceptions = {r["reference_type"]: r for r in rows}
    assert float(exceptions["ORPHAN_CUSTOMER"]["net_value"]) == 100.0
    assert float(exceptions["AMBIGUOUS_CUSTOMER"]["net_value"]) == 300.0


def test_mom_growth_complete_calendar_and_zero_prior_month(out):
    rows = {r["order_month"]: r for r in read(out, "kpi_04_channel_mom_growth")}
    assert rows["2024-02"]["order_count"] == "0"
    assert float(rows["2024-02"]["order_growth_pct"]) == -100.0
    assert rows["2024-03"]["order_growth_pct"] == ""
    assert rows["2024-03"]["order_growth_flag"] == "PRIOR_MONTH_ZERO"


def test_supplier_rating_is_normalised_on_its_own_scale(out):
    supplier = read(out, "kpi_06_supplier_scorecard")[0]
    assert (supplier["rating_scale"], float(supplier["rating_score"])) == ("5", 0.8)


def test_quarantined_duplicate_payment_is_flagged(out):
    rows = {r["order_id"]: r for r in read(out, "kpi_08_payment_reconciliation")}
    assert rows["O1"]["quarantined_duplicate_rows"] == "1"
    assert rows["O1"]["duplicate_payment"] == "1"
    assert rows["O2"]["duplicate_payment"] == "0"


def test_margin_risk_compares_text_money_as_numbers(out):
    # cost 50 is below every selling price, but as text '50.00' > '100.0' would flag them all
    assert read(out, "stretch_margin_risk") == []


def test_every_kpi_has_a_csv_and_a_report_section(out, tmp_path):
    report = (tmp_path / "report.md").read_text(encoding="utf-8")
    for sql in SQL_DIR.glob("*.sql"):
        assert (out / f"{sql.stem}.csv").exists()
        title, entries = read_header(sql.read_text(encoding="utf-8"))
        assert title and entries, f"{sql.name} needs a -- header"
        assert f"## {title}" in report


def test_refuses_failed_pipeline_run(tmp_path):
    build_gold(tmp_path / "gold.db", run_status="FAILED")
    with pytest.raises(RuntimeError, match="did not succeed"):
        run(tmp_path)


def test_every_sqlite_kpi_has_a_bigquery_twin_with_the_same_title():
    for sql in SQL_DIR.glob("*.sql"):
        twin = SQL_DIR / "bigquery" / sql.name
        assert twin.exists(), f"missing kpis/bigquery/{sql.name}"
        assert read_header(twin.read_text(encoding="utf-8"))[0] == read_header(
            sql.read_text(encoding="utf-8"))[0]


def test_query_params_prefer_overrides_then_config():
    params = query_params({"payment_tolerance": 2.5}, {"repeat_window_days": 30, "bogus": 1})
    assert params == {"return_rate_min_volume": 10, "payment_tolerance": 2.5,
                      "repeat_window_days": 30, "reference_date": None}


def test_read_header_joins_continuation_lines():
    title, entries = read_header("-- KPI 9: X\n-- Definition: a\n--    b\n-- Note\nSELECT 1;")
    assert title == "KPI 9: X"
    assert entries == [("Definition", "a b"), ("", "Note")]
