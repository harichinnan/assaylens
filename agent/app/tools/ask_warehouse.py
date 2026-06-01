"""Tool: natural-language question -> governed SQL over the curated warehouse.

The LLM drafts a single SELECT against the allow-listed marts (given their
schema), then the SAME guardrail that protects run_curated_sql validates it
(SELECT-only, allow-listed tables, mandatory LIMIT) before it runs on the
read-only, timeout-bounded connection. The generated SQL is always returned so
the user sees exactly what executed.

This is the "ask Postgres in English" surface (backlog B): broader than the
canned tools, but never less governed.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from app.db import pg_cursor
from app.guardrails.sql_guardrails import SqlGuardrailError, validate_sql
from app.llm import llm

TOOL_SPEC = {
    "name": "ask_warehouse",
    "description": (
        "Answer an analytical question by generating and running a governed, "
        "read-only SQL query over the curated marts (counts, rankings, filters, "
        "joins). Use when no specialized tool fits."
    ),
    "arguments": {"question": "a natural-language analytical question about the warehouse"},
}

_PROMPT = (Path(__file__).resolve().parent.parent / "prompts" / "nl_to_sql.md").read_text()

# Column hints per allow-listed mart, so the LLM writes valid SQL without a
# live catalog read. Mirrors the dbt gold models.
SCHEMA: dict[str, list[str]] = {
    "marts.mart_compound_target_potency": [
        "activity_id", "molecule_chembl_id", "compound_name", "canonical_smiles",
        "molecular_weight", "alogp", "target_chembl_id", "target_name", "organism",
        "assay_chembl_id", "assay_type", "assay_description", "confidence_score",
        "standard_type", "standard_relation", "standard_value_nm", "pchembl_value",
        "document_chembl_id", "journal", "year",
    ],
    "marts.mart_target_activity_summary": [
        "target_chembl_id", "target_name", "organism", "total_measurements",
        "total_compounds_tested", "total_assays", "curated_measurements",
        "active_compounds", "median_potency_nm", "median_pchembl", "best_pchembl",
    ],
    "marts.mart_assay_quality": [
        "assay_chembl_id", "assay_type", "assay_description", "confidence_score",
        "target_chembl_id", "target_name", "total_measurements", "curated_measurements",
        "missing_nm_value", "missing_pchembl", "flagged_validity", "ambiguous_relation",
        "is_low_confidence",
    ],
    "marts.mart_compound_profile": [
        "molecule_chembl_id", "compound_name", "canonical_smiles", "molecular_weight",
        "alogp", "hba", "hbd", "ro5_violations", "total_measurements", "targets_tested",
        "assays_tested", "curated_measurements", "curated_targets", "best_pchembl",
        "best_potency_nm",
    ],
    "marts.mart_data_quality_summary": ["metric_group", "metric", "value"],
    "marts.dim_target": ["target_key", "target_chembl_id", "target_name", "organism", "target_type"],
    "marts.dim_compound": ["compound_key", "molecule_chembl_id", "pref_name", "canonical_smiles",
                           "molecular_weight", "alogp", "hba", "hbd", "ro5_violations"],
    "marts.graph_compound_target_edge": [
        "molecule_chembl_id", "compound_name", "target_chembl_id", "target_name",
        "best_pchembl", "best_potency_nm", "n_measurements",
    ],
    "marts.graph_target_similarity": [
        "target_a", "target_a_name", "target_b", "target_b_name", "shared_compounds", "jaccard",
    ],
}


def _extract_sql(text: str) -> str:
    """Strip code fences / stray prose; keep from the first SELECT or WITH."""
    t = re.sub(r"```[a-zA-Z]*", "", text).replace("```", "").strip()
    m = re.search(r"\b(select|with)\b", t, flags=re.IGNORECASE)
    return t[m.start():].strip() if m else t


def run(question: str) -> dict:
    if not llm.enabled:
        return {"error": "ask_warehouse needs an LLM (set ANTHROPIC_API_KEY); "
                         "use run_curated_sql to pass SQL directly."}

    user = json.dumps({"question": question, "schema": SCHEMA})
    raw = llm._complete(_PROMPT, user, 400, gen_name="llm:nl_to_sql")
    sql = _extract_sql(raw)

    try:
        validated = validate_sql(sql)
    except SqlGuardrailError as exc:
        return {"error": str(exc), "rejected": True, "generated_sql": sql}

    with pg_cursor() as cur:
        cur.execute(validated.sql)
        rows = cur.fetchall()

    return {
        "result_count": len(rows),
        "question": question,
        "generated_sql": validated.sql,     # transparency guardrail
        "row_limit": validated.limit,
        "referenced_tables": validated.referenced_tables,
        "results": rows,
    }
