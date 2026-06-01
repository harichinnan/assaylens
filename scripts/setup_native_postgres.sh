#!/usr/bin/env bash
# Bootstrap the AssayLens warehouse on the host's NATIVE Postgres (Homebrew
# postgresql@14), replacing the former Dockerized Postgres.
#
# Creates:
#   - role  assaylens  (owner; used by dbt / loaders / services)
#   - role  agent_ro   (read-only; BROADENED: can read raw/staging/marts/public
#                       + information_schema/pg_catalog for general NL->SQL)
#   - db    assaylens  (warehouse)  + schemas raw / staging / marts
#   - db    metabase   (Metabase application metadata)
#
# Idempotent. Run as a native superuser (the OS user is one via trust auth):
#   bash scripts/setup_native_postgres.sh
set -euo pipefail

PGHOST="${PGHOST:-127.0.0.1}"
PGPORT="${PGPORT:-5432}"
SUPER="${PGSUPERUSER:-$(whoami)}"
APP_PW="${POSTGRES_PASSWORD:-assaylens}"
RO_PW="${POSTGRES_RO_PASSWORD:-agent_ro}"

psql_super() { psql -h "$PGHOST" -p "$PGPORT" -U "$SUPER" -v ON_ERROR_STOP=1 "$@"; }

echo "[native-pg] roles + databases…"
psql_super -d postgres <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='assaylens') THEN
    EXECUTE format('CREATE ROLE assaylens LOGIN PASSWORD %L', '${APP_PW}');
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='agent_ro') THEN
    EXECUTE format('CREATE ROLE agent_ro LOGIN PASSWORD %L', '${RO_PW}');
  END IF;
END
\$\$;
SQL

# CREATE DATABASE can't run inside a transaction/DO block — guard with \gexec.
psql_super -d postgres -tAc \
  "SELECT 'CREATE DATABASE assaylens OWNER assaylens' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname='assaylens')" | psql_super -d postgres
psql_super -d postgres -tAc \
  "SELECT 'CREATE DATABASE metabase OWNER assaylens' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname='metabase')" | psql_super -d postgres

echo "[native-pg] schemas + grants on assaylens…"
psql_super -d assaylens <<SQL
CREATE SCHEMA IF NOT EXISTS raw     AUTHORIZATION assaylens;
CREATE SCHEMA IF NOT EXISTS staging AUTHORIZATION assaylens;
CREATE SCHEMA IF NOT EXISTS marts   AUTHORIZATION assaylens;

COMMENT ON SCHEMA raw     IS 'ChEMBL extracts (loaded from the native ChEMBL restore).';
COMMENT ON SCHEMA staging IS 'dbt staging models.';
COMMENT ON SCHEMA marts   IS 'dbt dims/fact/marts — serving + agent layer.';

-- Read-only agent role. BROADENED so the NL->SQL "ask Postgres" tool can read
-- the whole warehouse + the catalog/information_schema, while staying read-only.
GRANT CONNECT ON DATABASE assaylens TO agent_ro;
GRANT USAGE ON SCHEMA raw, staging, marts, public TO agent_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA raw, staging, marts, public TO agent_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA raw     GRANT SELECT ON TABLES TO agent_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA staging GRANT SELECT ON TABLES TO agent_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA marts   GRANT SELECT ON TABLES TO agent_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public  GRANT SELECT ON TABLES TO agent_ro;
-- The lakehouse publisher (Spark JDBC) drops+recreates marts.* each run AS the
-- assaylens role, so default privileges must also be registered FOR THAT ROLE,
-- else agent_ro loses SELECT on every republished serving table.
ALTER DEFAULT PRIVILEGES FOR ROLE assaylens IN SCHEMA marts GRANT SELECT ON TABLES TO agent_ro;
-- Resolve unqualified mart names; information_schema/pg_catalog are world-readable.
ALTER ROLE agent_ro SET search_path = marts, public, raw, staging;
SQL

echo "[native-pg] done."
