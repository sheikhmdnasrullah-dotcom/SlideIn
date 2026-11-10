"""Thin synchronous Celery adapters around the async canonical services."""

from __future__ import annotations

import asyncio
import threading
from typing import Awaitable, TypeVar

from celery.signals import worker_shutdown

from .celery_app import celery_app
from .runner import execute_job, scheduler_tick

_Result = TypeVar("_Result")
_local = threading.local()


def _run(awaitable: Awaitable[_Result]) -> _Result:
    """Reuse one loop per worker process; asyncpg pools are loop-bound."""
    loop = getattr(_local, "loop", None)
    if loop is None or loop.is_closed():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        _local.loop = loop
    return loop.run_until_complete(awaitable)


@worker_shutdown.connect
def _close_worker_loop(**_kwargs) -> None:
    loop = getattr(_local, "loop", None)
    if loop is not None and not loop.is_closed():
        loop.close()
    _local.loop = None


@celery_app.task(name="slidein.workers.execute_job")
def execute_job_task(job_id: str) -> dict:
    return _run(execute_job(job_id))


@celery_app.task(name="slidein.workers.scheduler_tick")
def scheduler_tick_task() -> dict:
    return _run(scheduler_tick())


__all__ = ["execute_job_task", "scheduler_tick_task"]
