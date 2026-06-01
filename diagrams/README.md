# Diagrams

Architecture diagrams for AssayLens, authored in [Mermaid](https://mermaid.js.org/)
so they render directly on GitHub and stay version-controlled with the code.
SVG exports (for slides / client demos) sit alongside each source when rendered.

| # | Diagram | What it shows |
|---|---------|---------------|
| 1 | [Data-lake model & dependency graph](01_data_model.md) | Medallion (Bronze→Silver→Gold) Iceberg tables, the dbt/Spark `ref()` build-dependency graph, and the serving star schema (ER). |
| 2 | [Temporal workflows as DAGs](02_temporal_workflows.md) | The `AssayLensPipeline` activity DAG (+ what each stage launches), retry semantics, and the standalone graph-build / index workflows. |
| 3 | [LangGraph governed copilot](03_langgraph_agent.md) | The route→execute→summarize state machine, all 12 tools and the backend each reads (ES, vector RAG, Postgres marts, Metabase), guardrails, and Langfuse tracing. |
| 4 | [Graph lineage](04_graph_lineage.md) | How the Spark graph job derives `graph_compound_target_edge` (group-by) and `graph_target_similarity` (self-join + Jaccard) from the curated mart, then publishes them and who consumes them. |
| 5 | [Elasticsearch activity index](05_es_index.md) | `build_index.py`: curated mart (Postgres) → SELECT → bulk-load → `assaylens_activity_evidence` (mapping/analyzer) → `search_assay_evidence`. |
| 6 | [Vector embeddings (semantic RAG)](06_vector_embeddings.md) | `build_knowledge_index.py`: marts → docs → embedder (all-MiniLM-L6-v2, 384-d) → `dense_vector` in `assaylens_knowledge`; plus the `search_knowledge` query/kNN path. |

## Re-render SVGs

```bash
make diagrams      # renders diagrams/*.svg from the Mermaid sources (mermaid-cli in Docker)
```
