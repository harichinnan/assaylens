"""Tool: the target edges of a compound (graph view of polypharmacology).

Reads marts.graph_compound_target_edge — one edge per (compound, target) with
the strongest curated potency and supporting measurement count. Answers
"which targets does this compound hit, and how hard?".
"""
from __future__ import annotations

from app.db import query

TOOL_SPEC = {
    "name": "get_compound_targets",
    "description": "Targets a compound is active against (graph edges: best potency + evidence count per target).",
    "arguments": {"molecule_chembl_id": "ChEMBL molecule id, e.g. CHEMBL939"},
}


def run(molecule_chembl_id: str) -> dict:
    mid = (molecule_chembl_id or "").strip().upper()
    if not mid.startswith("CHEMBL"):
        return {"error": f"Expected a ChEMBL molecule id (e.g. CHEMBL939), got '{molecule_chembl_id}'."}

    rows = query(
        """
        select target_chembl_id, target_name, best_pchembl, best_potency_nm, n_measurements
        from marts.graph_compound_target_edge
        where molecule_chembl_id = %s
        order by best_pchembl desc nulls last, best_potency_nm asc nulls last
        """,
        (mid,),
    )
    return {
        "result_count": len(rows),
        "molecule_chembl_id": mid,
        "targets": rows,
    }
