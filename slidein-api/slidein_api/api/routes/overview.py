"""Overview, activity and workflow-run routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from ...db import session_scope
from ...runtime import StageRunner
from ...security import AuthContext, resolve_workspace
from ...services.activity import ActivityService
from ...services.overview import OverviewService

router = APIRouter()


@router.get("/tenants/{tenant_id}/overview", tags=["overview"])
async def overview(
    tenant_id: str,
    attention_limit: int = Query(8, ge=1, le=50),
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    async with session_scope() as session:
        return await OverviewService(session).summary(
            auth.tenant_id, attention_limit=attention_limit
        )


@router.get("/tenants/{tenant_id}/overview/handoffs", tags=["overview"])
async def handoffs(tenant_id: str, auth: AuthContext = Depends(resolve_workspace)) -> dict:
    """What each stage is holding and what it is waiting on."""
    async with session_scope() as session:
        return {"handoffs": await OverviewService(session).handoffs(auth.tenant_id)}


@router.get("/tenants/{tenant_id}/activity", tags=["activity"])
async def list_activity(
    tenant_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    stage: str | None = Query(None),
    action: str | None = Query(None),
    prospect_id: str | None = Query(None),
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    async with session_scope() as session:
        rows, total = await ActivityService(session).list(
            auth.tenant_id,
            limit=limit,
            offset=offset,
            stage=stage,
            action=action,
            prospect_id=prospect_id,
        )
    return {"data": rows, "total": total, "limit": limit, "offset": offset}


@router.get("/tenants/{tenant_id}/runs", tags=["activity"])
async def list_runs(
    tenant_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    stage: str | None = Query(None),
    run_status: str | None = Query(None),
    subject_id: str | None = Query(None),
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    async with session_scope() as session:
        rows, total = await StageRunner(session).list_runs(
            auth.tenant_id,
            limit=limit,
            offset=offset,
            stage=stage,
            status=run_status,
            subject_id=subject_id,
        )
        failed = await StageRunner(session).failed_runs(auth.tenant_id, limit=10)
        needs_review = await StageRunner(session).needs_review_runs(auth.tenant_id, limit=10)
    return {
        "data": rows,
        "total": total,
        "limit": limit,
        "offset": offset,
        "failed": failed,
        "needs_review": needs_review,
    }


@router.get("/tenants/{tenant_id}/prospects/{prospect_id}/runs", tags=["activity"])
async def runs_for_prospect(
    tenant_id: str, prospect_id: str, auth: AuthContext = Depends(resolve_workspace)
) -> dict:
    async with session_scope() as session:
        runs = await StageRunner(session).runs_for_subject(auth.tenant_id, prospect_id)
        activity = await ActivityService(session).for_prospect(auth.tenant_id, prospect_id)
    return {"runs": runs, "activity": activity}


@router.get("/tenants/{tenant_id}/health/dns", tags=["overview"])
async def dns_health(tenant_id: str, auth: AuthContext = Depends(resolve_workspace)) -> dict:
    """Sending-infrastructure health, from persisted delivery evidence only."""
    async with session_scope() as session:
        from ...services.outreach import OutreachService

        counts = await OutreachService(session).delivery_counts(auth.tenant_id)
        policy = await OutreachService(session).policy(auth.tenant_id)
    total = sum(counts.values())
    bounced = counts.get("bounced", 0)
    complained = counts.get("complained", 0)
    return {
        "delivery": counts,
        "total_sent": total,
        "bounce_rate": round(bounced / total * 100, 2) if total else 0.0,
        "complaint_rate": round(complained / total * 100, 2) if total else 0.0,
        "policy": policy,
        "note": (
            "Acceptance by a transport is not evidence of inbox placement. "
            "Delivered counts come from provider events only."
        ),
    }
