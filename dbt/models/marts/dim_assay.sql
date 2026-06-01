-- Assay dimension.
select
    {{ dbt_utils.generate_surrogate_key(['assay_chembl_id']) }} as assay_key,
    assay_chembl_id,
    assay_type,
    assay_description,
    confidence_score
from {{ ref('stg_assay') }}
