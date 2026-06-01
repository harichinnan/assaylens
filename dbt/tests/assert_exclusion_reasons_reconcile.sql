-- Every fact row must be classified by exactly one curation outcome
-- ('included' or one exclusion reason). This guards the curation_exclusion_reason
-- macro against gaps/overlaps: the sum of classified rows must equal the total.
-- A passing test = 0 rows.
with classified as (
    select {{ curation_exclusion_reason('f') }} as reason
    from {{ ref('fact_bioactivity_result') }} f
),
totals as (
    select
        (select count(*) from {{ ref('fact_bioactivity_result') }}) as total_rows,
        (select count(*) from classified)                            as classified_rows,
        (select count(*) from classified where reason is null)       as unclassified_rows
)
select * from totals
where total_rows <> classified_rows
   or unclassified_rows > 0
