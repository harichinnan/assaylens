# =============================================================================
# dbt-spark client image. Runs `dbt build` against the Spark Thrift Server,
# materializing the silver + gold Iceberg models in the `lake` catalog.
#
# The thrift transport uses SASL (PyHive), so the wheel for `sasl` needs a
# compiler + libsasl2 headers at build time.
# =============================================================================
FROM python:3.11-slim

# Pin classic (Python) dbt-core 1.8 explicitly: an unpinned resolve pulls
# dbt-core 2.0.0a1 (the Fusion engine), which has no Spark adapter.
RUN apt-get update && apt-get install -y --no-install-recommends \
      gcc libsasl2-dev libsasl2-2 && \
    pip install --no-cache-dir "dbt-core==1.8.7" "dbt-spark[PyHive]==1.8.0" && \
    apt-get purge -y gcc libsasl2-dev && apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /dbt
ENTRYPOINT ["dbt"]
