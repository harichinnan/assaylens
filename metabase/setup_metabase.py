#!/usr/bin/env python3
"""Idempotent Metabase provisioning for AssayLens.

Automates what would otherwise be manual onboarding so the BI layer is
reproducible:

  1. complete first-run setup (create admin from env)
  2. set site URL + enable static embedding (returns the signing secret)
  3. register the Postgres analytics database (marts schema) and sync it
  4. create a SEMANTIC LAYER of Models over the curated marts
  5. build the 4 dashboards (cards + a target/compound filter)
  6. mark each dashboard embeddable and print the ids + secret for .env

Re-running is safe: every object is looked up by name and reused.

Run on the compose network so it can reach Metabase + Postgres by service name:

  docker run --rm --network assaylens_default \
    -e MB_URL=http://metabase:3000 -e PG_HOST=postgres \
    -v "$PWD":/work -w /work python:3.11-slim \
    bash -lc 'pip install -q requests && python metabase/setup_metabase.py'
"""
from __future__ import annotations

import json
import os
import sys
import time

import requests

MB = os.getenv("MB_URL", "http://localhost:3000").rstrip("/")
SITE_URL = os.getenv("MB_SITE_URL", "http://localhost:3000").rstrip("/")
ADMIN_EMAIL = os.getenv("MB_ADMIN_EMAIL", "admin@assaylens.local")
ADMIN_PASSWORD = os.getenv("MB_ADMIN_PASSWORD", "AssayLens#2026demo")

PG = dict(
    host=os.getenv("PG_HOST", "postgres"),
    port=int(os.getenv("PG_PORT", "5432")),
    dbname=os.getenv("PG_DB", "assaylens"),
    user=os.getenv("PG_USER", "assaylens"),
    password=os.getenv("PG_PASSWORD", "assaylens"),
)
DB_NAME = "AssayLens Warehouse"
COLLECTION_NAME = "AssayLens"

session = requests.Session()


def api(method: str, path: str, **kw):
    r = session.request(method, f"{MB}{path}", timeout=60, **kw)
    if r.status_code >= 400:
        raise SystemExit(f"{method} {path} -> {r.status_code}: {r.text[:500]}")
    return r.json() if r.text else {}


# ---------------------------------------------------------------- 1. onboarding
def ensure_admin_session() -> None:
    props = requests.get(f"{MB}/api/session/properties", timeout=30).json()
    if props.get("has-user-setup"):
        token = api("POST", "/api/session",
                    json={"username": ADMIN_EMAIL, "password": ADMIN_PASSWORD}).get("id")
        session.headers["X-Metabase-Session"] = token
        print("[mb] logged in (already set up)")
        return

    setup_token = props["setup-token"]
    resp = api("POST", "/api/setup", json={
        "token": setup_token,
        "prefs": {"site_name": "AssayLens", "site_locale": "en"},
        "user": {
            "first_name": "Assay", "last_name": "Lens",
            "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD,
            "site_name": "AssayLens",
        },
    })
    session.headers["X-Metabase-Session"] = resp["id"]
    print("[mb] completed first-run setup")


# ------------------------------------------------------ 2. site url + embedding
def configure_embedding() -> str:
    import secrets as _s
    api("PUT", "/api/setting/site-url", json={"value": SITE_URL})
    api("PUT", "/api/setting/enable-embedding", json={"value": True})
    # Set a deterministic secret we control (and hand to the agent) rather than
    # parsing the auto-generated one, whose response encoding varies by version.
    secret = os.getenv("MB_EMBEDDING_SECRET_KEY") or _s.token_hex(32)
    api("PUT", "/api/setting/embedding-secret-key", json={"value": secret})
    print("[mb] embedding enabled")
    return secret


# ---------------------------------------------------------------- 3. database
def ensure_database() -> int:
    for db in api("GET", "/api/database").get("data", []):
        if db["name"] == DB_NAME:
            print(f"[mb] database exists (id={db['id']})")
            return db["id"]
    db = api("POST", "/api/database", json={
        "engine": "postgres",
        "name": DB_NAME,
        "details": {
            "host": PG["host"], "port": PG["port"], "dbname": PG["dbname"],
            "user": PG["user"], "password": PG["password"],
            "schema-filters-type": "inclusion", "schema-filters-patterns": "marts",
            "ssl": False, "tunnel-enabled": False,
        },
    })
    db_id = db["id"]
    api("POST", f"/api/database/{db_id}/sync_schema")
    print(f"[mb] database created (id={db_id}); syncing…")
    # Wait until the marts tables appear.
    for _ in range(30):
        meta = api("GET", f"/api/database/{db_id}/metadata")
        tables = [t for t in meta.get("tables", []) if t["schema"] == "marts"]
        if len(tables) >= 5:
            print(f"[mb] synced {len(tables)} marts tables")
            return db_id
        time.sleep(2)
    print("[mb] WARNING: marts tables not fully synced yet")
    return db_id


# ---------------------------------------------------------------- collection
def ensure_collection() -> int:
    for c in api("GET", "/api/collection"):
        if c.get("name") == COLLECTION_NAME and not c.get("archived"):
            return c["id"]
    c = api("POST", "/api/collection",
            json={"name": COLLECTION_NAME, "description": "AssayLens BI", "color": "#509EE3"})
    return c["id"]


# ------------------------------------------------------ card / model helpers
def native(db_id: int, sql: str, tags: dict | None = None) -> dict:
    return {
        "type": "native",
        "native": {"query": sql, "template-tags": tags or {}},
        "database": db_id,
    }


def find_card(name: str, coll_id: int):
    for c in api("GET", f"/api/collection/{coll_id}/items?models=card&models=dataset").get("data", []):
        if c["name"] == name:
            return c["id"]
    return None


def upsert_card(name, db_id, coll_id, sql, display="table", viz=None, tags=None, is_model=False):
    existing = find_card(name, coll_id)
    body = {
        "name": name,
        "dataset_query": native(db_id, sql, tags),
        "display": display,
        "visualization_settings": viz or {},
        "collection_id": coll_id,
    }
    # In v0.49 a Model is a card with dataset=true.
    body["dataset"] = is_model
    if existing:
        return api("PUT", f"/api/card/{existing}", json=body)["id"]
    return api("POST", "/api/card", json=body)["id"]


def target_tag() -> dict:
    # Optional native variable used by filterable cards: [[ and ... = {{target}} ]]
    return {"target": {"id": "tt-target", "name": "target", "display-name": "Target",
                       "type": "text", "required": False}}


def compound_tag() -> dict:
    return {"compound": {"id": "tt-compound", "name": "compound", "display-name": "Compound",
                         "type": "text", "required": False}}


# ---------------------------------------------------- 4. semantic-layer models
MODELS = {
    "Curated Potency Evidence": "select * from marts.mart_compound_target_potency",
    "Target Activity Summary":  "select * from marts.mart_target_activity_summary",
    "Assay Quality":            "select * from marts.mart_assay_quality",
    "Compound Profile":         "select * from marts.mart_compound_profile",
    "Data Quality Summary":     "select * from marts.mart_data_quality_summary",
    "Target Similarity":        "select * from marts.graph_target_similarity",
    "Compound-Target Edges":    "select * from marts.graph_compound_target_edge",
}


def ensure_models(db_id: int, coll_id: int) -> None:
    for name, sql in MODELS.items():
        upsert_card(name, db_id, coll_id, sql, display="table", is_model=True)
    print(f"[mb] {len(MODELS)} semantic-layer models ready")


# -------------------------------------------------------------- 5. dashboards
def scalar(name, db_id, coll_id, metric):
    sql = f"select value from marts.mart_data_quality_summary where metric = '{metric}'"
    return upsert_card(name, db_id, coll_id, sql, display="scalar")


def ensure_dashboard(name: str, coll_id: int) -> int:
    for d in api("GET", f"/api/collection/{coll_id}/items?models=dashboard").get("data", []):
        if d["name"] == name:
            return d["id"]
    return api("POST", "/api/dashboard", json={"name": name, "collection_id": coll_id})["id"]


def grid(card_ids_with_pos, parameters=None, param_map_slug=None):
    """Build a dashcards array. card_ids_with_pos: list of (card_id, row,col,sx,sy, filtered)."""
    dashcards = []
    for i, (cid, row, col, sx, sy, filtered) in enumerate(card_ids_with_pos):
        dc = {"id": -(i + 1), "card_id": cid, "row": row, "col": col,
              "size_x": sx, "size_y": sy, "series": [], "visualization_settings": {},
              "parameter_mappings": []}
        if filtered and parameters and param_map_slug:
            p = parameters[0]
            dc["parameter_mappings"] = [{
                "parameter_id": p["id"], "card_id": cid,
                "target": ["variable", ["template-tag", param_map_slug]],
            }]
        dashcards.append(dc)
    return dashcards


def save_dashboard(dash_id, dashcards, parameters=None):
    api("PUT", f"/api/dashboard/{dash_id}",
        json={"dashcards": dashcards, "parameters": parameters or []})


def enable_embed(dash_id, slug=None):
    params = {slug: "enabled"} if slug else {}
    api("PUT", f"/api/dashboard/{dash_id}",
        json={"enable_embedding": True, "embedding_params": params})


def build_overview(db_id, coll_id) -> int:
    d = ensure_dashboard("Scientific Warehouse Overview", coll_id)
    cards = [
        (scalar("Total Compounds", db_id, coll_id, "total_compounds"), 0, 0, 4, 3, False),
        (scalar("Total Targets", db_id, coll_id, "total_targets"), 0, 4, 4, 3, False),
        (scalar("Total Assays", db_id, coll_id, "total_assays"), 0, 8, 4, 3, False),
        (scalar("Total Measurements", db_id, coll_id, "total_measurements"), 0, 12, 4, 3, False),
        (scalar("% Normalized nM", db_id, coll_id, "pct_with_normalized_nm"), 3, 0, 4, 3, False),
        (scalar("% With pChEMBL", db_id, coll_id, "pct_with_pchembl"), 3, 4, 4, 3, False),
        (scalar("% Curated", db_id, coll_id, "pct_curated"), 3, 8, 4, 3, False),
        (upsert_card("Excluded Rows by Reason", db_id, coll_id,
            "select metric as reason, value from marts.mart_data_quality_summary "
            "where metric_group = 'excluded_by_reason' order by value desc",
            display="bar",
            viz={"graph.dimensions": ["reason"], "graph.metrics": ["value"]}), 6, 0, 12, 5, False),
    ]
    save_dashboard(d, grid(cards))
    enable_embed(d)
    return d


def build_target_explorer(db_id, coll_id) -> int:
    d = ensure_dashboard("Target Activity Explorer", coll_id)
    params = [{"id": "p_target", "name": "Target", "slug": "target", "type": "string/="}]
    tt = target_tag()
    filt = "where 1=1 [[ and target_chembl_id = {{target}} ]]"
    cards = [
        (upsert_card("Measurements by Target", db_id, coll_id,
            f"select target_name, total_measurements from marts.mart_target_activity_summary {filt} order by 2 desc",
            display="bar", tags=tt,
            viz={"graph.dimensions": ["target_name"], "graph.metrics": ["total_measurements"]}), 0, 0, 8, 5, True),
        (upsert_card("Active Compounds by Target", db_id, coll_id,
            f"select target_name, active_compounds from marts.mart_target_activity_summary {filt} order by 2 desc",
            display="bar", tags=tt,
            viz={"graph.dimensions": ["target_name"], "graph.metrics": ["active_compounds"]}), 0, 8, 8, 5, True),
        (upsert_card("Median Potency (nM) by Target", db_id, coll_id,
            f"select target_name, median_potency_nm from marts.mart_target_activity_summary {filt} order by 2",
            display="bar", tags=tt,
            viz={"graph.dimensions": ["target_name"], "graph.metrics": ["median_potency_nm"]}), 5, 0, 8, 5, True),
        (upsert_card("Curated Evidence", db_id, coll_id,
            "select compound_name, target_name, standard_type, standard_value_nm, pchembl_value, "
            f"confidence_score, assay_description from marts.mart_compound_target_potency {filt} "
            "order by pchembl_value desc", display="table", tags=tt), 5, 8, 8, 5, True),
    ]
    save_dashboard(d, grid(cards, params, "target"), params)
    enable_embed(d, "target")
    return d


def build_compound_profile(db_id, coll_id) -> int:
    d = ensure_dashboard("Compound Profile", coll_id)
    params = [{"id": "p_compound", "name": "Compound", "slug": "compound", "type": "string/="}]
    ct = compound_tag()
    filt = "where 1=1 [[ and molecule_chembl_id = {{compound}} ]]"
    cards = [
        (upsert_card("Compound Properties", db_id, coll_id,
            "select molecule_chembl_id, compound_name, molecular_weight, alogp, hba, hbd, ro5_violations, "
            f"canonical_smiles from marts.mart_compound_profile {filt}", display="table", tags=ct), 0, 0, 16, 3, True),
        (upsert_card("Best pChEMBL by Target", db_id, coll_id,
            "select target_name, max(pchembl_value) as best_pchembl from marts.mart_compound_target_potency "
            f"{filt} group by target_name order by best_pchembl desc", display="bar", tags=ct,
            viz={"graph.dimensions": ["target_name"], "graph.metrics": ["best_pchembl"]}), 3, 0, 8, 5, True),
        (upsert_card("Assay Evidence & Lineage", db_id, coll_id,
            "select target_name, assay_description, standard_type, standard_value_nm, pchembl_value, "
            f"journal, year from marts.mart_compound_target_potency {filt} order by pchembl_value desc",
            display="table", tags=ct), 3, 8, 8, 5, True),
    ]
    save_dashboard(d, grid(cards, params, "compound"), params)
    enable_embed(d, "compound")
    return d


def build_data_quality(db_id, coll_id) -> int:
    d = ensure_dashboard("Data Quality", coll_id)
    params = [{"id": "p_target", "name": "Target", "slug": "target", "type": "string/="}]
    tt = target_tag()
    cards = [
        (scalar("Missing Units", db_id, coll_id, "missing_standard_units"), 0, 0, 3, 3, False),
        (scalar("Missing pChEMBL", db_id, coll_id, "missing_pchembl_value"), 0, 3, 3, 3, False),
        (scalar("Ambiguous Relation", db_id, coll_id, "ambiguous_relation"), 0, 6, 3, 3, False),
        (scalar("Low Confidence", db_id, coll_id, "low_confidence"), 0, 9, 3, 3, False),
        (scalar("Duplicate Rows", db_id, coll_id, "duplicate_measurements"), 0, 12, 3, 3, False),
        (upsert_card("Excluded by Reason", db_id, coll_id,
            "select metric as reason, value from marts.mart_data_quality_summary "
            "where metric_group = 'excluded_by_reason' order by value desc", display="bar",
            viz={"graph.dimensions": ["reason"], "graph.metrics": ["value"]}), 3, 0, 8, 5, False),
        (upsert_card("Assay Quality Detail", db_id, coll_id,
            "select assay_chembl_id, target_name, confidence_score, total_measurements, curated_measurements, "
            "missing_pchembl, ambiguous_relation from marts.mart_assay_quality "
            "where 1=1 [[ and target_chembl_id = {{target}} ]] order by confidence_score",
            display="table", tags=tt), 3, 8, 8, 5, True),
    ]
    save_dashboard(d, grid(cards, params, "target"), params)
    enable_embed(d, "target")
    return d


def build_relationships(db_id, coll_id) -> int:
    d = ensure_dashboard("Target Relationships", coll_id)
    cards = [
        (upsert_card("Target Pairs by Shared Compounds", db_id, coll_id,
            "select target_a_name || ' <-> ' || target_b_name as pair, shared_compounds, jaccard "
            "from marts.graph_target_similarity order by shared_compounds desc",
            display="bar",
            viz={"graph.dimensions": ["pair"], "graph.metrics": ["shared_compounds"]}), 0, 0, 8, 5, False),
        (upsert_card("Target Similarity Matrix", db_id, coll_id,
            "select target_a_name, target_b_name, shared_compounds, jaccard "
            "from marts.graph_target_similarity order by jaccard desc",
            display="table"), 0, 8, 8, 5, False),
        (upsert_card("Most Promiscuous Compounds", db_id, coll_id,
            "select molecule_chembl_id, compound_name, count(*) as targets_hit, "
            "round(max(best_pchembl)::numeric, 2) as best_pchembl "
            "from marts.graph_compound_target_edge group by 1, 2 having count(*) > 1 "
            "order by targets_hit desc, best_pchembl desc limit 50",
            display="table"), 5, 0, 16, 6, False),
    ]
    save_dashboard(d, grid(cards))
    enable_embed(d)
    return d


# ---------------------------------------------------------------------- main
def main() -> int:
    ensure_admin_session()
    secret = configure_embedding()
    db_id = ensure_database()
    coll_id = ensure_collection()
    ensure_models(db_id, coll_id)

    ids = {
        "MB_DASH_OVERVIEW": build_overview(db_id, coll_id),
        "MB_DASH_TARGET": build_target_explorer(db_id, coll_id),
        "MB_DASH_COMPOUND": build_compound_profile(db_id, coll_id),
        "MB_DASH_QUALITY": build_data_quality(db_id, coll_id),
        "MB_DASH_RELATIONSHIPS": build_relationships(db_id, coll_id),
    }
    print("[mb] dashboards built:", json.dumps(ids))

    out = {"embedding_secret": secret, "dashboards": ids, "site_url": SITE_URL}
    with open("metabase/.metabase_ids.json", "w") as f:
        json.dump(out, f, indent=2)

    print("\n# ---- add these to .env (agent embed config) ----")
    print(f"MB_SITE_URL={SITE_URL}")
    print(f"MB_EMBEDDING_SECRET_KEY={secret}")
    for k, v in ids.items():
        print(f"{k}={v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
