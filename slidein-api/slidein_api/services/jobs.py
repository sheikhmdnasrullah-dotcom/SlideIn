"""Database-backed durable execution for setup and canonical autopilot work.

PostgreSQL/SQLite is the system of record. Celery + Redis only dispatch job
IDs; losing or duplicating a broker message must not lose or duplicate the
business operation. Workers claim leases and every state transition is an
atomic, tenant-scoped database update.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, exists, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..errors import ConfigError, NotFoundError, ValidationError
from ..ids import new_id
from ..models import (
    AutopilotState,
    BusinessProfile,
    IcpDefinition,
    Tenant,
    WorkJob,
    utcnow,
)
from .config import ConfigService

logger = logging.getLogger("slidein.jobs")

READY_STATES = ("queued", "retrying")
ACTIVE_STATES = ("queued", "running", "retrying")
JOB_KINDS = ("setup", "autopilot", "operation")


def execution_mode() -> str:
    mode = os.getenv("SLIDEIN_EXECUTION_MODE", "inline").strip().lower()
    if mode not in {"inline", "celery"}:
        raise ConfigError(
            "SLIDEIN_EXECUTION_MODE must be 'inline' or 'celery'",
            code="worker_configuration",
            recovery_action="check_worker_configuration",
        )
    return mode


def broker_url() -> str:
    return (
        os.getenv("SLIDEIN_CELERY_BROKER_URL")
        or os.getenv("REDIS_URL")
        or "redis://127.0.0.1:6379/0"
    ).strip()


def _positive_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        return default


def lease_seconds() -> int:
    return _positive_env("SLIDEIN_JOB_LEASE_SECONDS", 900)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def job_dict(row: WorkJob) -> dict[str, Any]:
    return {
        "id": row.id,
        "tenant_id": row.tenant_id,
        "kind": row.kind,
        "idempotency_key": row.idempotency_key,
        "state": row.state,
        "payload": dict(row.payload or {}),
        "result": dict(row.result or {}),
        "attempts": row.attempts,
        "max_attempts": row.max_attempts,
        "run_at": _iso(row.run_at),
        "leased_by": row.leased_by,
        "lease_expires_at": _iso(row.lease_expires_at),
        "dispatched_at": _iso(row.dispatched_at),
        "broker_task_id": row.broker_task_id,
        "error_code": row.error_code,
        "error": row.error,
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
        "completed_at": _iso(row.completed_at),
    }


def public_job_dict(job: dict) -> dict:
    """Operational metadata only; source payloads never leave the worker API."""
    return {
        key: value
        for key, value in job.items()
        if key not in {"payload", "leased_by", "broker_task_id"}
    }


class JobService:
    def __init__(self, session: AsyncSession, *, backoff_base: int | None = None) -> None:
        self.session = session
        self.backoff_base = backoff_base or _positive_env("SLIDEIN_JOB_BACKOFF_SECONDS", 30)

    async def enqueue(
        self,
        *,
        tenant_id: str,
        kind: str,
        idempotency_key: str,
        payload: dict | None = None,
        max_attempts: int = 3,
        run_at: datetime | None = None,
    ) -> dict:
        if kind not in JOB_KINDS:
            raise ValidationError(
                f"Unsupported background job kind {kind!r}",
                code="job_invalid",
                recovery_action="check_job_request",
            )
        if not idempotency_key.strip():
            raise ValidationError(
                "A background job requires an idempotency key",
                code="job_invalid",
                recovery_action="check_job_request",
            )
        await ConfigService(self.session).ensure_tenant(tenant_id)

        existing = await self._by_key(idempotency_key)
        if existing is not None:
            return job_dict(existing)
        if kind == "autopilot":
            active = await self._active_autopilot(tenant_id)
            if active is not None:
                return job_dict(active)

        row = WorkJob(
            id=new_id("work_job"),
            tenant_id=tenant_id,
            kind=kind,
            idempotency_key=idempotency_key,
            payload=payload or {},
            max_attempts=max(1, min(10, int(max_attempts))),
            run_at=run_at or utcnow(),
        )
        self.session.add(row)
        try:
            # A nested transaction lets a concurrent duplicate enqueue return
            # the canonical row without rolling back unrelated caller work.
            async with self.session.begin_nested():
                await self.session.flush()
        except IntegrityError:
            row = await self._by_key(idempotency_key)
            if row is None:
                raise
        return job_dict(row)

    async def get(self, tenant_id: str, job_id: str) -> dict:
        row = await self.session.get(WorkJob, job_id)
        if row is None or row.tenant_id != tenant_id:
            raise NotFoundError(
                "Background job not found",
                code="not_found",
                recovery_action="check_job_id",
            )
        return job_dict(row)

    async def claim(self, job_id: str, *, worker_id: str, lease: int | None = None) -> dict:
        row = await self.session.get(WorkJob, job_id)
        if row is None:
            return {"status": "not_found"}
        if row.state in {"complete", "cancelled", "dead_letter"}:
            return {"status": row.state, "job": job_dict(row)}

        # PostgreSQL serializes claims for jobs belonging to one tenant. The
        # active-job check then prevents two scheduler windows from advancing
        # the same prospect or sending pipeline concurrently.
        await self.session.execute(
            select(Tenant.id).where(Tenant.id == row.tenant_id).with_for_update()
        )
        other_active = (
            await self.session.execute(
                select(WorkJob.id).where(
                    WorkJob.tenant_id == row.tenant_id,
                    WorkJob.id != job_id,
                    WorkJob.state == "running",
                    WorkJob.lease_expires_at > utcnow(),
                )
            )
        ).first()
        if other_active:
            return {"status": "busy", "job": job_dict(row)}

        now = utcnow()
        duration = lease or lease_seconds()
        result = await self.session.execute(
            update(WorkJob).execution_options(synchronize_session=False)
            .where(
                WorkJob.id == job_id,
                WorkJob.run_at <= now,
                or_(
                    WorkJob.state.in_(READY_STATES),
                    and_(
                        WorkJob.state == "running",
                        WorkJob.lease_expires_at <= now,
                    ),
                ),
            )
            .values(
                state="running",
                attempts=WorkJob.attempts + 1,
                leased_by=worker_id,
                lease_expires_at=now + timedelta(seconds=duration),
                dispatched_at=now,
                completed_at=None,
                error_code="",
                error="",
            )
        )
        if result.rowcount != 1:
            await self.session.refresh(row)
            return {"status": row.state, "job": job_dict(row)}
        await self.session.refresh(row)
        return {"status": "claimed", "job": job_dict(row)}

    async def defer(self, job_id: str, *, delay_seconds: int = 5) -> None:
        await self.session.execute(
            update(WorkJob).execution_options(synchronize_session=False)
            .where(WorkJob.id == job_id, WorkJob.state.in_(READY_STATES))
            .values(
                run_at=utcnow() + timedelta(seconds=max(1, delay_seconds)),
                dispatched_at=None,
                broker_task_id="",
            )
        )

    async def heartbeat(self, job_id: str, *, worker_id: str, lease: int | None = None) -> bool:
        """Extend only the live worker's lease; stale workers cannot renew."""
        result = await self.session.execute(
            update(WorkJob).execution_options(synchronize_session=False)
            .where(
                WorkJob.id == job_id,
                WorkJob.state == "running",
                WorkJob.leased_by == worker_id,
            )
            .values(lease_expires_at=utcnow() + timedelta(seconds=lease or lease_seconds()))
        )
        return result.rowcount == 1

    async def record_result(self, job_id: str, *, result: dict) -> None:
        """Persist an execution result on a non-complete job so the outcome
        (including metered partial results) stays inspectable after a
        failure transition."""
        await self.session.execute(
            update(WorkJob)
            .where(WorkJob.id == job_id)
            .values(result=result)
        )

    async def complete(self, job_id: str, *, worker_id: str, result: dict) -> dict:
        now = utcnow()
        updated = await self.session.execute(
            update(WorkJob).execution_options(synchronize_session=False)
            .where(
                WorkJob.id == job_id,
                WorkJob.state == "running",
                WorkJob.leased_by == worker_id,
            )
            .values(
                state="complete",
                result=result,
                leased_by="",
                lease_expires_at=None,
                completed_at=now,
                error_code="",
                error="",
            )
        )
        if updated.rowcount != 1:
            logger.warning("ignored stale completion for job %s from %s", job_id, worker_id)
        row = await self.session.get(WorkJob, job_id)
        return job_dict(row)

    async def fail(
        self,
        job_id: str,
        *,
        worker_id: str,
        code: str,
        message: str,
        retryable: bool,
    ) -> dict:
        row = await self.session.get(WorkJob, job_id)
        if row is None or row.state != "running" or row.leased_by != worker_id:
            return job_dict(row)
        retry = retryable and row.attempts < row.max_attempts
        delay = min(900, self.backoff_base * (2 ** max(0, row.attempts - 1)))
        await self.session.execute(
            update(WorkJob).execution_options(synchronize_session=False)
            .where(
                WorkJob.id == job_id,
                WorkJob.state == "running",
                WorkJob.leased_by == worker_id,
            )
            .values(
                state="retrying" if retry else "dead_letter",
                run_at=utcnow() + timedelta(seconds=delay) if retry else row.run_at,
                leased_by="",
                lease_expires_at=None,
                dispatched_at=None,
                broker_task_id="",
                completed_at=None if retry else utcnow(),
                error_code=code[:64],
                error=message[:2000],
            )
        )
        await self.session.refresh(row)
        return job_dict(row)

    async def recover_expired(self, *, now: datetime | None = None) -> dict[str, int]:
        moment = now or utcnow()
        expired = (
            WorkJob.state == "running"
        ) & (WorkJob.lease_expires_at.is_not(None)) & (WorkJob.lease_expires_at <= moment)
        requeued = await self.session.execute(
            update(WorkJob).execution_options(synchronize_session=False)
            .where(expired, WorkJob.attempts < WorkJob.max_attempts)
            .values(
                state="queued",
                run_at=moment,
                leased_by="",
                lease_expires_at=None,
                dispatched_at=None,
                broker_task_id="",
                error_code="worker_lease_expired",
                error="Worker lease expired; the job was recovered for another worker",
            )
        )
        dead = await self.session.execute(
            update(WorkJob).execution_options(synchronize_session=False)
            .where(expired, WorkJob.attempts >= WorkJob.max_attempts)
            .values(
                state="dead_letter",
                leased_by="",
                lease_expires_at=None,
                dispatched_at=None,
                broker_task_id="",
                completed_at=moment,
                error_code="worker_lease_expired",
                error="Worker lease expired after the final attempt; review required",
            )
        )
        return {"requeued": requeued.rowcount or 0, "dead_letter": dead.rowcount or 0}

    async def cancel(self, tenant_id: str, job_id: str) -> dict:
        await self.get(tenant_id, job_id)
        await self.session.execute(
            update(WorkJob).execution_options(synchronize_session=False)
            .where(
                WorkJob.id == job_id,
                WorkJob.tenant_id == tenant_id,
                WorkJob.state.in_(READY_STATES),
            )
            .values(
                state="cancelled",
                dispatched_at=None,
                broker_task_id="",
                completed_at=utcnow(),
                error_code="cancelled",
                error="Cancelled before execution",
            )
        )
        return await self.get(tenant_id, job_id)

    async def cancel_pending_autopilot(self, tenant_id: str) -> int:
        result = await self.session.execute(
            update(WorkJob).execution_options(synchronize_session=False)
            .where(
                WorkJob.tenant_id == tenant_id,
                WorkJob.kind == "autopilot",
                WorkJob.state.in_(READY_STATES),
            )
            .values(
                state="cancelled",
                dispatched_at=None,
                broker_task_id="",
                completed_at=utcnow(),
                error_code="tenant_paused",
                error="Autopilot paused before execution",
            )
        )
        return result.rowcount or 0

    async def retry(self, tenant_id: str, job_id: str) -> dict:
        await self.get(tenant_id, job_id)
        await self.session.execute(
            update(WorkJob).execution_options(synchronize_session=False)
            .where(
                WorkJob.id == job_id,
                WorkJob.tenant_id == tenant_id,
                WorkJob.state.in_(("dead_letter", "cancelled")),
            )
            .values(
                state="queued",
                attempts=0,
                run_at=utcnow(),
                result={},
                dispatched_at=None,
                broker_task_id="",
                completed_at=None,
                error_code="",
                error="",
            )
        )
        return await self.get(tenant_id, job_id)

    async def due_ids(self, *, limit: int = 100) -> list[str]:
        rows = (
            await self.session.execute(
                select(WorkJob.id)
                .where(
                    WorkJob.state.in_(READY_STATES),
                    WorkJob.run_at <= utcnow(),
                    WorkJob.dispatched_at.is_(None),
                )
                .order_by(WorkJob.run_at, WorkJob.created_at)
                .limit(limit)
            )
        ).scalars().all()
        return list(rows)

    async def mark_dispatched(self, job_id: str) -> bool:
        result = await self.session.execute(
            update(WorkJob).execution_options(synchronize_session=False)
            .where(
                WorkJob.id == job_id,
                WorkJob.state.in_(READY_STATES),
                WorkJob.dispatched_at.is_(None),
                WorkJob.run_at <= utcnow(),
            )
            .values(dispatched_at=utcnow())
        )
        return result.rowcount == 1

    async def record_dispatch(self, job_id: str, *, broker_task_id: str = "") -> None:
        await self.session.execute(
            update(WorkJob).execution_options(synchronize_session=False)
            .where(WorkJob.id == job_id)
            .values(
                dispatched_at=utcnow() if broker_task_id else None,
                broker_task_id=broker_task_id,
            )
        )

    async def schedule_due_tenants(self, *, interval_seconds: int, now: datetime | None = None) -> list[dict]:
        """Enqueue one active autopilot job per ready tenant, at most.

        Business readiness comes from canonical active profile + ICP records;
        sending remains independently gated inside the existing autopilot.
        """
        moment = now or utcnow()
        profile_ready = exists(
            select(BusinessProfile.id).where(
                BusinessProfile.tenant_id == Tenant.id,
                BusinessProfile.is_active.is_(True),
            )
        )
        icp_ready = exists(
            select(IcpDefinition.id).where(
                IcpDefinition.tenant_id == Tenant.id,
                IcpDefinition.is_active.is_(True),
            )
        )
        tenant_ids = list(
            (
                await self.session.execute(
                    select(Tenant.id)
                    .join(AutopilotState, AutopilotState.tenant_id == Tenant.id)
                    .where(
                        Tenant.is_active.is_(True),
                        profile_ready,
                        icp_ready,
                        AutopilotState.enabled.is_(True),
                    )
                    .order_by(Tenant.id)
                )
            ).scalars().all()
        )
        window = int(moment.timestamp()) // max(1, interval_seconds)
        jobs = []
        for tenant_id in tenant_ids:
            jobs.append(
                await self.enqueue(
                    tenant_id=tenant_id,
                    kind="autopilot",
                    idempotency_key=f"autopilot:{tenant_id}:{window}",
                    payload={},
                )
            )
        return jobs

    async def _by_key(self, key: str) -> WorkJob | None:
        return (
            await self.session.execute(select(WorkJob).where(WorkJob.idempotency_key == key))
        ).scalars().first()

    async def _active_autopilot(self, tenant_id: str) -> WorkJob | None:
        return (
            await self.session.execute(
                select(WorkJob)
                .where(
                    WorkJob.tenant_id == tenant_id,
                    WorkJob.kind == "autopilot",
                    WorkJob.state.in_(ACTIVE_STATES),
                )
                .order_by(WorkJob.created_at)
                .limit(1)
            )
        ).scalars().first()


__all__ = [
    "ACTIVE_STATES",
    "JobService",
    "READY_STATES",
    "broker_url",
    "execution_mode",
    "job_dict",
    "lease_seconds",
]
