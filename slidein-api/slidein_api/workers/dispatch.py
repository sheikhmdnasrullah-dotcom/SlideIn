"""Dispatch persisted job IDs to Celery without making Redis authoritative."""

from __future__ import annotations

import logging

from ..db import session_scope
from ..services.jobs import JobService, execution_mode

logger = logging.getLogger("slidein.workers.dispatch")


async def dispatch_job(job_id: str) -> bool:
    """Best-effort immediate dispatch; Beat redispatches any durable gap."""
    if execution_mode() != "celery":
        return False
    async with session_scope() as session:
        if not await JobService(session).mark_dispatched(job_id):
            return False
    try:
        from .celery_app import celery_app

        result = celery_app.send_task(
            "slidein.workers.execute_job", args=[job_id], queue="workflow"
        )
    except Exception:  # noqa: BLE001 — broker loss must not lose the DB job
        logger.exception("Celery dispatch failed for job %s; scheduler will retry", job_id)
        async with session_scope() as session:
            await JobService(session).record_dispatch(job_id, broker_task_id="")
        return False
    async with session_scope() as session:
        await JobService(session).record_dispatch(job_id, broker_task_id=str(result.id))
    return True


__all__ = ["dispatch_job"]
