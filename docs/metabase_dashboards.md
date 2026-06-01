# Metabase dashboards

Four dashboards over the curated marts. This file is the narrative; precise
card-by-card SQL/source specs are in
[../metabase/dashboard_specs.md](../metabase/dashboard_specs.md), and connection
setup is in [../metabase/setup.md](../metabase/setup.md).

## 1. Scientific Warehouse Overview
The "is the warehouse healthy and how big is it" view.
- Total compounds / assays / targets / activity measurements (single-value cards)
- % rows with normalized nM value
- % rows with pChEMBL
- Rows excluded from the curated mart (count + % )
Source: `mart_data_quality_summary` (volume + completeness groups).

## 2. Target Activity Explorer
Explore evidence per target.
- **Filters:** target, activity type (IC50/Ki/Kd/EC50), pChEMBL threshold,
  confidence score.
- Measurements by target (bar)
- Active (curated) compounds by target (bar)
- Median potency (nM) by target (bar)
- Assay count by target (bar)
Source: `mart_target_activity_summary` + `mart_compound_target_potency`.

## 3. Compound Profile
Everything about one selected compound.
- **Filter:** compound (molecule_chembl_id / name)
- SMILES + molecular properties (MW, AlogP, HBA, HBD, Ro5 violations)
- Targets tested against
- Best pChEMBL by target
- Assay evidence table
- Publication lineage (journal / year / pubmed id)
Source: `mart_compound_profile` + `mart_compound_target_potency`.

## 4. Data Quality
The governance view — what's wrong and what got excluded.
- Missing units / missing pChEMBL (counts)
- Ambiguous relation signs (`>`, `<`, `~`)
- Low-confidence assays
- Duplicate measurement rows
- **Excluded rows by reason** (bar)
Source: `mart_data_quality_summary` (issue + excluded_by_reason groups) +
`mart_assay_quality`.

## Agent integration
`get_metabase_dashboard(dashboard_name, filters)` returns the dashboard link and
filter parameters, mapping logical names — `warehouse_overview`,
`target_activity_explorer`, `compound_profile`, `data_quality` — to their
Metabase ids (configured via env, see metabase/setup.md).
