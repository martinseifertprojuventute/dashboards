"""
Populate the dashboards app's local DuckDB from Snowflake.

Runs at app startup (blocking) via `streamlit_app.py`. Mirrors a
configurable list of Snowflake objects into a single local DuckDB file
using a dlt pipeline (full-replace via Arrow batches).

By default `OBJECTS_TO_MIRROR` is empty, so `populate()` is a no-op and
the demo pages run without any Snowflake connectivity. To wire your own
Snowflake objects, fill `OBJECTS_TO_MIRROR` with fully-qualified names
(e.g. `["MY_DB.MY_SCHEMA.SOME_TABLE", ...]`). The dlt pipeline will
mirror them into a DuckDB schema named after `LOCAL_SCHEMA_NAME`.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

# dlt's default `snake_case` naming convention lowercases identifiers, so
# Snowflake's `LEADSOURCE` would land in DuckDB as `leadsource`. DuckDB's
# pandas adapter then returns lowercase result column names, breaking
# pages that access columns by their Snowflake-style upper case
# (e.g. `df["LEADSOURCE"]`). Force the `direct` naming convention so
# storage and result-set casing match Snowflake.
os.environ.setdefault("SCHEMA__NAMING", "direct")

# dlt + pendulum/pytz interaction: snowflake-connector returns timestamps
# with pytz fixed-offset tzinfo, which pendulum.instance() can't handle
# without an explicit tz. Patch instance() to fall back to UTC for those.
import pendulum

_original_instance = pendulum.instance


def _patched_instance(dt, tz=None):
    if tz is None and dt.tzinfo is not None and not hasattr(dt.tzinfo, "key"):
        import pytz

        if isinstance(dt.tzinfo, pytz._FixedOffset):
            tz = pendulum.UTC
            dt = dt.astimezone(tz)
    return _original_instance(dt, tz=tz)


pendulum.instance = _patched_instance


# Fully-qualified Snowflake object names to mirror at startup.
# Empty by default — the demo pages generate synthetic data inline and
# do not need any Snowflake objects. Populate this list (and pick a
# `LOCAL_SCHEMA_NAME`) to wire real data sources.
OBJECTS_TO_MIRROR: list[str] = []

# Local DuckDB schema name the mirrored objects land under.
LOCAL_SCHEMA_NAME = "main"


def get_duckdb_path() -> Path:
    """Where the local DuckDB file lives.

    SPCS container: `/tmp/dashboards.duckdb` (tmpfs, ephemeral — re-built
    on every container start, which is what we want).
    Local dev: `<tempdir>/dashboards.duckdb`.
    Override with `DASHBOARDS_DUCKDB_PATH` if needed.
    """
    override = os.environ.get("DASHBOARDS_DUCKDB_PATH")
    if override:
        return Path(override)
    return Path(tempfile.gettempdir()) / "dashboards.duckdb"


def _local_table_name(fqn: str) -> str:
    return fqn.rsplit(".", 1)[-1].lower()


def _make_resource(fqn: str):
    import dlt
    from lib.snowflake import get_snowflake_connector_connection

    table = _local_table_name(fqn)

    @dlt.resource(name=table, write_disposition="replace", max_table_nesting=0)
    def _res():
        print(f"[{fqn}] opening connection", flush=True)
        conn = get_snowflake_connector_connection()
        try:
            cur = conn.cursor()
            cur.execute(f"SELECT * FROM {fqn}")
            rows = 0
            for batch in cur.fetch_arrow_batches():
                rows += batch.num_rows
                yield batch
            print(f"[{fqn}] yielded {rows} rows", flush=True)
            cur.close()
        finally:
            conn.close()

    return _res


def populate() -> Path | None:
    """Mirror the configured Snowflake objects into the local DuckDB file.

    No-op (returns None) when `OBJECTS_TO_MIRROR` is empty. Otherwise
    blocks until the schema is fully replaced and returns the DuckDB
    file path.
    """
    if not OBJECTS_TO_MIRROR:
        return None

    import dlt

    duckdb_path = get_duckdb_path()
    duckdb_path.parent.mkdir(parents=True, exist_ok=True)

    @dlt.source(name=LOCAL_SCHEMA_NAME, max_table_nesting=0)
    def _src():
        return [_make_resource(fqn) for fqn in OBJECTS_TO_MIRROR]

    print(
        f"=== mirroring {LOCAL_SCHEMA_NAME} ({len(OBJECTS_TO_MIRROR)} objects) ===",
        flush=True,
    )
    pipeline = dlt.pipeline(
        pipeline_name=f"dashboards_local_{LOCAL_SCHEMA_NAME}",
        destination=dlt.destinations.duckdb(str(duckdb_path)),
        dataset_name=LOCAL_SCHEMA_NAME,
    )
    load_info = pipeline.run(_src(), loader_file_format="parquet")
    print(load_info, flush=True)

    return duckdb_path


if __name__ == "__main__":
    populate()
