"""Tool: search curated assay evidence in Elasticsearch.

Builds a bool query from structured arguments (never free-form ES DSL from the
LLM) and returns compact hits. The index only holds curated evidence, so this
is safe to expose directly.
"""
from __future__ import annotations

from app.config import resolve_target, settings
from app.db import es_client

TOOL_SPEC = {
    "name": "search_assay_evidence",
    "description": "Search curated compound-target-assay evidence with optional filters.",
    "arguments": {
        "query": "free-text (matched against assay description, compound/target name)",
        "target": "target name/gene/ChEMBL id (optional)",
        "standard_type": "IC50|Ki|Kd|EC50 (optional)",
        "max_value_nm": "upper bound on standard_value_nm (optional)",
        "min_confidence": "minimum confidence_score (optional)",
        "limit": "max hits (default 10, max 50)",
    },
}


def run(
    query: str | None = None,
    target: str | None = None,
    standard_type: str | None = None,
    max_value_nm: float | None = None,
    min_confidence: int | None = None,
    limit: int = 10,
) -> dict:
    limit = max(1, min(int(limit or 10), 50))
    must: list[dict] = []
    filt: list[dict] = []

    if query:
        must.append({
            "multi_match": {
                "query": query,
                "fields": ["assay_description", "compound_name", "target_name"],
            }
        })

    target_id = resolve_target(target) if target else None
    if target_id:
        filt.append({"term": {"target_chembl_id": target_id}})
    elif target:
        filt.append({"match": {"target_name": target}})

    if standard_type:
        filt.append({"term": {"standard_type": standard_type}})
    if max_value_nm is not None:
        filt.append({"range": {"standard_value_nm": {"lte": float(max_value_nm)}}})
    if min_confidence is not None:
        filt.append({"range": {"confidence_score": {"gte": int(min_confidence)}}})

    body = {
        "size": limit,
        "query": {"bool": {"must": must or [{"match_all": {}}], "filter": filt}},
        "sort": [{"pchembl_value": "desc"}, {"standard_value_nm": "asc"}],
    }

    es = es_client()
    resp = es.search(index=settings.es_index, body=body)
    hits = [h["_source"] for h in resp["hits"]["hits"]]

    return {
        "result_count": len(hits),
        "filters_used": {
            "query": query, "target_chembl_id": target_id, "standard_type": standard_type,
            "max_value_nm": max_value_nm, "min_confidence": min_confidence, "limit": limit,
        },
        "es_query": body,            # surfaced to the user (transparency guardrail)
        "results": hits,
    }
