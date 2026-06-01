-- Compound dimension. Surrogate key derived from the natural key.
select
    {{ dbt_utils.generate_surrogate_key(['molecule_chembl_id']) }} as compound_key,
    molecule_chembl_id,
    pref_name,
    canonical_smiles,
    molecular_weight,
    alogp,
    hba,
    hbd,
    ro5_violations
from {{ ref('stg_compound') }}
