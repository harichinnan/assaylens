"""Temporal worker — hosts the AssayLens pipeline workflow + activities.

Long-running service: connects to the Temporal dev server, polls the
`assaylens-pipeline` task queue, and executes workflow + activity tasks. Start
it (via docker compose), then trigger a run with orchestration/starter.py or the
`temporal` CLI.
"""
from __future__ import annotations

import asyncio
import logging
import os

from temporalio.client import Client
from temporalio.worker import Worker

from orchestration.activities import (
    build_graph,
    build_index,
    dbt_build,
    ingest_bronze,
    publish_marts,
)
from orchestration.workflows import AssayLensPipeline, GraphBuildWorkflow, IndexWorkflow

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s worker %(message)s")
TASK_QUEUE = "assaylens-pipeline"


async def main() -> None:
    address = os.getenv("TEMPORAL_ADDRESS", "temporal:7233")
    namespace = os.getenv("TEMPORAL_NAMESPACE", "default")

    # The dev server may take a moment to accept connections on first boot.
    client = None
    for attempt in range(30):
        try:
            client = await Client.connect(address, namespace=namespace)
            break
        except Exception as exc:  # noqa: BLE001
            logging.info("waiting for Temporal at %s (%s)", address, exc)
            await asyncio.sleep(2)
    if client is None:
        raise SystemExit(f"could not connect to Temporal at {address}")

    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[AssayLensPipeline, GraphBuildWorkflow, IndexWorkflow],
        activities=[ingest_bronze, dbt_build, build_graph, publish_marts, build_index],
    )
    logging.info("worker polling task queue %r at %s", TASK_QUEUE, address)
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
