"""Tool: describe the curated warehouse (schema overview).

Answers structural / meta questions — "how many tables are there", "what
tables/columns can I query", "what's in the warehouse" — by introspecting the
live `marts` schema via information_schema (read as the agent_ro role). This is
a fixed, parameter-free query, so it stays governed without going through the
free-SQL guardrail (which intentionally blocks information_schema).
"""
from __future__ import annotations

from app.db import query

TOOL_SPEC = {
    "name": "describe_warehouse",
    "description": (
        "Overview of the curated warehouse: how many tables exist and their columns "
        "(the `marts` serving schema). Use for schema / structure / 'what tables or "
        "columns are available' / 'how many tables' questions."
    ),
    "arguments": {"table": "optional: a single table name to describe; omit for the whole schema"},
}


def run(table: str | None = None) -> dict:
    rows = query(
        """
        select table_name, column_name, data_type
        from information_schema.columns
        where table_schema = 'marts'
          and (%s::text is null or table_name = %s::text)
        order by table_name, ordinal_position
        """,
        (table, table),
    )

    tables: dict[str, list[dict]] = {}
    for r in rows:
        tables.setdefault(r["table_name"], []).append(
            {"column": r["column_name"], "type": r["data_type"]}
        )

    if table and not tables:
        return {"result_count": 0, "schema": "marts",
                "error": f"No table named '{table}' in the marts schema."}

    return {
        "result_count": len(tables),
        "schema": "marts",
        "table_count": len(tables),
        "tables": [
            {"name": name, "column_count": len(cols), "columns": cols}
            for name, cols in sorted(tables.items())
        ],
    }
