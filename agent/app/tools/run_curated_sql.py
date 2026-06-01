"""Tool: run SELECT-only SQL against the curated marts.

Every query passes through validate_sql (SELECT-only, allow-listed marts,
mandatory LIMIT, no DDL/DML/file access) AND runs on the read-only,
timeout-bounded connection. The validated SQL is always returned so the user
sees exactly what executed.
"""
from __future__ import annotations

from app.db import pg_cursor
from app.guardrails.sql_guardrails import SqlGuardrailError, validate_sql

TOOL_SPEC = {
    "name": "run_curated_sql",
    "description": "Run a single read-only SELECT against curated marts (governed).",
    "arguments": {"sql": "a single SELECT/WITH statement over allowed marts"},
}


def run(sql: str) -> dict:
    try:
        validated = validate_sql(sql)
    except SqlGuardrailError as exc:
        return {"error": str(exc), "rejected": True, "submitted_sql": sql}

    with pg_cursor() as cur:
        cur.execute(validated.sql)
        rows = cur.fetchall()

    return {
        "result_count": len(rows),
        "executed_sql": validated.sql,        # transparency guardrail
        "row_limit": validated.limit,
        "referenced_tables": validated.referenced_tables,
        "results": rows,
    }
