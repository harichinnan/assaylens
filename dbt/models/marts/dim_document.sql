-- Document dimension (publication lineage).
select
    {{ dbt_utils.generate_surrogate_key(['document_chembl_id']) }} as document_key,
    document_chembl_id,
    pubmed_id,
    journal,
    year
from {{ ref('stg_document') }}
