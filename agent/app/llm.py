"""LLM layer for the AssayLens copilot (Anthropic Claude Haiku).

Two jobs, both deliberately small:
  1. plan(question)       -> an ordered list of governed tool calls (1-3 steps)
  2. summarize(question, results) -> a short, faithful natural-language answer

Every API call goes through `_complete`, which is wrapped by a response cache
(see cache.py): identical (model, system, messages, max_tokens) requests return
the cached completion and cost zero tokens. If no ANTHROPIC_API_KEY is set, both
methods fall back to deterministic behavior so the service still runs offline.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from app.cache import cache
from app.config import settings
from app.tracing import observe_generation, record_generation

logger = logging.getLogger("assaylens.agent")
PROMPTS_DIR = Path(__file__).parent / "prompts"

MAX_STEPS = 3                 # bound multi-step plans
SUMMARY_ROW_CAP = 8           # rows per tool result sent to the summarizer


def _read_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text()


class LLM:
    def __init__(self) -> None:
        self._client = None
        self.api_calls = 0          # actual Anthropic calls made (cache misses)
        if settings.anthropic_api_key:
            try:
                import anthropic

                self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
            except Exception as exc:  # pragma: no cover - optional dependency
                logger.warning("[llm] Anthropic client unavailable, using fallback: %s", exc)

    @property
    def enabled(self) -> bool:
        return self._client is not None

    # ---- cached completion ------------------------------------------------
    def _complete(self, system: str, user: str, max_tokens: int, gen_name: str = "llm") -> str:
        """Single-turn completion with response caching. Returns text."""
        messages = [{"role": "user", "content": user}]
        ck = cache.key(settings.anthropic_model, system, messages, max_tokens)
        cached = cache.get(ck)
        if cached is not None:
            logger.info("[llm] cache hit")
            return cached

        with observe_generation(gen_name, settings.anthropic_model, system, user) as gen:
            msg = self._client.messages.create(
                model=settings.anthropic_model, max_tokens=max_tokens,
                system=system, messages=messages,
            )
            self.api_calls += 1
            usage = getattr(msg, "usage", None)
            if usage:
                logger.info("[llm] api call in=%s out=%s", usage.input_tokens, usage.output_tokens)
            text = "".join(b.text for b in msg.content if b.type == "text").strip()
            record_generation(
                gen, text,
                getattr(usage, "input_tokens", None),
                getattr(usage, "output_tokens", None),
            )
        cache.set(ck, text)
        return text

    # ---- 1. planning ------------------------------------------------------
    def plan(self, question: str, tool_specs: list[dict]) -> dict:
        """Return {"steps": [{"tool", "arguments"}, ...]} (1-3 governed calls)."""
        if not self.enabled:
            return _fallback_plan(question)

        system = _read_prompt("intent_router.md")
        user = json.dumps({"question": question, "tools": tool_specs})
        try:
            data = json.loads(_extract_json(self._complete(system, user, 500, gen_name="llm:plan")))
        except Exception:
            return _fallback_plan(question)

        steps = data.get("steps")
        if not steps and data.get("tool"):       # tolerate single-step shape
            steps = [{"tool": data["tool"], "arguments": data.get("arguments", {})}]
        if not steps:
            return _fallback_plan(question)
        return {"steps": steps[:MAX_STEPS]}

    # ---- 2. summarization -------------------------------------------------
    def summarize(self, question: str, results: list[dict]) -> str:
        compact = [_compact_result(r) for r in results]
        if not self.enabled:
            return _fallback_summary(compact)

        system = _read_prompt("system_prompt.md")
        user = json.dumps({"question": question, "tool_results": compact}, default=str)
        try:
            return self._complete(system, user, 600, gen_name="llm:summarize")
        except Exception as exc:
            logger.warning("[llm] summarize failed, using fallback: %s", exc)
            return _fallback_summary(compact)


# --- helpers ---------------------------------------------------------------

def _extract_json(text: str) -> str:
    start, end = text.find("{"), text.rfind("}")
    return text[start:end + 1] if start != -1 and end != -1 else "{}"


def _compact_result(step: dict) -> dict:
    """Trim a tool result before sending to the summarizer to save tokens:
    keep counts/filters/metadata, cap large row arrays, drop verbose query DSL."""
    res = dict(step.get("result", {}) or {})
    for big in ("es_query",):
        res.pop(big, None)
    for arr_key in ("results", "rows", "assay_evidence"):
        if isinstance(res.get(arr_key), list) and len(res[arr_key]) > SUMMARY_ROW_CAP:
            res[arr_key] = res[arr_key][:SUMMARY_ROW_CAP] + [
                {"_truncated": len(res[arr_key]) - SUMMARY_ROW_CAP}
            ]
    return {"tool": step.get("tool"), "arguments": step.get("arguments", {}), "result": res}


# --- deterministic fallbacks (no API key) ----------------------------------

def _fallback_plan(question: str) -> dict:
    """Keyword router. Handles the common single-tool cases and the
    'compare A and B' two-target case as a 2-step plan."""
    q = question.lower()
    targets = [t for t in ("egfr", "her2", "erbb2", "braf", "jak2", "vegfr2", "kdr") if t in q]

    if any(w in q for w in ("how many table", "what table", "which table", "schema",
                            "what columns", "what can i query", "list table")):
        return {"steps": [{"tool": "describe_warehouse", "arguments": {}}]}
    if "dashboard" in q:
        return {"steps": [{"tool": "get_metabase_dashboard",
                           "arguments": {"dashboard_name": _guess_dashboard(q),
                                         "filters": {"target": targets[0]} if targets else {}}}]}
    if "compare" in q and len(targets) >= 2:
        return {"steps": [{"tool": "get_target_summary", "arguments": {"target_name": t}}
                          for t in targets[:MAX_STEPS]]}
    if any(w in q for w in ("explain", "why", "differ", "difference")):
        if any(w in q for w in ("ic50", "ki", "kd", "ec50", "pchembl", "confidence", "relation", "validity")):
            return {"steps": [{"tool": "get_metric_definition", "arguments": {"metric_name": _guess_metric(q)}}]}
        return {"steps": [{"tool": "explain_data_quality", "arguments": {}}]}
    if "profile" in q or "smiles" in q:
        return {"steps": [{"tool": "get_compound_profile", "arguments": {}}]}
    if "summary" in q or "median" in q or ("active compound" in q and targets):
        return {"steps": [{"tool": "get_target_summary",
                           "arguments": {"target_name": targets[0] if targets else ""}}]}
    return {"steps": [{"tool": "search_assay_evidence",
                       "arguments": {"query": question, "target": targets[0] if targets else None}}]}


def _guess_dashboard(q: str) -> str:
    if "quality" in q:
        return "data_quality"
    if "compound" in q:
        return "compound_profile"
    if "target" in q or "explorer" in q:
        return "target_activity_explorer"
    return "warehouse_overview"


def _guess_metric(q: str) -> str:
    for m in ("pchembl", "ic50", "ki", "kd", "ec50", "confidence", "relation", "validity"):
        if m in q:
            return m
    return "pchembl"


def _fallback_summary(compact: list[dict]) -> str:
    parts = []
    for c in compact:
        n = (c.get("result") or {}).get("result_count")
        parts.append(f"[{c['tool']}] {n if n is not None else '?'} result(s)")
    return ("; ".join(parts) +
            " — set ANTHROPIC_API_KEY for natural-language answers.")


llm = LLM()
