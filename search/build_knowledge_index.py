#!/usr/bin/env python3
"""Build the Elasticsearch KNOWLEDGE index for the agent's RAG retrieval.

Unlike the row-grained activity-evidence index, this assembles short natural-
language *documents* the LLM can retrieve as grounding context:

  * target_summary      — one per target: counts, median potency, organism
  * assay               — one per assay: description + type + confidence
  * target_relationship — one per target pair: shared compounds + Jaccard
                          (this is the ES relationship surface for the graph)
  * metric_glossary     — static definitions (IC50/Ki/Kd/EC50/pChEMBL/...)

Source is the curated marts.* in native Postgres. The agent's search_knowledge
tool does a lexical multi_match over title+text.

Usage:
    python search/build_knowledge_index.py
    python search/build_knowledge_index.py --recreate
"""
from __future__ import annotations

import argparse
import json
import os
import urllib.request
from pathlib import Path

import psycopg
from elasticsearch import Elasticsearch, helpers

MAPPING_PATH = Path(__file__).parent / "knowledge_mapping.json"
INDEX = os.getenv("ELASTICSEARCH_KNOWLEDGE_INDEX", "assaylens_knowledge")
ASSAY_DOC_CAP = int(os.getenv("KNOWLEDGE_ASSAY_CAP", "4000"))
EMBEDDER_URL = os.getenv("EMBEDDER_URL", "http://localhost:8100").rstrip("/")


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Call the embedding service (stdlib HTTP, no torch dep here). Batches to
    keep request bodies sane."""
    out: list[list[float]] = []
    for i in range(0, len(texts), 256):
        batch = texts[i:i + 256]
        body = json.dumps({"texts": batch}).encode()
        req = urllib.request.Request(
            f"{EMBEDDER_URL}/embed", data=body,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            out.extend(json.loads(resp.read())["vectors"])
    return out

METRIC_GLOSSARY = {
    "IC50": "Half-maximal inhibitory concentration: the concentration that inhibits a biological process by 50%. Lower is more potent.",
    "Ki": "Inhibition constant: binding affinity of an inhibitor; lower is stronger binding.",
    "Kd": "Dissociation constant: equilibrium binding affinity; lower is tighter binding.",
    "EC50": "Half-maximal effective concentration: the concentration giving 50% of maximal effect. Lower is more potent.",
    "pChEMBL": "Negative log10 of the molar activity value (-log10(M)). Higher is more potent; pChEMBL 7 = 100 nM.",
    "confidence_score": "ChEMBL assay-to-target confidence (0-9). Higher means the assay more directly measures the assigned target; curation requires >= 7.",
    "standard_relation": "Operator on the measured value ('=', '>', '<', ...). Only '=' (or unspecified) rows are curated as comparable.",
}


def pg_dsn() -> str:
    return (
        f"host={os.getenv('POSTGRES_HOST', 'localhost')} "
        f"port={os.getenv('POSTGRES_PORT', '5432')} "
        f"dbname={os.getenv('POSTGRES_DB', 'assaylens')} "
        f"user={os.getenv('POSTGRES_USER', 'assaylens')} "
        f"password={os.getenv('POSTGRES_PASSWORD', 'assaylens')}"
    )


def es_client() -> Elasticsearch:
    url = os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")
    user = os.getenv("ELASTICSEARCH_USER") or None
    password = os.getenv("ELASTICSEARCH_PASSWORD") or None
    return Elasticsearch(url, basic_auth=(user, password)) if user else Elasticsearch(url)


def _rows(cur, sql: str) -> list[dict]:
    cur.execute(sql)
    cols = [c.name for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def build_docs(cur) -> list[dict]:
    docs: list[dict] = []

    # ---- target summaries ----
    for t in _rows(cur, "select * from marts.mart_target_activity_summary"):
        docs.append({
            "doc_id": f"target:{t['target_chembl_id']}",
            "doc_type": "target_summary",
            "target_chembl_id": t["target_chembl_id"],
            "entity_id": t["target_chembl_id"],
            "title": f"{t['target_name']} ({t['target_chembl_id']}) activity summary",
            "text": (
                f"{t['target_name']} ({t['organism']}) has {t['total_measurements']} total measurements "
                f"and {t['curated_measurements']} curated comparable measurements across "
                f"{t['total_compounds_tested']} compounds tested ({t['active_compounds']} active). "
                f"Median curated potency is {t['median_potency_nm']} nM "
                f"(median pChEMBL {t['median_pchembl']}, best pChEMBL {t['best_pchembl']})."
            ),
        })

    # ---- target relationships (the graph, as retrievable text) ----
    for r in _rows(cur, "select * from marts.graph_target_similarity"):
        docs.append({
            "doc_id": f"rel:{r['target_a']}:{r['target_b']}",
            "doc_type": "target_relationship",
            "entity_id": f"{r['target_a']}|{r['target_b']}",
            "title": f"Relationship: {r['target_a_name']} and {r['target_b_name']}",
            "text": (
                f"{r['target_a_name']} ({r['target_a']}) and {r['target_b_name']} ({r['target_b']}) "
                f"share {r['shared_compounds']} curated compounds (Jaccard similarity {r['jaccard']}). "
                f"Compounds active on both suggest overlapping chemistry / polypharmacology."
            ),
        })

    # ---- assays (capped) ----
    for a in _rows(cur, f"select * from marts.mart_assay_quality where assay_description is not null "
                        f"order by curated_measurements desc nulls last limit {ASSAY_DOC_CAP}"):
        docs.append({
            "doc_id": f"assay:{a['assay_chembl_id']}",
            "doc_type": "assay",
            "target_chembl_id": a.get("target_chembl_id"),
            "entity_id": a["assay_chembl_id"],
            "title": f"Assay {a['assay_chembl_id']} ({a.get('target_name')})",
            "text": (
                f"{a['assay_description']} Type {a.get('assay_type')}, confidence {a.get('confidence_score')}. "
                f"{a.get('total_measurements')} measurements, {a.get('curated_measurements')} curated."
            ),
        })

    # ---- metric glossary (static) ----
    for term, definition in METRIC_GLOSSARY.items():
        docs.append({
            "doc_id": f"metric:{term}",
            "doc_type": "metric_glossary",
            "entity_id": term,
            "title": f"Metric: {term}",
            "text": f"{term}: {definition}",
        })

    return docs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--recreate", action="store_true", help="drop + rebuild the index")
    args = ap.parse_args()

    es = es_client()
    mapping = json.loads(MAPPING_PATH.read_text())
    if es.indices.exists(index=INDEX):
        if args.recreate:
            es.indices.delete(index=INDEX)
            es.indices.create(index=INDEX, **mapping)
    else:
        es.indices.create(index=INDEX, **mapping)

    with psycopg.connect(pg_dsn()) as conn, conn.cursor() as cur:
        docs = build_docs(cur)

    # Dense-vector embeddings for semantic (kNN) retrieval: embed title + text.
    vectors = embed_texts([f"{d['title']}. {d['text']}" for d in docs])
    for d, v in zip(docs, vectors):
        d["embedding"] = v

    actions = ({"_index": INDEX, "_id": d["doc_id"], "_source": d} for d in docs)
    ok, _ = helpers.bulk(es, actions, stats_only=False)
    es.indices.refresh(index=INDEX)
    by_type: dict[str, int] = {}
    for d in docs:
        by_type[d["doc_type"]] = by_type.get(d["doc_type"], 0) + 1
    print(f"Indexed {ok} knowledge documents into '{INDEX}'. By type: {by_type}")


if __name__ == "__main__":
    main()
