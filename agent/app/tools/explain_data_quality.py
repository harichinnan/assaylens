"""Tool: explain why rows are included in / excluded from the curated marts.

This is the lineage tool that may reach the fact table (not just curated marts)
— it runs fixed, parameterized queries here, NOT arbitrary SQL, so raw/staging
access stays governed. Accepts one of: activity_id, molecule_chembl_id,
assay_chembl_id. With no argument, returns the warehouse-wide exclusion summary.
"""
from __future__ import annotations

from app.db import query

TOOL_SPEC = {
    "name": "explain_data_quality",
    "description": "Explain inclusion/exclusion from curated marts for a row, compound, or assay.",
    "arguments": {
        "activity_id": "optional",
        "molecule_chembl_id": "optional",
        "assay_chembl_id": "optional",
    },
}

# Reproduces curation.curation_exclusion_reason in SQL against fact, so the
# explanation matches dbt exactly. Read-only; fact_bioactivity_result is exposed
# only through this governed lineage tool, never via run_curated_sql.
_REASON_EXPR = """
    case
        when standard_type not in ('IC50','Ki','Kd','EC50') then 'non_curated_standard_type'
        when standard_value_nm is null then 'missing_or_unconvertible_nm_value'
        when pchembl_value is null then 'missing_pchembl_value'
        when confidence_score is null or confidence_score < 7 then 'low_confidence_score'
        when data_validity_comment is not null then 'data_validity_comment_present'
        when not (standard_relation = '=' or standard_relation is null) then 'ambiguous_standard_relation'
        else 'included'
    end
"""


def _rows_for(where: str, param) -> list[dict]:
    return query(
        f"""
        select activity_id, molecule_chembl_id, target_chembl_id, assay_chembl_id,
               standard_type, standard_relation, standard_value_nm, pchembl_value,
               confidence_score, data_validity_comment,
               {_REASON_EXPR} as curation_outcome
        from marts.fact_bioactivity_result
        where {where}
        order by activity_id
        limit 100
        """,
        (param,),
    )


def run(
    activity_id: int | None = None,
    molecule_chembl_id: str | None = None,
    assay_chembl_id: str | None = None,
) -> dict:
    if activity_id is not None:
        rows = _rows_for("activity_id = %s", int(activity_id))
        scope = {"activity_id": activity_id}
    elif molecule_chembl_id:
        rows = _rows_for("molecule_chembl_id = %s", molecule_chembl_id.strip().upper())
        scope = {"molecule_chembl_id": molecule_chembl_id}
    elif assay_chembl_id:
        rows = _rows_for("assay_chembl_id = %s", assay_chembl_id.strip().upper())
        scope = {"assay_chembl_id": assay_chembl_id}
    else:
        # Warehouse-wide: the excluded-by-reason rollup.
        rows = query(
            """
            select metric as exclusion_reason, value as row_count
            from marts.mart_data_quality_summary
            where metric_group = 'excluded_by_reason'
            order by value desc
            """,
        )
        return {"result_count": len(rows), "scope": "warehouse", "excluded_by_reason": rows}

    included = sum(1 for r in rows if r["curation_outcome"] == "included")
    return {
        "result_count": len(rows),
        "scope": scope,
        "included": included,
        "excluded": len(rows) - included,
        "rows": rows,
    }
