# =============================================================================
# Spark 3.5 + Iceberg 1.6.1 + S3FileIO (MinIO) + Postgres JDBC.
#
# Shared image for the lakehouse's SparkSQL workloads:
#   * the Spark Thrift Server that dbt-spark connects to (silver/gold models)
#   * the Spark graph job and the gold->Postgres publisher (spark-submit)
#
# Jars are baked in (not fetched via --packages at runtime) so the long-lived
# Thrift Server starts fast and offline.
# =============================================================================
FROM apache/spark:3.5.1

USER root

ARG ICEBERG_VERSION=1.6.1
ARG PG_JDBC_VERSION=42.7.3

# curl for the jar downloads; removed afterwards to keep the layer lean.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends curl; \
    cd /opt/spark/jars; \
    curl -fsSLO "https://repo1.maven.org/maven2/org/apache/iceberg/iceberg-spark-runtime-3.5_2.12/${ICEBERG_VERSION}/iceberg-spark-runtime-3.5_2.12-${ICEBERG_VERSION}.jar"; \
    curl -fsSLO "https://repo1.maven.org/maven2/org/apache/iceberg/iceberg-aws-bundle/${ICEBERG_VERSION}/iceberg-aws-bundle-${ICEBERG_VERSION}.jar"; \
    curl -fsSLO "https://repo1.maven.org/maven2/org/postgresql/postgresql/${PG_JDBC_VERSION}/postgresql-${PG_JDBC_VERSION}.jar"; \
    apt-get purge -y curl; \
    apt-get autoremove -y; \
    rm -rf /var/lib/apt/lists/*

USER spark
