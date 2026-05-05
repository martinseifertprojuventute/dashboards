"""
Sales — Overview (sample dashboard)

Generic sample page used as a template. Generates synthetic data
locally so the demo runs without any Snowflake connectivity.

Replace the `_load_*` helpers with real `run_sql_template(...)` calls
against your own Snowflake objects when wiring up production data.
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from lib.brand import BRAND_BLUE, BRAND_GREEN, BRAND_YELLOW, CATEGORICAL
from lib.components import (
    date_range_picker,
    format_count,
    kpi_card,
    render_dashboard_picker,
)

st.set_page_config(page_title="Sales — Overview", layout="wide")
st.title("Sales — Overview")

with st.expander("About this page", icon=":material/info:"):
    st.markdown(
        """
        Sample dashboard showing four headline KPIs plus two charts:
        revenue trend over time and revenue split by region.

        All numbers on this page are **synthetic** — generated locally
        by `numpy` for demo purposes. To wire it to real data, replace
        the `_load_*` helpers with `run_sql_template(...)` calls
        against your own Snowflake (or local DuckDB) objects.
        """
    )

render_dashboard_picker("Sales — Overview")

# --------------------------------------------------------------------
# Sidebar filters
# --------------------------------------------------------------------

with st.sidebar:
    st.header("Filters")
    start_date, end_date = date_range_picker(
        "Period",
        default_years=2,
        key="sales_date_range",
    )
    regions = st.multiselect(
        "Region",
        options=["North", "South", "East", "West"],
        default=["North", "South", "East", "West"],
        key="sales_regions",
    )

# --------------------------------------------------------------------
# Synthetic data
# --------------------------------------------------------------------

@st.cache_data(ttl=3600, show_spinner=False)
def _load_daily_sales(start: date, end: date, regions: tuple[str, ...]) -> pd.DataFrame:
    """One synthetic row per day per region."""
    rng = np.random.default_rng(seed=hash((start, end, regions)) & 0xFFFFFFFF)
    days = pd.date_range(start, end, freq="D")
    rows = []
    for region in regions:
        base = {"North": 1200, "South": 900, "East": 1100, "West": 1000}[region]
        seasonality = 1 + 0.25 * np.sin(np.linspace(0, 6 * np.pi, len(days)))
        noise = rng.normal(1.0, 0.15, len(days))
        revenue = base * seasonality * noise
        orders = (revenue / rng.uniform(40, 60, len(days))).round().astype(int)
        for d, r, o in zip(days, revenue, orders):
            rows.append({"date": d, "region": region, "revenue": float(r), "orders": int(o)})
    return pd.DataFrame(rows)


df = _load_daily_sales(start_date, end_date, tuple(regions))

# --------------------------------------------------------------------
# KPI cards
# --------------------------------------------------------------------

if df.empty:
    st.info("No data in the selected period.", icon=":material/info:")
    st.stop()

total_revenue = df["revenue"].sum()
total_orders = int(df["orders"].sum())
aov = total_revenue / total_orders if total_orders else 0.0
unique_customers = int(total_orders * 0.72)  # synthetic ratio

# Prior-period comparison (same length window, immediately before)
period_days = (end_date - start_date).days + 1
prev_start = start_date - timedelta(days=period_days)
prev_end = start_date - timedelta(days=1)
prev_df = _load_daily_sales(prev_start, prev_end, tuple(regions))
prev_revenue = prev_df["revenue"].sum() if not prev_df.empty else 0.0
prev_orders = int(prev_df["orders"].sum()) if not prev_df.empty else 0


def _delta(cur: float, prev: float) -> str | None:
    if not prev:
        return None
    return f"{(cur - prev) / prev * 100:+.1f}%"


c1, c2, c3, c4 = st.columns(4)
with c1:
    kpi_card("Revenue", f"${total_revenue:,.0f}", delta=_delta(total_revenue, prev_revenue))
with c2:
    kpi_card("Orders", format_count(total_orders), delta=_delta(total_orders, prev_orders))
with c3:
    kpi_card("Avg Order Value", f"${aov:,.2f}")
with c4:
    kpi_card("Unique Customers", format_count(unique_customers))

st.divider()

# --------------------------------------------------------------------
# Revenue trend (monthly)
# --------------------------------------------------------------------

st.subheader("Revenue trend")

monthly = (
    df.assign(month=df["date"].dt.to_period("M").dt.to_timestamp())
    .groupby("month", as_index=False)["revenue"].sum()
)
fig = px.line(
    monthly,
    x="month",
    y="revenue",
    markers=True,
    labels={"month": "Month", "revenue": "Revenue ($)"},
)
fig.update_traces(line_color=BRAND_YELLOW, line_width=3, marker_size=8)
fig.update_layout(
    yaxis=dict(tickformat=",.0f", separatethousands=True, rangemode="tozero"),
    margin=dict(l=0, r=0, t=10, b=0),
    hovermode="x unified",
)
st.plotly_chart(fig, width="stretch")

# --------------------------------------------------------------------
# Revenue by region
# --------------------------------------------------------------------

st.subheader("Revenue by region")

by_region = df.groupby("region", as_index=False)["revenue"].sum().sort_values("revenue", ascending=False)
fig2 = px.bar(
    by_region,
    x="region",
    y="revenue",
    color="region",
    color_discrete_sequence=CATEGORICAL,
    labels={"region": "Region", "revenue": "Revenue ($)"},
)
fig2.update_layout(
    yaxis=dict(tickformat=",.0f", separatethousands=True),
    margin=dict(l=0, r=0, t=10, b=0),
    showlegend=False,
)
st.plotly_chart(fig2, width="stretch")
