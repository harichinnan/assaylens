{#
  Use the schema configured on the model verbatim (e.g. `staging`, `marts`)
  instead of dbt's default "<target_schema>_<custom_schema>" concatenation.
  This gives us clean, stable schema names that match postgres/init/01_schemas.sql
  and the read-only agent grants.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
