-- Dashboards App: SPCS scheduled start/stop tasks
--
-- Run AFTER the base setup in snowflake_setup.sql. Replace the
-- `<your-...>` placeholders to match your own account.
--
-- Pattern:
--
--   Start task (morning) — RESUME the compute pool and the service.
--     07:00  TASK_DASHBOARDS_START
--
--   Stop task (evening) — SUSPEND the service, then optionally suspend
--     the compute pool if no other service on it is still running. The
--     pool-suspend check is delegated to a small stored procedure.
--     19:00  TASK_DASHBOARDS_STOP
--
-- Notes:
--   - RESUME on an already-active pool/service is a no-op in SPCS, so
--     the start task can unconditionally call RESUME without checks.
--   - SUSPEND on a compute pool kills every service on it — so the
--     pool-suspend procedure only acts when no service on the pool is
--     in an active state. Suspended services show status='SUSPENDED' in
--     SHOW SERVICES, so the count naturally excludes self.

use role sysadmin;

-- --------------------------------------------------------------------
-- 1. Stored procedure: suspend the compute pool only if no services
--    on it are still running. Caller is expected to have already
--    suspended its own service before invoking this procedure.
-- --------------------------------------------------------------------
CREATE OR ALTER PROCEDURE <your-db>.<your-schema>.P_SUSPEND_POOL_IF_IDLE()
    RETURNS STRING
    LANGUAGE SQL
AS
$$
DECLARE
    running_count NUMBER DEFAULT 0;
BEGIN
    SHOW SERVICES IN COMPUTE POOL <your-compute-pool>;

    SELECT COUNT(*) INTO :running_count
    FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
    WHERE "status" IN ('PENDING', 'READY', 'RESUMING', 'STARTING');

    IF (running_count = 0) THEN
        ALTER COMPUTE POOL <your-compute-pool> SUSPEND;
        RETURN 'OK — pool suspended (no services running)';
    END IF;

    RETURN 'Skipped — pool still has ' || running_count || ' running service(s)';
EXCEPTION
    WHEN OTHER THEN
        -- Defensive default: do NOT attempt to suspend the pool if
        -- anything went wrong. Safer to leak cost than to kill a
        -- service we can't see.
        RETURN 'error — ' || SQLERRM || ' (pool left active)';
END;
$$;

-- --------------------------------------------------------------------
-- 2. TASK_DASHBOARDS_START — resume pool + service every weekday morning.
-- --------------------------------------------------------------------
CREATE OR ALTER TASK <your-db>.<your-schema>.TASK_DASHBOARDS_START
    SCHEDULE = 'USING CRON 0 7 * * MON-FRI UTC'
    ALLOW_OVERLAPPING_EXECUTION = FALSE
AS
BEGIN
    ALTER COMPUTE POOL <your-compute-pool> RESUME;
    ALTER SERVICE <your-db>.<your-schema>.DASHBOARDS_APP RESUME;
END;

-- --------------------------------------------------------------------
-- 3. TASK_DASHBOARDS_STOP — suspend service + optionally pool.
-- --------------------------------------------------------------------
CREATE OR ALTER TASK <your-db>.<your-schema>.TASK_DASHBOARDS_STOP
    SCHEDULE = 'USING CRON 0 19 * * MON-FRI UTC'
    ALLOW_OVERLAPPING_EXECUTION = FALSE
AS
BEGIN
    BEGIN
        ALTER SERVICE <your-db>.<your-schema>.DASHBOARDS_APP SUSPEND;
    EXCEPTION WHEN OTHER THEN NULL;
    END;
    CALL <your-db>.<your-schema>.P_SUSPEND_POOL_IF_IDLE();
END;

-- --------------------------------------------------------------------
-- 4. Resume the tasks (new tasks are created suspended by default)
-- --------------------------------------------------------------------
ALTER TASK <your-db>.<your-schema>.TASK_DASHBOARDS_START RESUME;
ALTER TASK <your-db>.<your-schema>.TASK_DASHBOARDS_STOP RESUME;

-- --------------------------------------------------------------------
-- 5. Verification queries (uncomment as needed)
-- --------------------------------------------------------------------
-- SHOW TASKS LIKE 'TASK_DASHBOARDS_%' IN SCHEMA <your-db>.<your-schema>;
-- CALL <your-db>.<your-schema>.P_SUSPEND_POOL_IF_IDLE();  -- manual dry run
-- SELECT * FROM TABLE(INFORMATION_SCHEMA.TASK_HISTORY(
--     SCHEDULED_TIME_RANGE_START => DATEADD('hour', -24, CURRENT_TIMESTAMP()),
--     TASK_NAME => 'TASK_DASHBOARDS_STOP'
-- )) ORDER BY SCHEDULED_TIME DESC;
