-- Dashboards App: SPCS deployment
-- Run once to register the service. Assumes a compute pool, a stage for
-- service specs, and an image repository are already provisioned. Fill
-- in the placeholders (`<your-...>`) for your own account.
--
-- Scheduled start/stop: handled in a separate file, snowflake_tasks.sql.
-- Run snowflake_tasks.sql AFTER this file.

use role sysadmin;

-- 1. Upload YAML spec to stage (run from the repo root in a separate terminal)
--   snow stage copy dashboards-app.yaml \
--     "@<your-db>.<your-schema>.<your-spec-stage>" --connection default --overwrite

-- 2. Build, tag and push Docker image (run from the repo root).
-- SPCS expects linux/amd64 images — explicit platform flag is required
-- on Apple Silicon and harmless on Windows x64.
--   docker build --platform=linux/amd64 -t dashboards-app:latest .
--   docker tag dashboards-app:latest \
--     <your-account>.registry.snowflakecomputing.com/<your-db>/<your-schema>/<your-image-repo>/dashboards-app:latest
--   docker push \
--     <your-account>.registry.snowflakecomputing.com/<your-db>/<your-schema>/<your-image-repo>/dashboards-app:latest

-- 3. Create the SPCS service — ONCE.
-- Do NOT use `CREATE OR REPLACE`: that drops and recreates the
-- service, which invalidates the public-endpoint hash and breaks
-- every bookmarked / shared dashboard URL. For spec changes use
-- `ALTER SERVICE ... FROM SPECIFICATION` (section 7). For pure
-- image updates push a new `:latest` tag and SUSPEND/RESUME.
CREATE SERVICE IF NOT EXISTS <your-db>.<your-schema>.DASHBOARDS_APP
    IN COMPUTE POOL <your-compute-pool>
    FROM @<your-db>.<your-schema>.<your-spec-stage>
    SPECIFICATION_FILE = 'dashboards-app.yaml'
    COMMENT = 'Sample Streamlit dashboards in SPCS — see README.md';

-- 4. Verify the service came up
-- CALL SYSTEM$GET_SERVICE_STATUS('<your-db>.<your-schema>.DASHBOARDS_APP');
-- CALL SYSTEM$GET_SERVICE_LOGS('<your-db>.<your-schema>.DASHBOARDS_APP', '0', 'dashboards-app', 100);

-- 5. Get the public endpoint URL
-- Users navigate to this URL and are challenged for Snowflake SSO.
-- Their OAuth token is injected into the container at
-- /snowflake/session/token. lib/snowflake.py picks it up automatically.
-- SHOW ENDPOINTS IN SERVICE <your-db>.<your-schema>.DASHBOARDS_APP;

-- 6. Grants
-- USAGE on the service lets any Snowflake user reach the endpoint
-- (after SSO authentication). Per-page authorization can be enforced
-- inside the app via a role check helper, not here.
GRANT USAGE ON SERVICE <your-db>.<your-schema>.DASHBOARDS_APP TO ROLE PUBLIC;

-- 7. Useful follow-ups (uncomment as needed)
-- After pushing a new image:
--   ALTER SERVICE <your-db>.<your-schema>.DASHBOARDS_APP FROM @<your-db>.<your-schema>.<your-spec-stage>
--     SPECIFICATION_FILE = 'dashboards-app.yaml';
-- To suspend/resume manually:
--   ALTER SERVICE <your-db>.<your-schema>.DASHBOARDS_APP SUSPEND;
--   ALTER SERVICE <your-db>.<your-schema>.DASHBOARDS_APP RESUME;
-- To drop:
--   DROP SERVICE <your-db>.<your-schema>.DASHBOARDS_APP;
