"""
Local DuckDB connection + query executor for the dashboards app.

`lib.populate.populate()` writes the mirrored Snowflake objects into a
single DuckDB file (under `lib.populate.LOCAL_SCHEMA_NAME`). This module
opens that file read-only and executes rendered SQL templates against
it. Routing (and Snowpark fallback) lives in `lib.cache`.

Schema rewrite: SQL templates may reference `<DB>.<SCHEMA>.<OBJECT>` so
they look identical to their Snowflake counterparts. Configure
`SCHEMA_REWRITE_RULES` below to map those references onto the local
DuckDB layout (e.g. drop the database prefix, keep only the schema and
object name). When no rules are configured, SQL is passed through
unchanged.

Connection is cached per Streamlit worker via `@st.cache_resource`.
"""

from __future__ import annotations

import re

import pandas as pd
import streamlit as st

from lib.populate import get_duckdb_path, populate


# Optional pattern → replacement rules applied to every SQL string before
# execution against the local DuckDB. Each entry is a (regex, replacement)
# pair compatible with `re.sub`. Empty by default — add rules when your
# SQL templates use fully-qualified Snowflake names that need to be
# rewritten to the local DuckDB layout.
#
# Example: drop the `MY_DB.` database prefix, keep schema + object name::
#
#     SCHEMA_REWRITE_RULES = [
#         (re.compile(r"\bMY_DB\.(\w+)\.(\w+)", re.IGNORECASE),
#          lambda m: f"{m.group(1).lower()}.{m.group(2).lower()}"),
#     ]
SCHEMA_REWRITE_RULES: list[tuple[re.Pattern, object]] = []


def _rewrite_to_local(sql: str) -> str:
    for pattern, repl in SCHEMA_REWRITE_RULES:
        sql = pattern.sub(repl, sql)
    return sql


@st.cache_resource(show_spinner=False)
def _ensure_populated() -> str | None:
    """Run the dlt populate exactly once per Streamlit worker.

    Returns the absolute DuckDB file path, or None if there is nothing
    to mirror (`lib.populate.OBJECTS_TO_MIRROR` is empty). Subsequent
    calls hit the cache and skip the populate.
    """
    with st.spinner("Loading data into local DuckDB …"):
        path = populate()
    return str(path) if path is not None else None


@st.cache_resource(show_spinner=False)
def get_local_conn():
    """Return a cached read-only DuckDB connection to the populated file."""
    import duckdb

    db_path = _ensure_populated()
    if db_path is None:
        # Nothing was mirrored. Open an in-memory DB so callers still get
        # a working connection (queries that reference missing tables
        # will raise and trigger the Snowflake fallback in lib.cache).
        return duckdb.connect(":memory:", read_only=False)
    return duckdb.connect(db_path, read_only=True)


def run_local(sql: str) -> pd.DataFrame:
    """Execute a rendered SQL string against the local DuckDB and return
    a DataFrame. Applies `SCHEMA_REWRITE_RULES` first.
    """
    rewritten = _rewrite_to_local(sql)
    return get_local_conn().execute(rewritten).df()
