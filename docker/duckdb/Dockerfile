# =============================================================================
# DuckDB demo console pre-wired to the AssayLens MinIO/Iceberg lakehouse.
# On launch it reads the Iceberg JDBC catalog and exposes one view per table,
# queryable directly from MinIO (httpfs + iceberg extensions baked in).
# =============================================================================
FROM python:3.11-slim

ARG DUCKDB_VERSION=v1.1.3
RUN apt-get update && apt-get install -y --no-install-recommends curl unzip ca-certificates && \
    pip install --no-cache-dir "psycopg[binary]" && \
    arch="$(dpkg --print-architecture)"; \
    case "$arch" in arm64) DA=aarch64 ;; amd64) DA=amd64 ;; *) DA="$arch" ;; esac; \
    curl -fsSL -o /tmp/duck.zip \
      "https://github.com/duckdb/duckdb/releases/download/${DUCKDB_VERSION}/duckdb_cli-linux-${DA}.zip" && \
    unzip /tmp/duck.zip -d /usr/local/bin && rm /tmp/duck.zip && \
    apt-get purge -y curl unzip && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

# Pre-install the extensions so the console starts offline/fast.
RUN duckdb -c "INSTALL httpfs; INSTALL iceberg;"

COPY gen_init.py /opt/gen_init.py
COPY entrypoint.sh /opt/entrypoint.sh
RUN chmod +x /opt/entrypoint.sh

ENTRYPOINT ["/opt/entrypoint.sh"]
