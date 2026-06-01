"""SQL guardrails for the agent's run_curated_sql tool.

Defense in depth. This module is the APPLICATION-level gate; beneath it sits a
DB-enforced read-only role (`agent_ro`, granted SELECT on marts only — see
postgres/init/01_schemas.sql). Both must agree before any query runs.

The validator enforces:
  * single statement only (no stacked queries)
  * must be a SELECT (or WITH ... SELECT); no DDL / DML / DCL / TCL
  * no dangerous keywords (COPY, extensions, file access, etc.)
  * table references restricted to an allow-list of curated marts
  * a mandatory LIMIT (injected if absent, capped to the configured max)

It is intentionally conservative: anything it cannot prove safe is rejected.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.config import settings


class SqlGuardrailError(ValueError):
    """Raised when a query violates the guardrails."""


# Statement types we allow. Everything else (INSERT/UPDATE/DELETE/CREATE/DROP/
# ALTER/GRANT/TRUNCATE/COPY/CALL/...) is rejected.
_ALLOWED_LEADING = ("select", "with")

# Hard-blocked tokens regardless of context. Word-boundary matched.
_FORBIDDEN_KEYWORDS = (
    "insert", "update", "delete", "merge", "upsert",
    "create", "drop", "alter", "truncate", "rename",
    "grant", "revoke",
    "commit", "rollback", "savepoint", "begin", "start",
    "copy", "vacuum", "analyze", "cluster", "reindex", "refresh",
    "call", "do", "execute", "prepare", "deallocate", "listen", "notify",
    "set", "reset", "show", "lock", "comment", "import", "load",
    "extension", "pg_read_file", "pg_ls_dir", "lo_import", "lo_export",
    "dblink", "pg_sleep",
)

# Functions / patterns that touch the filesystem or server internals.
_FORBIDDEN_PATTERNS = (
    r"pg_read_file", r"pg_read_binary_file", r"pg_ls_dir", r"pg_stat_file",
    r"lo_import", r"lo_export", r"copy\s", r"\bpg_catalog\b", r"\binformation_schema\b",
)


@dataclass
class ValidatedQuery:
    sql: str            # the (possibly LIMIT-injected) query to execute
    limit: int          # effective row limit
    referenced_tables: list[str]


def _strip_comments(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)  # block comments
    sql = re.sub(r"--[^\n]*", " ", sql)                     # line comments
    return sql


def _normalize(sql: str) -> str:
    return re.sub(r"\s+", " ", sql.strip()).strip().rstrip(";").strip()


def _split_statements(sql: str) -> list[str]:
    # Naive split on ';' is fine here because we strip comments first and reject
    # anything that yields >1 non-empty statement (no stacked queries allowed).
    return [s for s in (p.strip() for p in sql.split(";")) if s]


def _referenced_tables(sql: str) -> list[str]:
    """Extract identifiers following FROM / JOIN. Used for allow-listing."""
    found: list[str] = []
    for m in re.finditer(r"\b(?:from|join)\s+([a-zA-Z_][\w\.\"]*)", sql, flags=re.IGNORECASE):
        ident = m.group(1).replace('"', "")
        # Keep the final path component (strip schema qualifier).
        table = ident.split(".")[-1].lower()
        found.append(table)
    return found


# CTE names are local aliases, not real tables — collect them so they don't
# trip the allow-list.
def _cte_names(sql: str) -> set[str]:
    names: set[str] = set()
    for m in re.finditer(r"\b([a-zA-Z_]\w*)\s+as\s*\(", sql, flags=re.IGNORECASE):
        names.add(m.group(1).lower())
    return names


def validate_sql(raw_sql: str) -> ValidatedQuery:
    if not raw_sql or not raw_sql.strip():
        raise SqlGuardrailError("Empty query.")

    cleaned = _normalize(_strip_comments(raw_sql))
    statements = _split_statements(cleaned)
    if len(statements) != 1:
        raise SqlGuardrailError("Only a single statement is allowed (no stacked queries).")
    stmt = statements[0]
    lowered = stmt.lower()

    # 1. Must start with SELECT or WITH.
    if not lowered.startswith(_ALLOWED_LEADING):
        raise SqlGuardrailError("Only SELECT queries are permitted.")

    # 2. No forbidden keywords (word-boundary match).
    for kw in _FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{re.escape(kw)}\b", lowered):
            raise SqlGuardrailError(f"Forbidden keyword in query: '{kw}'.")

    # 3. No filesystem / catalog access patterns.
    for pat in _FORBIDDEN_PATTERNS:
        if re.search(pat, lowered):
            raise SqlGuardrailError("Query references a blocked function or schema.")

    # 4. Table allow-list: every FROM/JOIN target must be an approved mart
    #    (or a CTE alias defined in the same query).
    ctes = _cte_names(stmt)
    tables = _referenced_tables(stmt)
    allowed = {t.lower() for t in settings.allowed_marts}
    for t in tables:
        if t in ctes:
            continue
        if t not in allowed:
            raise SqlGuardrailError(
                f"Table '{t}' is not in the curated allow-list. "
                f"Use one of: {', '.join(sorted(allowed))}."
            )

    # 5. Mandatory LIMIT — inject if missing, cap to the configured max.
    limit = settings.sql_max_rows
    m = re.search(r"\blimit\s+(\d+)\b", lowered)
    if m:
        requested = int(m.group(1))
        limit = min(requested, settings.sql_max_rows)
        stmt = re.sub(r"\blimit\s+\d+\b", f"LIMIT {limit}", stmt, flags=re.IGNORECASE)
    else:
        limit = min(settings.sql_default_limit, settings.sql_max_rows)
        stmt = f"{stmt} LIMIT {limit}"

    return ValidatedQuery(sql=stmt, limit=limit, referenced_tables=tables)
