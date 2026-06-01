"""AssayLens — Streamlit chat UI over the governed agent.

A thin client: it sends the user's question to the FastAPI agent's /ask endpoint
and renders the answer plus the transparency payload (which tool ran, the
filters/SQL used, and the returned rows). It deliberately does no reasoning of
its own — all governance lives in the agent.
"""
from __future__ import annotations

import os

import requests
import streamlit as st

AGENT_API_URL = os.getenv("AGENT_API_URL", "http://localhost:8000")

st.set_page_config(page_title="AssayLens Copilot", page_icon="🔬", layout="wide")
st.title("🔬 AssayLens Copilot")
st.caption(
    "Read-only scientific data copilot over a curated ChEMBL kinase warehouse. "
    "Answers come only from governed tools — no scientific claims beyond the data."
)

with st.sidebar:
    st.header("About")
    st.markdown(
        "- Targets: **EGFR, HER2, BRAF, JAK2, VEGFR2**\n"
        "- Every answer shows the **tool**, **filters/SQL**, and **result count**.\n"
        "- SQL is SELECT-only against curated marts."
    )
    try:
        health = requests.get(f"{AGENT_API_URL}/health", timeout=3).json()
        st.success(f"Agent online · LLM {'on' if health.get('llm_enabled') else 'off (fallback)'}")
    except Exception:
        st.error(f"Agent unreachable at {AGENT_API_URL}")

    st.subheader("Try asking")
    st.caption("25 examples — each exercises a different governed tool / graph node.")
    # Grouped by the tool the router should pick, so every node gets covered:
    # ES search, knowledge RAG (lexical), schema, NL->SQL, raw SQL, compound &
    # target lookups, the graph relationship marts, DQ lineage, glossary,
    # Metabase dashboards, and a multi-step comparison.
    EXAMPLES = {
        "🔎 Assay search · Elasticsearch": [
            "Find high-confidence EGFR assays with IC50 under 100 nM.",
            "Search for VEGFR2 inhibitors with Ki below 10 nM.",
            "Show high-confidence BRAF assays that measure mutant activity.",
        ],
        "🧠 Semantic search · vector embeddings (RAG)": [
            "Which kinases behave alike chemically?",
            "Give me background on JAK2 and the assays used to study it.",
            "What evidence links EGFR and HER2?",
        ],
        "🗂️ Schema / metadata · describe_warehouse": [
            "How many tables are in the warehouse and what are they?",
            "What columns are in mart_compound_target_potency?",
        ],
        "🧮 Ask in English · NL→SQL": [
            "What are the top 10 most potent compounds against JAK2 by pChEMBL?",
            "How many curated measurements does each target have?",
            "Which 5 VEGFR2 assays have the most curated measurements?",
        ],
        "🛢️ Governed raw SQL": [
            "Run SQL: select target_name, count(*) from marts.mart_compound_target_potency "
            "group by 1 order by 2 desc.",
        ],
        "🧪 Compounds": [
            "Profile compound CHEMBL939 — properties, targets tested, best potency.",
            "Which targets does CHEMBL939 hit, and how strongly?",
            "Show the physicochemical profile for CHEMBL1421.",
        ],
        "🎯 Targets": [
            "Give me an activity summary for BRAF.",
            "How many active compounds and what's the median potency for VEGFR2?",
        ],
        "🕸️ Graph relationships": [
            "Which targets are most related to EGFR by shared compounds?",
            "What targets share the most chemistry with JAK2?",
        ],
        "🔍 Data-quality lineage": [
            "Why do raw EGFR rows differ from the curated EGFR potency mart?",
            "Why are some measurements excluded from the curated marts?",
        ],
        "📖 Metric glossary": [
            "Explain pChEMBL versus IC50 in plain English.",
            "What does the assay confidence score mean?",
        ],
        "📊 Dashboards · Metabase": [
            "Show me the warehouse overview dashboard.",
            "Open the Target Relationships dashboard.",
        ],
        "🔗 Multi-step comparison": [
            "Compare EGFR and HER2 by assay coverage and active compound count.",
        ],
    }
    for category, questions in EXAMPLES.items():
        st.caption(category)
        for ex in questions:
            if st.button(ex, use_container_width=True, key=ex):
                st.session_state["pending"] = ex

if "history" not in st.session_state:
    st.session_state["history"] = []


def ask_agent(question: str) -> dict:
    resp = requests.post(f"{AGENT_API_URL}/ask", json={"question": question}, timeout=60)
    resp.raise_for_status()
    return resp.json()


def render_turn(turn: dict) -> None:
    """Render one assistant turn: the answer, any embedded Metabase dashboards
    (for dashboard steps), and the transparency payload for every tool step."""
    st.write(turn["answer"])

    # A LangGraph plan can contain several steps; render each. Fall back to the
    # single-step convenience fields for older response shapes.
    steps = turn.get("steps")
    if not steps:
        steps = [{"tool": turn.get("tool"), "result": turn.get("tool_result", {}),
                  "result_count": turn.get("result_count")}]

    for step in steps:
        res = step.get("result", {}) or {}
        if step.get("tool") == "get_metabase_dashboard" and res.get("embed_url"):
            st.caption(f"📊 {res.get('dashboard','Dashboard')} — live from Metabase")
            st.components.v1.iframe(res["embed_url"], height=620, scrolling=True)
            if res.get("url"):
                st.markdown(f"[Open in Metabase ↗]({res['url']})")

    label = " → ".join(s.get("tool", "?") for s in steps)
    with st.expander(f"Plan: {label} ({len(steps)} step(s))"):
        st.json(steps)


# Render prior turns.
for turn in st.session_state["history"]:
    with st.chat_message("user"):
        st.write(turn["question"])
    with st.chat_message("assistant"):
        render_turn(turn)

question = st.chat_input("Ask about kinase assay evidence…") or st.session_state.pop("pending", None)
if question:
    with st.chat_message("user"):
        st.write(question)
    with st.chat_message("assistant"):
        with st.spinner("Routing to a governed tool…"):
            try:
                data = ask_agent(question)
            except Exception as exc:  # noqa: BLE001
                st.error(f"Request failed: {exc}")
                data = None
        if data:
            render_turn(data)
            st.session_state["history"].append(data)
