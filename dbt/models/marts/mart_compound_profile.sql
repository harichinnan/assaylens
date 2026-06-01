-- One row per compound: physchem properties plus a compact activity profile
-- (targets tested, best curated potency, evidence counts). Feeds the Compound
-- Profile dashboard and get_compound_profile.
with cpd as (
    select * from {{ ref('dim_compound') }}
),

all_fact as (
    select * from {{ ref('fact_bioactivity_result') }}
),

curated as (
    select * from {{ ref('mart_compound_target_potency') }}
),

activity_rollup as (
    select
        molecule_chembl_id,
        count(distinct activity_id)        as total_measurements,
        count(distinct target_chembl_id)   as targets_tested,
        count(distinct assay_chembl_id)    as assays_tested
    from all_fact
    group by 1
),

curated_rollup as (
    select
        molecule_chembl_id,
        count(distinct activity_id)        as curated_measurements,
        count(distinct target_chembl_id)   as curated_targets,
        max(pchembl_value)                 as best_pchembl,
        min(standard_value_nm)             as best_potency_nm
    from curated
    group by 1
)

select
    cpd.molecule_chembl_id,
    cpd.pref_name as compound_name,
    cpd.canonical_smiles,
    cpd.molecular_weight,
    cpd.alogp,
    cpd.hba,
    cpd.hbd,
    cpd.ro5_violations,
    coalesce(ar.total_measurements, 0) as total_measurements,
    coalesce(ar.targets_tested, 0)     as targets_tested,
    coalesce(ar.assays_tested, 0)      as assays_tested,
    coalesce(cr.curated_measurements, 0) as curated_measurements,
    coalesce(cr.curated_targets, 0)      as curated_targets,
    cr.best_pchembl,
    cr.best_potency_nm
from cpd
left join activity_rollup ar on cpd.molecule_chembl_id = ar.molecule_chembl_id
left join curated_rollup  cr on cpd.molecule_chembl_id = cr.molecule_chembl_id
