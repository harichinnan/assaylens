"""LangGraph orchestration for the AssayLens copilot.

A small, bounded, governed state machine:

    START → route → execute → summarize → END

  * route     — one (cached) LLM call classifies the question into an ordered
                list of 1-3 governed tool calls.
  * execute   — deterministically runs each planned tool (all guardrails live
                inside the tools; the LLM never touches data directly).
  * summarize — one (cached) LLM call turns the compact results into an answer.

The graph is linear but the plan can contain multiple steps, which is what
enables multi-target questions ("compare EGFR and HER2") without an unbounded
agent loop. Keeping control flow fixed is what makes the governance auditable.
"""
from __future__ import annotations

import logging
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.llm import llm
from app.registry import TOOLS, TOOL_SPECS
from app.tracing import observe_tool, set_output

logger = logging.getLogger("assaylens.agent")


class AgentState(TypedDict, total=False):
    request_id: str
    question: str
    plan: list[dict]                  # [{tool, arguments}]
    results: list[dict]               # [{tool, arguments, result}]
    answer: str


def route_node(state: AgentState) -> dict:
    rid = state.get("request_id", "-")
    plan = llm.plan(state["question"], TOOL_SPECS).get("steps", [])
    # Drop unknown tools defensively.
    plan = [s for s in plan if s.get("tool") in TOOLS] or [
        {"tool": "search_assay_evidence", "arguments": {"query": state["question"]}}
    ]
    logger.info("[%s] plan=%s", rid, [s["tool"] for s in plan])
    return {"plan": plan}


def execute_node(state: AgentState) -> dict:
    rid = state.get("request_id", "-")
    results: list[dict] = []
    for step in state["plan"]:
        tool, args = step["tool"], (step.get("arguments") or {})
        with observe_tool(tool, args) as span:
            try:
                res = TOOLS[tool].run(**args)
            except TypeError as exc:
                logger.warning("[%s] bad arguments for %s: %s", rid, tool, exc)
                res = {"error": f"Could not call {tool} with {args}: {exc}"}
            except Exception as exc:  # noqa: BLE001 - surface safe message, log detail
                logger.exception("[%s] tool %s failed", rid, tool)
                res = {"error": f"{tool} failed: {exc}"}
            set_output(span, {"result_count": res.get("result_count"), "error": res.get("error")})
        logger.info("[%s] tool=%s result_count=%s", rid, tool, res.get("result_count"))
        results.append({"tool": tool, "arguments": args, "result": res})
    return {"results": results}


def summarize_node(state: AgentState) -> dict:
    return {"answer": llm.summarize(state["question"], state["results"])}


def build_graph():
    g = StateGraph(AgentState)
    g.add_node("route", route_node)
    g.add_node("execute", execute_node)
    g.add_node("summarize", summarize_node)
    g.add_edge(START, "route")
    g.add_edge("route", "execute")
    g.add_edge("execute", "summarize")
    g.add_edge("summarize", END)
    return g.compile()


graph = build_graph()
