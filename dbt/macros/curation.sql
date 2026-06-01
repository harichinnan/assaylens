{#
  Curation rules for the potency mart, defined once and reused by:
    * mart_compound_target_potency  (keeps only curated rows)
    * mart_data_quality_summary     (counts excluded rows by reason)
    * the exclusion-reason singular test

  A row is "curated/comparable" when ALL hold:
    - standard_type in (IC50, Ki, Kd, EC50)
    - standard_value_nm is not null
    - pchembl_value is not null
    - confidence_score >= var('min_confidence_score')  (default 7)
    - data_validity_comment is null (acceptable)
    - standard_relation is '=' or null
#}

{% macro curated_potency_predicate(t) -%}
    {{ t }}.standard_type in (
        {%- for st in var('curated_standard_types') -%}
            '{{ st }}'{% if not loop.last %}, {% endif %}
        {%- endfor -%}
    )
    and {{ t }}.standard_value_nm is not null
    and {{ t }}.pchembl_value is not null
    and {{ t }}.confidence_score >= {{ var('min_confidence_score') }}
    and {{ t }}.data_validity_comment is null
    and ({{ t }}.standard_relation = '=' or {{ t }}.standard_relation is null)
{%- endmacro %}


{#
  First failing curation rule for a row, as a human-readable reason.
  Returns 'included' when the row passes all rules. Order matters — the most
  fundamental problems are reported first.
#}
{% macro curation_exclusion_reason(t) -%}
    case
        when {{ t }}.standard_type not in (
            {%- for st in var('curated_standard_types') -%}
                '{{ st }}'{% if not loop.last %}, {% endif %}
            {%- endfor -%}
        ) then 'non_curated_standard_type'
        when {{ t }}.standard_value_nm is null then 'missing_or_unconvertible_nm_value'
        when {{ t }}.pchembl_value is null then 'missing_pchembl_value'
        when {{ t }}.confidence_score is null
             or {{ t }}.confidence_score < {{ var('min_confidence_score') }} then 'low_confidence_score'
        when {{ t }}.data_validity_comment is not null then 'data_validity_comment_present'
        when not ({{ t }}.standard_relation = '=' or {{ t }}.standard_relation is null)
            then 'ambiguous_standard_relation'
        else 'included'
    end
{%- endmacro %}
