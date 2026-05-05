"""
Reusable UI components for the dashboards app.

Deliberately minimal — page-specific filter bars and charts stay in the
page files. These are the building blocks that get duplicated across pages
(KPI cards, number formatting, standard date range picker).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

# Optional app logo. Resolved relative to this file so it works regardless
# of which page is calling us. Drop a `logo.png` at the repo root and it
# will appear in the sidebar. A square mark works best — it renders
# cleanly both in the expanded sidebar and in the collapsed-sidebar icon
# slot without getting squished.
_LOGO_PATH = Path(__file__).resolve().parent.parent / "logo.png"

# ----- Dashboard navigation -----

# Ordered list of (path, display title) for the dashboard selector dropdown.
# The path is relative to the app root — what
# `st.switch_page` expects. Add new pages here to make them routable via the
# selectbox; removing the default Streamlit multi-page nav is handled by
# `render_dashboard_picker` via injected CSS.
_DASHBOARD_PAGES: tuple[tuple[str, str], ...] = (
    ("streamlit_app.py", "Start / Info"),
    ("pages/Sales_Overview.py", "Sales — Overview"),
    ("pages/Operations_Metrics.py", "Operations — Metrics"),
)


def render_dashboard_picker(current_title: str) -> None:
    """Render a compact dashboard selector in the sidebar.

    Hides the default Streamlit multi-page nav list (which grows vertically
    with one entry per page) and replaces it with a single `st.selectbox`.
    Saves a lot of sidebar space once the app has more than 4–5 pages.

    Call once near the top of each page — pass the page's own display
    title so the selectbox starts on the current page. When the user picks
    a different option, `st.switch_page` routes them there.

    `current_title` must match one of the titles in `_DASHBOARD_PAGES`;
    mismatches fall back to the first page silently rather than erroring.

    Also runs the cold-start data populate guard: every page calls this
    near its top, so wiring `ensure_data_ready()` here covers the whole
    app without per-page edits.
    """
    from lib.boot import ensure_data_ready

    ensure_data_ready()

    # Hide the default auto-generated sidebar nav and widen the
    # sidebar uniformly across all pages. `!important` is needed
    # because Streamlit's own styles come later in the cascade.
    st.markdown(
        """
        <style>
        [data-testid="stSidebarNav"] { display: none !important; }
        /* Widen the sidebar only when it is expanded. Guarding on
           `aria-expanded="true"` stops the width reservation from
           lingering when the user collapses the sidebar. */
        [data-testid="stSidebar"][aria-expanded="true"] {
            min-width: 380px !important;
            width: 380px !important;
        }
        [data-testid="stSidebar"] > div { overflow-x: hidden; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # Home page always stays at the top; everything else is sorted
    # alphabetically by display title so the dropdown is predictable.
    home_entries = [p for p in _DASHBOARD_PAGES if p[0] == "streamlit_app.py"]
    other_entries = sorted(
        (p for p in _DASHBOARD_PAGES if p[0] != "streamlit_app.py"),
        key=lambda pt: pt[1],
    )
    ordered_pages = [*home_entries, *other_entries]

    titles = [t for _, t in ordered_pages]
    path_by_title = {t: p for p, t in ordered_pages}

    try:
        idx = titles.index(current_title)
    except ValueError:
        idx = 0

    if _LOGO_PATH.is_file():
        st.logo(str(_LOGO_PATH), size="large")

    with st.sidebar:
        picked = st.selectbox(
            "Dashboard",
            options=titles,
            index=idx,
            key="_dashboard_picker",
            label_visibility="collapsed",
        )
        st.divider()

    # If the user picked a different option than the current page, route
    # to it. `st.switch_page` raises and restarts the script on a new page;
    # the call after it never runs during navigation.
    if picked != current_title:
        st.switch_page(path_by_title[picked])

# ----- Number formatting -----


def format_count(n: float | int | None) -> str:
    """Integer count with thousands separator."""
    if n is None:
        return "—"
    return f"{int(n):,}"


# ----- KPI card -----


def kpi_card(
    label: str,
    value: Any,
    *,
    delta: Any = None,
    help: str | None = None,
) -> None:
    """Thin wrapper around st.metric for consistent KPI display.

    Pass pre-formatted strings for value/delta to keep formatting logic
    in the calling page.
    """
    st.metric(label=label, value=value, delta=delta, help=help)


def yoy_metric(
    label: str,
    value_str: str,
    cur: float | int | None,
    prev: float | int | None,
    prev_formatted: str,
) -> None:
    """KPI card with a YoY delta whose hover tooltip exposes the prior value.

    Used on pages that want the prior-period value available on hover
    without burning a second column of screen real estate. Styled to
    approximate `st.metric` (grey label, large bold value, coloured delta
    row underneath) and rendered as raw HTML so we can attach a `title`
    attribute to the delta div.
    """
    if prev is None or (isinstance(prev, float) and pd.isna(prev)) or prev == 0:
        delta_html = '<div style="height:1.25rem;"></div>'
    else:
        pct = (cur - prev) / prev * 100
        sign = "+" if pct >= 0 else "−"
        color = "#09ab3b" if pct >= 0 else "#ff2b2b"
        arrow = "▲" if pct >= 0 else "▼"
        tooltip = f"Previous period (same length): {prev_formatted}"
        delta_html = (
            f'<div title="{tooltip}" '
            f'style="color:{color}; font-size:0.875rem; '
            f'margin-top:0.25rem; line-height:1.25rem; cursor:help;">'
            f"{arrow} {sign}{abs(pct):.1f} %</div>"
        )

    st.markdown(
        f"""
        <div style="padding:0.25rem 0;">
            <div style="color:rgba(49,51,63,.6); font-size:0.875rem;
                        line-height:1.25rem;">{label}</div>
            <div style="font-size:2rem; font-weight:400; line-height:2.25rem;
                        color:rgb(49,51,63);">{value_str}</div>
            {delta_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


# ----- Date range picker -----


def date_range_picker(
    label: str = "Period",
    *,
    default_years: int = 5,
    default_start: date | None = None,
    default_end: date | None = None,
    include_future: bool = False,
    key: str | None = None,
) -> tuple[date, date]:
    """Date range picker.

    Default behavior (all kwargs omitted): (Jan 1 of <default_years> years
    ago, today), capped at today.

    Override points:
      - `default_start` / `default_end`: pass explicit dates to replace the
        computed defaults.
      - `include_future=True`: removes the `max_value=today` cap so users
        can select forward-looking dates.

    Returns a (start, end) tuple of date objects.
    """
    today = date.today()
    if default_start is None:
        default_start = date(today.year - default_years, 1, 1)
    if default_end is None:
        default_end = today

    max_value = None if include_future else today

    selection = st.date_input(
        label,
        value=(default_start, default_end),
        max_value=max_value,
        key=key,
        format="YYYY-MM-DD",
    )
    # st.date_input returns a tuple when given a tuple default, but only a
    # single date if the user selects just one. Normalize to a pair.
    if isinstance(selection, tuple) and len(selection) == 2:
        return selection
    if isinstance(selection, date):
        return (selection, selection)
    return (default_start, default_end)
