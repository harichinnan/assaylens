#!/usr/bin/env bash
# =============================================================================
# Run dbt-spark against the Spark Thrift Server, building the silver + gold
# Iceberg models in the `lake` catalog.
#
# Single source of truth for the dbt `docker run`, called by:
#   * the Makefile (`make dbt-spark`) — run on the host
#   * the Temporal `dbt_build` activity — run from the pipeline-worker container
#     via the mounted Docker socket (docker-out-of-docker)
#
# Usage: run_dbt_spark.sh [build|run|test|deps ...]   (default: build)
# Runs `dbt deps` first (idempotent) so dbt_utils is available.
# =============================================================================
set -euo pipefail

REPO="${HOST_REPO_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
DBT_IMAGE="${DBT_IMAGE:-assaylens/dbt-spark:latest}"
CMD=("$@"); [ ${#CMD[@]} -eq 0 ] && CMD=(build)

# dbt-spark connects to the Thrift Server published on the host at :10000.
run_dbt() {
  docker run --rm \
    -v "$REPO/dbt":/dbt \
    -e DBT_PROFILES_DIR=/dbt \
    -e DBT_TARGET=spark \
    --add-host host.docker.internal:host-gateway \
    "$DBT_IMAGE" "$@" --project-dir /dbt --profiles-dir /dbt --target spark
}

echo "[run_dbt_spark] repo=$REPO image=$DBT_IMAGE cmd=${CMD[*]}"
run_dbt deps
run_dbt "${CMD[@]}"
