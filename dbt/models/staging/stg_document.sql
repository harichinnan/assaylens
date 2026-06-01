-- Staging (silver): documents (publication lineage).
with source as (
    select * from {{ source('bronze', 'document') }}
),

cleaned as (
    select
        document_chembl_id,
        cast(pubmed_id as int)    as pubmed_id,
        nullif(trim(journal), '') as journal,
        cast(year as int)         as year
    from source
    where document_chembl_id is not null
),

deduped as (
    select *,
        row_number() over (partition by document_chembl_id order by document_chembl_id) as _rn
    from cleaned
)

select
    document_chembl_id, pubmed_id, journal, year
from deduped where _rn = 1
