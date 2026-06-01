-- No duplicate compound-target-assay-type rows should remain in the curated
-- mart. (Duplicates may exist in raw/fact — they are reported by
-- mart_data_quality_summary — but the curated serving surface must be clean.)
select
    molecule_chembl_id,
    target_chembl_id,
    assay_chembl_id,
    standard_type,
    count(*) as n
from {{ ref('mart_compound_target_potency') }}
group by 1, 2, 3, 4
having count(*) > 1
