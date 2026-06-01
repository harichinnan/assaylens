# Dashboard specifications (card-by-card)

Source schema: `marts`. Each card lists its source and the query/aggregation.
SQL snippets are Metabase "native question" ready.

---

## Dashboard 1 — Scientific Warehouse Overview

| Card | Type | Source / query |
|------|------|----------------|
| Total compounds | single value | `select value from marts.mart_data_quality_summary where metric='total_compounds'` |
| Total assays | single value | `… where metric='total_assays'` |
| Total targets | single value | `… where metric='total_targets'` |
| Total measurements | single value | `… where metric='total_measurements'` |
| % normalized nM | single value (%) | `… where metric='pct_with_normalized_nm'` |
| % with pChEMBL | single value (%) | `… where metric='pct_with_pchembl'` |
| % curated | single value (%) | `… where metric='pct_curated'` |
| Excluded rows by reason | bar | `select metric as reason, value from marts.mart_data_quality_summary where metric_group='excluded_by_reason' order by value desc` |

---

## Dashboard 2 — Target Activity Explorer

**Dashboard filters:** target (`target_chembl_id`), activity type
(`standard_type`), pChEMBL threshold, confidence score — wired to the cards below.

| Card | Type | Source / query |
|------|------|----------------|
| Measurements by target | bar | `select target_name, total_measurements from marts.mart_target_activity_summary order by total_measurements desc` |
| Active compounds by target | bar | `select target_name, active_compounds from marts.mart_target_activity_summary order by active_compounds desc` |
| Median potency (nM) by target | bar | `select target_name, median_potency_nm from marts.mart_target_activity_summary` |
| Assay count by target | bar | `select target_name, total_assays from marts.mart_target_activity_summary` |
| Curated evidence (filtered) | table | `select compound_name, standard_type, standard_value_nm, pchembl_value, confidence_score, assay_description from marts.mart_compound_target_potency [[ where target_chembl_id = {{target}} ]] order by pchembl_value desc` |

Use Metabase **field filters** on the last card (`{{target}}`, `{{standard_type}}`,
`{{min_pchembl}}`, `{{min_confidence}}`) and connect them to the dashboard filters.

---

## Dashboard 3 — Compound Profile

**Dashboard filter:** compound (`molecule_chembl_id`).

| Card | Type | Source / query |
|------|------|----------------|
| Compound header (name, SMILES) | table (1 row) | `select compound_name, canonical_smiles from marts.mart_compound_profile where molecule_chembl_id = {{compound}}` |
| Molecular properties | table (1 row) | `select molecular_weight, alogp, hba, hbd, ro5_violations from marts.mart_compound_profile where molecule_chembl_id = {{compound}}` |
| Targets tested & best pChEMBL | bar | `select target_name, max(pchembl_value) best_pchembl from marts.mart_compound_target_potency where molecule_chembl_id = {{compound}} group by target_name order by best_pchembl desc` |
| Assay evidence | table | `select target_name, assay_description, standard_type, standard_value_nm, pchembl_value, confidence_score from marts.mart_compound_target_potency where molecule_chembl_id = {{compound}} order by pchembl_value desc` |
| Publication lineage | table | `select distinct journal, year, document_chembl_id from marts.mart_compound_target_potency where molecule_chembl_id = {{compound}} order by year desc` |

---

## Dashboard 4 — Data Quality

| Card | Type | Source / query |
|------|------|----------------|
| Missing units | single value | `select value from marts.mart_data_quality_summary where metric='missing_standard_units'` |
| Missing pChEMBL | single value | `… where metric='missing_pchembl_value'` |
| Ambiguous relations | single value | `… where metric='ambiguous_relation'` |
| Unconvertible units | single value | `… where metric='unconvertible_units'` |
| Low-confidence rows | single value | `… where metric='low_confidence'` |
| Duplicate measurements | single value | `… where metric='duplicate_measurements'` |
| Excluded by reason | bar | `select metric reason, value from marts.mart_data_quality_summary where metric_group='excluded_by_reason' order by value desc` |
| Assay quality detail | table | `select assay_chembl_id, target_name, confidence_score, total_measurements, curated_measurements, missing_pchembl, ambiguous_relation from marts.mart_assay_quality order by confidence_score asc` |

---

### Notes
- All numbers come from already-modeled marts — Metabase does no curation logic.
- Single-value cards read the long-format `mart_data_quality_summary`; filtering
  by `metric` keeps every KPI a one-liner that survives model changes.
