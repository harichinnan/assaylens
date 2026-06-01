-- The curated mart must contain ONLY comparable rows. This re-checks the
-- curation contract independently of the model that builds it: any row here
-- failing a rule is a defect. Returns offending rows (a passing test = 0 rows).
select
    activity_id,
    standard_type,
    standard_relation,
    standard_value_nm,
    pchembl_value,
    confidence_score
from {{ ref('mart_compound_target_potency') }}
where standard_type not in ('IC50', 'Ki', 'Kd', 'EC50')
   or standard_value_nm is null
   or standard_value_nm <= 0
   or pchembl_value is null
   or confidence_score < {{ var('min_confidence_score') }}
   or (standard_relation is not null and standard_relation <> '=')
