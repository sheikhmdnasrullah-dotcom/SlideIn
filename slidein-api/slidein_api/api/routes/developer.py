"""The unified Slidein API — one key, one balance, real capabilities.

External surface:
- API key lifecycle (create/list/revoke; raw key shown once, stored hashed)
- Capability catalog with pricing and execution status
- Operation estimates and idempotent, cost-aware job submission
- Job status/results and per-job usage

Tenant isolation comes from `resolve_workspace`: the workspace in the path
must be the workspace the key belongs to, or the request 404s.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Body, Depends, Request
from sqlalchemy import select

from ...db import session_scope
from ...errors import NotFoundError, ValidationError
from ...identity import IdentityService
from ...security import AuthContext, require_role, resolve_workspace
from ...services.jobs import JobService, execution_mode, job_dict
from ...workers.runner import execute_job
from ...billing.execution import SUPPORTED_PRODUCTS, OperationService
from ...billing.ledger import LedgerService
from ...billing.models import JobUsage
from ...billing.pricebook import PriceBookService

router = APIRouter()


def _usage_dict(row: JobUsage) -> dict:
    return {
        "id": row.id,
        "job_id": row.job_id,
        "product_id": row.product_id,
        "provider": row.provider,
        "units": row.units,
        "unit_type": row.unit_type,
        "provider_cost_cents": row.provider_cost_cents,
        "cost_basis": row.cost_basis,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


# ---------------------------------------------------------------------------
# API keys
# ---------------------------------------------------------------------------


@router.get("/tenants/{tenant_id}/api-keys", tags=["api-keys"])
async def list_api_keys(
    tenant_id: str, auth: AuthContext = Depends(resolve_workspace)
) -> dict:
    require_role(auth, "operator")
    async with session_scope() as session:
        keys = await IdentityService(session).list_api_keys(auth.tenant_id)
    return {"api_keys": keys}


@router.post("/tenants/{tenant_id}/api-keys", tags=["api-keys"])
async def create_api_key(
    tenant_id: str,
    body: dict = Body(...),
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    require_role(auth, "admin")
    role = str(body.get("role") or "operator")
    label = str(body.get("label") or "")
    async with session_scope() as session:
        key_id, raw = await IdentityService(session).create_api_key(
            auth.tenant_id, role=role, label=label
        )
    return {
        "api_key": {
            "id": key_id,
            "tenant_id": auth.tenant_id,
            "label": label,
            "role": role,
            "created_at": None,
            "revoked": False,
            "last_used_at": None,
        },
        "secret": raw,  # shown exactly once; only the hash is stored
    }


@router.delete("/tenants/{tenant_id}/api-keys/{key_id}", tags=["api-keys"])
async def revoke_api_key(
    tenant_id: str, key_id: str, auth: AuthContext = Depends(resolve_workspace)
) -> dict:
    require_role(auth, "admin")
    async with session_scope() as session:
        revoked = await IdentityService(session).revoke_api_key(auth.tenant_id, key_id)
    if not revoked:
        raise NotFoundError(
            "API key not found", code="not_found", recovery_action="check_key_id"
        )
    return {"revoked": True, "id": key_id}


# ---------------------------------------------------------------------------
# Capabilities + operations
# ---------------------------------------------------------------------------


@router.get("/tenants/{tenant_id}/capabilities", tags=["operations"])
async def list_capabilities(
    tenant_id: str, auth: AuthContext = Depends(resolve_workspace)
) -> dict:
    require_role(auth, "viewer")
    async with session_scope() as session:
        catalog = await PriceBookService(session).catalog(include_restricted=True)
    for entry in catalog:
        entry["executable"] = entry["product_id"] in SUPPORTED_PRODUCTS
        if entry["status"] == "restricted":
            entry["purchasable"] = False
    return {"capabilities": catalog}


@router.post("/tenants/{tenant_id}/operations/estimate", tags=["operations"])
async def estimate_operation(
    tenant_id: str,
    body: dict = Body(...),
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    require_role(auth, "viewer")
    product_id = str(body.get("product_id") or "")
    units = int(body.get("units") or 0)
    async with session_scope() as session:
        estimate = await OperationService(session).estimate_operation(
            auth.tenant_id, product_id, units=units
        )
    return {"estimate": estimate}


@router.post("/tenants/{tenant_id}/operations", tags=["operations"])
async def submit_operation(
    tenant_id: str,
    request: Request,
    background: BackgroundTasks,
    body: dict = Body(...),
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    require_role(auth, "operator")
    product_id = str(body.get("product_id") or "")
    units = int(body.get("units") or 0)
    params = body.get("params") or {}
    idempotency_key = request.headers.get("idempotency-key") or str(
        body.get("idempotency_key") or ""
    )
    allow_restricted = bool(body.get("allow_restricted")) and auth.is_admin
    async with session_scope() as session:
        outcome = await OperationService(session).submit(
            tenant_id=auth.tenant_id,
            product_id=product_id,
            units=units,
            params=params,
            idempotency_key=idempotency_key.strip(),
            allow_restricted=allow_restricted,
            actor=f"key:{auth.key_fingerprint}",
        )
        job = outcome["job"]
    if execution_mode() == "celery":
        from ...workers.dispatch import dispatch_job

        await dispatch_job(job["id"])
    else:
        background.add_task(execute_job, job["id"], worker_id="inline:operation")
    return {"job": {"id": job["id"], "state": job["state"], "kind": job["kind"]},
            "estimate": outcome["estimate"]}


# ---------------------------------------------------------------------------
# Jobs + usage
# ---------------------------------------------------------------------------


@router.get("/tenants/{tenant_id}/jobs/{job_id}", tags=["operations"])
async def get_job(
    tenant_id: str, job_id: str, auth: AuthContext = Depends(resolve_workspace)
) -> dict:
    require_role(auth, "viewer")
    async with session_scope() as session:
        job = await JobService(session).get(auth.tenant_id, job_id)
        usage_rows = (
            await session.execute(
                select(JobUsage).where(
                    JobUsage.job_id == job_id, JobUsage.tenant_id == auth.tenant_id
                )
            )
        ).scalars().all()
        reservation = await LedgerService(session).reservation_for_job(job_id)
    return {
        "job": job,
        "usage": [_usage_dict(row) for row in usage_rows],
        "reservation": (
            {
                "id": reservation.id,
                "amount": reservation.amount,
                "state": reservation.state,
            }
            if reservation
            else None
        ),
    }


@router.get("/tenants/{tenant_id}/jobs", tags=["operations"])
async def list_jobs(
    tenant_id: str,
    kind: str = "",
    limit: int = 100,
    offset: int = 0,
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    require_role(auth, "viewer")
    from sqlalchemy import select

    from ...models import WorkJob

    async with session_scope() as session:
        query = (
            select(WorkJob)
            .where(WorkJob.tenant_id == auth.tenant_id)
            .order_by(WorkJob.created_at.desc())
            .limit(min(500, max(1, limit)))
            .offset(max(0, offset))
        )
        if kind:
            query = query.where(WorkJob.kind == kind)
        rows = (await session.execute(query)).scalars().all()
    return {"jobs": [job_dict(row) for row in rows]}


@router.get("/tenants/{tenant_id}/usage", tags=["operations"])
async def list_usage(
    tenant_id: str,
    job_id: str = "",
    limit: int = 100,
    offset: int = 0,
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    require_role(auth, "viewer")
    from sqlalchemy import select

    async with session_scope() as session:
        query = (
            select(JobUsage)
            .where(JobUsage.tenant_id == auth.tenant_id)
            .order_by(JobUsage.created_at.desc())
            .limit(min(500, max(1, limit)))
            .offset(max(0, offset))
        )
        if job_id:
            query = query.where(JobUsage.job_id == job_id)
        rows = (await session.execute(query)).scalars().all()
    return {"usage": [_usage_dict(row) for row in rows]}


__all__ = ["router"]
