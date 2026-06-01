-- Per-assay quality view: confidence, measurement volume, and how much of each
-- assay's data survives curation. Feeds the Data Quality dashboard.
with fact as (
    select * from {{ ref('fact_bioactivity_result') }}
)

select
    f.assay_chembl_id,
    asy.assay_type,
    asy.assay_description,
    f.confidence_score,
    t.target_chembl_id,
    t.target_name,
    count(*)                                                        as total_measurements,
    count(*) filter (where {{ curated_potency_predicate('f') }})    as curated_measurements,
    count(*) filter (where f.standard_value_nm is null)             as missing_nm_value,
    count(*) filter (where f.pchembl_value is null)                 as missing_pchembl,
    count(*) filter (where f.data_validity_comment is not null)     as flagged_validity,
    count(*) filter (
        where f.standard_relation is not null and f.standard_relation <> '='
    )                                                               as ambiguous_relation,
    (f.confidence_score is not null and f.confidence_score < {{ var('min_confidence_score') }})
                                                                    as is_low_confidence
from fact f
left join {{ ref('dim_assay')  }} asy on f.assay_key  = asy.assay_key
left join {{ ref('dim_target') }} t   on f.target_key = t.target_key
group by 1, 2, 3, 4, 5, 6
