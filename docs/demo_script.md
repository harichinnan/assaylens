# 5-minute demo script

A recordable walkthrough that tells the data-engineering story end to end. Use
the offline sample so it runs anywhere with no ChEMBL network dependency.

**Pre-roll (before recording):**
```bash
make env            # set ANTHROPIC_API_KEY in .env (optional; fallback works without)
make up             # postgres, elasticsearch, metabase, agent, ui
make ingest-offline # Spark → Parquet from sample fixtures
make load           # Parquet → Postgres raw
make dbt            # build + test the warehouse
make index          # build the Elasticsearch index
```

---

### 0:00 — Framing (20s)
> "AssayLens is an open-source scientific data warehouse for public ChEMBL
> bioactivity data. It's not a chemistry project — it's a data-engineering one:
> ingestion, dimensional modeling, data quality, search, BI, and a *governed* AI
> copilot. Stack is Spark → Parquet → Postgres → dbt → Metabase / Elasticsearch /
> FastAPI. No DuckDB — it's built to port to a real warehouse."

### 0:20 — Ingestion & the lake (40s)
- Show `data/seeds/target_seed.csv` (5 kinase targets) — "this is the entire
  ingestion scope."
- Show `ingestion/.../ActivityIngestionJob.scala` + `NormalizeUnits.scala` —
  "Scala Spark pulls ChEMBL, normalizes units to nM at ingestion time."
- Show `data/lake/` Parquet output. "Parquet is the contract to the warehouse."

### 1:00 — Warehouse & dbt (60s)
- `make dbt` output (or scroll the run): staging → dims/fact → marts, tests pass.
- Open `dbt/macros/curation.sql`: "the curation rule is code, defined once."
- In Postgres (or Metabase SQL): `select * from marts.mart_compound_target_potency;`
  — "only comparable rows survive: IC50/Ki/Kd/EC50, normalized nM, pChEMBL
  present, confidence ≥ 7, exact relation, no validity flag."
- `select * from marts.mart_data_quality_summary where metric_group='excluded_by_reason';`
  — "and we track *why* every excluded row was dropped."

### 2:00 — BI (45s)
- Metabase → **Scientific Warehouse Overview**: totals, % normalized, % pChEMBL,
  excluded rows.
- **Data Quality** dashboard: excluded-by-reason, ambiguous relations,
  low-confidence assays, duplicates. "Governance is visible, not hidden."

### 2:45 — Search (30s)
- Show `search/sample_queries.md`, then hit Elasticsearch:
  "EGFR + IC50 + standard_value_nm < 100, sorted by pChEMBL." Curated evidence
  only — search never sees junk rows.

### 3:15 — Governed AI copilot (90s)
Open the Streamlit UI (http://localhost:8501). Ask, narrating that each answer
shows the tool + filters/SQL it used:
1. "Find high-confidence EGFR assays with IC50 under 100 nM." → `search_assay_evidence`.
2. "Why do raw EGFR rows differ from the curated EGFR potency mart?" →
   `explain_data_quality` (inclusion/exclusion reasons).
3. "Explain pChEMBL versus IC50 in plain English." → `get_metric_definition`.
- Then show a *blocked* query to prove the guardrails:
  in `/docs` (FastAPI) or via the SQL tool, attempt
  `DROP TABLE marts.dim_target` → rejected. "Read-only, SELECT-only,
  curated-marts-only, with a DB-enforced read-only role beneath the app."

### 4:45 — Close (15s)
> "Spark ingestion, a tested dbt warehouse with explicit curation and data
> quality, search and BI on top, and an AI layer that can only ever read
> governed, curated data and always shows its work. That's AssayLens."

---

**Tips:** keep a terminal + browser side by side; pre-open Metabase dashboards
and the Streamlit tab; if recording offline, confirm `make index` succeeded so
search returns hits.
