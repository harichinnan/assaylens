"""AssayLens governed AI copilot — FastAPI service (LangGraph-backed).

POST /ask runs the compiled LangGraph state machine (route → execute →
summarize; see graph.py). The response carries the full ordered list of tool
`steps` (each with its filters/SQL and result — the transparency guardrail),
plus convenience top-level fields for the primary step. LLM calls are cached
(see cache.py) to save tokens on repeated questions.
"""
from __future__ import annotations

import logging
import uuid

from fastapi import FastAPI
from pydantic import BaseModel

from app.cache import cache
from app.graph import graph
from app.llm import llm
from app.registry import TOOLS, TOOL_SPECS
from app.tracing import enabled as trace_enabled, flush as trace_flush, set_output, trace_request

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s assaylens.agent %(message)s",
)
logger = logging.getLogger("assaylens.agent")

app = FastAPI(title="AssayLens Copilot", version="0.2.0")


class AskRequest(BaseModel):
    question: str


class Step(BaseModel):
    tool: str
    arguments: dict
    result_count: int | None = None
    result: dict


class AskResponse(BaseModel):
    request_id: str
    question: str
    answer: str
    steps: list[Step]
    # convenience mirrors of the primary (first) step — keeps simple clients working
    tool: str
    arguments: dict
    result_count: int | None = None
    tool_result: dict


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "tools": list(TOOLS), "llm_enabled": llm.enabled,
            "engine": "langgraph", "tracing": trace_enabled(), "cache": cache.stats()}


@app.get("/tools")
def tools() -> dict:
    return {"tools": TOOL_SPECS}


@app.get("/cache")
def cache_stats() -> dict:
    return {"cache": cache.stats(), "llm_api_calls": llm.api_calls}


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest) -> AskResponse:
    rid = uuid.uuid4().hex[:8]
    logger.info("[%s] question=%r", rid, req.question)

    with trace_request(rid, req.question) as span:
        final = graph.invoke({"request_id": rid, "question": req.question})
        set_output(span, final.get("answer", ""))
    trace_flush()

    raw_steps = final.get("results", [])
    steps = [
        Step(tool=s["tool"], arguments=s["arguments"],
             result_count=(s["result"] or {}).get("result_count"), result=s["result"])
        for s in raw_steps
    ]
    primary = steps[0] if steps else Step(tool="none", arguments={}, result={})
    return AskResponse(
        request_id=rid, question=req.question, answer=final.get("answer", ""),
        steps=steps,
        tool=primary.tool, arguments=primary.arguments,
        result_count=primary.result_count, tool_result=primary.result,
    )
