"""Optional Langfuse v3 tracing for the agent.

Centralizes all observability so the rest of the code stays clean. Everything
here is defensive: if Langfuse is unconfigured (no keys) or unreachable, every
helper degrades to a no-op context manager and the agent runs exactly as before.

Trace shape per /ask request:
    span "ask" (root, carries request_id + question/answer)
      ├─ generation "llm:plan"        (Anthropic call, with token usage)
      ├─ span       "tool:<name>" ...  (one per executed tool)
      └─ generation "llm:summarize"
"""
from __future__ import annotations

import contextlib
import logging
import os

logger = logging.getLogger("assaylens.agent")

_client = None
try:
    if os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"):
        from langfuse import get_client

        _client = get_client()  # reads LANGFUSE_PUBLIC_KEY/SECRET_KEY/HOST from env
        logger.info("[trace] Langfuse tracing enabled (host=%s)", os.getenv("LANGFUSE_HOST"))
except Exception as exc:  # pragma: no cover - optional dependency
    logger.warning("[trace] Langfuse unavailable, tracing disabled: %s", exc)
    _client = None


def enabled() -> bool:
    return _client is not None


@contextlib.contextmanager
def trace_request(request_id: str, question: str):
    """Root span for one /ask request; yields the span (or None if disabled)."""
    if not enabled():
        yield None
        return
    try:
        with _client.start_as_current_span(name="ask", input={"question": question}) as span:
            try:
                _client.update_current_trace(
                    name="ask",
                    input={"question": question},
                    metadata={"request_id": request_id},
                    tags=["assaylens-agent"],
                )
            except Exception:  # pragma: no cover
                pass
            yield span
    except Exception as exc:  # pragma: no cover
        logger.warning("[trace] request span failed: %s", exc)
        yield None


@contextlib.contextmanager
def observe_generation(name: str, model: str, system: str, user: str):
    """LLM-call generation observation; yields the generation (or None)."""
    if not enabled():
        yield None
        return
    try:
        with _client.start_as_current_generation(
            name=name, model=model, input={"system": system, "user": user}
        ) as gen:
            yield gen
    except Exception as exc:  # pragma: no cover
        logger.warning("[trace] generation failed: %s", exc)
        yield None


@contextlib.contextmanager
def observe_tool(name: str, arguments: dict):
    """Span around a single tool execution; yields the span (or None)."""
    if not enabled():
        yield None
        return
    try:
        with _client.start_as_current_span(name=f"tool:{name}", input=arguments) as span:
            yield span
    except Exception as exc:  # pragma: no cover
        logger.warning("[trace] tool span failed: %s", exc)
        yield None


def record_generation(gen, output: str, usage_in: int | None = None, usage_out: int | None = None) -> None:
    if gen is None:
        return
    try:
        kwargs = {"output": output}
        if usage_in is not None or usage_out is not None:
            kwargs["usage_details"] = {"input": usage_in or 0, "output": usage_out or 0}
        gen.update(**kwargs)
    except Exception:  # pragma: no cover
        pass


def set_output(span, output) -> None:
    if span is None:
        return
    try:
        span.update(output=output)
    except Exception:  # pragma: no cover
        pass


def flush() -> None:
    if enabled():
        try:
            _client.flush()
        except Exception:  # pragma: no cover
            pass
