"""Tool: semantic RAG retrieval over the AssayLens knowledge corpus.

Primary path is DENSE-VECTOR (kNN): the query is embedded by the embedding
service and matched against the `embedding` field of `assaylens_knowledge`
(target summaries, assay descriptions, target relationships, metric defs) — so
"how do these two kinases relate?" retrieves the relationship doc even without
shared keywords. Falls back to lexical BM25 if the embedder is unavailable, so
the tool never hard-fails. `mode` can force "semantic" or "keyword".
"""
from __future__ import annotations

import httpx

from app.config import settings
from app.db import es_client

TOOL_SPEC = {
    "name": "search_knowledge",
    "description": (
        "Semantic (vector-embedding) retrieval of background passages — target summaries, "
        "assay descriptions, target relationships, metric definitions — for explanatory / "
        "'what is' / 'how are X and Y related' questions."
    ),
    "arguments": {
        "query": "free-text query",
        "doc_type": "optional filter: target_summary | assay | target_relationship | metric_glossary",
        "limit": "max passages (default 5, max 20)",
        "mode": "optional: semantic (default) | keyword",
    },
}

_DOC_TYPES = {"target_summary", "assay", "target_relationship", "metric_glossary"}


def _embed(query: str) -> list[float] | None:
    try:
        r = httpx.post(f"{settings.embedder_url.rstrip('/')}/embed",
                       json={"texts": [query]}, timeout=15.0)
        r.raise_for_status()
        return r.json()["vectors"][0]
    except Exception:
        return None


def _hits(resp) -> list[dict]:
    return [
        {"doc_type": h["_source"]["doc_type"], "title": h["_source"]["title"],
         "text": h["_source"]["text"], "score": round(h["_score"], 3)}
        for h in resp["hits"]["hits"]
    ]


def run(query: str, doc_type: str | None = None, limit: int = 5, mode: str = "semantic") -> dict:
    size = max(1, min(int(limit or 5), 20))
    if doc_type and doc_type not in _DOC_TYPES:
        return {"error": f"Unknown doc_type '{doc_type}'. Use one of: {', '.join(sorted(_DOC_TYPES))}."}
    filters = [{"term": {"doc_type": doc_type}}] if doc_type else []
    es = es_client()
    index = settings.es_knowledge_index

    # ---- semantic (dense-vector kNN) ----
    if mode != "keyword":
        vec = _embed(query)
        if vec is not None:
            try:
                resp = es.search(index=index, knn={
                    "field": "embedding", "query_vector": vec,
                    "k": size, "num_candidates": max(50, size * 10),
                    "filter": filters,
                }, size=size, source_excludes=["embedding"])
                return {"result_count": len(_hits(resp)), "query": query,
                        "retrieval": "semantic", "passages": _hits(resp)}
            except Exception as exc:
                # fall through to lexical
                lexical_err = str(exc)
        else:
            lexical_err = "embedder unavailable"
    else:
        lexical_err = None

    # ---- lexical (BM25) fallback / explicit keyword mode ----
    try:
        resp = es.search(index=index, query={"bool": {
            "must": [{"multi_match": {"query": query, "fields": ["title^2", "text"]}}],
            "filter": filters,
        }}, size=size, source_excludes=["embedding"])
    except Exception as exc:
        return {"error": f"knowledge search unavailable: {exc}",
                "hint": "build it: python search/build_knowledge_index.py --recreate"}
    out = {"result_count": len(_hits(resp)), "query": query,
           "retrieval": "keyword" if mode == "keyword" else "keyword_fallback",
           "passages": _hits(resp)}
    if lexical_err:
        out["note"] = f"semantic retrieval unavailable ({lexical_err}); used BM25."
    return out
