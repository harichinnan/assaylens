# 4 · Graph lineage

How the two GOLD relationship marts are derived. The Spark graph job
(`scripts/build_graph.py`) reads only the **curated** potency mart and produces
a compound↔target edge list and a target↔target similarity graph; the publisher
copies them to Postgres, where agent tools, the knowledge index, and Metabase
consume them.

```mermaid
flowchart TD
  classDef gold fill:#fff8e1,stroke:#f9a825,color:#000;
  classDef job  fill:#ede7f6,stroke:#5e35b1,color:#000;
  classDef grph fill:#e8f5e9,stroke:#2e7d32,color:#000;
  classDef serve fill:#e3f2fd,stroke:#1565c0,color:#000;
  classDef use  fill:#e0f7fa,stroke:#00838f,color:#000;

  MCTP["lake.gold.mart_compound_target_potency<br/>(curated evidence — the only input)"]:::gold

  subgraph JOB["Spark graph job · scripts/build_graph.py"]
    direction TB
    EAGG["edges: group by<br/>(molecule, target)"]:::job
    SDIST["distinct (compound, target)<br/>+ per-target compound counts"]:::job
    SJOIN["self-join a.molecule = b.molecule<br/>AND a.target &lt; b.target"]:::job
    JAC["jaccard = shared / (|A|+|B|-shared)"]:::job
    SDIST --> SJOIN --> JAC
  end

  MCTP --> EAGG
  MCTP --> SDIST

  GE["lake.gold.graph_compound_target_edge<br/>best_pchembl · best_potency_nm · n_measurements"]:::grph
  GS["lake.gold.graph_target_similarity<br/>shared_compounds · jaccard"]:::grph

  EAGG --> GE
  JAC --> GS

  PG[("Postgres marts.graph_compound_target_edge<br/>marts.graph_target_similarity")]:::serve
  GE -->|"Spark publisher (JDBC)"| PG
  GS -->|"Spark publisher (JDBC)"| PG

  subgraph USE["Consumers"]
    direction TB
    T7["agent: get_compound_targets"]:::use
    T9["agent: get_target_neighbors"]:::use
    KN["knowledge index: target_relationship docs"]:::use
    MB["Metabase: Target Relationships dashboard"]:::use
  end

  PG --> T7
  PG --> T9
  PG --> KN
  PG --> MB
```

**Edge mart** = one row per (compound, target): strongest curated pChEMBL, best
nM potency, and supporting measurement count. **Similarity mart** = one undirected
row per target pair sharing ≥1 curated compound, weighted by shared-compound count
and Jaccard over their curated compound sets. Both run in the Temporal
`build_graph` stage (or the standalone `GraphBuildWorkflow`).
