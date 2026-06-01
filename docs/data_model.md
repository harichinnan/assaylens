# Data model

## Grain

The warehouse's central grain is **one bioactivity measurement**: a compound
tested against a target in an assay, yielding an activity value (IC50, Ki, Kd,
EC50, …). That grain lives in `fact_bioactivity_result`.

## Layers

```
raw schema            staging schema     marts schema (dims + fact)     marts schema (marts)
──────────            ──────────────     ──────────────────────────     ────────────────────
raw_chembl_molecule → stg_compound   ─┐  dim_compound ─┐                 mart_compound_target_potency  (curated)
raw_chembl_target   → stg_target     ─┤  dim_target    ├─ fact_          mart_target_activity_summary
raw_chembl_assay    → stg_assay      ─┤  dim_assay     │  bioactivity_   mart_assay_quality
raw_chembl_document → stg_document   ─┤  dim_document  │  result         mart_compound_profile
raw_chembl_activity → stg_activity   ─┘                ┘                 mart_data_quality_summary
```

- **raw** — loaded verbatim from the Parquet lake. Explicit DDL in the loader.
- **staging** (views) — typed, renamed, deduplicated. No business logic.
- **marts** (tables) — conformed dimensions + the fact, then the analytical marts.
  This is the only layer the agent and BI read.

## Dimensions

### dim_compound
`compound_key` (surrogate), `molecule_chembl_id`, `pref_name`,
`canonical_smiles`, `molecular_weight`, `alogp`, `hba`, `hbd`, `ro5_violations`.

### dim_target
`target_key`, `target_chembl_id`, `target_name`, `organism`, `target_type`.

### dim_assay
`assay_key`, `assay_chembl_id`, `assay_type`, `assay_description`,
`confidence_score`.

### dim_document
`document_key`, `document_chembl_id`, `pubmed_id`, `journal`, `year`.

Surrogate keys are generated with `dbt_utils.generate_surrogate_key` over the
natural ChEMBL id.

## Fact

### fact_bioactivity_result
One row per `activity_id`. Foreign keys: `compound_key`, `target_key`,
`assay_key`, `document_key`. Measures / attributes: `standard_type`,
`standard_relation`, `standard_value`, `standard_units`, `standard_value_nm`,
`pchembl_value`, `activity_comment`, `data_validity_comment`. `confidence_score`
is denormalized from the assay because it drives curation and most queries.

The fact keeps **every** measurement — good and bad. Comparability filtering is
the marts' job, never the fact's.

## Marts

- **mart_compound_target_potency** — the *curated* mart. Only comparable rows
  (curation rule below), collapsed to one representative potency per
  compound-target-assay-standard_type (strongest pChEMBL). Enriched with compound
  / target / assay / document attributes. This is what search indexes and the
  agent queries by default.
- **mart_target_activity_summary** — per-target coverage + curated potency
  rollup (measurements, compounds, assays, median potency, active compounds).
- **mart_assay_quality** — per-assay confidence, volume, and how much survives
  curation; counts of each quality issue.
- **mart_compound_profile** — one row per compound: physchem properties + a
  compact activity profile (targets tested, best curated potency, evidence counts).
- **mart_data_quality_summary** — long format `(metric_group, metric, value)`
  covering volume, completeness %, issue counts, and **excluded rows by reason**.

## Unit normalization

ChEMBL `standard_units` vary (M, mM, µM, nM, pM, …). Ingestion
(`NormalizeUnits.scala`) converts concentration-like values to **nM**
(`standard_value_nm`). Values that cannot be safely converted (%, `ug.mL-1`
without a molecular weight, unitless) are left null and flagged with a
`units_note`, so they are excluded from curation rather than mis-compared.

## Curation rule (the curated potency mart)

A measurement is "curated / comparable" only if **all** hold:

| Rule | Rationale |
|------|-----------|
| `standard_type ∈ {IC50, Ki, Kd, EC50}` | comparable potency endpoints |
| `standard_value_nm is not null` | a usable normalized value |
| `pchembl_value is not null` | comparable across endpoints |
| `confidence_score >= 7` | reliable target assignment |
| `data_validity_comment is null` | not flagged as problematic |
| `standard_relation = '=' or null` | exact, not bounded/approximate |

Defined once in `dbt/macros/curation.sql` and reused by the mart, the DQ
summary, and the exclusion-reason logic so they can never drift.

## Lineage / governance note

`fact_bioactivity_result` lives in `marts` (so the DB role can read it) but is
**not** on the `run_curated_sql` allow-list. It is reachable only through the
`explain_data_quality` lineage tool — keeping ad-hoc SQL on the curated marts
while still allowing governed "why excluded?" explanations.
