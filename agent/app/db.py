"""Shared Postgres + Elasticsearch client helpers for the agent tools.

The agent always connects to Postgres as the read-only role with a statement
timeout, so even a guardrail bug cannot mutate data or run away.
"""
from __future__ import annotations

from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

from app.config import settings


@contextmanager
def pg_cursor():
    """Yield a dict-row cursor on a read-only, timeout-bounded connection."""
    with psycopg.connect(settings.pg_dsn(with_timeout=True)) as conn:
        # Belt and suspenders: also mark the transaction read-only.
        conn.read_only = True
        with conn.cursor(row_factory=dict_row) as cur:
            yield cur


def query(sql: str, params: tuple | None = None) -> list[dict]:
    with pg_cursor() as cur:
        cur.execute(sql, params or ())
        return cur.fetchall()


def es_client():
    from elasticsearch import Elasticsearch

    if settings.es_user:
        return Elasticsearch(settings.es_url, basic_auth=(settings.es_user, settings.es_password))
    return Elasticsearch(settings.es_url)
