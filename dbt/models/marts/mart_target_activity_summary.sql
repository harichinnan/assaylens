-- Per-target rollup over the CURATED potency mart: the headline numbers for
-- the Target Activity Explorer dashboard and get_target_summary.
--
-- Pre-aggregate coverage (all measurements) and quality (curated) per target
-- BEFORE joining to dim_target. Joining the two grains on target alone would
-- otherwise form a per-target cartesian product (correct via count-distinct,
-- but it OOMs Spark's exact percentile); pre-aggregation keeps each side to one
-- row per target.
with all_fact as (
    select * from {{ ref('fact_bioactivity_result') }}
),

curated as (
    select * from {{ ref('mart_compound_target_potency') }}
),

coverage as (
    select
        target_chembl_id,
        count(distinct activity_id)        as total_measurements,
        count(distinct molecule_chembl_id) as total_compounds_tested,
        count(distinct assay_chembl_id)    as total_assays
    from all_fact
    group by target_chembl_id
),

quality as (
    select
        target_chembl_id,
        count(distinct activity_id)        as curated_measurements,
        count(distinct molecule_chembl_id) as active_compounds,
        percentile(standard_value_nm, 0.5) as median_potency_nm,
        percentile(pchembl_value, 0.5)     as median_pchembl,
        max(pchembl_value)                 as best_pchembl
    from curated
    group by target_chembl_id
)

select
    t.target_chembl_id,
    t.target_name,
    t.organism,
    coalesce(cov.total_measurements, 0)     as total_measurements,
    coalesce(cov.total_compounds_tested, 0) as total_compounds_tested,
    coalesce(cov.total_assays, 0)           as total_assays,
    coalesce(q.curated_measurements, 0)     as curated_measurements,
    coalesce(q.active_compounds, 0)         as active_compounds,
    q.median_potency_nm,
    q.median_pchembl,
    q.best_pchembl
from {{ ref('dim_target') }} t
left join coverage cov on t.target_chembl_id = cov.target_chembl_id
left join quality  q   on t.target_chembl_id = q.target_chembl_id
