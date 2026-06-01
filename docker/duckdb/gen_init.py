#!/usr/bin/env python3
"""Generate a DuckDB init script with a view over every table in the Iceberg
lakehouse, reading each table's CURRENT metadata pointer from the Iceberg JDBC
catalog (Postgres `iceberg_catalog`). Re-run every launch so the views always
point at the latest snapshot — no stale metadata paths.

Views are named `<namespace>_<table>` (e.g. gold_mart_target_activity_summary),
and read straight from MinIO via DuckDB's httpfs + iceberg extensions.
"""
import os

import psycopg

OUT = os.getenv("DUCKDB_INIT", "/tmp/lakehouse.sql")
CAT_HOST = os.getenv("ICEBERG_CATALOG_HOST", "host.docker.internal")
CAT_USER = os.getenv("ICEBERG_CATALOG_USER", "assaylens")
CAT_PW = os.getenv("ICEBERG_CATALOG_PASSWORD", "assaylens")
S3_ENDPOINT = os.getenv("S3_ENDPOINT", "host.docker.internal:9000")
S3_AK = os.getenv("S3_ACCESS_KEY", "minioadmin")
S3_SK = os.getenv("S3_SECRET_KEY", "minioadmin")


def main() -> None:
    conn = psycopg.connect(
        f"host={CAT_HOST} port=5432 dbname=iceberg_catalog user={CAT_USER} password={CAT_PW}"
    )
    rows = conn.execute(
        "select table_namespace, table_name, metadata_location "
        "from iceberg_tables order by table_namespace, table_name"
    ).fetchall()
    conn.close()

    lines = [
        "-- AssayLens lakehouse — auto-generated DuckDB init (views over MinIO Iceberg).",
        "INSTALL httpfs; LOAD httpfs;",
        "INSTALL iceberg; LOAD iceberg;",
        f"CREATE OR REPLACE SECRET minio (TYPE S3, KEY_ID '{S3_AK}', SECRET '{S3_SK}', "
        f"ENDPOINT '{S3_ENDPOINT}', URL_STYLE 'path', USE_SSL false, REGION 'us-east-1');",
    ]
    for ns, tbl, loc in rows:
        view = f"{ns}_{tbl}"
        # Scan the exact metadata.json from the catalog (no allow_moved_paths —
        # that option is rejected for direct metadata-file scans).
        lines.append(
            f"CREATE OR REPLACE VIEW {view} AS SELECT * FROM iceberg_scan('{loc}');"
        )
    lines.append(".mode duckbox")
    lines.append(
        f".print '\\nAssayLens lakehouse ready: {len(rows)} Iceberg tables as views "
        f"(bronze_* / silver_* / gold_*).'"
    )
    lines.append(".print \"Try:  SELECT target_name, curated_measurements, median_potency_nm "
                 "FROM gold_mart_target_activity_summary ORDER BY 2 DESC;\\n\"")

    with open(OUT, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"[duckdb] wrote {OUT}: {len(rows)} views over s3://...@{S3_ENDPOINT}")


if __name__ == "__main__":
    main()
