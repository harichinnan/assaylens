#!/usr/bin/env bash
# =============================================================================
# Run a PySpark job (graph build, gold->Postgres publisher) in the shared
# spark-iceberg image via spark-submit, with the `lake` Iceberg catalog wired in
# (same config as the Bronze sbt job and the Thrift Server).
#
# Single source of truth for these `docker run`s, called by:
#   * the Makefile (`make graph` / `make publish`) — on the host
#   * the Temporal build_graph / publish_marts activities — from the worker via
#     the Docker socket (HOST_REPO_DIR gives host-correct bind-mount paths)
#
# Usage: run_spark_job.sh <script-name-under-scripts/> [args...]
# =============================================================================
set -euo pipefail

REPO="${HOST_REPO_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
IMAGE="${SPARK_IMAGE:-assaylens/spark-iceberg:latest}"
SCRIPT="${1:?usage: run_spark_job.sh <script.py> [args...]}"; shift || true

echo "[run_spark_job] repo=$REPO image=$IMAGE script=$SCRIPT"
exec docker run --rm --add-host host.docker.internal:host-gateway \
  -e AWS_REGION="${AWS_REGION:-us-east-1}" \
  -v "$REPO/scripts":/scripts \
  "$IMAGE" \
  /opt/spark/bin/spark-submit \
    --master "local[*]" --driver-memory 3g \
    --conf spark.sql.extensions=org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions \
    --conf spark.sql.catalog.lake=org.apache.iceberg.spark.SparkCatalog \
    --conf spark.sql.catalog.lake.catalog-impl=org.apache.iceberg.jdbc.JdbcCatalog \
    --conf spark.sql.catalog.lake.uri=jdbc:postgresql://host.docker.internal:5432/iceberg_catalog \
    --conf spark.sql.catalog.lake.jdbc.user=assaylens \
    --conf spark.sql.catalog.lake.jdbc.password=assaylens \
    --conf spark.sql.catalog.lake.warehouse=s3://assaylens/lakehouse \
    --conf spark.sql.catalog.lake.io-impl=org.apache.iceberg.aws.s3.S3FileIO \
    --conf spark.sql.catalog.lake.s3.endpoint=http://host.docker.internal:9000 \
    --conf spark.sql.catalog.lake.s3.path-style-access=true \
    --conf spark.sql.catalog.lake.s3.access-key-id=minioadmin \
    --conf spark.sql.catalog.lake.s3.secret-access-key=minioadmin \
    --conf spark.sql.defaultCatalog=lake \
    "/scripts/$SCRIPT" "$@"
