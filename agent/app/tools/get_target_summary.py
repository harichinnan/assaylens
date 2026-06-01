"""Tool: activity + quality summary for one target.

Returns counts, median potency, active compound count, and a compact data-
quality breakdown — from mart_target_activity_summary + mart_data_quality_summary.
"""
from __future__ import annotations

from app.config import resolve_target
from app.db import query

TOOL_SPEC = {
    "name": "get_target_summary",
    "description": "Activity counts, median potency, active compounds, and DQ summary for a target.",
    "arguments": {"target_name": "target name / gene / ChEMBL id, e.g. EGFR"},
}


def run(target_name: str) -> dict:
    target_id = resolve_target(target_name)
    if not target_id:
        return {"error": f"Unknown target '{target_name}'. Known: EGFR, HER2, BRAF, JAK2, VEGFR2."}

    summary = query(
        "select * from marts.mart_target_activity_summary where target_chembl_id = %s",
        (target_id,),
    )
    if not summary:
        return {"result_count": 0, "target_chembl_id": target_id,
                "message": "No measurements for this target."}

    # Per-target data-quality: counts of excluded rows by reason for this target.
    dq = query(
        """
        select standard_type,
               count(*) filter (where pchembl_value is null) as missing_pchembl,
               count(*) as curated_rows
        from marts.mart_compound_target_potency
        where target_chembl_id = %s
        group by standard_type
        order by curated_rows desc
        """,
        (target_id,),
    )

    return {
        "result_count": 1,
        "target_chembl_id": target_id,
        "summary": summary[0],
        "curated_breakdown_by_type": dq,
    }
