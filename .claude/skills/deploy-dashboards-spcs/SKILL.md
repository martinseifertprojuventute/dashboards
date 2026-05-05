---
name: deploy-dashboards-spcs
description: Use when deploying the Streamlit dashboards app in this repo to Snowflake Container Services (SPCS) — building a new Docker image, pushing it to the Snowflake image registry with a timestamped version tag, and updating the existing service in place without replacing it.
---

# Deploy Dashboards App to SPCS

## Overview

Deploy the app at the repo root to its existing SPCS service using a timestamped image tag (`YYYY-MM-DD_HH-mm`) — not `:latest`. Preserves the service's public endpoint URL so bookmarked dashboard links keep working, and leaves older image tags in the registry for easy rollback.

**Never** use `CREATE OR REPLACE SERVICE` or `DROP SERVICE` — they invalidate the endpoint hash.

## When to use

- User says "deploy dashboards", "push a new dashboards version", "redeploy the dashboards app", or similar.
- A code change in the app needs to reach users.
- Do NOT use for first-time service creation (that lives in `snowflake_setup.sql`).

## Prerequisites

- Docker daemon running locally.
- `snow` CLI installed and a connection profile configured in `~/.snowflake/connections.toml`.
- Service already exists (check with `SHOW SERVICES LIKE 'DASHBOARDS_APP' IN SCHEMA <your-db>.<your-schema>;`).

Define these once at the top of the deploy session and reuse them:

```bash
ACCOUNT=<your-account>            # e.g. xy12345
DB=<your-db>
SCHEMA=<your-schema>
SPEC_STAGE=<your-spec-stage>      # name of the stage holding service specs
IMAGE_REPO=<your-image-repo>      # name of the image repository
SERVICE_NAME=DASHBOARDS_APP
PROFILE=default                   # ~/.snowflake/connections.toml profile

REGISTRY="${ACCOUNT}.registry.snowflakecomputing.com"
IMAGE_PATH="${DB}/${SCHEMA}/${IMAGE_REPO}/dashboards-app"
```

## Procedure

### 1. Pick version tag

```bash
VERSION=$(date +%Y-%m-%d_%H-%M)
echo "deploying dashboards-app:$VERSION"
```

Keep `VERSION` in scope for every following step.

### 2. Registry login

```bash
snow spcs image-registry login --connection "$PROFILE"
```

### 3. Build + tag + push image

Run from the repo root so the Dockerfile context is correct. `--platform=linux/amd64` is mandatory (SPCS refuses ARM images; flag is harmless on x64).

```bash

docker build --platform=linux/amd64 -t "dashboards-app:$VERSION" .

docker tag "dashboards-app:$VERSION" "${REGISTRY}/${IMAGE_PATH}:$VERSION"
docker push "${REGISTRY}/${IMAGE_PATH}:$VERSION"
```

### 4. Generate a versioned spec file

The checked-in `dashboards-app.yaml` points at `:latest` as a readable default. For each deploy, write a one-off spec with the timestamped tag and upload it under a versioned name so old specs remain in the stage (handy for rollback).

```bash
SPEC_NAME="dashboards-app_${VERSION}.yaml"

python - "$VERSION" "$SPEC_NAME" <<'PY'
import sys, pathlib, re
version, spec_name = sys.argv[1], sys.argv[2]
src = pathlib.Path("dashboards-app.yaml").read_text(encoding="utf-8")
new = re.sub(r"(dashboards-app):latest", rf"\1:{version}", src)
pathlib.Path(spec_name).write_text(new, encoding="utf-8")
print(f"wrote {spec_name}")
PY
```

Sanity-check the line that changed:

```bash
grep "image:" "$SPEC_NAME"
```

### 5. Upload spec to stage

```bash
snow stage copy "$SPEC_NAME" "@${DB}.${SCHEMA}.${SPEC_STAGE}" --connection "$PROFILE" --overwrite
```

### 6. Update the service in place

Uses `ALTER SERVICE ... FROM SPECIFICATION_FILE` — preserves the endpoint hash. Do NOT drop/recreate.

```bash
snow sql --connection "$PROFILE" -q "ALTER SERVICE ${DB}.${SCHEMA}.${SERVICE_NAME} FROM @${DB}.${SCHEMA}.${SPEC_STAGE} SPECIFICATION_FILE = '${SPEC_NAME}';"
```

### 7. Verify rollout

```bash
snow sql --connection "$PROFILE" -q "CALL SYSTEM\$GET_SERVICE_STATUS('${DB}.${SCHEMA}.${SERVICE_NAME}');"
```

Wait for status to return to `READY` (usually 30–90 seconds). If it stays `PENDING` or goes to `FAILED`, grab logs:

```bash
snow sql --connection "$PROFILE" -q "CALL SYSTEM\$GET_SERVICE_LOGS('${DB}.${SCHEMA}.${SERVICE_NAME}', '0', 'dashboards-app', 200);"
```

### 8. Clean up local temp spec

```bash
rm "$SPEC_NAME"
```

(The stage copy in Snowflake is intentionally kept — it documents what was deployed when, and enables rollback.)

### 9. Rollback (only if needed)

List deployed specs:

```bash
snow sql --connection "$PROFILE" -q "LIST @${DB}.${SCHEMA}.${SPEC_STAGE} PATTERN='.*dashboards-app_.*';"
```

Re-point the service at an older one (no rebuild, no push):

```bash
snow sql --connection "$PROFILE" -q "ALTER SERVICE ${DB}.${SCHEMA}.${SERVICE_NAME} FROM @${DB}.${SCHEMA}.${SPEC_STAGE} SPECIFICATION_FILE = 'dashboards-app_<OLD_VERSION>.yaml';"
```

Works because the old image tag still exists in the registry.

## Common mistakes

| Mistake | Why it breaks | Fix |
|---|---|---|
| Running docker build from a subdirectory | Dockerfile context wrong, bakes in junk / misses files | Build from the repo root |
| Omitting `--platform=linux/amd64` on ARM Macs | SPCS refuses the image, service goes FAILED | Always pass the flag |
| Using `CREATE OR REPLACE SERVICE` | Drops service → new endpoint hash → every bookmarked URL breaks | Use `ALTER SERVICE ... FROM SPECIFICATION_FILE` |
| Overwriting the single `dashboards-app.yaml` in stage | No rollback trail | Upload each deploy as `dashboards-app_<VERSION>.yaml` |
| Forgetting to upload the new spec before `ALTER SERVICE` | Service still pulls the old tag | Step 5 must precede step 6 |
| Committing the temp `dashboards-app_<VERSION>.yaml` | Clutter, no purpose (stage has the canonical copy) | Step 8 removes it |

## Related

- First-time service setup: `snowflake_setup.sql`
- App source: repo root
