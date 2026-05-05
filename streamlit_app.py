"""
Sample Dashboards — SPCS-hosted Streamlit app.

Landing / info page. The actual dashboards live in pages/. This file
exists only to give new users orientation: which pages are available
and how to navigate them.
"""
import streamlit as st

from lib.components import render_dashboard_picker

st.set_page_config(
    page_title="Sample Dashboards",
    page_icon=":bar_chart:",
    layout="wide",
    initial_sidebar_state="expanded",
)

# `render_dashboard_picker` calls `lib.boot.ensure_data_ready()` first,
# which blocks on the cold-start populate behind a full-viewport overlay.
# Same call lives in every page, so deep links are covered too.
render_dashboard_picker("Start / Info")

st.title("Sample Dashboards")

st.markdown(
    "Template Streamlit-in-SPCS app with two sample dashboards. "
    "Pick one from the **dropdown** in the sidebar, or use this app "
    "as a starting point for your own."
)

st.divider()

st.subheader("Pages")
st.markdown(
    """
    | Page | Description |
    |---|---|
    | **Sales — Overview** | Revenue KPIs, monthly trend, region breakdown |
    | **Operations — Metrics** | Active users, latency, throughput, errors |

    Both pages generate synthetic data locally so the demo runs
    without any Snowflake objects. Replace the `_load_*` helpers in
    each page with real `run_sql_template(...)` calls when wiring to
    production data.
    """
)

st.divider()

st.subheader("Navigation")
st.markdown(
    """
    - **Pick a dashboard**: dropdown in the sidebar
    - **Filters**: appear under the dropdown, page-specific
    - **Page summary**: in the `About this page` expander above the filters
    """
)
