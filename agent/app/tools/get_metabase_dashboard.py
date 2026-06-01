"""Tool: route a question to the relevant Metabase dashboard and return a
signed static-embedding URL the UI can drop into an iframe.

Metabase static embedding: the agent signs a short-lived JWT (HS256) with the
shared embedding secret, naming the dashboard resource. Filter values (target /
compound) are passed as "enabled" query parameters keyed by the dashboard
parameter slug. The result is a self-contained, login-free, time-boxed URL —
so the copilot can literally show live Metabase data inline.
"""
from __future__ import annotations

import time
from urllib.parse import urlencode

from app.config import resolve_target, settings

TOOL_SPEC = {
    "name": "get_metabase_dashboard",
    "description": "Return a relevant Metabase dashboard as a signed embeddable URL + filters.",
    "arguments": {
        "dashboard_name": "warehouse_overview | target_activity_explorer | compound_profile | data_quality | target_relationships",
        "filters": "optional dict, e.g. {'target': 'BRAF'} or {'compound': 'CHEMBL939'}",
    },
}

# logical name -> (title, env-id setting attr, filter param slug or None)
DASHBOARDS = {
    "warehouse_overview":        ("Scientific Warehouse Overview", "MB_DASH_OVERVIEW", None),
    "target_activity_explorer":  ("Target Activity Explorer", "MB_DASH_TARGET", "target"),
    "compound_profile":          ("Compound Profile", "MB_DASH_COMPOUND", "compound"),
    "data_quality":              ("Data Quality", "MB_DASH_QUALITY", "target"),
    "target_relationships":      ("Target Relationships", "MB_DASH_RELATIONSHIPS", None),
}

import os


def _dashboard_id(env_attr: str) -> str:
    return os.getenv(env_attr, "")


def _sign_embed_url(dash_id: int, query_params: dict) -> str | None:
    """Build a signed static-embedding URL, or None if embedding isn't configured."""
    if not settings.mb_embedding_secret:
        return None
    import jwt  # PyJWT

    payload = {
        "resource": {"dashboard": int(dash_id)},
        "params": {},  # enabled params travel in the query string, not the token
        "exp": int(time.time()) + settings.mb_embed_ttl_seconds,
    }
    token = jwt.encode(payload, settings.mb_embedding_secret, algorithm="HS256")
    base = f"{settings.mb_site_url.rstrip('/')}/embed/dashboard/{token}"
    qs = urlencode({k: v for k, v in query_params.items() if v is not None})
    fragment = "#bordered=true&titled=true"
    return f"{base}?{qs}{fragment}" if qs else f"{base}{fragment}"


def run(dashboard_name: str, filters: dict | None = None) -> dict:
    name = (dashboard_name or "").strip().lower()
    if name not in DASHBOARDS:
        return {"error": f"Unknown dashboard '{dashboard_name}'.", "available": sorted(DASHBOARDS)}

    title, env_attr, param_slug = DASHBOARDS[name]
    dash_id = _dashboard_id(env_attr)
    filters = dict(filters or {})

    # Resolve a filter value for this dashboard's parameter (if it takes one).
    query_params: dict = {}
    resolved_filters: dict = {}
    if param_slug == "target":
        raw = filters.get("target") or filters.get("target_chembl_id") or filters.get("target_name")
        tid = resolve_target(str(raw)) if raw else None
        if tid:
            query_params["target"] = tid
            resolved_filters["target_chembl_id"] = tid
    elif param_slug == "compound":
        raw = filters.get("compound") or filters.get("molecule_chembl_id")
        if raw:
            cid = str(raw).strip().upper()
            query_params["compound"] = cid
            resolved_filters["molecule_chembl_id"] = cid

    if not dash_id:
        return {
            "result_count": 1, "dashboard": title,
            "url": f"{settings.mb_site_url.rstrip('/')}/dashboards",
            "embed_url": None, "filters_used": resolved_filters,
            "note": f"Set {env_attr} (run metabase/setup_metabase.py) for a deep link.",
        }

    embed_url = _sign_embed_url(dash_id, query_params)
    # Direct (login) link as a fallback for users with a Metabase session.
    direct = f"{settings.mb_site_url.rstrip('/')}/dashboard/{dash_id}"
    if query_params:
        direct += "?" + urlencode(query_params)

    return {
        "result_count": 1,
        "dashboard": title,
        "dashboard_id": int(dash_id),
        "embed_url": embed_url,           # iframe-ready, signed, no login
        "url": direct,                    # open in Metabase (needs session)
        "filters_used": resolved_filters,
        "note": None if embed_url else
            "Embedding secret not set (MB_EMBEDDING_SECRET_KEY); returning a direct link only.",
    }
