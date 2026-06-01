# Architecture

AssayLens is a vertical slice of a production-style scientific data platform:
ingestion → lake → warehouse → modeling → BI / search / governed AI. Each layer
uses a tool that ports to real systems; nothing is locked to a local-only engine
(in particular, **no DuckDB**).

## Component overview

| Layer | Component | Technology | Runs as |
|-------|-----------|-----------|---------|
| Source | ChEMBL bioactivity data | ChEMBL REST API | external |
| Ingestion | `ingestion/` | Scala + Spark | `sbt run` (or Docker) one-shot |
| Lake | `data/lake/` | Parquet | files on disk |
| Load | `scripts/load_parquet_to_postgres.py` | Python + pyarrow + psycopg | one-shot |
| Warehouse | Postgres `raw` / `staging` / `marts` | Postgres 16 | container |
| Modeling | `dbt/` | dbt-postgres | one-shot |
| BI | Metabase | Metabase | container |
| Search | `search/` + index | Elasticsearch 8 | container |
| Agent | `agent/` | FastAPI + Anthropic Haiku | container |
| UI | `ui/` | Streamlit | container |

## Data flow

```
                         data/seeds/target_seed.csv  (5 kinase targets)
                                      │
         ┌────────────────────────────┴───────────────────────────┐
         ▼                                                          │
ChEMBL REST API ──► Scala Spark ingestion ──► Parquet lake          │ scope
   (or offline       (extract → normalize       data/lake/<entity>  │ control
    fixtures)         units → write)                  │             │
                                                       ▼            │
                              load_parquet_to_postgres.py           │
                                                       │            │
                                                       ▼            │
                                            Postgres  raw.raw_chembl_*
                                                       │  dbt
                                  staging  →  dim_* / fact  →  marts
                                                       │
              ┌────────────────────────────────────────┼─────────────────────────────┐
              ▼                                          ▼                            ▼
        Metabase (4 dashboards)        search/build_index.py → Elasticsearch    FastAPI agent
                                       (curated mart → 1 doc/result)            (7 governed tools)
                                                                                       │
                                                                            Streamlit chat UI
```

## Why these choices

- **Scala + Spark** for ingestion: demonstrates distributed, typed ingestion and
  porting to a cluster via `spark-submit`. The same code path runs locally with
  `local[*]`. Unit normalization happens here so the lake already carries a
  comparable `standard_value_nm`.
- **Parquet** as the lake format: columnar, compressed, engine-agnostic — the
  contract between ingestion and the warehouse.
- **Postgres** as warehouse + serving DB: portable SQL, no proprietary engine,
  and the read-only role gives a hard governance boundary for the agent.
- **dbt** for modeling: versioned, tested transformations with lineage. The
  curation rules and DQ checks live as code + tests, not tribal knowledge.
- **Elasticsearch** for search: full-text over assay descriptions plus structured
  filters (nM thresholds, confidence, pChEMBL). Indexed only from the curated
  mart so search never surfaces non-comparable rows.
- **FastAPI + Claude Haiku** for the agent: a small LLM routes intent and
  summarizes compact results; deterministic tools do the data work. See
  [agent_design.md](agent_design.md).

## Governance boundaries (defense in depth)

1. **DB role.** The agent connects as `agent_ro`, which has `SELECT` on `marts`
   only (`postgres/init/01_schemas.sql`).
2. **Application guardrails.** `run_curated_sql` validates SELECT-only, single
   statement, allow-listed marts, mandatory LIMIT, statement timeout
   (`agent/app/guardrails/sql_guardrails.py`).
3. **Structured tools.** Search and lineage tools never accept free-form ES DSL
   or SQL from the LLM — only typed arguments.
4. **Curation in dbt.** Comparability filtering is upstream of every serving
   surface, so search and SQL operate on already-clean data.

## Local vs production

| Concern | Local (this repo) | Production direction |
|---------|-------------------|----------------------|
| Spark | `local[*]` via sbt | `spark-submit` to a cluster (deps `provided`) |
| Lake | local Parquet dir | S3/GCS/ADLS object store |
| Warehouse | Postgres | Snowflake / BigQuery / Redshift (dbt adapter swap) |
| Orchestration | Makefile | Airflow / Dagster |
| Secrets | `.env` | a secrets manager |
| Search | single-node ES, security off | managed ES/OpenSearch with auth |
