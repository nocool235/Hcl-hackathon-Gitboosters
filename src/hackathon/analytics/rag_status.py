"""Red/Amber/Green scorecards per team, derived from the KPI results.

Thresholds are working assumptions, not business-agreed targets: override them per metric under
`analytics.thresholds` in config/config.yaml once each team confirms its own targets.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

TEAMS = ("Finance", "Marketing", "Supply Chain")

# green/amber are the boundary values; higher_is_better flips the comparison direction.
DEFAULT_THRESHOLDS: dict[str, dict[str, Any]] = {
    "net_revenue_mom_pct": {"green": 0.0, "amber": -10.0, "higher_is_better": True},
    "payment_match_pct": {"green": 95.0, "amber": 85.0, "higher_is_better": True},
    "refund_rate_pct": {"green": 5.0, "amber": 10.0, "higher_is_better": False},
    "margin_risk_products": {"green": 0, "amber": 5, "higher_is_better": False},
    "repeat_purchase_pct": {"green": 30.0, "amber": 15.0, "higher_is_better": True},
    "channel_revenue_mom_pct": {"green": 0.0, "amber": -10.0, "higher_is_better": True},
    "top10_ltv_share_pct": {"green": 30.0, "amber": 50.0, "higher_is_better": False},
    "worst_return_rate_pct": {"green": 15.0, "amber": 30.0, "higher_is_better": False},
    "avg_supplier_return_pct": {"green": 10.0, "amber": 20.0, "higher_is_better": False},
    "min_supplier_rating": {"green": 0.7, "amber": 0.5, "higher_is_better": True},
    "margin_exposure_amount": {"green": 0.0, "amber": 500000.0, "higher_is_better": False},
}


@dataclass(frozen=True)
class Metric:
    key: str
    team: str
    label: str
    value: float | None
    unit: str
    status: str  # "G" | "A" | "R" | "N/A"
    rule: str
    source_kpi: str


def classify(value: float | None, green: float, amber: float, higher_is_better: bool = True) -> str:
    if value is None:
        return "N/A"
    if higher_is_better:
        return "G" if value >= green else "A" if value >= amber else "R"
    return "G" if value <= green else "A" if value <= amber else "R"


def _rule_text(t: dict[str, Any], unit: str) -> str:
    if t["higher_is_better"]:
        return f"Green >= {t['green']}{unit}; Amber >= {t['amber']}{unit}; else Red"
    return f"Green <= {t['green']}{unit}; Amber <= {t['amber']}{unit}; else Red"


def _growth(current: float, previous: float) -> float | None:
    return round((current - previous) / previous * 100, 2) if previous else None


def complete_months(months: list[str], reference_date: str | None) -> list[str]:
    """Drop the month containing `reference_date` unless the data runs to that month's last day."""
    if not reference_date:
        return months
    ref = date.fromisoformat(reference_date)
    last_day = (ref + timedelta(days=1)).month != ref.month
    return [
        m for m in months if m < ref.strftime("%Y-%m") or (last_day and m == ref.strftime("%Y-%m"))
    ]


def _monthly_totals(rows: list[dict[str, Any]], field: str, months_ok: list[str]) -> list[float]:
    totals: dict[str, float] = {}
    for row in rows:
        month = row.get("order_month")
        if month in months_ok:
            totals[month] = totals.get(month, 0.0) + float(row.get(field) or 0)
    return [totals[m] for m in sorted(totals)]


def _num(value: Any) -> float | None:
    return None if value is None else float(value)


def build_scorecards(
    kpis: dict[str, list[dict[str, Any]]], overrides: dict[str, dict[str, Any]] | None = None
) -> dict[str, list[Metric]]:
    """`kpis` is keyed by KPI id ('kpi_01' ... 'kpi_08', 'stretch_margin_risk')."""
    thresholds = {k: {**v, **(overrides or {}).get(k, {})} for k, v in DEFAULT_THRESHOLDS.items()}

    def metric(key: str, team: str, label: str, value, unit: str, source: str) -> Metric:
        t = thresholds[key]
        value = None if value is None else round(float(value), 2)
        status = classify(value, t["green"], t["amber"], t["higher_is_better"])
        return Metric(key, team, label, value, unit, status, _rule_text(t, unit), source)

    repeat = kpis.get("kpi_07", [])
    reference_date = next((r.get("reference_date") for r in repeat), None)

    revenue = kpis.get("kpi_01", [])
    months = complete_months(sorted({r["order_month"] for r in revenue}), reference_date)
    net_by_month = _monthly_totals(revenue, "net_revenue", months)
    gross = sum(float(r.get("gross_revenue") or 0) for r in revenue)
    refunds = sum(float(r.get("refunds") or 0) for r in revenue)
    net = gross - refunds
    # Judged on Completed orders only: Cancelled/Pending orders are not expected to be paid.
    completed = [
        r
        for r in kpis.get("kpi_08", [])
        if r.get("order_status") == "Completed"
        and r.get("reconciliation_status") != "NO_VALID_LINES"
    ]
    matched = sum(1 for r in completed if r["reconciliation_status"] == "MATCHED")
    margin = kpis.get("stretch_margin_risk", [])

    finance = [
        metric(
            "net_revenue_mom_pct",
            "Finance",
            "Net revenue, last complete month vs previous",
            _growth(net_by_month[-1], net_by_month[-2]) if len(net_by_month) >= 2 else None,
            "%",
            "kpi_01",
        ),
        metric(
            "payment_match_pct",
            "Finance",
            "Completed orders whose payments match the order total",
            matched / len(completed) * 100 if completed else None,
            "%",
            "kpi_08",
        ),
        metric(
            "refund_rate_pct",
            "Finance",
            "Refunds as share of gross revenue",
            refunds / gross * 100 if gross else None,
            "%",
            "kpi_01",
        ),
        metric(
            "margin_risk_products",
            "Finance",
            "Products sold below cost",
            len(margin),
            "",
            "stretch_margin_risk",
        ),
    ]

    primary = next((r for r in repeat if r.get("is_primary")), None)
    channel = kpis.get("kpi_04", [])
    last_month = months[-1] if months else None
    channel_growth = [
        float(r["revenue_growth_pct"])
        for r in channel
        if r.get("order_month") == last_month and r.get("revenue_growth_pct") is not None
    ]
    top_ltv = sum(float(r.get("net_lifetime_value") or 0) for r in kpis.get("kpi_02", []))

    marketing = [
        metric(
            "repeat_purchase_pct",
            "Marketing",
            "Customers repeat-purchasing within window",
            primary["repeat_rate_pct"] if primary else None,
            "%",
            "kpi_07",
        ),
        metric(
            "channel_revenue_mom_pct",
            "Marketing",
            "Avg channel revenue growth, last complete month",
            sum(channel_growth) / len(channel_growth) if channel_growth else None,
            "%",
            "kpi_04",
        ),
        metric(
            "top10_ltv_share_pct",
            "Marketing",
            "Top-10 customers' share of net revenue",
            top_ltv / net * 100 if net else None,
            "%",
            "kpi_02",
        ),
    ]

    returns = [
        float(r["return_rate_pct"])
        for r in kpis.get("kpi_05", [])
        if r.get("return_rate_pct") is not None
    ]
    suppliers = kpis.get("kpi_06", [])
    supplier_rates = [
        float(r["avg_product_return_rate_pct"])
        for r in suppliers
        if r.get("avg_product_return_rate_pct") is not None
    ]
    ratings = [
        float(r["rating_raw"]) / float(r["rating_scale"])
        for r in suppliers
        if r.get("rating_raw") is not None and r.get("rating_scale")
    ]
    exposure = sum(float(r.get("margin_shortfall") or 0) for r in margin)

    supply_chain = [
        metric(
            "worst_return_rate_pct",
            "Supply Chain",
            "Highest product return rate",
            max(returns) if returns else None,
            "%",
            "kpi_05",
        ),
        metric(
            "avg_supplier_return_pct",
            "Supply Chain",
            "Average supplier product return rate",
            sum(supplier_rates) / len(supplier_rates) if supplier_rates else None,
            "%",
            "kpi_06",
        ),
        metric(
            "min_supplier_rating",
            "Supply Chain",
            "Lowest normalised supplier rating",
            min(ratings) if ratings else None,
            "",
            "kpi_06",
        ),
        metric(
            "margin_exposure_amount",
            "Supply Chain",
            "Margin shortfall where cost exceeds net selling price",
            exposure,
            "",
            "stretch_margin_risk",
        ),
    ]
    return {"Finance": finance, "Marketing": marketing, "Supply Chain": supply_chain}


def overall_status(metrics: list[Metric]) -> str:
    statuses = {m.status for m in metrics}
    return "R" if "R" in statuses else "A" if "A" in statuses else "G" if "G" in statuses else "N/A"
