"""
App-wide boot guard: full-viewport overlay during cold-start populate.

Streamlit's built-in spinners (`st.spinner`, `st.cache_resource(show_spinner=…)`)
attach to whichever container the calling code is currently rendering into
— sidebar, main area, an `st.empty` slot, etc. For an app whose populate
is triggered by whichever query happens to fire first on the active page,
that means the spinner ends up in unpredictable places (often the
sidebar's filter widgets) and is easy to miss while the user stares at an
otherwise-empty page for ~1 minute.

`ensure_data_ready()` paints a fixed-position overlay across the entire
viewport, runs the populate, then clears the overlay. The overlay only
renders on truly cold-cache hits — once the populate has completed within
a worker process, a module-level flag short-circuits the overlay path so
warm reruns don't flash.
"""

from __future__ import annotations

import streamlit as st

# Module attributes survive Streamlit script reruns within the same
# worker process. After the first successful populate, every subsequent
# rerun skips overlay rendering and only the (now-instant) cached
# `_ensure_populated` lookup remains.
_data_ready: bool = False


_OVERLAY_HTML = """
<style>
.dashboards-loading-overlay {
    position: fixed;
    inset: 0;
    background: rgba(255, 255, 255, 0.92);
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    z-index: 99999;
    font-family: 'Source Sans Pro', sans-serif;
}
.dashboards-loading-overlay .spinner {
    border: 6px solid #f0f2f6;
    border-top: 6px solid #ff4b4b;
    border-radius: 50%;
    width: 56px;
    height: 56px;
    animation: dashboards-spin 1s linear infinite;
}
.dashboards-loading-overlay .label {
    margin-top: 1.25rem;
    font-size: 1.05rem;
    color: #262730;
    text-align: center;
    max-width: 32rem;
    line-height: 1.4;
}
@keyframes dashboards-spin {
    0%   { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
}
</style>
<div class="dashboards-loading-overlay">
  <div class="spinner"></div>
  <div class="label">
    Loading data into local DuckDB &hellip;<br/>
    This can take ~1 minute on first launch.
  </div>
</div>
"""


def ensure_data_ready() -> None:
    """Block on the populate; paint a full-viewport overlay on cold cache.

    Idempotent. Call once per page render — `render_dashboard_picker`
    does this at its top, so every page that uses the picker is covered.

    When `lib.populate.OBJECTS_TO_MIRROR` is empty (the demo default),
    the populate returns immediately and the overlay never appears.
    """
    global _data_ready
    from lib.local_duckdb import _ensure_populated
    from lib.populate import OBJECTS_TO_MIRROR

    if _data_ready or not OBJECTS_TO_MIRROR:
        _ensure_populated()
        _data_ready = True
        return

    placeholder = st.empty()
    placeholder.markdown(_OVERLAY_HTML, unsafe_allow_html=True)
    try:
        _ensure_populated()
        _data_ready = True
    finally:
        placeholder.empty()
