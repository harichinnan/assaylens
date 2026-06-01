# 6 · Vector embeddings (semantic RAG)

How dense-vector embeddings are created and used. `search/build_knowledge_index.py`
assembles short knowledge documents from the marts, embeds them via the embedding
microservice (sentence-transformers `all-MiniLM-L6-v2`, 384-d), and stores them in
a `dense_vector` field. The agent's `search_knowledge` tool embeds the query and
retrieves by cosine **kNN** (with a lexical BM25 fallback).

## Build path

```mermaid
flowchart TD
  classDef serve fill:#e3f2fd,stroke:#1565c0,color:#000;
  classDef job  fill:#ede7f6,stroke:#5e35b1,color:#000;
  classDef svc  fill:#f1f8e9,stroke:#558b3a,color:#000;
  classDef es   fill:#fbe9e7,stroke:#d84315,color:#000;
  classDef cfg  fill:#eceff1,stroke:#607d8b,color:#000;

  subgraph SRC["Document sources · Postgres marts.* (+ static)"]
    direction TB
    D1["mart_target_activity_summary → target_summary (5)"]:::serve
    D2["graph_target_similarity → target_relationship (10)"]:::serve
    D3["mart_assay_quality → assay (≤4000)"]:::serve
    D4["static glossary → metric_glossary (7)"]:::serve
  end

  subgraph JOB["search/build_knowledge_index.py"]
    direction TB
    ASM["assemble docs<br/>{doc_id, doc_type, title, text, ...}"]:::job
    EMB1["embed_texts(title + text)<br/>POST /embed in batches"]:::job
    ATT["attach embedding[384] to each doc"]:::job
    BULK["helpers.bulk · _id = doc_id · refresh"]:::job
    ASM --> EMB1 --> ATT --> BULK
  end

  D1 --> ASM
  D2 --> ASM
  D3 --> ASM
  D4 --> ASM

  EMBED["Embedder service (:8100)<br/>sentence-transformers all-MiniLM-L6-v2<br/>384-d · L2-normalized"]:::svc
  EMB1 -->|texts| EMBED -->|vectors| EMB1

  MAP["knowledge_mapping.json<br/>embedding: dense_vector(384, cosine, index=true)<br/>+ text: title/text · keyword: doc_type/entity_id"]:::cfg

  ESK[("Elasticsearch index<br/>assaylens_knowledge (~4022 docs)")]:::es
  MAP --> ESK
  BULK --> ESK
```

## Query path (what `search_knowledge` does)

```mermaid
flowchart LR
  classDef svc fill:#f1f8e9,stroke:#558b3a,color:#000;
  classDef es  fill:#fbe9e7,stroke:#d84315,color:#000;
  classDef use fill:#e0f7fa,stroke:#00838f,color:#000;
  classDef llm fill:#fce4ec,stroke:#c2185b,color:#000;

  Q["search_knowledge(query, doc_type?)"]:::use
  EMBED["Embedder /embed<br/>query → vector[384]"]:::svc
  KNN["ES kNN search<br/>field=embedding · cosine · k · num_candidates<br/>filter: doc_type"]:::es
  BM25["BM25 multi_match<br/>(fallback if embedder down)"]:::es
  P["top-k passages → LLM summarizer"]:::llm

  Q -->|"mode = semantic (default)"| EMBED --> KNN --> P
  Q -. "embedder unavailable" .-> BM25 --> P
```

Built in the same Temporal `build_index` stage as the activity-evidence index
(diagram 5). The embedding service is a shared microservice so the indexer and
the agent use one model copy; the MinIO/S3 secret in DuckDB and Spark is unrelated
to this path.
