"""
Operations — Metrics (sample dashboard)

Generic sample page used as a template. Generates synthetic data
locally so the demo runs without any Snowflake connectivity.

Replace the `_load_*` helpers with real `run_sql_template(...)` calls
against your own Snowflake objects when wiring up production data.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from lib.brand import (
    CATEGORICAL,
    SEMANTIC_NEGATIVE,
    SEMANTIC_NEUTRAL,
    SEMANTIC_POSITIVE,
)
from lib.components import (
    format_count,
    kpi_card,
    render_dashboard_picker,
)

st.set_page_config(page_title="Operations — Metrics", layout="wide")
st.title("Operations — Metrics")

with st.expander("About this page", icon=":material/info:"):
    st.markdown(
        """
        Sample dashboard showing service-level operational metrics:
        active users, latency, error rate and throughput, plus a
        time-series chart of throughput and a per-service error
        breakdown.

        All numbers on this page are **synthetic** — generated locally
        by `numpy` for demo purposes. To wire it to real data, replace
        the `_load_*` helpers with `run_sql_template(...)` calls
        against your own Snowflake (or local DuckDB) objects.
        """
    )

render_dashboard_picker("Operations — Metrics")

# --------------------------------------------------------------------
# Sidebar filters
# --------------------------------------------------------------------

with st.sidebar:
    st.header("Filters")
    window_hours = st.selectbox(
        "Time window",
        options=[6, 12, 24, 72, 168],
        index=2,
        format_func=lambda h: f"Last {h} h" if h < 168 else "Last 7 days",
        key="ops_window",
    )
    services = st.multiselect(
        "Services",
        options=["api", "web", "worker", "auth"],
        default=["api", "web", "worker", "auth"],
        key="ops_services",
    )

# --------------------------------------------------------------------
# Synthetic data
# --------------------------------------------------------------------

@st.cache_data(ttl=300, show_spinner=False)
def _load_throughput(window_hours: int, services: tuple[str, ...]) -> pd.DataFrame:
    """One synthetic row per minute per service."""
    rng = np.random.default_rng(seed=hash((window_hours, services)) & 0xFFFFFFFF)
    end = datetime.utcnow().replace(second=0, microsecond=0)
    start = end - timedelta(hours=window_hours)
    minutes = pd.date_range(start, end, freq="1min")
    rows = []
    for svc in services:
        base = {"api": 320, "web": 410, "worker": 90, "auth": 180}[svc]
        seasonality = 1 + 0.35 * np.sin(np.linspace(0, 4 * np.pi, len(minutes)))
        rps = np.maximum(0, base * seasonality + rng.normal(0, base * 0.08, len(minutes)))
        errs = rng.binomial(rps.astype(int), p=0.012)
        latency = np.maximum(40, rng.normal(120, 25, len(minutes)) + (errs * 5))
        for ts, r, e, l in zip(minutes, rps, errs, latency):
            rows.append(
                {"ts": ts, "service": svc, "rps": float(r), "errors": int(e), "latency_ms": float(l)}
            )
    return pd.DataFrame(rows)


df = _load_throughput(window_hours, tuple(services))

if df.empty:
    st.info("No data in the selected window.", icon=":material/info:")
    st.stop()

# --------------------------------------------------------------------
# KPI cards
# --------------------------------------------------------------------

active_users = int(df["rps"].sum() / max(window_hours, 1) * 0.45)
avg_latency = float(df["latency_ms"].mean())
total_requests = float(df["rps"].sum() * 60)  # rps -> per-minute rows
total_errors = int(df["errors"].sum())
error_rate_pct = (total_errors / max(total_requests, 1)) * 100
avg_rps = float(df["rps"].mean())

c1, c2, c3, c4 = st.columns(4)
with c1:
    kpi_card("Active Users", format_count(active_users))
with c2:
    kpi_card("Avg Latency (p50)", f"{avg_latency:,.0f} ms")
with c3:
    kpi_card("Error Rate", f"{error_rate_pct:.2f}%")
with c4:
    kpi_card("Throughput (avg)", f"{avg_rps:,.0f} rps")

st.divider()

# --------------------------------------------------------------------
# Throughput over time
# --------------------------------------------------------------------

st.subheader("Throughput over time")

# Aggregate to 5-minute buckets so the line stays readable on long windows.
bucket = df.assign(bucket=df["ts"].dt.floor("5min"))
agg = bucket.groupby(["bucket", "service"], as_index=False)["rps"].mean()

fig = px.line(
    agg,
    x="bucket",
    y="rps",
    color="service",
    labels={"bucket": "Time", "rps": "Requests / sec", "service": "Service"},
    color_discrete_sequence=CATEGORICAL,
)
fig.update_traces(line_width=2)
fig.update_layout(
    yaxis=dict(rangemode="tozero"),
    margin=dict(l=0, r=0, t=10, b=0),
    hovermode="x unified",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
)
st.plotly_chart(fig, width="stretch")

# --------------------------------------------------------------------
# Error count by service
# --------------------------------------------------------------------

st.subheader("Errors by service")

err_by_svc = (
    df.groupby("service", as_index=False)["errors"].sum().sort_values("errors", ascending=False)
)
fig2 = px.bar(
    err_by_svc,
    x="service",
    y="errors",
    labels={"service": "Service", "errors": "Errors"},
)
# Color the worst offender red, the rest neutral blue, healthy green.
worst = err_by_svc.iloc[0]["service"] if not err_by_svc.empty else None
best = err_by_svc.iloc[-1]["service"] if not err_by_svc.empty else None
fig2.update_traces(
    marker_color=[
        SEMANTIC_NEGATIVE if s == worst else SEMANTIC_POSITIVE if s == best else SEMANTIC_NEUTRAL
        for s in err_by_svc["service"]
    ]
)
fig2.update_layout(margin=dict(l=0, r=0, t=10, b=0), showlegend=False)
st.plotly_chart(fig2, width="stretch")
