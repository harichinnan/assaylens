-- CURATED potency mart: only comparable rows survive (see macros/curation.sql).
-- This is the default surface for the search index and the agent. Each row is
-- one curated compound-target-assay potency measurement, enriched with compound
-- / target / assay / document attributes for self-contained serving.
with fact as (
    select * from {{ ref('fact_bioactivity_result') }}
),

curated as (
    select * from fact f
    where {{ curated_potency_predicate('f') }}
),

-- Collapse replicate measurements (same compound-target-assay-standard_type)
-- to one representative row — the strongest pChEMBL, tie-broken by lowest nM.
-- Replicates still exist in the fact and are counted by
-- mart_data_quality_summary; the curated serving surface stays one-per-evidence.
deduped as (
    select *,
        row_number() over (
            partition by molecule_chembl_id, target_chembl_id, assay_chembl_id, standard_type
            order by pchembl_value desc, standard_value_nm asc, activity_id asc
        ) as rn
    from curated
)

select
    f.activity_id,
    f.molecule_chembl_id,
    cpd.pref_name        as compound_name,
    cpd.canonical_smiles,
    cpd.molecular_weight,
    cpd.alogp,
    f.target_chembl_id,
    tgt.target_name,
    tgt.organism,
    f.assay_chembl_id,
    asy.assay_type,
    asy.assay_description,
    f.confidence_score,
    f.standard_type,
    f.standard_relation,
    f.standard_value_nm,
    f.pchembl_value,
    f.document_chembl_id,
    doc.journal,
    doc.year
from deduped f
left join {{ ref('dim_compound') }} cpd on f.compound_key = cpd.compound_key
left join {{ ref('dim_target')   }} tgt on f.target_key   = tgt.target_key
left join {{ ref('dim_assay')    }} asy on f.assay_key    = asy.assay_key
left join {{ ref('dim_document') }} doc on f.document_key  = doc.document_key
where f.rn = 1
