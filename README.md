# Sample Dashboards (Streamlit on SPCS)

A template Streamlit app deployable to Snowflake Container Services (SPCS). Two sample dashboards are included; the rest of the repo is a starting point you can adapt to your own data.

## Layout

```
streamlit_app.py                  Home / landing page; triggers startup populate
pages/
  Sales_Overview.py               Revenue KPIs, monthly trend, region breakdown
  Operations_Metrics.py           Active users, latency, throughput, errors
lib/
  snowflake.py                    Snowpark session + connector factory (SPCS OAuth + local keypair)
  populate.py                     dlt pipeline: Snowflake → local DuckDB at startup (no-op by default)
  local_duckdb.py                 Read-only DuckDB conn + optional schema rewrite
  cache.py                        run_sql_template() — routing + fallback + TTL cache
  auth.py                         Role-based page gating
  brand.py                        Color palette (categorical, sequential, semantic)
  components.py                   KPI cards, dashboard picker, date picker
  boot.py                         Cold-start overlay
  hierarchy_filter.py             Reusable N-level hierarchy filter widget
Dockerfile                        Python 3.13 + streamlit on 8501
requirements.txt                  streamlit, snowpark, plotly, pandas, duckdb, dlt
dashboards-app.yaml               SPCS service spec
snowflake_setup.sql               First-time service creation + grants
snowflake_tasks.sql               Scheduled start/stop tasks
```

## Sample pages

Both pages generate **synthetic data locally** with `numpy`, so the demo runs out of the box without any Snowflake objects, warehouses, or grants. To wire real data, replace the `_load_*` helpers in each page with `run_sql_template(...)` calls that target your own Snowflake schema.

## Hosting (when deployed to SPCS)

- **SPCS service**: `<your-db>.<your-schema>.DASHBOARDS_APP` on a compute pool of your choice
- **Image**: `<your-account>.registry.snowflakecomputing.com/<your-db>/<your-schema>/<your-image-repo>/dashboards-app:<version>`
- **Port**: 8501
- **Auth**: Snowflake SSO / OAuth, with optional in-app role gating via `lib/auth.py`

## Data layer (optional, for production wiring)

### Local DuckDB mirror, populated at startup
On every container start, `lib/populate.py` runs a dlt pipeline that full-replaces the configured Snowflake objects into a local DuckDB file at `/tmp/dashboards.duckdb`. Out of the box, `OBJECTS_TO_MIRROR` is empty so the populate is a no-op. Fill it with fully-qualified Snowflake names (e.g. `["MY_DB.MY_SCHEMA.SOME_TABLE", ...]`) to start mirroring.

### Snowflake fallback
Every query flows through `run_sql_template(sql, **params)` in [lib/cache.py](lib/cache.py). The default behavior:

1. If the rendered SQL matches any pattern in `SNOWFLAKE_ONLY_PATTERNS` (empty by default), run it on Snowflake via Snowpark.
2. Otherwise, try the local DuckDB first. On any failure (file missing, populate not finished, DuckDB rejects Snowflake-specific syntax) fall back to Snowflake and log a warning.

Successful fallbacks are cached for the TTL so a degraded local path does not thrash on every rerun.

### Schema rewrite
`lib/local_duckdb.py` exposes a `SCHEMA_REWRITE_RULES` list that lets you keep one SQL source per query for both backends — your templates can use Snowflake-style fully qualified names while DuckDB sees them rewritten to its local layout. Empty by default.

## Caching

- `@st.cache_resource` on every connection factory (one Snowpark session, one DuckDB connection, one populate run per worker).
- `@st.cache_data(ttl=3600)` on `run_sql_template` — cache key is `(sql_template, **params)`, so editing a `.sql` file naturally invalidates the cache next rerun.
- Snowflake's built-in 24h query result cache handles cross-user deduplication on the Snowflake path.

## Local development

```bash
streamlit run streamlit_app.py
```

The two sample pages do not need Snowflake credentials. If you wire real data and want to run locally, set up a profile in `~/.snowflake/connections.toml` (named `default` by default) and optionally `export SNOWFLAKE_CONNECTION=<profile>`.

If your repo-root `.venv` has incompatible `duckdb`, use an isolated env:

```bash
uv run --isolated --with-requirements requirements.txt streamlit run streamlit_app.py
```

To force a fresh populate (when wired): delete `<tempdir>/dashboards.duckdb` and restart the Streamlit server.

## Deployment

See [snowflake_setup.sql](snowflake_setup.sql) for one-time service registration, and [snowflake_tasks.sql](snowflake_tasks.sql) for scheduled start/stop. Replace every `<your-...>` placeholder with values from your own Snowflake account.

For redeploys, build a timestamped image, upload a versioned spec to your spec stage, and run `ALTER SERVICE ... FROM SPECIFICATION_FILE = '...'` — never `CREATE OR REPLACE SERVICE`, which invalidates the public-endpoint hash and breaks bookmarked URLs.
