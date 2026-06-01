# =============================================================================
# DuckDB demo console pre-wired to the AssayLens MinIO/Iceberg lakehouse.
# On launch it reads the Iceberg JDBC catalog and exposes one view per table,
# queryable directly from MinIO (httpfs + iceberg extensions baked in).
# =============================================================================
FROM python:3.11-slim

# v1.5.3 ships the browser UI extension. (Asset names are arm64/amd64 since >=1.2.)
ARG DUCKDB_VERSION=v1.5.3
RUN apt-get update && apt-get install -y --no-install-recommends curl unzip ca-certificates socat && \
    pip install --no-cache-dir "psycopg[binary]" && \
    arch="$(dpkg --print-architecture)"; \
    case "$arch" in arm64) DA=arm64 ;; amd64) DA=amd64 ;; *) DA="$arch" ;; esac; \
    curl -fsSL -o /tmp/duck.zip \
      "https://github.com/duckdb/duckdb/releases/download/${DUCKDB_VERSION}/duckdb_cli-linux-${DA}.zip" && \
    unzip /tmp/duck.zip -d /usr/local/bin && rm /tmp/duck.zip && \
    apt-get purge -y curl unzip && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

# Pre-install the extensions so the console starts offline/fast.
RUN duckdb -c "INSTALL httpfs; INSTALL iceberg; INSTALL ui;"

COPY gen_init.py /opt/gen_init.py
COPY entrypoint.sh /opt/entrypoint.sh
RUN chmod +x /opt/entrypoint.sh

ENTRYPOINT ["/opt/entrypoint.sh"]
