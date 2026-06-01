# 2 · Temporal workflows as DAGs

The medallion pipeline is a durable, replayable Temporal workflow. Each stage is
an **activity** (own timeout + retry policy) that the worker runs by launching a
job container via the Docker socket (docker-out-of-docker). The stage list is a
run parameter, and two **standalone workflows** re-run just the graph build or
the indexing without re-ingesting.

Task queue: `assaylens-pipeline` · Worker: `assaylens-pipeline-worker` ·
Per-activity: `start_to_close=30m`, `heartbeat=5m`, retry `3×` exp-backoff.

```mermaid
flowchart TD
  classDef act fill:#ede7f6,stroke:#5e35b1,color:#000;
  classDef job fill:#fff3e0,stroke:#e65100,color:#000;
  classDef store fill:#e3f2fd,stroke:#1565c0,color:#000;
  classDef wf fill:#e8f5e9,stroke:#2e7d32,color:#000;

  START(["▶ start_workflow"]):::wf

  subgraph PIPE["Workflow: AssayLensPipeline (default stages)"]
    direction TD
    A1["ingest_bronze"]:::act
    A2["dbt_build"]:::act
    A3["build_graph"]:::act
    A4["publish_marts"]:::act
    A5["build_index"]:::act
    A1 --> A2 --> A3 --> A4 --> A5
  end

  START --> A1
  A5 --> DONE(["✓ result: per-stage summary"]):::wf

  %% what each activity launches (docker-out-of-docker) + what it writes
  A1 -. "run_bronze.sh → sbt container" .-> J1["Scala Spark<br/>JDBC → lake.bronze.*"]:::job
  A2 -. "run_dbt_spark.sh → dbt-spark" .-> J2["dbt-spark via Thrift<br/>lake.silver.* + lake.gold.*"]:::job
  A3 -. "run_spark_job.sh build_graph.py" .-> J3["Spark<br/>lake.gold.graph_*"]:::job
  A4 -. "run_spark_job.sh publish…" .-> J4["Spark JDBC<br/>→ Postgres marts.*"]:::job
  A5 -. "build_index + build_knowledge_index" .-> J5["Elasticsearch<br/>activity + knowledge(vec)"]:::job

  J4 --> PGS[("Postgres marts.*")]:::store
  J5 --> ESS[("Elasticsearch")]:::store

  %% standalone workflows (backlog G)
  subgraph STAND["Standalone workflows (run independently)"]
    direction LR
    G1(["GraphBuildWorkflow"]):::wf --> Ga["build_graph"]:::act
    I1(["IndexWorkflow"]):::wf --> Ia["build_index"]:::act
  end
  Ga -. reuses .-> J3
  Ia -. reuses .-> J5
```

**Retry semantics (per activity):**

```mermaid
flowchart LR
  classDef act fill:#ede7f6,stroke:#5e35b1,color:#000;
  R["activity attempt"]:::act -->|success| OK([next stage])
  R -->|"failure (transient)"| W{"attempts < 3?"}
  W -->|yes| B["backoff 5s → ×2 → ≤60s"] --> R
  W -->|no| F([workflow fails · replayable in UI :8233])
```

Run: `make pipeline-up && make pipeline-run` · single stage:
`… starter ingest_bronze` · standalone: `… starter --workflow graph_build|index`.
