"""
Cache helpers for data-returning functions.

Default TTL is 1 hour, which pairs well with daily-refreshed source data
plus Snowflake's free 24h query result cache.

Two entry points:

    `cached_query()`      — decorator factory wrapping `st.cache_data`.
                            Lower-level; cache key is (function, args).

    `run_sql_template()`  — preferred for dashboard pages. Takes the SQL
                            template TEXT as an argument, so the cache
                            key naturally includes the template content.
                            Editing a .sql file invalidates the cache on
                            the next rerender, without restarting
                            Streamlit or clearing the cache manually.

Usage of `run_sql_template`::

    from lib.cache import run_sql_template

    SQL_DIR = Path(__file__).parent.parent / "sql" / "my_page"
    SQL_TEMPLATES = {p.stem: p.read_text() for p in SQL_DIR.glob("*.sql")}

    def load_kpi(start_date: date, end_date: date) -> int:
        df = run_sql_template(
            SQL_TEMPLATES["kpi"],
            start_date=start_date,
            end_date=end_date,
        )
        return int(df.iloc[0, 0]) if not df.empty else 0

The scalar unwrapping is done outside the cached function so the cache
key covers just the SQL text and parameters — the same DataFrame result
is reused for all callers that share those.
"""

from __future__ import annotations

import logging
import re
from datetime import date
from typing import Any

import pandas as pd
import streamlit as st

DEFAULT_TTL_SECONDS = 3600  # 1 hour

# Object names that must run on Snowflake (e.g. tables too large to mirror,
# or table functions that can't be materialized into DuckDB). Add patterns
# here when you have queries that should bypass the local DuckDB and hit
# Snowflake directly. Empty by default.
SNOWFLAKE_ONLY_PATTERNS: list[str] = []
_SNOWFLAKE_ONLY_RE = (
    re.compile("|".join(SNOWFLAKE_ONLY_PATTERNS), re.IGNORECASE)
    if SNOWFLAKE_ONLY_PATTERNS
    else None
)

_logger = logging.getLogger(__name__)


def _needs_snowflake(sql: str) -> bool:
    return bool(_SNOWFLAKE_ONLY_RE and _SNOWFLAKE_ONLY_RE.search(sql))


def cached_query(ttl: int = DEFAULT_TTL_SECONDS, show_spinner: bool = False):
    """Decorator factory wrapping st.cache_data with our default TTL.

    Lower-level than `run_sql_template`. Use when you need a custom
    caching pattern that doesn't fit "render a SQL template, return a
    DataFrame".
    """
    return st.cache_data(ttl=ttl, show_spinner=show_spinner)


@st.cache_data(ttl=DEFAULT_TTL_SECONDS, show_spinner=False)
def run_sql_template(sql_template: str, **params: Any) -> pd.DataFrame:
    """Render a SQL template with Python f-string substitution, execute
    it against the local DuckDB (or Snowflake, depending on what it
    touches), and return the result as a pandas DataFrame.

    **Routing**: any query whose rendered text matches a pattern in
    `SNOWFLAKE_ONLY_PATTERNS` runs on Snowflake. Everything else is
    attempted on the local DuckDB first (via `lib.local_duckdb.run_local`)
    and falls back to Snowflake on any error (file missing, DuckDB-
    incompatible syntax, populate not finished). A warning is logged
    on fallback.

    **Cache semantics**: the cache key is `(sql_template, **params)`.
    Because the full template text is part of the key, edits to the
    underlying .sql file invalidate the cache naturally on the next
    rerender — no need to restart Streamlit or clear the cache when
    you change a query.

    Date parameters are ISO-formatted automatically; other types pass
    through unchanged. Templates should use f-string placeholders
    matching the parameter names::

        # my_query.sql
        SELECT ... WHERE event_date BETWEEN '{start_date}' AND '{end_date}'
    """
    # Imported here (not at module top) so lib.cache stays importable
    # even when lib.snowflake would crash at import time in tests.
    from lib.snowflake import get_session

    formatted = {
        k: (v.isoformat() if isinstance(v, date) else v)
        for k, v in params.items()
    }
    rendered = sql_template.format(**formatted)

    if _needs_snowflake(rendered):
        return get_session().sql(rendered).to_pandas()

    # Local-DuckDB-eligible: try the mirror first, fall back to Snowflake
    # on any failure (file missing, syntax the DuckDB dialect rejects,
    # populate not finished). A successful fallback is still cached via
    # this function's outer @st.cache_data decorator, so we don't retry
    # the local path on every rerender during an incident.
    try:
        from lib.local_duckdb import run_local
        return run_local(rendered)
    except Exception as e:
        _logger.warning(
            "Local DuckDB query failed (%s: %s); falling back to Snowflake",
            type(e).__name__,
            str(e).splitlines()[0] if str(e) else "",
        )
        return get_session().sql(rendered).to_pandas()
