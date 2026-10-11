from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from hackathon.analytics import qa, source
from hackathon.analytics.rag_status import (
    build_scorecards,
    classify,
    complete_months,
    overall_status,
)


def _rev(month, gross, refunds):
    return {
        "order_month": month,
        "category": "A",
        "gross_revenue": gross,
        "refunds": refunds,
        "net_revenue": gross - refunds,
    }


KPIS = {
    "kpi_01": [_rev("2024-01", 100.0, 5.0), _rev("2024-02", 100.0, 30.0), _rev("2024-03", 5.0, 0)],
    "kpi_08": [
        {"order_status": "Completed", "reconciliation_status": "MATCHED"},
        {"order_status": "Completed", "reconciliation_status": "MATCHED"},
        {"order_status": "Completed", "reconciliation_status": "UNDERPAID"},
        {"order_status": "Cancelled", "reconciliation_status": "NO_SUCCESSFUL_PAYMENT"},
    ],
    "stretch_margin_risk": [{"product_id": "P1", "margin_shortfall": 50.0}],
    "kpi_07": [
        {"is_primary": True, "repeat_rate_pct": 40.0, "reference_date": "2024-03-05"},
        {"is_primary": False, "repeat_rate_pct": 10.0, "reference_date": "2024-03-05"},
    ],
    "kpi_04": [
        {"channel": "Web", "order_month": "2024-02", "revenue_growth_pct": -20.0},
        {"channel": "App", "order_month": "2024-03", "revenue_growth_pct": 99.0},
    ],
    "kpi_02": [{"customer_id": "C1", "net_lifetime_value": 10.0}],
    "kpi_05": [{"product_id": "P1", "return_rate_pct": 12.0}],
    "kpi_06": [
        {
            "supplier_id": "S1",
            "avg_product_return_rate_pct": 8.0,
            "rating_raw": 4.5,
            "rating_scale": 5,
        }
    ],
}


def test_classify_both_directions_and_boundaries():
    assert classify(95, 95, 85) == "G"
    assert classify(90, 95, 85) == "A"
    assert classify(10, 95, 85) == "R"
    assert classify(5, 5, 10, higher_is_better=False) == "G"
    assert classify(10, 5, 10, higher_is_better=False) == "A"
    assert classify(11, 5, 10, higher_is_better=False) == "R"
    assert classify(None, 1, 0) == "N/A"


def test_complete_months_drops_partial_reference_month():
    months = ["2024-01", "2024-02", "2024-03"]
    assert complete_months(months, "2024-03-05") == ["2024-01", "2024-02"]
    assert complete_months(months, "2024-03-31") == months
    assert complete_months(months, None) == months


def test_scorecards_assign_expected_statuses():
    cards = build_scorecards(KPIS)
    finance = {m.key: m for m in cards["Finance"]}
    # March is a partial month (reference 2024-03-05), so Feb vs Jan: 70 vs 95.
    assert finance["net_revenue_mom_pct"].value == pytest.approx(-26.32)
    assert finance["net_revenue_mom_pct"].status == "R"
    # Cancelled orders are not counted: 2 of 3 Completed orders match.
    assert finance["payment_match_pct"].value == pytest.approx(66.67)
    assert finance["payment_match_pct"].status == "R"
    assert finance["margin_risk_products"].status == "A"
    marketing = {m.key: m for m in cards["Marketing"]}
    assert marketing["repeat_purchase_pct"].value == 40.0
    assert marketing["channel_revenue_mom_pct"].value == -20.0  # the partial March row is ignored
    supply = {m.key: m for m in cards["Supply Chain"]}
    assert supply["min_supplier_rating"].value == 0.9
    assert overall_status(cards["Finance"]) == "R"


def test_threshold_override():
    cards = build_scorecards(KPIS, {"payment_match_pct": {"green": 60, "amber": 50}})
    assert {m.key: m for m in cards["Finance"]}["payment_match_pct"].status == "G"


def test_normalise_values():
    assert source.normalise_value(date(2024, 1, 2)) == "2024-01-02"
    assert source.normalise_value(Decimal("1.50")) == 1.5
    assert source.normalise_value("x") == "x"
    assert source.kpi_key("kpi_02b_customer_reference_exceptions") == "kpi_02b"
    assert source.kpi_key("stretch_margin_risk") == "stretch_margin_risk"


def test_retrieval_is_team_scoped_and_relevant():
    notes = {"kpi_06": "KPI 6: Supplier scorecard\nDefinition: composite supplier score"}
    chunks = qa.build_corpus(KPIS, build_scorecards(KPIS), "# Model\nstar schema notes", notes)
    hits = qa.retrieve(chunks, "which supplier return rate", "Supply Chain")
    assert hits and all(not c.teams or "Supply Chain" in c.teams for c in hits)
    assert "supplier" in hits[0].text.lower()
    finance_hits = qa.retrieve(chunks, "supplier scorecard rating", "Finance")
    assert all("kpi_06" not in c.source for c in finance_hits)


def test_answer_uses_stub_client_and_returns_sources():
    seen = {}

    def generate_content(**kwargs):
        seen.update(kwargs)
        return SimpleNamespace(text="Match rate is 66.67% [1]")

    client = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    chunks = qa.build_corpus(KPIS, build_scorecards(KPIS))
    result = qa.answer_question("payment match rate", "Finance", chunks, client=client)
    assert result.text.startswith("Match rate")
    assert result.sources
    assert "Context:" in seen["contents"]
    assert "Finance" in seen["config"]["system_instruction"]


def test_answer_without_relevant_chunks_skips_llm():
    result = qa.answer_question("zzzz qqqq", "Finance", qa.build_corpus(KPIS, {}), client=object())
    assert "do not have" in result.text


DB = Path("data/processed/shopsphere.db")


@pytest.mark.skipif(not DB.exists(), reason="gold SQLite not built")
def test_sqlite_kpis_feed_scorecards_with_no_gaps():
    results, notes = source.run_kpis_sqlite(str(DB), {})
    assert {"kpi_01", "kpi_08", "kpi_07", "stretch_margin_risk"} <= set(results)
    assert all(notes[k] for k in results)
    cards = build_scorecards(results)
    assert all(m.status != "N/A" for team in cards.values() for m in team)
