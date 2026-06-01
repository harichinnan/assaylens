"""Central configuration for the AssayLens agent.

All knobs come from environment variables (see .env.example) so the same code
runs locally and in Docker. Governance limits (row caps, timeouts, default
LIMIT) live here and are imported by the guardrails and tools.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    # ---- Postgres (curated marts; agent uses the READ-ONLY role) ----
    pg_host: str = os.getenv("POSTGRES_HOST", "localhost")
    pg_port: str = os.getenv("POSTGRES_PORT", "5432")
    pg_db: str = os.getenv("POSTGRES_DB", "assaylens")
    # The agent connects as the least-privilege read-only role by default.
    pg_user: str = os.getenv("POSTGRES_RO_USER", "agent_ro")
    pg_password: str = os.getenv("POSTGRES_RO_PASSWORD", "agent_ro")

    # ---- Elasticsearch ----
    es_url: str = os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")
    es_index: str = os.getenv("ELASTICSEARCH_INDEX", "assaylens_activity_evidence")
    es_knowledge_index: str = os.getenv("ELASTICSEARCH_KNOWLEDGE_INDEX", "assaylens_knowledge")
    es_user: str = os.getenv("ELASTICSEARCH_USER", "")
    es_password: str = os.getenv("ELASTICSEARCH_PASSWORD", "")

    # ---- Embedding service (semantic / dense-vector retrieval) ----
    embedder_url: str = os.getenv("EMBEDDER_URL", "http://embedder:8100")

    # ---- Metabase ----
    metabase_url: str = os.getenv("METABASE_URL", "http://localhost:3000")
    # Browser-facing URL for embed iframes (the user's browser loads these,
    # so it must be the host-reachable URL, not the in-network service name).
    mb_site_url: str = os.getenv("MB_SITE_URL", "http://localhost:3000")
    mb_embedding_secret: str = os.getenv("MB_EMBEDDING_SECRET_KEY", "")
    mb_embed_ttl_seconds: int = int(os.getenv("MB_EMBED_TTL_SECONDS", "600"))

    # ---- LLM (Anthropic Claude Haiku) ----
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")

    # ---- SQL governance ----
    sql_max_rows: int = int(os.getenv("SQL_MAX_ROWS", "200"))
    sql_default_limit: int = int(os.getenv("SQL_DEFAULT_LIMIT", "100"))
    sql_statement_timeout_ms: int = int(os.getenv("SQL_STATEMENT_TIMEOUT_MS", "5000"))

    # Only these marts are reachable via run_curated_sql. Raw / staging are
    # off-limits to ad-hoc SQL and only reachable via approved lineage tools.
    allowed_marts: tuple[str, ...] = (
        "mart_compound_target_potency",
        "mart_target_activity_summary",
        "mart_assay_quality",
        "mart_compound_profile",
        "mart_data_quality_summary",
        "dim_compound",
        "dim_target",
        "dim_assay",
        "dim_document",
        # Graph relationship marts (compound<->target edges, target<->target similarity).
        "graph_compound_target_edge",
        "graph_target_similarity",
    )

    def pg_dsn(self, *, with_timeout: bool = False) -> str:
        dsn = (
            f"host={self.pg_host} port={self.pg_port} dbname={self.pg_db} "
            f"user={self.pg_user} password={self.pg_password}"
        )
        if with_timeout:
            dsn += f" options='-c statement_timeout={self.sql_statement_timeout_ms}'"
        return dsn


settings = Settings()

# Seed target name/gene -> ChEMBL id, so tools can resolve "EGFR" to CHEMBL203
# without an LLM call. Mirrors data/seeds/target_seed.csv.
TARGET_ALIASES: dict[str, str] = {
    "egfr": "CHEMBL203",
    "her2": "CHEMBL1824",
    "erbb2": "CHEMBL1824",
    "braf": "CHEMBL5145",
    "jak2": "CHEMBL2971",
    "vegfr2": "CHEMBL279",
    "kdr": "CHEMBL279",
}


def resolve_target(name_or_id: str) -> str | None:
    """Resolve a gene symbol / alias / ChEMBL id to a target_chembl_id."""
    if not name_or_id:
        return None
    s = name_or_id.strip()
    if s.upper().startswith("CHEMBL"):
        return s.upper()
    return TARGET_ALIASES.get(s.lower())
