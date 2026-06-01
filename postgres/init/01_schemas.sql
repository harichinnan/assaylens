-- =============================================================================
-- AssayLens — Postgres bootstrap
--
-- Runs once on first cluster initialization (mounted into
-- /docker-entrypoint-initdb.d). Creates:
--   * the warehouse schemas (raw / staging / marts)
--   * a separate `metabase` database for Metabase's own app state
--   * a least-privilege read-only role for the agent's run_curated_sql tool
--
-- The schema layering mirrors the dbt project:
--   raw      <- loaded from the Parquet lake (load_parquet_to_postgres.py)
--   staging  <- dbt staging models (views)
--   marts    <- dbt dims/fact/marts (tables) — the only layer the agent reads
-- =============================================================================

-- Separate database for Metabase application metadata (not analytics data).
-- CREATE DATABASE cannot run inside the DO block, so do it directly; the
-- entrypoint runs this file against the default POSTGRES_DB.
SELECT 'CREATE DATABASE metabase'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'metabase')\gexec

-- ---- Warehouse schemas -----------------------------------------------------
CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS marts;

COMMENT ON SCHEMA raw     IS 'Untransformed ChEMBL extracts loaded from the Parquet lake.';
COMMENT ON SCHEMA staging IS 'dbt staging models: typed, renamed, lightly cleaned.';
COMMENT ON SCHEMA marts   IS 'dbt dimensional model + marts. The serving + agent layer.';

-- ---- Read-only agent role --------------------------------------------------
-- This role is what the FastAPI agent connects as for run_curated_sql, giving
-- a hard, DB-enforced backstop beneath the application-level SQL guardrails.
--
-- NOTE: the Postgres docker entrypoint runs *.sql files without psql variable
-- substitution, so credentials are literal here. They MUST match
-- POSTGRES_RO_USER / POSTGRES_RO_PASSWORD in your .env. If you change them,
-- update this file (defaults: agent_ro / agent_ro) or run an ALTER ROLE after.
DO $$
DECLARE
  ro_user TEXT := 'agent_ro';
  ro_pass TEXT := 'agent_ro';
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = ro_user) THEN
    EXECUTE format('CREATE ROLE %I LOGIN PASSWORD %L', ro_user, ro_pass);
  END IF;

  -- Connect + read marts only. No write, no temp, no other schemas.
  EXECUTE format('GRANT CONNECT ON DATABASE %I TO %I', current_database(), ro_user);
  EXECUTE format('GRANT USAGE ON SCHEMA marts TO %I', ro_user);
  EXECUTE format('GRANT SELECT ON ALL TABLES IN SCHEMA marts TO %I', ro_user);

  -- Resolve unqualified mart names (the allow-list is schema-agnostic, so the
  -- agent may issue `... from mart_compound_target_potency` without `marts.`).
  EXECUTE format('ALTER ROLE %I SET search_path = marts, public', ro_user);

  -- Ensure future dbt-built marts are readable too.
  EXECUTE format(
    'ALTER DEFAULT PRIVILEGES IN SCHEMA marts GRANT SELECT ON TABLES TO %I', ro_user);

  -- Explicitly deny the rest. The agent must reach raw/staging only through
  -- approved lineage tools, never via ad-hoc SQL.
  EXECUTE format('REVOKE ALL ON SCHEMA raw FROM %I', ro_user);
  EXECUTE format('REVOKE ALL ON SCHEMA staging FROM %I', ro_user);
END
$$;
