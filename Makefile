# =============================================================================
# AssayLens — developer entrypoints
#
# Typical first run (lakehouse):
#   make env           # create .env from template
#   bash scripts/setup_native_postgres.sh   # roles/dbs on native PG (one-time)
#   make thrift-up     # Spark Thrift Server over the Iceberg `lake` catalog
#   make bronze        # ChEMBL(JDBC) -> Iceberg lake.bronze.*  (sbt container)
#   make dbt-spark     # silver + gold Iceberg models (dbt-spark)
#   make graph         # gold graph relationship marts
#   make publish       # gold -> native Postgres marts.* (serving)
#   make index         # build elasticsearch index from curated mart
#   make lakehouse     # bronze -> dbt-spark -> graph -> publish -> index (all)
#   make pipeline-up && make pipeline-run   # same flow, orchestrated by Temporal
# =============================================================================
.DEFAULT_GOAL := help
SHELL := /bin/bash

# Load .env if present so recipes can use the same config as the services.
ifneq (,$(wildcard ./.env))
include .env
export
endif

PY ?= python3

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

.PHONY: env
env: ## Create .env from .env.example (no overwrite)
	@test -f .env || (cp .env.example .env && echo "Created .env — fill in ANTHROPIC_API_KEY")

.PHONY: up
up: ## Start core infra (postgres, elasticsearch, metabase, agent, ui)
	docker compose up -d

.PHONY: down
down: ## Stop all services (keeps volumes)
	docker compose down

.PHONY: clean
clean: ## Stop services and delete volumes (DESTRUCTIVE)
	docker compose down -v

.PHONY: thrift-up
thrift-up: ## Start the Spark Thrift Server over the Iceberg `lake` catalog
	docker compose up -d --build spark-thrift
	@echo "Thrift Server on localhost:10000 (Spark UI :4041)"

.PHONY: bronze
bronze: ## Ingest the 5-target ChEMBL slice (Postgres JDBC) -> Iceberg lake.bronze.*
	bash scripts/run_bronze.sh

.PHONY: dbt-spark
dbt-spark: ## Build silver + gold Iceberg models with dbt-spark (+ tests)
	bash scripts/run_dbt_spark.sh build

.PHONY: graph
graph: ## Derive gold graph relationship marts (lake.gold.graph_*)
	bash scripts/run_spark_job.sh build_graph.py

.PHONY: publish
publish: ## Publish every lake.gold.* table to native Postgres marts.*
	bash scripts/run_spark_job.sh publish_gold_to_postgres.py

.PHONY: lakehouse
lakehouse: bronze dbt-spark graph publish index ## Full medallion: bronze -> silver/gold -> graph -> publish -> index

.PHONY: index
index: ## Build the Elasticsearch activity-evidence + knowledge (RAG) indexes
	$(PY) search/build_index.py --recreate
	$(PY) search/build_knowledge_index.py --recreate

.PHONY: pipeline-up
pipeline-up: ## Start the Temporal dev server + pipeline worker
	docker compose up -d --build temporal pipeline-worker
	@echo "Temporal UI: http://localhost:8233"

.PHONY: pipeline-run
pipeline-run: ## Trigger one pipeline run (extract -> dbt -> index) and wait
	docker compose run --rm pipeline-worker python -m orchestration.starter

.PHONY: metabase-setup
metabase-setup: ## Provision Metabase (onboard, DB, semantic models, dashboards, embedding)
	docker run --rm --network assaylens_default --add-host host.docker.internal:host-gateway \
	  -e MB_URL=http://metabase:3000 -e MB_SITE_URL=$(MB_SITE_URL) -e PG_HOST=host.docker.internal \
	  -e MB_ADMIN_EMAIL=$(MB_ADMIN_EMAIL) -e MB_ADMIN_PASSWORD=$(MB_ADMIN_PASSWORD) \
	  -e MB_EMBEDDING_SECRET_KEY=$(MB_EMBEDDING_SECRET_KEY) \
	  -v "$(PWD)":/work -w /work python:3.11-slim \
	  bash -lc 'pip install -q requests && python metabase/setup_metabase.py'

.PHONY: agent
agent: ## Run the FastAPI agent locally (hot reload)
	cd agent && uvicorn app.main:app --reload --host $(AGENT_HOST) --port $(AGENT_PORT)

.PHONY: ui
ui: ## Run the Streamlit UI locally
	streamlit run ui/streamlit_app.py

.PHONY: test
test: ## Run python unit tests (guardrails + metric definitions)
	pytest -q tests/

.PHONY: demo
demo: up thrift-up lakehouse ## End-to-end local demo from scratch (lakehouse + serving)
	@echo "AssayLens demo data ready. Start the agent with 'make agent' and UI with 'make ui'."
