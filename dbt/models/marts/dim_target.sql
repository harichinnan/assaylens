-- Target dimension.
select
    {{ dbt_utils.generate_surrogate_key(['target_chembl_id']) }} as target_key,
    target_chembl_id,
    target_name,
    organism,
    target_type
from {{ ref('stg_target') }}
