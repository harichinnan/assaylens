-- Staging (silver): activities (the measurement grain).
-- Types/renames and normalizes the standard_relation symbol; keeps the
-- ingestion-time nM value and units note. No filtering of "bad" rows here —
-- the dimensional layer keeps everything; curation happens in the marts.
with source as (
    select * from {{ source('bronze', 'activity') }}
),

cleaned as (
    select
        activity_id,
        molecule_chembl_id,
        target_chembl_id,
        assay_chembl_id,
        document_chembl_id,
        nullif(trim(standard_type), '')             as standard_type,
        -- Preserve null relations so DQ checks can distinguish "exact" (=) from
        -- "unspecified" (null); do NOT coerce blank to '='.
        nullif(trim(standard_relation), '')         as standard_relation,
        -- Coerce NaN -> NULL defensively (a missing numeric must not slip past
        -- `is null` checks in curation/DQ). Bronze columns are already doubles.
        case when isnan(standard_value)    then null else standard_value    end as standard_value,
        nullif(trim(standard_units), '')            as standard_units,
        case when isnan(standard_value_nm) then null else standard_value_nm end as standard_value_nm,
        nullif(trim(units_note), '')                as units_note,
        case when isnan(pchembl_value)     then null else pchembl_value     end as pchembl_value,
        nullif(trim(activity_comment), '')          as activity_comment,
        nullif(trim(data_validity_comment), '')     as data_validity_comment
    from source
    where activity_id is not null
)

select * from cleaned
