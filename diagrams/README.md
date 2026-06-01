# Diagrams

Architecture diagrams for AssayLens, authored in [Mermaid](https://mermaid.js.org/)
so they render directly on GitHub and stay version-controlled with the code.
SVG exports (for slides / client demos) sit alongside each source when rendered.

| # | Diagram | What it shows |
|---|---------|---------------|
| 1 | [Data-lake model & dependency graph](01_data_model.md) | Medallion (Bronze→Silver→Gold) Iceberg tables, the dbt/Spark `ref()` build-dependency graph, and the serving star schema (ER). |
| 2 | [Temporal workflows as DAGs](02_temporal_workflows.md) | The `AssayLensPipeline` activity DAG (+ what each stage launches), retry semantics, and the standalone graph-build / index workflows. |
| 3 | [LangGraph governed copilot](03_langgraph_agent.md) | The route→execute→summarize state machine, all 12 tools and the backend each reads (ES, vector RAG, Postgres marts, Metabase), guardrails, and Langfuse tracing. |

## Re-render SVGs

```bash
make diagrams      # renders diagrams/*.svg from the Mermaid sources (mermaid-cli in Docker)
```
