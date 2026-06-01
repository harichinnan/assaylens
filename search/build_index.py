#!/usr/bin/env python3
"""Build the Elasticsearch activity-evidence index from the curated potency mart.

One document per curated compound-target-assay result — the same grain the
agent's search_assay_evidence tool queries. The source is
marts.mart_compound_target_potency, so only comparable, high-quality evidence is
ever searchable (curation happens in dbt, not here).

Usage:
    python search/build_index.py
    python search/build_index.py --recreate    # drop + rebuild the index
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import psycopg
from elasticsearch import Elasticsearch, helpers

MAPPING_PATH = Path(__file__).parent / "index_mapping.json"

# Columns selected from the curated mart -> indexed document fields.
SELECT_SQL = """
    select
        activity_id,
        molecule_chembl_id,
        compound_name,
        canonical_smiles,
        target_chembl_id,
        target_name,
        assay_chembl_id,
        assay_description,
        standard_type,
        standard_value_nm,
        pchembl_value,
        confidence_score,
        journal,
        year
    from marts.mart_compound_target_potency
"""


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
    if user:
        return Elasticsearch(url, basic_auth=(user, password))
    return Elasticsearch(url)


def ensure_index(es: Elasticsearch, index: str, recreate: bool) -> None:
    mapping = json.loads(MAPPING_PATH.read_text())
    if es.indices.exists(index=index):
        if recreate:
            es.indices.delete(index=index)
        else:
            return
    es.indices.create(index=index, **mapping)
    print(f"Created index '{index}'")


def fetch_rows() -> list[dict]:
    with psycopg.connect(pg_dsn(), row_factory=psycopg.rows.dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(SELECT_SQL)
            return cur.fetchall()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--recreate", action="store_true", help="Drop and recreate the index.")
    args = ap.parse_args()

    index = os.getenv("ELASTICSEARCH_INDEX", "assaylens_activity_evidence")
    es = es_client()
    ensure_index(es, index, recreate=args.recreate)

    rows = fetch_rows()
    actions = (
        {"_index": index, "_id": str(r["activity_id"]), "_source": r}
        for r in rows
    )
    ok, errors = helpers.bulk(es, actions, stats_only=False)
    es.indices.refresh(index=index)
    print(f"Indexed {ok} documents into '{index}'.")
    if errors:
        print(f"WARNING: {len(errors)} indexing errors (showing first): {errors[:1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
