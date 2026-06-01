-- Fact table at the bioactivity-measurement grain: one row per activity_id.
-- Joins each measurement to its compound / target / assay / document
-- dimension keys. confidence_score is denormalized from the assay dimension
-- because it is central to curation and to most downstream serving queries.
--
-- This table keeps EVERY measurement (good and bad). Filtering to comparable
-- rows is the job of mart_compound_target_potency, never of the fact.
with activity as (
    select * from {{ ref('stg_activity') }}
)

select
    a.activity_id,
    c.compound_key,
    t.target_key,
    s.assay_key,
    d.document_key,

    -- natural keys kept for convenient filtering / lineage
    a.molecule_chembl_id,
    a.target_chembl_id,
    a.assay_chembl_id,
    a.document_chembl_id,

    a.standard_type,
    a.standard_relation,
    a.standard_value,
    a.standard_units,
    a.standard_value_nm,
    a.pchembl_value,
    a.activity_comment,
    a.data_validity_comment,

    -- denormalized from dim_assay for curation + serving
    s.confidence_score,
    a.units_note
from activity a
left join {{ ref('dim_compound') }} c on a.molecule_chembl_id = c.molecule_chembl_id
left join {{ ref('dim_target')   }} t on a.target_chembl_id   = t.target_chembl_id
left join {{ ref('dim_assay')    }} s on a.assay_chembl_id    = s.assay_chembl_id
left join {{ ref('dim_document') }} d on a.document_chembl_id = d.document_chembl_id
