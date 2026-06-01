"""Trigger one AssayLens pipeline run and wait for the result.

Usage (one-off, default stages):
    docker compose run --rm pipeline-worker python -m orchestration.starter
Run specific stages (e.g. just Bronze ingestion):
    docker compose run --rm pipeline-worker python -m orchestration.starter ingest_bronze
Or via Make:     make pipeline-run            (default stages)
                 make pipeline-run STAGES="ingest_bronze"
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid

from temporalio.client import Client

from orchestration.workflows import AssayLensPipeline, GraphBuildWorkflow, IndexWorkflow

TASK_QUEUE = "assaylens-pipeline"
STANDALONE = {"graph_build": GraphBuildWorkflow, "index": IndexWorkflow}


async def main() -> None:
    address = os.getenv("TEMPORAL_ADDRESS", "temporal:7233")
    client = await Client.connect(address, namespace=os.getenv("TEMPORAL_NAMESPACE", "default"))

    argv = sys.argv[1:]

    # `--workflow graph_build|index` starts a standalone workflow (backlog G).
    if argv and argv[0] == "--workflow":
        name = argv[1] if len(argv) > 1 else ""
        wf = STANDALONE.get(name)
        if not wf:
            raise SystemExit(f"unknown --workflow '{name}'; choose: {', '.join(STANDALONE)}")
        workflow_id = f"assaylens-{name}-{uuid.uuid4().hex[:8]}"
        print(f"starting {name} workflow id={workflow_id} on {address}")
        handle = await client.start_workflow(wf.run, id=workflow_id, task_queue=TASK_QUEUE)
        print(f"started; watch it at http://localhost:8233 (workflow {workflow_id})")
        print("PIPELINE RESULT:")
        print(json.dumps(await handle.result(), indent=2))
        return

    # Otherwise: the full pipeline, with optional stage subset.
    raw = argv or ([os.environ["STAGES"]] if os.getenv("STAGES") else [])
    stages = [s for chunk in raw for s in chunk.replace(",", " ").split()] or None

    workflow_id = f"assaylens-pipeline-{uuid.uuid4().hex[:8]}"
    print(f"starting workflow id={workflow_id} stages={stages or 'default'} on {address}")
    handle = await client.start_workflow(
        AssayLensPipeline.run,
        args=[stages],
        id=workflow_id,
        task_queue=TASK_QUEUE,
    )
    print(f"started; watch it at http://localhost:8233 (workflow {workflow_id})")
    result = await handle.result()
    print("PIPELINE RESULT:")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
