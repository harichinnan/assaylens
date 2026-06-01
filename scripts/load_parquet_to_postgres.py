#!/usr/bin/env python3
"""Load the Parquet lake into the Postgres `raw` schema.

This is the bridge between Spark ingestion and dbt modeling: it reads each
entity's Parquet directory and (re)creates the matching `raw.raw_chembl_<entity>`
table, then bulk-loads rows. It is idempotent — each run fully replaces the raw
tables, so the warehouse always reflects the latest lake snapshot.

Design choices:
  * Explicit DDL per entity (not inferred) so the raw contract is visible and
    stable regardless of Parquet quirks. dbt's sources.yml mirrors these.
  * COPY via psycopg for fast bulk load.
  * No DuckDB — pyarrow reads Parquet directly.

Usage:
    python scripts/load_parquet_to_postgres.py --lake data/lake
"""
from __future__ import annotations

import argparse
import io
import os
import sys
from pathlib import Path

import pyarrow.parquet as pq
import psycopg

# Entity -> (raw table name, ordered list of (column, postgres type)).
# Column order matches the Scala case classes / Parquet schema.
SCHEMA: dict[str, tuple[str, list[tuple[str, str]]]] = {
    "activity": (
        "raw_chembl_activity",
        [
            ("activity_id", "BIGINT"),
            ("molecule_chembl_id", "TEXT"),
            ("target_chembl_id", "TEXT"),
            ("assay_chembl_id", "TEXT"),
            ("document_chembl_id", "TEXT"),
            ("standard_type", "TEXT"),
            ("standard_relation", "TEXT"),
            ("standard_value", "DOUBLE PRECISION"),
            ("standard_units", "TEXT"),
            ("standard_value_nm", "DOUBLE PRECISION"),
            ("units_note", "TEXT"),
            ("pchembl_value", "DOUBLE PRECISION"),
            ("activity_comment", "TEXT"),
            ("data_validity_comment", "TEXT"),
        ],
    ),
    "molecule": (
        "raw_chembl_molecule",
        [
            ("molecule_chembl_id", "TEXT"),
            ("pref_name", "TEXT"),
            ("canonical_smiles", "TEXT"),
            ("molecular_weight", "DOUBLE PRECISION"),
            ("alogp", "DOUBLE PRECISION"),
            ("hba", "INTEGER"),
            ("hbd", "INTEGER"),
            ("ro5_violations", "INTEGER"),
        ],
    ),
    "target": (
        "raw_chembl_target",
        [
            ("target_chembl_id", "TEXT"),
            ("target_name", "TEXT"),
            ("organism", "TEXT"),
            ("target_type", "TEXT"),
        ],
    ),
    "assay": (
        "raw_chembl_assay",
        [
            ("assay_chembl_id", "TEXT"),
            ("assay_type", "TEXT"),
            ("assay_description", "TEXT"),
            ("confidence_score", "INTEGER"),
            ("target_chembl_id", "TEXT"),
        ],
    ),
    "document": (
        "raw_chembl_document",
        [
            ("document_chembl_id", "TEXT"),
            ("pubmed_id", "INTEGER"),
            ("journal", "TEXT"),
            ("year", "INTEGER"),
        ],
    ),
}


def dsn() -> str:
    return (
        f"host={os.getenv('POSTGRES_HOST', 'localhost')} "
        f"port={os.getenv('POSTGRES_PORT', '5432')} "
        f"dbname={os.getenv('POSTGRES_DB', 'assaylens')} "
        f"user={os.getenv('POSTGRES_USER', 'assaylens')} "
        f"password={os.getenv('POSTGRES_PASSWORD', 'assaylens')}"
    )


def read_parquet_dir(path: Path) -> "pq.lib.Table | None":
    """Read a Spark Parquet output dir (a folder of part files)."""
    if not path.exists():
        return None
    if path.is_file():
        return pq.read_table(path)
    parts = sorted(path.glob("*.parquet"))
    if not parts:
        return None
    return pq.read_table(path)  # pyarrow reads a dataset directory directly


def load_entity(conn: "psycopg.Connection", entity: str, lake: Path) -> int:
    table, columns = SCHEMA[entity]
    col_names = [c for c, _ in columns]

    tbl = read_parquet_dir(lake / entity)
    if tbl is None:
        print(f"  [skip] no parquet for '{entity}' at {lake / entity}")
        return 0

    # Reorder/select to the declared contract; missing cols -> error early.
    missing = set(col_names) - set(tbl.column_names)
    if missing:
        raise SystemExit(f"[{entity}] parquet missing columns: {sorted(missing)}")
    tbl = tbl.select(col_names)

    ddl_cols = ",\n  ".join(f'"{c}" {t}' for c, t in columns)
    with conn.cursor() as cur:
        cur.execute(f"DROP TABLE IF EXISTS raw.{table} CASCADE;")
        cur.execute(f"CREATE TABLE raw.{table} (\n  {ddl_cols}\n);")

        # Stream rows through COPY. Text format (the default) is what
        # psycopg's write_row emits — it encodes Nones as \N automatically.
        copy_sql = f"COPY raw.{table} ({', '.join(col_names)}) FROM STDIN"
        with cur.copy(copy_sql) as cp:
            for batch in tbl.to_batches():
                rows = batch.to_pylist()
                for r in rows:
                    cp.write_row([r[c] for c in col_names])

    n = tbl.num_rows
    print(f"  [ok]   raw.{table}: {n} rows")
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description="Load Parquet lake into Postgres raw schema.")
    ap.add_argument("--lake", default="data/lake", help="Path to the Parquet lake root.")
    ap.add_argument(
        "--entities", nargs="*", default=list(SCHEMA), help="Subset of entities to load."
    )
    args = ap.parse_args()

    lake = Path(args.lake)
    print(f"Loading lake '{lake}' -> Postgres raw schema")
    with psycopg.connect(dsn()) as conn:
        with conn.cursor() as cur:
            cur.execute("CREATE SCHEMA IF NOT EXISTS raw;")
        total = sum(load_entity(conn, e, lake) for e in args.entities)
        conn.commit()
    print(f"Done. {total} total rows loaded.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
