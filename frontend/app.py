"""ShopSphere Analytics - Streamlit Frontend Dashboard."""

import streamlit as st
import pandas as pd

from sample_data import (
    get_sample_kpis,
    get_sales_trend_data,
    get_category_sales_data,
    get_customer_table_data,
    answer_sample_question,
)

# 1. Page Configuration
st.set_page_config(
    page_title="ShopSphere Analytics",
    page_icon="🛍️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 2. Custom CSS for polished, clean UI
st.markdown("""
<style>
    .main-title {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1E293B;
        margin-bottom: 0.2rem;
    }
    .sub-title {
        font-size: 1rem;
        color: #64748B;
        margin-bottom: 1.5rem;
    }
    .metric-card {
        background-color: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 10px;
        padding: 16px;
        text-align: center;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    .metric-val {
        font-size: 1.8rem;
        font-weight: 700;
        color: #0F172A;
    }
    .metric-lbl {
        font-size: 0.85rem;
        color: #64748B;
        margin-top: 4px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .metric-delta {
        font-size: 0.85rem;
        font-weight: 600;
        color: #10B981;
        margin-top: 2px;
    }
    .section-header {
        font-size: 1.3rem;
        font-weight: 600;
        color: #334155;
        margin-top: 1.5rem;
        margin-bottom: 0.8rem;
    }
</style>
""", unsafe_allow_html=True)

# 3. Sidebar Filters
with st.sidebar:
    st.image("https://api.iconify.design/lucide:shopping-bag.svg?color=%233b82f6", width=50)
    st.title("ShopSphere")
    st.caption("E-Commerce Intelligence Platform")
    st.markdown("---")

    st.subheader("Filters")
    time_range = st.selectbox(
        "Time Range",
        ["Last 30 Days", "Last 7 Days", "Quarter to Date", "Year to Date"],
        index=0,
    )

    region_filter = st.multiselect(
        "Region",
        ["All Regions", "North", "South", "East", "West"],
        default=["All Regions"],
    )

    segment_filter = st.multiselect(
        "Customer Segment",
        ["All Segments", "VIP", "Regular", "New", "At-Risk"],
        default=["All Segments"],
    )

    st.markdown("---")
    st.info("💡 **Mode:** Running in Demo Mode with ShopSphere Sample Data.")

# 4. Top Header
st.markdown('<div class="main-title">ShopSphere Analytics 🛍️</div>', unsafe_allow_html=True)
st.markdown(f'<div class="sub-title">Real-time Performance, Customer Intelligence & Sales Insights ({time_range})</div>', unsafe_allow_html=True)

# 5. KPI Cards
kpis = get_sample_kpis()
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-val">${kpis['total_revenue']:,.2f}</div>
        <div class="metric-lbl">Total Revenue</div>
        <div class="metric-delta">{kpis['revenue_growth']}</div>
    </div>
    """, unsafe_allow_html=True)

with col2:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-val">{kpis['total_orders']:,}</div>
        <div class="metric-lbl">Total Orders</div>
        <div class="metric-delta">{kpis['orders_growth']}</div>
    </div>
    """, unsafe_allow_html=True)

with col3:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-val">${kpis['avg_order_value']:.2f}</div>
        <div class="metric-lbl">Avg Order Value (AOV)</div>
        <div class="metric-delta">{kpis['aov_growth']}</div>
    </div>
    """, unsafe_allow_html=True)

with col4:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-val">{kpis['active_customers']:,}</div>
        <div class="metric-lbl">Active Customers</div>
        <div class="metric-delta">{kpis['customer_growth']}</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# 6. Interactive Analytics & Charts
col_chart1, col_chart2 = st.columns([3, 2])

with col_chart1:
    st.markdown('<div class="section-header">📈 Revenue & Order Trend</div>', unsafe_allow_html=True)
    sales_df = get_sales_trend_data(days=30)
    chart_view = st.radio("Metric", ["Revenue ($)", "Orders"], horizontal=True, label_visibility="collapsed")
    chart_data = sales_df.set_index("Date")[[chart_view]]
    st.line_chart(chart_data, color="#3B82F6")

with col_chart2:
    st.markdown('<div class="section-header">🍩 Revenue by Category</div>', unsafe_allow_html=True)
    cat_df = get_category_sales_data()
    cat_chart_data = cat_df.set_index("Category")[["Revenue ($)"]]
    st.bar_chart(cat_chart_data, color="#10B981")

# 7. Customer Table Section
st.markdown('<div class="section-header">👥 Customer Directory & Spend Analysis</div>', unsafe_allow_html=True)

raw_cust_df = get_customer_table_data()

# Filter customer records
cust_df = raw_cust_df.copy()
if "All Regions" not in region_filter and region_filter:
    cust_df = cust_df[cust_df["region"].isin(region_filter)]
if "All Segments" not in segment_filter and segment_filter:
    cust_df = cust_df[cust_df["segment"].isin(segment_filter)]

search_query = st.text_input("🔍 Search Customers (by name or email):", placeholder="e.g. Rahul, Emily, @example.com")
if search_query:
    q = search_query.lower()
    cust_df = cust_df[
        cust_df["name"].str.lower().str.contains(q) | cust_df["email"].str.lower().str.contains(q)
    ]

# Display table
st.dataframe(
    cust_df.rename(columns={
        "customer_id": "Customer ID",
        "name": "Full Name",
        "email": "Email Address",
        "region": "Region",
        "segment": "Segment",
        "orders": "Total Orders",
        "total_spend": "Total Spend ($)",
        "last_active": "Last Active Date",
    }),
    use_container_width=True,
    hide_index=True,
)

# Download CSV button
csv_data = cust_df.to_csv(index=False).encode("utf-8")
st.download_button(
    label="📥 Export Filtered Customers (CSV)",
    data=csv_data,
    file_name="shopsphere_customers.csv",
    mime="text/csv",
)

st.markdown("<br>", unsafe_allow_html=True)

# 8. Interactive Question Input Box
st.markdown('<div class="section-header">💬 Ask ShopSphere Analytics Assistant</div>', unsafe_allow_html=True)
st.caption("Ask natural-language questions about sales trends, high-value customers, categories, or churn risk.")

# Sample prompt pills
st.markdown("**Suggested Questions:**")
c_p1, c_p2, c_p3 = st.columns(3)
preset_question = None

if c_p1.button("📊 Top product category?"):
    preset_question = "What is the top product category by revenue?"
if c_p2.button("💰 Who are our VIP customers?"):
    preset_question = "List high value VIP customers and total spend"
if c_p3.button("⚠️ Any churn risk accounts?"):
    preset_question = "Which customers are at risk of churning?"

user_query = st.text_input(
    "Type your question:",
    value=preset_question or "",
    placeholder="e.g., What was our average order value? or Top sales category?",
)

if user_query:
    with st.spinner("Analyzing ShopSphere metrics..."):
        response = answer_sample_question(user_query)
        st.success(response)

st.markdown("---")
st.caption("ShopSphere Analytics v1.0 • Built with Streamlit • Branch: `vikrant`")
