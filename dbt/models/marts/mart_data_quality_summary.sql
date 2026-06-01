-- Warehouse-wide data quality summary in long format:
--   (metric_group, metric, value)
-- Powers the Scientific Warehouse Overview + Data Quality dashboards and the
-- agent's explain_data_quality / get_target_summary DQ section.
--
-- Long format keeps it dashboard- and agent-friendly: each metric is one row,
-- new checks are additive, and "excluded rows by reason" slots in naturally.
-- `value` is cast to double throughout so the unions line up.
with fact as (
    select * from {{ ref('fact_bioactivity_result') }}
),

reasons as (
    select {{ curation_exclusion_reason('f') }} as exclusion_reason
    from fact f
),

volume as (
    select 'volume' as metric_group, m.metric, m.value from (
        select 'total_measurements'      as metric, cast(count(*) as double) as value from fact
        union all
        select 'total_compounds',  cast(count(distinct molecule_chembl_id) as double) from fact
        union all
        select 'total_targets',    cast(count(distinct target_chembl_id) as double)   from fact
        union all
        select 'total_assays',     cast(count(distinct assay_chembl_id) as double)     from fact
        union all
        select 'total_documents',  cast(count(distinct document_chembl_id) as double)  from fact
    ) m
),

completeness as (
    select 'completeness' as metric_group, m.metric, m.value from (
        select 'pct_with_normalized_nm' as metric,
               round(100.0 * count(*) filter (where standard_value_nm is not null) / nullif(count(*), 0), 1) as value
               from fact
        union all
        select 'pct_with_pchembl',
               round(100.0 * count(*) filter (where pchembl_value is not null) / nullif(count(*), 0), 1)
               from fact
        union all
        select 'pct_curated',
               round(100.0 * count(*) filter (where {{ curated_potency_predicate('fact') }}) / nullif(count(*), 0), 1)
               from fact
    ) m
),

issues as (
    select 'issue' as metric_group, m.metric, m.value from (
        select 'missing_molecule_chembl_id' as metric, cast(count(*) as double) as value from fact where molecule_chembl_id is null
        union all
        select 'missing_target_chembl_id',  cast(count(*) as double) from fact where target_chembl_id is null
        union all
        select 'missing_assay_chembl_id',   cast(count(*) as double) from fact where assay_chembl_id is null
        union all
        select 'missing_standard_value',    cast(count(*) as double) from fact where standard_value is null
        union all
        select 'missing_standard_units',    cast(count(*) as double) from fact where standard_units is null
        union all
        select 'unconvertible_units',       cast(count(*) as double) from fact
               where standard_value is not null and standard_value_nm is null and standard_units is not null
        union all
        select 'missing_pchembl_value',     cast(count(*) as double) from fact where pchembl_value is null
        union all
        select 'ambiguous_relation',        cast(count(*) as double) from fact
               where standard_relation is not null and standard_relation <> '='
        union all
        select 'low_confidence',            cast(count(*) as double) from fact
               where confidence_score is not null and confidence_score < {{ var('min_confidence_score') }}
        union all
        select 'has_data_validity_comment', cast(count(*) as double) from fact where data_validity_comment is not null
        union all
        select 'duplicate_measurements',    cast(coalesce(sum(dups), 0) as double) from (
            select count(*) - 1 as dups
            from fact
            group by molecule_chembl_id, target_chembl_id, assay_chembl_id, standard_type
            having count(*) > 1
        ) d
    ) m
),

excluded_by_reason as (
    select 'excluded_by_reason' as metric_group, exclusion_reason as metric, cast(count(*) as double) as value
    from reasons
    where exclusion_reason <> 'included'
    group by exclusion_reason
)

select * from volume
union all select * from completeness
union all select * from issues
union all select * from excluded_by_reason
