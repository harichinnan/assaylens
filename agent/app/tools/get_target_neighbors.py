"""Tool: targets most related to a given target (graph similarity).

Reads marts.graph_target_similarity (target<->target edges weighted by shared
curated compounds + Jaccard over their curated compound sets). Answers
"what targets behave like EGFR / share its chemistry?".
"""
from __future__ import annotations

from app.config import resolve_target
from app.db import query

TOOL_SPEC = {
    "name": "get_target_neighbors",
    "description": "Targets most related to a given target by shared curated compounds (graph similarity).",
    "arguments": {"target_name": "target name / gene / ChEMBL id, e.g. EGFR"},
}


def run(target_name: str) -> dict:
    tid = resolve_target(target_name)
    if not tid:
        return {"error": f"Unknown target '{target_name}'. Known: EGFR, HER2, BRAF, JAK2, VEGFR2."}

    rows = query(
        """
        select
            case when target_a = %s then target_b      else target_a      end as neighbor_chembl_id,
            case when target_a = %s then target_b_name else target_a_name end as neighbor_name,
            shared_compounds,
            jaccard
        from marts.graph_target_similarity
        where target_a = %s or target_b = %s
        order by shared_compounds desc, jaccard desc
        """,
        (tid, tid, tid, tid),
    )
    return {
        "result_count": len(rows),
        "target_chembl_id": tid,
        "neighbors": rows,
    }
