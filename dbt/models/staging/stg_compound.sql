-- Staging (silver): compounds. Type/rename/dedup only — no business logic.
with source as (
    select * from {{ source('bronze', 'molecule') }}
),

cleaned as (
    select
        molecule_chembl_id,
        nullif(trim(pref_name), '')        as pref_name,
        nullif(trim(canonical_smiles), '') as canonical_smiles,
        cast(molecular_weight as double)   as molecular_weight,
        cast(alogp as double)              as alogp,
        cast(hba as int)                   as hba,
        cast(hbd as int)                   as hbd,
        cast(ro5_violations as int)        as ro5_violations
    from source
    where molecule_chembl_id is not null
),

-- One row per compound (bronze can carry dup pulls).
deduped as (
    select *,
        row_number() over (partition by molecule_chembl_id order by molecule_chembl_id) as _rn
    from cleaned
)

select
    molecule_chembl_id, pref_name, canonical_smiles, molecular_weight,
    alogp, hba, hbd, ro5_violations
from deduped where _rn = 1
