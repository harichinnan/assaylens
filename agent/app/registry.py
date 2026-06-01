"""Shared tool registry.

Single source of truth for the governed tools and their specs, imported by both
the LangGraph nodes (graph.py) and the FastAPI app (main.py) to avoid a circular
import between them.
"""
from __future__ import annotations

from typing import Any

from app.tools import (
    ask_warehouse,
    describe_warehouse,
    explain_data_quality,
    get_compound_profile,
    get_compound_targets,
    get_metabase_dashboard,
    get_metric_definition,
    get_target_neighbors,
    get_target_summary,
    run_curated_sql,
    search_assay_evidence,
    search_knowledge,
)

# name -> module exposing .run(**args) and .TOOL_SPEC
TOOLS: dict[str, Any] = {
    "search_assay_evidence": search_assay_evidence,
    "search_knowledge": search_knowledge,
    "describe_warehouse": describe_warehouse,
    "run_curated_sql": run_curated_sql,
    "ask_warehouse": ask_warehouse,
    "get_compound_profile": get_compound_profile,
    "get_compound_targets": get_compound_targets,
    "get_target_summary": get_target_summary,
    "get_target_neighbors": get_target_neighbors,
    "explain_data_quality": explain_data_quality,
    "get_metric_definition": get_metric_definition,
    "get_metabase_dashboard": get_metabase_dashboard,
}

TOOL_SPECS: list[dict] = [m.TOOL_SPEC for m in TOOLS.values()]
