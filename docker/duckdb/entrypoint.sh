#!/usr/bin/env bash
# Refresh lakehouse views from the live Iceberg catalog, then launch DuckDB.
#   DUCKDB_MODE=ui  -> browser UI at http://localhost:4213 (served from a file DB
#                      so the UI's query sessions see the views + persistent secret)
#   otherwise       -> interactive CLI shell (or runs passed args, e.g. -c "...")
set -e
python3 /opt/gen_init.py

if [ "${DUCKDB_MODE}" = "ui" ]; then
  DB=/tmp/lake.duckdb
  # The UI server binds IPv6 loopback only ([::1]:4213). Bridge IPv4 0.0.0.0:4213
  # -> [::1]:4213 (different address family, same port -> no conflict, no SPA
  # port mismatch) so the published port reaches it.
  socat TCP4-LISTEN:4213,bind=0.0.0.0,reuseaddr,fork TCP6:[::1]:4213 &
  echo "[duckdb] UI starting at http://localhost:4213  (Ctrl-C to stop)"
  # Seed the views into the file DB, start the UI server, keep the process alive.
  { printf "CALL start_ui_server();\n"; tail -f /dev/null; } | duckdb "$DB" -init /tmp/lakehouse.sql
else
  exec duckdb -init /tmp/lakehouse.sql "$@"
fi
