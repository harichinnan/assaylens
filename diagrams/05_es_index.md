# 5 · Elasticsearch activity-evidence index

How the full-text search index is produced. `search/build_index.py` reads the
curated potency mart from Postgres and bulk-loads one document per
compound-target-assay measurement into the `assaylens_activity_evidence` index,
which the agent's `search_assay_evidence` tool queries.

```mermaid
flowchart TD
  classDef serve fill:#e3f2fd,stroke:#1565c0,color:#000;
  classDef job  fill:#ede7f6,stroke:#5e35b1,color:#000;
  classDef es   fill:#fbe9e7,stroke:#d84315,color:#000;
  classDef cfg  fill:#eceff1,stroke:#607d8b,color:#000;
  classDef use  fill:#e0f7fa,stroke:#00838f,color:#000;

  PG[("Postgres marts.mart_compound_target_potency<br/>(curated rows)")]:::serve

  subgraph JOB["search/build_index.py  (Temporal build_index stage)"]
    direction TB
    SEL["SELECT 14 fields<br/>activity_id, compound/target/assay ids + names,<br/>standard_type, standard_value_nm, pchembl_value,<br/>confidence_score, journal, year"]:::job
    ENS["ensure_index (--recreate)"]:::job
    BULK["helpers.bulk · _id = activity_id<br/>then refresh"]:::job
    SEL --> BULK
    ENS --> BULK
  end

  MAP["index_mapping.json<br/>analyzer assay_text = standard + lowercase + asciifolding<br/>text: compound/target/assay_description/journal<br/>keyword: *_chembl_id, standard_type · numeric: nm/pchembl/score/year"]:::cfg
  MAP --> ENS

  PG --> SEL

  ES[("Elasticsearch index<br/>assaylens_activity_evidence")]:::es
  BULK --> ES

  T1["agent: search_assay_evidence<br/>multi_match(text) + filters<br/>(target, standard_type, max_value_nm, min_confidence)"]:::use
  ES --> T1
```

Grain = one curated measurement (≈65k docs). Connects to Postgres as the
`assaylens` role (a write-side indexing job, not the read-only agent role). Run
via `make index` or the Temporal `build_index` activity (which also builds the
knowledge/vector index — see diagram 6).
