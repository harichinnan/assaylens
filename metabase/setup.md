# Metabase setup

Metabase runs in the compose stack and stores its own state in a separate
`metabase` database inside the same Postgres (created by
`postgres/init/01_schemas.sql`).

## Automated provisioning (recommended)

Instead of clicking through onboarding, run the idempotent provisioner once the
warehouse is built (`make dbt`):

```bash
make metabase-setup        # or run metabase/setup_metabase.py directly
```

It completes onboarding, registers the Postgres analytics DB (marts schema),
creates a **semantic layer of Models** over the five marts, builds the **four
dashboards** with target/compound filters, enables **static embedding**, and
prints the dashboard ids + embedding secret. Those values are written to
`metabase/.metabase_ids.json` (gitignored) and should be copied into `.env`
(`MB_EMBEDDING_SECRET_KEY`, `MB_DASH_*`) so the agent can mint signed embed URLs.
Re-running is safe — objects are looked up by name and reused.

The rest of this doc describes the equivalent manual steps.

## First-run

1. `make up` (or `docker compose up -d metabase postgres`).
2. Open http://localhost:3000 and complete the admin onboarding.
3. **Add the analytics database** (this is the data you build dashboards on):
   - Type: **PostgreSQL**
   - Host: `postgres` (the in-network service name)
   - Port: `5432`
   - Database name: `assaylens`
   - Username / password: from `.env` (`POSTGRES_USER` / `POSTGRES_PASSWORD`)
   - Schemas: include `marts` (you can exclude `raw` / `staging` to keep the BI
     surface clean).
4. Let Metabase scan; the `marts.*` tables/views become available as data sources.

> For least privilege you can instead point Metabase at the read-only `agent_ro`
> role — it has `SELECT` on `marts`, which is all the dashboards need.

## Building the dashboards

Create the four dashboards described in
[../docs/metabase_dashboards.md](../docs/metabase_dashboards.md) using the
card-level specs in [dashboard_specs.md](dashboard_specs.md). Most cards are
either a direct table/aggregation on a mart or a short SQL question; the specs
give the exact source mart and grouping for each.

## Linking the agent's dashboard tool

`get_metabase_dashboard` can deep-link to a dashboard if you expose its id via
environment variables on the `agent` service. After creating a dashboard, copy
its numeric id from the URL (`/dashboard/<id>`) and set the matching var:

| Dashboard | Env var |
|-----------|---------|
| Scientific Warehouse Overview | `MB_DASH_OVERVIEW` |
| Target Activity Explorer | `MB_DASH_TARGET` |
| Compound Profile | `MB_DASH_COMPOUND` |
| Data Quality | `MB_DASH_QUALITY` |

Add them to `.env` (the `agent` service uses `env_file: .env`) and restart the
agent. Without them the tool returns the Metabase dashboards index URL plus the
filter parameters to apply.
