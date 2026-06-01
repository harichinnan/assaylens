-- Staging (silver): assays.
with source as (
    select * from {{ source('bronze', 'assay') }}
),

cleaned as (
    select
        assay_chembl_id,
        nullif(trim(assay_type), '')        as assay_type,
        nullif(trim(assay_description), '') as assay_description,
        cast(confidence_score as int)       as confidence_score,
        target_chembl_id
    from source
    where assay_chembl_id is not null
),

deduped as (
    select *,
        row_number() over (partition by assay_chembl_id order by assay_chembl_id) as _rn
    from cleaned
)

select
    assay_chembl_id, assay_type, assay_description, confidence_score, target_chembl_id
from deduped where _rn = 1
