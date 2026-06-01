# AssayLens — A Reference Architecture for Chem/Bio Data Engineering

**An end-to-end, cloud-agnostic reference implementation of a modern data + AI platform for chemistry / life-sciences bioactivity data.** It takes public [ChEMBL](https://www.ebi.ac.uk/chembl/) assay data through a **medallion lakehouse** (Apache Iceberg on object storage), serves it as a governed analytical warehouse, and exposes it through BI, full-text + **semantic (vector) search**, a **graph** relationship layer, and a **governed LLM copilot** — all orchestrated by a durable workflow engine and fully instrumented for observability.

> **Positioning.** This is a **data-engineering reference architecture**, not a drug-discovery tool. It demonstrates how to build a reliable, governed scientific data platform around the *shape* of chem/bio assay data. Every component is **open-source and runs locally**, and each maps 1:1 to a managed service on the public clouds and on DE platforms like **Snowflake** and **Databricks** (see the mapping table below). Adopt the pattern; swap the substrate.

---

## Why this exists

Chem/bio organizations repeatedly need the same backbone: ingest messy public + internal assay data, **curate it to comparable evidence**, model it dimensionally, and expose it safely to scientists through dashboards, search, and AI — without losing **lineage, governance, or reproducibility**. AssayLens is a working blueprint for that backbone, deliberately scoped small (5 kinase targets) so the entire stack runs on a laptop, yet built from production-shaped patterns (Spark, Iceberg, dbt, a workflow engine, a serving store, a governed agent) rather than toy ones.

## The dataset in one sentence

The central grain is **one bioactivity measurement**: *a compound was tested against a biological target in an assay, producing an activity value such as IC50, Ki, Kd, or EC50.* Scope is a curated slice of ChEMBL centered on five oncology kinase targets:

| Gene | Target | ChEMBL ID |
|------|--------|-----------|
| EGFR | Epidermal growth factor receptor | CHEMBL203 |
| HER2 / ERBB2 | Receptor tyrosine-protein kinase erbB-2 | CHEMBL1824 |
| BRAF | Serine/threonine-protein kinase B-raf | CHEMBL5145 |
| JAK2 | Tyrosine-protein kinase JAK2 | CHEMBL2971 |
| VEGFR2 / KDR | Vascular endothelial growth factor receptor 2 | CHEMBL279 |

---

## Reference architecture

```
            ChEMBL (full Postgres release; 5-target slice pulled via JDBC pushdown)
                                   │  Scala + Apache Spark  (scope + nM unit normalization)
                                   ▼
   ┌──────────────────────────  MEDALLION LAKEHOUSE (Apache Iceberg on object storage)  ──────────────────────────┐
   │   BRONZE  lake.bronze.*        SILVER  lake.silver.stg_*        GOLD  lake.gold.{dim_*,fact_*,mart_*,graph_*}  │
   │       (raw extract)   ──dbt──►   (typed / cleaned)   ──dbt──►      (dims · facts · marts · graph edges)        │
   └─────────────────────────────────────────────────┬───────────────────────────────────────────────────────────┘
                                                      │  Spark publisher (JDBC)
                                                      ▼
                              SERVING STORE  ·  Postgres  assaylens.marts.*  (read-only role for the agent)
                                                      │
        ┌──────────────────────┬──────────────────────┼───────────────────────┬──────────────────────────┐
        ▼                      ▼                      ▼                       ▼                          ▼
   BI dashboards         Full-text search      Semantic search (RAG)      Graph relationships      Governed LLM copilot
   (Metabase, 5)         (Elasticsearch)       (dense-vector kNN +        (target↔target,          (LangGraph agent, 12
                                                embedding service)         compound↔target)         tools, NL→SQL, RAG)

        Orchestration: Temporal  (ingest → dbt → graph → publish → index, durable + replayable)
        Observability: Langfuse  (every LLM call + tool span traced, with token usage)
```

**Layers, in flow order:**

1. **Source** — the official ChEMBL Postgres release, restored locally. The 5-target slice (with nanomolar unit normalization) is pushed *down* to the source DB as SQL, so Spark only streams a small result set.
2. **Bronze (Iceberg)** — a Scala/Spark job writes one Iceberg table per entity (`activity`, `molecule`, `target`, `assay`, `document`) to object storage, registered in a JDBC catalog.
3. **Silver → Gold (dbt-spark over Iceberg)** — staging models type/clean/dedup; the gold layer builds the star schema (`dim_*`, `fact_bioactivity_result`) and the curated/serving marts. Data-quality tests run inline.
4. **Graph** — a Spark job derives relationship marts from the curated evidence: compound↔target edges (best potency per target) and target↔target similarity (shared compounds + Jaccard).
5. **Publisher** — a Spark job copies every gold table to the **serving Postgres** (`marts.*`) over JDBC — the low-latency surface for apps.
6. **Serving & consumption** — BI (Metabase), full-text search (Elasticsearch), **semantic search** (sentence-transformers embeddings + Elasticsearch `dense_vector` kNN), and a **governed AI copilot** (LangGraph).
7. **Orchestration** — Temporal runs the medallion as a durable, observable, retryable pipeline (plus standalone graph-build / re-index workflows).
8. **Observability** — Langfuse (self-hosted v3) traces every agent request: root span → LLM generations (with token usage) → per-tool spans.

See [docs/architecture.md](docs/architecture.md) and [docs/data_model.md](docs/data_model.md) for deeper detail.

---

## Cloud-agnostic by design — map it to your platform

Every component is an open-source, local-first stand-in for a managed service. The **patterns** (medallion lakehouse, dbt transforms, dimensional serving marts, governed RAG/agent, workflow orchestration) are what transfer; the substrate is swappable:

| Concern | This repo (OSS / local) | AWS | GCP | Azure | Snowflake | Databricks |
|---|---|---|---|---|---|---|
| Object storage | **MinIO** | S3 | GCS | ADLS Gen2 | Internal/external stage | UC Volumes / DBFS |
| Table format | **Apache Iceberg** | Iceberg (Glue) | BigLake Iceberg | Iceberg on ADLS | Iceberg / native tables | Delta Lake (or Iceberg via UC) |
| Catalog / metastore | **Iceberg JDBC catalog** (Postgres) | Glue / Iceberg REST | BigLake Metastore | Unity-style catalog | Snowflake catalog | **Unity Catalog** |
| Transform compute | **Spark** (Thrift Server) | EMR / Glue | Dataproc | Synapse / Fabric | Snowpark / warehouses | Databricks clusters / SQL WH |
| Transform framework | **dbt** (dbt-spark) | dbt | dbt | dbt | **dbt-snowflake** | **dbt-databricks** |
| Orchestration | **Temporal** | Step Functions / MWAA | Cloud Composer / Workflows | Data Factory | Tasks / Airflow | Databricks Workflows |
| Serving store | **Postgres** | RDS / Redshift | Cloud SQL / BigQuery | Azure SQL / Synapse | Snowflake | Databricks SQL |
| BI / dashboards | **Metabase** | QuickSight | Looker | Power BI | Snowsight | Databricks Dashboards |
| Full-text search | **Elasticsearch** | OpenSearch | (Elastic/3p) | Azure AI Search | — | — |
| Embeddings | **sentence-transformers** svc | Bedrock / SageMaker | Vertex AI | Azure OpenAI | **Cortex `EMBED_TEXT`** | FM APIs / MosaicML |
| Vector search | **ES `dense_vector` kNN** | OpenSearch kNN / pgvector | Vertex Vector Search | Azure AI Search | **Cortex Search** | **Vector Search** |
| LLM | **Anthropic Claude** | Bedrock | Vertex | Azure OpenAI | Cortex | FM API / external |
| LLM observability | **Langfuse** | Langfuse / CloudWatch | Langfuse | Langfuse | Langfuse | MLflow / Langfuse |
| Agent framework | **LangGraph** | (same) | (same) | (same) | (same) | (same) |

**Adopting on Snowflake or Databricks** is the smallest leap, because the medallion + dbt + marts pattern is native to both:
- **Snowflake** — keep the medallion as schemas/Iceberg tables; replace dbt-spark with **dbt-snowflake**; replace the publisher with a no-op (gold *is* the serving layer) or a separate serving warehouse; use **Cortex** `EMBED_TEXT` + **Cortex Search** for the RAG/vector layer; orchestrate with Tasks or Airflow. The LangGraph agent and guardrails are unchanged.
- **Databricks** — bronze/silver/gold as **Delta** (or Iceberg) tables in **Unity Catalog**; **dbt-databricks** for transforms; Databricks Workflows for orchestration; **Vector Search** for embeddings/kNN; Databricks SQL for serving + dashboards. The agent points at a SQL Warehouse instead of Postgres.

---

## Warehouse model & curation

```
bronze (Iceberg)     silver (Iceberg)     gold (Iceberg → published to Postgres marts.*)
────────────────     ────────────────     ──────────────────────────────────────────────
activity          →  stg_activity      →  dim_compound · dim_target · dim_assay · dim_document
molecule          →  stg_compound         fact_bioactivity_result        (measurement grain)
target            →  stg_target           mart_compound_target_potency   (CURATED evidence)
assay             →  stg_assay            mart_target_activity_summary · mart_assay_quality
document          →  stg_document         mart_compound_profile · mart_data_quality_summary
                                          graph_compound_target_edge · graph_target_similarity
```

`fact_bioactivity_result` keeps **every** measurement; `mart_compound_target_potency` is the **curated** surface (the default for search + the agent). A row is curated only if **all** hold:

- `standard_type` ∈ {IC50, Ki, Kd, EC50}
- `standard_value_nm` is not null · `pchembl_value` is not null
- `confidence_score >= 7`
- `data_validity_comment` is null/acceptable · `standard_relation` is `'='` or null

`mart_data_quality_summary` aggregates every check and breaks down **excluded rows by reason**, so curation is auditable, not a black box. dbt schema + singular tests enforce the contract on every build.

---

## The governed AI copilot

A read-only scientific copilot — a **LangGraph** state machine (route → execute → summarize): the LLM plans 1–3 governed tool calls and summarizes compact results; **it never receives raw data dumps** and **never writes**. 12 governed tools spanning every serving surface:

| Category | Tools |
|---|---|
| Full-text search (ES) | `search_assay_evidence` |
| **Semantic search (vector kNN)** | `search_knowledge` (embeds the query → ES `dense_vector` kNN, BM25 fallback) |
| Ad-hoc analytics | `ask_warehouse` (**NL→SQL**, generated → guardrail-validated → read-only) · `run_curated_sql` |
| Schema / metadata | `describe_warehouse` |
| Entity lookups | `get_compound_profile` · `get_target_summary` |
| **Graph** | `get_compound_targets` · `get_target_neighbors` |
| Lineage / quality | `explain_data_quality` |
| Glossary / BI | `get_metric_definition` · `get_metabase_dashboard` |

**Guardrails:** a DB-enforced read-only role (`agent_ro`) backs application-level checks — SELECT-only SQL (DDL/DML/COPY/file access/catalog blocked), an allow-list of curated marts, mandatory LIMIT + statement timeout, and full transparency (the exact SQL/filters and result counts are returned and traced). See [docs/agent_design.md](docs/agent_design.md).

**Observability:** every `/ask` is one Langfuse trace — the request span, each LLM generation (with input/output token usage), and a span per tool call — so prompt cost and tool behavior are inspectable end-to-end.

---

## Tech stack

Scala 2.12 + **Apache Spark 3.5** · **Apache Iceberg 1.6** (S3FileIO + JDBC catalog) · **MinIO** · **dbt 1.8** (dbt-spark, via a Spark Thrift Server) · **Postgres** (serving) · **Temporal** (orchestration) · **Elasticsearch 8** (text + vector) · **sentence-transformers** (`all-MiniLM-L6-v2`, 384-d, in a small embedding service) · **Metabase** · **FastAPI + LangGraph + Anthropic Claude** · **Langfuse v3** (Clickhouse + Redis) · **Streamlit** · Docker Compose. Spark/dbt jobs run as containers launched by the Temporal worker via the Docker socket.

---

## Quick start (local, Docker)

**Prerequisites:** Docker + Docker Compose, `make`, and a host with native **Postgres** + **MinIO** (the lakehouse uses the host's Postgres as both the ChEMBL source and the Iceberg JDBC catalog/serving store; MinIO is the object store). See [docs/architecture.md](docs/architecture.md) for the host bootstrap (`scripts/setup_native_postgres.sh`) and restoring the ChEMBL `.dmp`.

```bash
make env                 # .env.example -> .env  (set ANTHROPIC_API_KEY for the agent)
make thrift-up           # Spark Thrift Server over the Iceberg `lake` catalog
make lakehouse           # bronze -> dbt silver/gold -> graph -> publish -> ES index
make up                  # serving + apps: elasticsearch, metabase, agent, ui, embedder, langfuse
make metabase-setup      # provision Metabase models + dashboards against marts.*
make duckdb              # DuckDB console wired to the lakehouse — query Iceberg straight from MinIO
```

**Quick client demo — query the lakehouse from DuckDB.** `make duckdb` reads the live
Iceberg catalog and opens a DuckDB shell with a view per table (`bronze_* / silver_* / gold_*`)
scanning MinIO directly — zero copies, no warehouse needed:

```sql
SELECT target_name, curated_measurements, round(median_potency_nm, 1) AS median_nm
FROM gold_mart_target_activity_summary ORDER BY curated_measurements DESC;
SELECT * FROM gold_graph_target_similarity ORDER BY shared_compounds DESC;
```

> **Langfuse:** log in with the seeded admin (`admin@assaylens.local` / `LANGFUSE_INIT_USER_PASSWORD`
> from `.env`) — that account owns the project the agent traces into. Registering a fresh account
> creates a separate empty org.

Or run the whole medallion under **Temporal** (durable, observable, retryable):

```bash
make pipeline-up         # temporal dev server + worker
make pipeline-run        # one full pipeline run; watch it at http://localhost:8233
# single stage:   docker compose run --rm pipeline-worker python -m orchestration.starter ingest_bronze
# standalone wf:  docker compose run --rm pipeline-worker python -m orchestration.starter --workflow graph_build
```

**Endpoints:** Agent API http://localhost:8000/docs · UI http://localhost:8501 · Metabase http://localhost:3000 · Langfuse http://localhost:3001 · Temporal UI http://localhost:8233 · Elasticsearch http://localhost:9200 · Embedder http://localhost:8100 · MinIO console http://localhost:9001 · DuckDB console `make duckdb`

The Streamlit UI ships **25 example questions** grouped by the tool/graph node each exercises (ES search, semantic/vector RAG, NL→SQL, graph, lineage, dashboards, a multi-step comparison, …).

---

## Repository layout

```
assaylens/
├── docker-compose.yml      # serving + apps + Spark Thrift + Temporal + Langfuse + embedder
├── Makefile                # developer entrypoints (see `make help`)
├── ingestion/              # Scala Spark: ChEMBL (JDBC) → Iceberg bronze
├── dbt/                    # dbt-spark: bronze → silver → gold (+ tests, macros)
├── scripts/                # run_bronze / run_dbt_spark / run_spark_job, build_graph,
│                           #   publish_gold_to_postgres, setup_native_postgres
├── orchestration/          # Temporal workflows + activities + worker (docker-out-of-docker)
├── search/                 # ES indexers (activity-evidence + knowledge/RAG) + mappings
├── embedder/               # sentence-transformers embedding microservice
├── agent/                  # FastAPI + LangGraph governed copilot (12 tools, guardrails, tracing)
├── ui/                     # Streamlit front end (25 canned questions)
├── metabase/               # idempotent dashboard/model provisioner
├── docker/                 # spark-iceberg, dbt-spark, and duckdb (lakehouse console) images
├── postgres/init/          # schema + read-only role bootstrap
├── docs/                   # architecture, data model, agent design, dashboards
└── tests/                  # pytest: SQL guardrails, tool validation, metric definitions
```

---

## Design principles

- **Lakehouse-first, open formats** — Iceberg on object storage; no proprietary lock-in, portable to any engine.
- **Curation is a contract** — comparability rules are explicit, tested, and reported (excluded-by-reason), not implicit.
- **Governed AI** — the agent is read-only, allow-listed, transparent, and fully traced; SQL it generates is validated before it runs.
- **Reproducible & orchestrated** — the whole pipeline is one durable Temporal workflow; re-runs are deterministic.
- **Cloud-agnostic** — every box maps to a managed equivalent; the architecture is the product.

## Caveats

This is a **local dev reference**, not a hardened deployment. Compose ships **dev-default credentials** (e.g. `minioadmin`, local Postgres passwords) and opens services without TLS — fine for a laptop, **not** for any shared/production environment. Secrets belong in `.env` (gitignored); rotate and externalize them (a secrets manager) before deploying anywhere real.

## License & data attribution

Code: **MIT** (see [LICENSE](LICENSE)). Data: ChEMBL is provided by EMBL-EBI under **CC BY-SA 3.0** — cite ChEMBL when reusing derived data. AssayLens makes **no scientific or clinical claims**; it is a data-engineering reference project.
