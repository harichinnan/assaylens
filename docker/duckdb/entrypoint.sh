#!/usr/bin/env bash
# Refresh the lakehouse views from the live Iceberg catalog, then launch DuckDB.
# With no args -> interactive shell; with args (e.g. -c "SELECT ...") -> runs them.
set -e
python3 /opt/gen_init.py
exec duckdb -init /tmp/lakehouse.sql "$@"
