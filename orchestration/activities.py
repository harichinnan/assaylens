"""Temporal activities — one per lakehouse pipeline stage.

Each activity is a thin, deterministic wrapper that shells out to a `run_*.sh`
script, streaming output to the Temporal logs and heartbeating so long stages
stay alive and observable. The medallion stages run Spark/dbt in their OWN
containers, which the worker launches via the mounted Docker socket
(docker-out-of-docker) — the scripts use HOST_REPO_DIR so those containers'
bind-mount paths resolve on the host daemon.

    ingest_bronze  ->  dbt_build  ->  (build_graph -> publish_marts -> build_index)

The worker image carries only the Docker CLI + a Postgres/ES client; all heavy
runtimes (Spark, Iceberg, dbt-spark) live in the per-stage job images.
"""
from __future__ import annotations

import asyncio
import os

from temporalio import activity

REPO = "/app"


async def _run(cmd: list[str], stage: str) -> str:
    """Run a command, stream + heartbeat its output, raise on non-zero exit."""
    activity.logger.info("[%s] $ %s", stage, " ".join(cmd))
    proc = await asyncio.create_subprocess_exec(
        *cmd, cwd=REPO,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        env=os.environ.copy(),
    )
    lines: list[str] = []
    assert proc.stdout is not None
    while True:
        raw = await proc.stdout.readline()
        if not raw:
            break
        line = raw.decode(errors="replace").rstrip()
        lines.append(line)
        activity.logger.info("[%s] %s", stage, line)
        activity.heartbeat(line[:160])     # keeps long stages alive + visible
    await proc.wait()
    tail = "\n".join(lines[-25:])
    if proc.returncode != 0:
        raise RuntimeError(f"[{stage}] exit={proc.returncode}\n{tail}")
    return tail


@activity.defn
async def ingest_bronze() -> str:
    """Bronze: run the Scala Spark job that reads the 5-target ChEMBL slice from
    the restored Postgres over JDBC and writes Iceberg tables lake.bronze.*
    (scripts/run_bronze.sh -> sbt container)."""
    return await _run(["bash", "scripts/run_bronze.sh"], "ingest_bronze")


@activity.defn
async def dbt_build() -> str:
    """Silver+Gold: run dbt-spark (build + tests) against the Spark Thrift Server,
    materializing lake.silver.* and lake.gold.* as Iceberg tables
    (scripts/run_dbt_spark.sh -> dbt-spark container)."""
    return await _run(["bash", "scripts/run_dbt_spark.sh", "build"], "dbt_build")


@activity.defn
async def build_graph() -> str:
    """Gold graph: derive relationship marts (compound-target edges +
    target-target similarity) from the curated potency mart, written back as
    Iceberg lake.gold.graph_* (scripts/build_graph.py -> spark-iceberg container)."""
    return await _run(["bash", "scripts/run_spark_job.sh", "build_graph.py"], "build_graph")


@activity.defn
async def publish_marts() -> str:
    """Serving: copy every lake.gold.* Iceberg table into native Postgres marts.*
    (scripts/publish_gold_to_postgres.py -> spark-iceberg container)."""
    return await _run(
        ["bash", "scripts/run_spark_job.sh", "publish_gold_to_postgres.py"], "publish_marts"
    )


@activity.defn
async def build_index() -> str:
    """Serving: (re)build BOTH Elasticsearch indexes from the published marts.* —
    the row-grained activity-evidence index and the RAG knowledge corpus (target
    summaries, assays, relationships, metric glossary)."""
    out = await _run(["python", "search/build_index.py", "--recreate"], "build_index")
    out += "\n" + await _run(["python", "search/build_knowledge_index.py", "--recreate"], "build_index")
    return out
