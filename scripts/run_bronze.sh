#!/usr/bin/env bash
# =============================================================================
# Bronze ingestion: run the Scala Spark job (JDBC ChEMBL -> Iceberg lake.bronze.*)
# inside the JDK17 sbt container.
#
# Single source of truth for the bronze `docker run`, called by:
#   * the Makefile (`make bronze`) — run on the host
#   * the Temporal `ingest_bronze` activity — run from the pipeline-worker
#     container via the mounted Docker socket (docker-out-of-docker)
#
# Because the bind-mount path is resolved by the HOST Docker daemon (even when
# this script runs inside a container), it must be a HOST path. On the host we
# derive it from this script's location; inside the worker, compose passes the
# real host repo path as HOST_REPO_DIR.
# =============================================================================
set -euo pipefail

REPO="${HOST_REPO_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

SBT_IMAGE="${SBT_IMAGE:-sbtscala/scala-sbt:eclipse-temurin-jammy-17.0.10_7_1.9.9_2.12.18}"

echo "[run_bronze] repo=$REPO image=$SBT_IMAGE"
exec docker run --rm --platform linux/arm64 \
  -v "$REPO/ingestion":/work -w /work \
  -v assaylens-coursier:/root/.cache \
  -v assaylens-ivy:/root/.ivy2 \
  -v assaylens-sbt:/root/.sbt \
  -e JDK_JAVA_OPTIONS=-XX:UseSVE=0 \
  -e AWS_REGION="${AWS_REGION:-us-east-1}" \
  "$SBT_IMAGE" \
  sbt -batch "runMain com.assaylens.ingestion.Main"
