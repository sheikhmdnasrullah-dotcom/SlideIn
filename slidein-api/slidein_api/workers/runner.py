"""Canonical job execution shared by Celery and the legacy inline slice."""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import suppress

from ..db import session_scope
from ..services.autopilot import AutopilotConfig, tick as autopilot_tick
from ..services.jobs import JobService, execution_mode, lease_seconds
from ..setup.service import SetupService

logger = logging.getLogger("slidein.workers.runner")


class JobFailure(Exception):
    def __init__(self, message: str, *, code: str, retryable: bool) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


async def _execute_payload(job: dict) -> dict:
    tenant_id = job["tenant_id"]
    payload = job.get("payload") or {}
    if job["kind"] == "setup":
        async with session_scope() as session:
            run = await SetupService(session).execute(
                tenant_id,
                str(payload["run_id"]),
                list(payload.get("sources") or []),
                actor=str(payload.get("actor") or "service:setup"),
            )
        if run.get("state") != "complete":
            raise JobFailure(
                str(run.get("error") or "Setup generation failed"),
                code=str(run.get("error_code") or "setup_failed"),
                retryable=bool(run.get("retryable")),
            )
        return {"setup_run_id": run["id"], "state": "complete"}
    if job["kind"] == "autopilot":
        outcome = await autopilot_tick(tenant_id, AutopilotConfig.from_env())
        if outcome.get("status") == "failed":
            raise JobFailure(
                str(outcome.get("error") or "Autopilot tick failed"),
                code=str(outcome.get("error") or "autopilot_failed")[:64],
                retryable=True,
            )
        return {"tick": outcome}
    if job["kind"] == "operation":
        from ..billing.execution import execute_operation_job

        result = await execute_operation_job(job)
        if result.get("status") not in ("complete", "partial"):
            async with session_scope() as session:
                await JobService(session).record_result(job_id=job["id"], result=result)
            retryable = bool(
                result.get("failures") and result["failures"][-1].get("retryable")
            )
            raise JobFailure(
                str(result.get("crash") or "Operation produced no accepted output"),
                code="operation_failed",
                retryable=retryable,
            )
        return {**result, "state": result["status"]}
    raise JobFailure("Unsupported job kind", code="job_invalid", retryable=False)


async def _enqueue_post_setup(job: dict, result: dict) -> dict:
    run_id = str(result["setup_run_id"])
    async with session_scope() as session:
        followup = await JobService(session).enqueue(
            tenant_id=job["tenant_id"],
            kind="autopilot",
            idempotency_key=f"autopilot:setup:{run_id}",
            payload={},
        )
    return followup


async def _heartbeat(job_id: str, *, worker_id: str) -> None:
    """Keep long-running work leased without allowing stale workers to renew it."""
    while True:
        await asyncio.sleep(max(1, lease_seconds() // 3))
        try:
            async with session_scope() as session:
                renewed = await JobService(session).heartbeat(job_id, worker_id=worker_id)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — a later scheduler can recover the lease
            logger.exception("Could not renew lease for background job %s", job_id)
            return
        if not renewed:
            logger.warning("Stopped renewing lost lease for background job %s", job_id)
            return


async def _stop_heartbeat(task: asyncio.Task[None]) -> None:
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


async def execute_job(job_id: str, *, worker_id: str | None = None) -> dict:
    """Claim and execute one persisted job; safe under duplicate delivery."""
    worker = worker_id or f"worker:{os.getpid()}"
    async with session_scope() as session:
        service = JobService(session)
        claim = await service.claim(job_id, worker_id=worker)
        if claim["status"] == "busy":
            await service.defer(job_id)
            return claim
        if claim["status"] != "claimed":
            return claim
        job = claim["job"]

    heartbeat = asyncio.create_task(_heartbeat(job_id, worker_id=worker))
    try:
        try:
            result = await _execute_payload(job)
        except JobFailure as exc:
            await _stop_heartbeat(heartbeat)
            async with session_scope() as session:
                failed = await JobService(session).fail(
                    job_id,
                    worker_id=worker,
                    code=exc.code,
                    message=str(exc),
                    retryable=exc.retryable,
                )
            return {"status": failed["state"], "job": failed}
        except Exception as exc:  # noqa: BLE001 — durable failure boundary
            await _stop_heartbeat(heartbeat)
            logger.exception("Background job %s crashed", job_id)
            async with session_scope() as session:
                failed = await JobService(session).fail(
                    job_id,
                    worker_id=worker,
                    code="worker_exception",
                    message=f"{type(exc).__name__}: background job failed",
                    retryable=True,
                )
            return {"status": failed["state"], "job": failed}

        await _stop_heartbeat(heartbeat)
        async with session_scope() as session:
            completed = await JobService(session).complete(job_id, worker_id=worker, result=result)
    finally:
        # Also stop renewal if the worker coroutine itself is cancelled.
        await _stop_heartbeat(heartbeat)

    if job["kind"] == "setup" and completed["state"] == "complete":
        followup = await _enqueue_post_setup(job, result)
        if execution_mode() == "celery":
            from .dispatch import dispatch_job

            await dispatch_job(followup["id"])
        else:
            # Preserve the original local vertical slice: onboarding starts
            # research immediately, while Celery deployments use their worker.
            await execute_job(followup["id"], worker_id=f"{worker}:followup")
    return {"status": completed["state"], "job": completed}


async def scheduler_tick() -> dict:
    """Recover orphaned work, enqueue ready tenants, and dispatch due jobs."""
    from .dispatch import dispatch_job

    async with session_scope() as session:
        recovered = await JobService(session).recover_expired()
    scheduled = 0
    cfg = AutopilotConfig.from_env()
    if cfg.master_enabled:
        async with session_scope() as session:
            jobs = await JobService(session).schedule_due_tenants(
                interval_seconds=cfg.interval_seconds
            )
        scheduled = len(jobs)
    async with session_scope() as session:
        due = await JobService(session).due_ids()
    dispatched = 0
    for job_id in due:
        if await dispatch_job(job_id):
            dispatched += 1
    return {"recovered": recovered, "ready_tenants": scheduled, "dispatched": dispatched}


__all__ = ["JobFailure", "execute_job", "scheduler_tick"]
