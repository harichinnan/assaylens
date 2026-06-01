"""Tool: full profile for one compound.

Returns physchem properties, targets tested, best curated potency per target,
assay evidence, and publication lineage — assembled from curated marts via
parameterized queries (no LLM-authored SQL).
"""
from __future__ import annotations

from app.db import query

TOOL_SPEC = {
    "name": "get_compound_profile",
    "description": "Compound properties, tested targets, best potency, evidence, lineage.",
    "arguments": {"molecule_chembl_id": "ChEMBL molecule id, e.g. CHEMBL939"},
}


def run(molecule_chembl_id: str) -> dict:
    mol = (molecule_chembl_id or "").strip().upper()
    if not mol:
        return {"error": "molecule_chembl_id is required."}

    profile = query(
        "select * from marts.mart_compound_profile where molecule_chembl_id = %s",
        (mol,),
    )
    if not profile:
        return {"result_count": 0, "molecule_chembl_id": mol,
                "message": "No compound found in the curated warehouse."}

    evidence = query(
        """
        select target_chembl_id, target_name, assay_chembl_id, assay_description,
               standard_type, standard_value_nm, pchembl_value, confidence_score,
               journal, year
        from marts.mart_compound_target_potency
        where molecule_chembl_id = %s
        order by pchembl_value desc
        limit 50
        """,
        (mol,),
    )

    best_by_target = query(
        """
        select target_chembl_id, target_name,
               max(pchembl_value) as best_pchembl,
               min(standard_value_nm) as best_potency_nm
        from marts.mart_compound_target_potency
        where molecule_chembl_id = %s
        group by target_chembl_id, target_name
        order by best_pchembl desc
        """,
        (mol,),
    )

    return {
        "result_count": 1,
        "molecule_chembl_id": mol,
        "profile": profile[0],
        "best_potency_by_target": best_by_target,
        "assay_evidence": evidence,
    }
