"""Temporal workflow: the AssayLens medallion lakehouse pipeline.

A durable, observable orchestration of the medallion stages:

    ingest_bronze  ->  dbt_build  ->  (build_graph -> publish_marts -> build_index)

Each stage is a Temporal activity with its own timeout + retry policy, so a
transient failure (e.g. a flaky DB/Spark connection) is retried automatically
and the whole run is visible/replayable in the Temporal UI. The workflow body
stays deterministic — all side effects live in the activities.

The stage list is a run parameter, so a caller can run a single stage
(e.g. ["ingest_bronze"]) or the whole pipeline. Unknown stage names are
rejected up front for a clear failure.
"""
from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from orchestration.activities import (
        build_graph,
        build_index,
        dbt_build,
        ingest_bronze,
        publish_marts,
    )

# Full medallion pipeline: ChEMBL(JDBC) -> Iceberg bronze -> dbt silver/gold ->
# graph gold -> publish to native Postgres marts.* -> Elasticsearch index.
DEFAULT_STAGES = ["ingest_bronze", "dbt_build", "build_graph", "publish_marts", "build_index"]


def _activity_opts() -> dict:
    """Shared per-activity timeout + retry policy."""
    return dict(
        start_to_close_timeout=timedelta(minutes=30),
        heartbeat_timeout=timedelta(minutes=5),
        retry_policy=RetryPolicy(
            initial_interval=timedelta(seconds=5),
            backoff_coefficient=2.0,
            maximum_interval=timedelta(minutes=1),
            maximum_attempts=3,
        ),
    )


@workflow.defn
class AssayLensPipeline:
    @workflow.run
    async def run(self, stages: list[str] | None = None) -> dict:
        registry = {
            "ingest_bronze": ingest_bronze,
            "dbt_build": dbt_build,
            "build_graph": build_graph,
            "publish_marts": publish_marts,
            "build_index": build_index,
        }
        stages = stages or DEFAULT_STAGES
        unknown = [s for s in stages if s not in registry]
        if unknown:
            raise ValueError(f"unknown stage(s): {unknown}; known: {sorted(registry)}")

        common = _activity_opts()
        results: dict[str, list[str]] = {}
        for stage in stages:
            workflow.logger.info("AssayLens pipeline: %s", stage)
            out = await workflow.execute_activity(registry[stage], **common)
            results[stage] = out.splitlines()[-6:]  # compact tail for the summary

        return {"stages": stages, "results": results}


# --- Standalone workflows (backlog G) ---------------------------------------
# These let the graph-build and ES-indexing run / schedule independently of the
# full pipeline (e.g. re-index after a marts hotfix without re-ingesting).

@workflow.defn
class GraphBuildWorkflow:
    """Rebuild only the gold graph relationship marts (lake.gold.graph_*)."""
    @workflow.run
    async def run(self) -> dict:
        out = await workflow.execute_activity(build_graph, **_activity_opts())
        return {"workflow": "graph_build", "build_graph": out.splitlines()[-4:]}


@workflow.defn
class IndexWorkflow:
    """Rebuild only the Elasticsearch indexes (activity-evidence + knowledge)."""
    @workflow.run
    async def run(self) -> dict:
        out = await workflow.execute_activity(build_index, **_activity_opts())
        return {"workflow": "index", "build_index": out.splitlines()[-4:]}
