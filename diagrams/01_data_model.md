# 1 · Data-lake model & dependency graph

The medallion lakehouse (Apache Iceberg on MinIO) and the dbt/Spark **build
dependency graph** — every edge is a `ref()`/`source()` dependency, from the
ChEMBL source through Bronze → Silver → Gold and out to the Postgres serving marts.

```mermaid
flowchart LR
  classDef src   fill:#eceff1,stroke:#607d8b,color:#000;
  classDef bronze fill:#fff3e0,stroke:#e65100,color:#000;
  classDef silver fill:#eceff1,stroke:#455a64,color:#000;
  classDef gold  fill:#fff8e1,stroke:#f9a825,color:#000;
  classDef grph fill:#e8f5e9,stroke:#2e7d32,color:#000;
  classDef serve fill:#e3f2fd,stroke:#1565c0,color:#000;

  subgraph SRC["Source · Postgres (restored ChEMBL)"]
    CH[("public.* — full ChEMBL 37")]:::src
  end

  subgraph BRONZE["🥉 BRONZE · lake.bronze.* (Iceberg / MinIO) — Scala Spark, JDBC pushdown"]
    Bact["activity"]:::bronze
    Bmol["molecule"]:::bronze
    Btgt["target"]:::bronze
    Basy["assay"]:::bronze
    Bdoc["document"]:::bronze
  end

  subgraph SILVER["🥈 SILVER · lake.silver.stg_* (Iceberg) — dbt-spark"]
    Sact["stg_activity"]:::silver
    Smol["stg_compound"]:::silver
    Stgt["stg_target"]:::silver
    Sasy["stg_assay"]:::silver
    Sdoc["stg_document"]:::silver
  end

  subgraph GOLD["🥇 GOLD · lake.gold.* (Iceberg) — dbt-spark + Spark graph job"]
    Dcmp["dim_compound"]:::gold
    Dtgt["dim_target"]:::gold
    Dasy["dim_assay"]:::gold
    Ddoc["dim_document"]:::gold
    FACT["fact_bioactivity_result<br/>(measurement grain)"]:::gold
    Mpot["mart_compound_target_potency<br/>(CURATED)"]:::gold
    Mtas["mart_target_activity_summary"]:::gold
    Masq["mart_assay_quality"]:::gold
    Mcp["mart_compound_profile"]:::gold
    Mdq["mart_data_quality_summary"]:::gold
    Gedge["graph_compound_target_edge"]:::grph
    Gsim["graph_target_similarity"]:::grph
  end

  subgraph SERVE["Serving · Postgres assaylens.marts.* (read-only agent_ro)"]
    PG[("marts.* — 12 published tables")]:::serve
  end

  CH -->|"5-target slice + nM normalization"| Bact & Bmol & Btgt & Basy & Bdoc

  Bact --> Sact
  Bmol --> Smol
  Btgt --> Stgt
  Basy --> Sasy
  Bdoc --> Sdoc

  Smol --> Dcmp
  Stgt --> Dtgt
  Sasy --> Dasy
  Sdoc --> Ddoc

  Sact --> FACT
  Dcmp --> FACT
  Dtgt --> FACT
  Dasy --> FACT
  Ddoc --> FACT

  FACT --> Mpot
  Dcmp --> Mpot
  Dtgt --> Mpot
  Dasy --> Mpot
  Ddoc --> Mpot

  Mpot --> Mtas
  FACT --> Mtas
  Dtgt --> Mtas

  FACT --> Masq
  Dasy --> Masq
  Dtgt --> Masq

  Dcmp --> Mcp
  FACT --> Mcp
  Mpot --> Mcp

  FACT --> Mdq

  Mpot --> Gedge
  Mpot --> Gsim

  Dcmp & Dtgt & Dasy & Ddoc & FACT & Mpot & Mtas & Masq & Mcp & Mdq & Gedge & Gsim -->|"Spark publisher (JDBC)"| PG
```

## Star schema (serving grain)

`fact_bioactivity_result` is the measurement-grain fact; `mart_compound_target_potency`
is the curated subset; the two `graph_*` marts are derived relationship tables.

```mermaid
erDiagram
  DIM_COMPOUND   ||--o{ FACT_BIOACTIVITY_RESULT : compound_key
  DIM_TARGET     ||--o{ FACT_BIOACTIVITY_RESULT : target_key
  DIM_ASSAY      ||--o{ FACT_BIOACTIVITY_RESULT : assay_key
  DIM_DOCUMENT   ||--o{ FACT_BIOACTIVITY_RESULT : document_key
  FACT_BIOACTIVITY_RESULT ||--o| MART_COMPOUND_TARGET_POTENCY : "curated subset"
  DIM_COMPOUND   ||--o{ GRAPH_COMPOUND_TARGET_EDGE : molecule_chembl_id
  DIM_TARGET     ||--o{ GRAPH_COMPOUND_TARGET_EDGE : target_chembl_id
  DIM_TARGET     ||--o{ GRAPH_TARGET_SIMILARITY : "target_a / target_b"

  DIM_COMPOUND {
    string compound_key PK
    string molecule_chembl_id
    string pref_name
    string canonical_smiles
    double molecular_weight
    double alogp
  }
  DIM_TARGET {
    string target_key PK
    string target_chembl_id
    string target_name
    string organism
  }
  DIM_ASSAY {
    string assay_key PK
    string assay_chembl_id
    string assay_type
    int    confidence_score
  }
  DIM_DOCUMENT {
    string document_key PK
    string document_chembl_id
    int    pubmed_id
    int    year
  }
  FACT_BIOACTIVITY_RESULT {
    long   activity_id PK
    string compound_key FK
    string target_key FK
    string assay_key FK
    string document_key FK
    string standard_type
    double standard_value_nm
    double pchembl_value
    int    confidence_score
  }
  MART_COMPOUND_TARGET_POTENCY {
    long   activity_id PK
    string molecule_chembl_id
    string target_chembl_id
    string standard_type
    double standard_value_nm
    double pchembl_value
  }
  GRAPH_COMPOUND_TARGET_EDGE {
    string molecule_chembl_id
    string target_chembl_id
    double best_pchembl
    long   n_measurements
  }
  GRAPH_TARGET_SIMILARITY {
    string target_a
    string target_b
    long   shared_compounds
    double jaccard
  }
```

**Curation gate** — a `fact_bioactivity_result` row enters `mart_compound_target_potency`
only if: `standard_type ∈ {IC50,Ki,Kd,EC50}` · `standard_value_nm` not null · `pchembl_value`
not null · `confidence_score ≥ 7` · `data_validity_comment` null · `standard_relation` `=`/null.
