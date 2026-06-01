# AssayLens — Session Handoff / Resume State

_Last updated: 2026-06-01. Pick up here next session._

## TL;DR
The **MinIO/Iceberg medallion lakehouse is BUILT and runs end-to-end**, orchestrated
by Temporal: ChEMBL (Postgres JDBC) → Iceberg **bronze → silver → gold** (dbt-spark)
→ Spark **graph** marts → **publisher** to native Postgres `marts.*` → Elasticsearch
index. Postgres is **serving-only** now (Docker Postgres abandoned). Last full run:
`PASS=63 ERROR=0` dbt, 12 gold tables published, 65,206 ES docs indexed. Analysis is
scoped to the **5 kinase targets** by design. Disk ~159 GB free (no longer binding).

## Architecture (IMPLEMENTED)
```
ChEMBL 37 restored in native Postgres  (assaylens.public.*, 24.5M activities)
   │  Scala Spark, JDBC pushdown (ChemblJdbcSource) — 5-target scope + nM normalization
   ▼
ICEBERG BRONZE  lake.bronze.*   (MinIO s3://assaylens/lakehouse ; JdbcCatalog DB 'iceberg_catalog')
   │  dbt-spark (SparkSQL over Iceberg, via Spark Thrift Server)
   ▼
ICEBERG SILVER lake.silver.stg_*   ──► Spark graph job ──► lake.gold.graph_* (edges + similarity)
   │  dbt-spark
   ▼
ICEBERG GOLD  lake.gold.{dim_*,fact_*,mart_*,graph_*}
   │  publisher (PySpark, gold → JDBC)
   ▼
NATIVE POSTGRES  assaylens.marts.*  (SERVING)  ──► Elasticsearch · Metabase · LangGraph agent (agent_ro)
```
- `lake` = Iceberg `SparkCatalog`/`JdbcCatalog` on `iceberg_catalog`, warehouse
  `s3://assaylens/lakehouse`, `S3FileIO` → MinIO. `lake` is the Spark **default catalog**,
  so dbt's 2-part `silver.x`/`gold.x` names resolve into it. Bronze sbt job also creates
  the `lake.default` namespace (the Thrift Server opens sessions there).

## What is UP / how to run
- **MinIO** (native binary): `:9000` (console `:9001`), `minioadmin/minioadmin`,
  data `~/dev/work/minio-data`, bucket `assaylens`. Restart: see Useful commands.
- **Native Postgres 14** (Homebrew): superuser `harichinnan`. DBs `assaylens`, `metabase`,
  `iceberg_catalog` (owned by assaylens). Roles `assaylens`/`assaylens`, `agent_ro`/`agent_ro`.
  - **Full ChEMBL 37 in `assaylens.public.*`** (~22 GB; see [[chembl-restore-btree-index]]).
  - `assaylens.marts.*` = 12 published serving tables; `agent_ro` has SELECT (durable via
    `ALTER DEFAULT PRIVILEGES FOR ROLE assaylens` — the publisher recreates marts each run).
  - pg_hba/listen opened for containers (`host.docker.internal`). Bootstrap:
    `bash scripts/setup_native_postgres.sh`.
- **Docker compose** (postgres service REMOVED; all repointed to `host.docker.internal`):
  `elasticsearch`, `metabase` (:3000, 5 dashboards incl. **Target Relationships** id=5),
  `agent` (:8000, 12 tools, Langfuse tracing on), `ui` (:8501), `temporal` (host gRPC **7244**,
  UI 8233), `pipeline-worker` (Temporal worker, **docker-out-of-docker** via mounted socket +
  `HOST_REPO_DIR`), `spark-thrift` (Spark Thrift Server, `lake` catalog, host `:10000`).
- **Langfuse v3** (LLM observability, self-hosted): `langfuse-web` (UI **:3001**, admin
  `admin@assaylens.local`), `langfuse-worker`, `clickhouse`, `redis` — reuse native PG (db
  `langfuse`) + MinIO (bucket `langfuse`). Agent traces every /ask (root span + llm
  generations w/ token usage + tool spans). Keys/secrets in `.env` (`LANGFUSE_*`).
- **Two ES indexes**: `assaylens_activity_evidence` (65k curated rows) + `assaylens_knowledge`
  (~4k RAG docs w/ 384-d embeddings: target summaries, assays, target relationships, metric glossary).
- **Embedder** (`embedder`, host **:8100**): sentence-transformers `all-MiniLM-L6-v2` (384-d,
  CPU). Powers dense-vector kNN in `search_knowledge`; indexer + agent both call it. (Pin
  `torch==2.2.2` + `numpy<2` — newer torch pulls CUDA wheels and numpy 2 breaks `.numpy()`.)
- **Run the lakehouse** (host): `make thrift-up` then `make lakehouse`
  (= bronze → dbt-spark → graph → publish → index). Or orchestrated:
  `make pipeline-up && make pipeline-run` (Temporal `AssayLensPipeline`, 5 stages).
  Single stage: `docker compose run --rm pipeline-worker python -m orchestration.starter ingest_bronze`.

## Hard constraints / caveats
- **arm64 (Apple Silicon).** The JDK17 **sbt** Bronze image needs `-XX:UseSVE=0`; the
  **Spark** image is **JDK 11** and must NOT get that flag (it aborts the JVM).
- dbt-spark thrift uses **NOSASL** on both sides (`auth: NOSASL` + STS
  `hive.server2.authentication=NOSASL`) — SASL handshake otherwise hangs.
- dbt image pins **`dbt-core==1.8.7`** (unpinned resolves to 2.0.0a1 Fusion, no Spark adapter).
- **Rotate the Anthropic API key** (in `.env` + earlier chat); also Metabase secret / dev DB pws.

## Code state (working tree; repo is NOT git-initialized)
- **Ingestion (Scala Spark)** `ingestion/`: `Main` (Iceberg `lake` SparkSession) +
  `ChemblJdbcSource` (5-target pushdown SQL) + `WriteIceberg` → `lake.bronze.*`. Build deps:
  iceberg-spark-runtime/aws-bundle 1.6.1, postgresql 42.7.3. (Legacy REST client retained, off-path.)
- **dbt** `dbt/` → **dbt-spark** (target `spark`): sources→`bronze`, staging→`silver` (tables),
  marts→`gold`, `+file_format: iceberg`. SparkSQL fixes: dedup via `row_number` (no
  `distinct on`/`* except`), `cast()`, `percentile()` with pre-aggregation (avoids the
  cartesian OOM in `mart_target_activity_summary`).
- **Orchestration** `orchestration/`: `AssayLensPipeline` with parameterizable stages
  `ingest_bronze → dbt_build → build_graph → publish_marts → build_index`; activities shell
  out to `scripts/run_*.sh` which `docker run` the job containers via the socket.
- **scripts/**: `run_bronze.sh`, `run_dbt_spark.sh`, `run_spark_job.sh` (host-path aware via
  HOST_REPO_DIR), `build_graph.py`, `publish_gold_to_postgres.py`, `setup_native_postgres.sh`,
  `extract_raw_from_chembl.sql` (direct-to-Postgres alt path, still valid).
- **docker/**: `spark-iceberg/Dockerfile` (apache/spark 3.5.1 + Iceberg/AWS/PG jars),
  `dbt-spark/Dockerfile` (dbt-core 1.8.7 + dbt-spark[PyHive]).
- **Agent (LangGraph)** `agent/`: 12 governed tools incl. new `ask_warehouse` (NL→SQL),
  `search_knowledge` (RAG), `get_target_neighbors` + `get_compound_targets` (graph),
  `describe_warehouse` (schema/meta — "how many tables"). Langfuse
  instrumentation in `app/tracing.py` (no-op if unconfigured). `app/llm.py`, `app/main.py`,
  `app/graph.py` wrapped. **search** `search/build_index.py` + `build_knowledge_index.py`.
  **Metabase** `metabase/setup_metabase.py` — 7 models + 5 dashboards, against native PG `marts.*`.

## Backlog — DONE 2026-06-01 (was A/B/C/D/G)
- **A. RAG** ✓ `assaylens_knowledge` ES corpus + `search_knowledge` tool with **dense-vector
  kNN** (sentence-transformers via the `embedder` service) and a lexical BM25 fallback.
- **B. NL→SQL** ✓ `ask_warehouse` tool: LLM drafts SQL → `validate_sql` guardrail → agent_ro.
  Allow-list broadened to the graph marts.
- **C. Langfuse v3** ✓ self-hosted stack + agent instrumentation (`app/tracing.py`); traces
  verified via the public API.
- **D. Graph** ✓ tools (`get_target_neighbors`, `get_compound_targets`), Metabase **Target
  Relationships** dashboard (id 5), ES relationship docs folded into the knowledge index.
- **G. Workflows** ✓ standalone `GraphBuildWorkflow` + `IndexWorkflow`
  (`starter --workflow graph_build|index`), plus the full `AssayLensPipeline`.

### Still open / next upgrades
- **Hybrid RRF**: `search_knowledge` does semantic kNN OR lexical fallback; true hybrid
  (RRF-combined) needs an ES trial license — optional.
- **Langfuse worker** logs benign `prisma:error` upserting managed evaluators on boot — cosmetic.
- **Rotate secrets** (`.env`): Anthropic key, Langfuse keys, Metabase secret, dev DB passwords.

## Recommended resume order
1. `make pipeline-up && make pipeline-run` (green pipeline), `make up` (serving + Langfuse).
2. Smoke the agent: `curl -XPOST localhost:8000/ask -d '{"question":"..."}'`; watch traces at :3001.
3. Optional upgrades above (dense-vector RAG, secret rotation).

## Useful commands
- Lakehouse (host): `make thrift-up`, `make bronze`, `make dbt-spark`, `make graph`, `make publish`, `make lakehouse`.
- Temporal: `make pipeline-up`, `make pipeline-run` (UI http://localhost:8233).
- Standalone workflows (G): `docker compose run --rm pipeline-worker python -m orchestration.starter --workflow graph_build` (or `index`).
- Serving + observability: `make up` (agent :8000, ui :8501, metabase :3000, **Langfuse :3001**), `make metabase-setup`.
- Langfuse traces API: `curl -H "Authorization: Basic $(printf '<pk>:<sk>'|base64)" localhost:3001/api/public/traces`.
- Thrift/beeline probe: `docker run --rm --add-host host.docker.internal:host-gateway assaylens/spark-iceberg:latest /opt/spark/bin/beeline -u "jdbc:hive2://host.docker.internal:10000/default;auth=noSasl" -n dbt -e "SHOW TABLES IN lake.gold;"`
- MinIO restart: `MINIO_ROOT_USER=minioadmin MINIO_ROOT_PASSWORD=minioadmin minio server ~/dev/work/minio-data --address :9000 --console-address :9001`
- Iceberg tables: `psql -h 127.0.0.1 -U harichinnan -d iceberg_catalog -c "select table_namespace,table_name from iceberg_tables order by 1,2"`
- Native PG marts: `psql -h 127.0.0.1 -U harichinnan -d assaylens -c "\dt marts.*"`
- Re-restore ChEMBL: `pg_restore -h 127.0.0.1 -U harichinnan -d assaylens --no-owner --no-privileges -j4 ~/dev/work/20260531/chembl_37_postgresql.dmp`
