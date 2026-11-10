"""Autopilot control plane — status and switches for the agent loop.

The loop itself runs in the API lifespan (services/autopilot.py); these
routes only report its state and flip the per-workspace switches. Module
gates and stage contracts are enforced inside every tick, step by step.
"""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends

from ...errors import SlideinError
from ...db import session_scope
from ...security import AuthContext, require_role, resolve_workspace
from ...services.jobs import JobService, execution_mode
from ...workers.dispatch import dispatch_job
from ...services.autopilot import (
    AutopilotConfig,
    set_switches,
    status_payload,
    tick,
)

router = APIRouter()


@router.get("/tenants/{tenant_id}/autopilot", tags=["autopilot"])
async def autopilot_status(
    tenant_id: str, auth: AuthContext = Depends(resolve_workspace)
) -> dict:
    """Loop state, per-stage pipeline counts and the last tick's stats."""
    require_role(auth, "viewer")
    return await status_payload(auth.tenant_id)


@router.post("/tenants/{tenant_id}/autopilot", tags=["autopilot"])
async def autopilot_configure(
    tenant_id: str,
    payload: dict = Body(default={}),
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    """Flip `enabled` / `auto_approve` / `send_enabled` for this workspace."""
    require_role(auth, "operator")
    updates = {
        key: payload[key]
        for key in ("enabled", "auto_approve", "send_enabled")
        if key in payload
    }
    if not updates:
        raise SlideinError(
            "Provide at least one of enabled, auto_approve, send_enabled",
            code="prospect_invalid",
            recovery_action="retry_stage",
        )
    return await set_switches(auth.tenant_id, actor=f"user:{auth.role}", **updates)


@router.post("/tenants/{tenant_id}/autopilot/run", tags=["autopilot"])
async def autopilot_run(
    tenant_id: str, auth: AuthContext = Depends(resolve_workspace)
) -> dict:
    """Advance now inline, or enqueue the identical tick in durable mode."""
    require_role(auth, "operator")
    if execution_mode() == "inline":
        outcome = await tick(auth.tenant_id, AutopilotConfig.from_env())
        return {"tick": outcome, "status": await status_payload(auth.tenant_id)}
    from ...ids import new_id
    from ...services.jobs import public_job_dict

    async with session_scope() as session:
        job = await JobService(session).enqueue(
            tenant_id=auth.tenant_id,
            kind="autopilot",
            idempotency_key=f"autopilot:manual:{new_id('work_job')}",
            payload={},
        )
    await dispatch_job(job["id"])
    return {
        "job": public_job_dict(job),
        "status": await status_payload(auth.tenant_id),
    }


@router.get("/tenants/{tenant_id}/autopilot/jobs/{job_id}", tags=["autopilot"])
async def autopilot_job(
    tenant_id: str, job_id: str, auth: AuthContext = Depends(resolve_workspace)
) -> dict:
    require_role(auth, "viewer")
    from ...services.jobs import public_job_dict

    async with session_scope() as session:
        job = await JobService(session).get(auth.tenant_id, job_id)
    return {"job": public_job_dict(job)}


@router.delete("/tenants/{tenant_id}/autopilot/jobs/{job_id}", tags=["autopilot"])
async def autopilot_cancel_job(
    tenant_id: str, job_id: str, auth: AuthContext = Depends(resolve_workspace)
) -> dict:
    require_role(auth, "operator")
    from ...services.jobs import public_job_dict

    async with session_scope() as session:
        job = await JobService(session).cancel(auth.tenant_id, job_id)
    return {"job": public_job_dict(job)}


@router.post("/tenants/{tenant_id}/autopilot/jobs/{job_id}/retry", tags=["autopilot"])
async def autopilot_retry_job(
    tenant_id: str, job_id: str, auth: AuthContext = Depends(resolve_workspace)
) -> dict:
    require_role(auth, "operator")
    from ...services.jobs import public_job_dict

    async with session_scope() as session:
        job = await JobService(session).retry(auth.tenant_id, job_id)
    await dispatch_job(job["id"])
    return {"job": public_job_dict(job)}
