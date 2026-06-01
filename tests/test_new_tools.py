"""Unit tests for the lakehouse-era agent tools (B/A/D).

Guardrail tests are pure (config only). Tool tests exercise the early-return
validation paths that run BEFORE any DB/ES call, so they need no live services;
they importorskip psycopg (the only hard import dep) to stay host-portable.
"""
import pytest

from app.guardrails.sql_guardrails import SqlGuardrailError, validate_sql


# ---- B: broadened allow-list now includes the graph relationship marts ----
def test_graph_marts_are_allowlisted():
    v = validate_sql("select * from marts.graph_target_similarity")
    assert "graph_target_similarity" in v.referenced_tables
    assert v.limit <= 200  # mandatory LIMIT injected

    v2 = validate_sql(
        "select molecule_chembl_id, target_chembl_id from marts.graph_compound_target_edge limit 5"
    )
    assert "graph_compound_target_edge" in v2.referenced_tables
    assert v2.limit == 5


def test_non_allowlisted_table_still_blocked():
    with pytest.raises(SqlGuardrailError):
        validate_sql("select * from public.activities")
    with pytest.raises(SqlGuardrailError):
        validate_sql("select * from marts.fact_bioactivity_result")  # fact is tool-only


# ---- B: NL->SQL extraction strips fences / prose ----
def test_ask_warehouse_extract_sql():
    pytest.importorskip("psycopg")
    from app.tools.ask_warehouse import _extract_sql

    assert _extract_sql("```sql\nSELECT 1\n```").lower().startswith("select")
    assert _extract_sql("Sure:\nWITH x AS (select 1) select * from x").lower().startswith("with")


# ---- A: knowledge retrieval rejects unknown doc_type before hitting ES ----
def test_search_knowledge_rejects_bad_doc_type():
    pytest.importorskip("psycopg")
    from app.tools.search_knowledge import run

    out = run("egfr", doc_type="not_a_type")
    assert "error" in out


# ---- D: graph tools validate ids before querying ----
def test_get_compound_targets_requires_chembl_id():
    pytest.importorskip("psycopg")
    from app.tools.get_compound_targets import run

    assert "error" in run("not-a-chembl-id")


def test_get_target_neighbors_unknown_target():
    pytest.importorskip("psycopg")
    from app.tools.get_target_neighbors import run

    assert "error" in run("definitely-not-a-target")
