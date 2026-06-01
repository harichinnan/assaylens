-- Staging (silver): targets.
with source as (
    select * from {{ source('bronze', 'target') }}
),

cleaned as (
    select
        target_chembl_id,
        nullif(trim(target_name), '') as target_name,
        nullif(trim(organism), '')    as organism,
        nullif(trim(target_type), '') as target_type
    from source
    where target_chembl_id is not null
),

deduped as (
    select *,
        row_number() over (partition by target_chembl_id order by target_chembl_id) as _rn
    from cleaned
)

select
    target_chembl_id, target_name, organism, target_type
from deduped where _rn = 1
