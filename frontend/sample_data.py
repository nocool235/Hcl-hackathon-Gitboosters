"""Sample data generator for ShopSphere Analytics dashboard."""

from datetime import datetime, timedelta
import numpy as np
import pandas as pd


def get_sample_kpis():
    """Return top-level KPIs for ShopSphere Analytics."""
    return {
        "total_revenue": 128450.00,
        "revenue_growth": "+14.2% vs last month",
        "total_orders": 3420,
        "orders_growth": "+8.5% vs last month",
        "avg_order_value": 37.56,
        "aov_growth": "+5.1%",
        "active_customers": 2180,
        "customer_growth": "+12.0%",
    }


def get_sales_trend_data(days: int = 30) -> pd.DataFrame:
    """Generate daily sales trend data."""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    dates = pd.date_range(start=start_date, end=end_date, freq="D")

    np.random.seed(42)
    daily_revenue = np.random.normal(loc=4200, scale=600, size=len(dates)).round(2)
    daily_orders = (daily_revenue / np.random.uniform(32, 45, size=len(dates))).astype(int)

    df = pd.DataFrame({
        "Date": dates.strftime("%Y-%m-%d"),
        "Revenue ($)": daily_revenue,
        "Orders": daily_orders,
    })
    return df


def get_category_sales_data() -> pd.DataFrame:
    """Generate product category revenue data."""
    categories = ["Electronics", "Fashion & Apparel", "Home & Kitchen", "Beauty & Personal Care", "Sports & Outdoors"]
    revenues = [48500, 32100, 24800, 14250, 8800]
    percentages = [37.8, 25.0, 19.3, 11.1, 6.8]

    return pd.DataFrame({
        "Category": categories,
        "Revenue ($)": revenues,
        "Share (%)": percentages,
    })


def get_customer_table_data() -> pd.DataFrame:
    """Generate detailed sample customer records."""
    customers = [
        {"customer_id": "CUST-1001", "name": "Aarav Sharma", "email": "aarav.s@example.com", "region": "North", "segment": "VIP", "orders": 14, "total_spend": 1420.50, "last_active": "2026-10-09"},
        {"customer_id": "CUST-1002", "name": "Emily Watson", "email": "emily.w@example.com", "region": "West", "segment": "Regular", "orders": 6, "total_spend": 450.00, "last_active": "2026-10-08"},
        {"customer_id": "CUST-1003", "name": "Rahul Verma", "email": "rahul.v@example.com", "region": "East", "segment": "VIP", "orders": 21, "total_spend": 2890.75, "last_active": "2026-10-11"},
        {"customer_id": "CUST-1004", "name": "Sofia Rodriguez", "email": "sofia.r@example.com", "region": "South", "segment": "New", "orders": 1, "total_spend": 85.20, "last_active": "2026-10-10"},
        {"customer_id": "CUST-1005", "name": "Liam Johnson", "email": "liam.j@example.com", "region": "North", "segment": "At-Risk", "orders": 3, "total_spend": 195.00, "last_active": "2026-08-15"},
        {"customer_id": "CUST-1006", "name": "Priya Patel", "email": "priya.p@example.com", "region": "West", "segment": "VIP", "orders": 18, "total_spend": 2150.00, "last_active": "2026-10-10"},
        {"customer_id": "CUST-1007", "name": "Lucas Martin", "email": "lucas.m@example.com", "region": "South", "segment": "Regular", "orders": 5, "total_spend": 380.40, "last_active": "2026-10-04"},
        {"customer_id": "CUST-1008", "name": "Ananya Gupta", "email": "ananya.g@example.com", "region": "East", "segment": "VIP", "orders": 12, "total_spend": 1670.00, "last_active": "2026-10-07"},
        {"customer_id": "CUST-1009", "name": "Marcus Brown", "email": "marcus.b@example.com", "region": "West", "segment": "At-Risk", "orders": 2, "total_spend": 120.50, "last_active": "2026-07-22"},
        {"customer_id": "CUST-1010", "name": "Sneha Reddy", "email": "sneha.r@example.com", "region": "South", "segment": "New", "orders": 1, "total_spend": 65.00, "last_active": "2026-10-11"},
    ]
    return pd.DataFrame(customers)


def answer_sample_question(question: str) -> str:
    """Provide realistic analytical answers to natural language questions."""
    q = question.lower()
    if "top" in q and "category" in q:
        return "**Top Category:** Electronics is leading revenue at **$48,500** (37.8% of total sales), followed by Fashion & Apparel at **$32,100**."
    elif "revenue" in q or "total" in q or "sales" in q:
        return "**Revenue Summary:** Current 30-day total revenue is **$128,450.00**, representing a **+14.2%** increase over the previous period."
    elif "vip" in q or "customer" in q or "spend" in q:
        return "**High Value Customers:** VIP segment accounts for **48%** of total revenue. Rahul Verma (`CUST-1003`) is the top spender with **$2,890.75** across 21 orders."
    elif "risk" in q or "churn" in q:
        return "**Churn Alert:** 2 customer accounts (`CUST-1005`, `CUST-1009`) have been inactive for over 60 days. Recommended action: trigger automated re-engagement promotion."
    else:
        return f"**Analysis for '{question}':**\nBased on ShopSphere data: Overall performance is strong with an Average Order Value of **$37.56** and healthy active customer retention across all 4 regions."
