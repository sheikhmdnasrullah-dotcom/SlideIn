"""Read-only tool catalog and side-effect-free capability coverage routes."""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import ValidationError
from sqlalchemy import func, select

from ...db import session_scope
from ...integrations.tool_registry import TOOL_REGISTRY, ToolContext, build_coverage_plan
from ...models import ToolAttempt, ToolExecution
from ...security import AuthContext, require_auth, require_role, resolve_workspace
from ...serialize import tool_execution
from ...services.inbound_mail import GoogleWorkspaceInboundService
from ..deps import module_gate

router = APIRouter()


@router.get("/tools/catalog", tags=["tools"])
async def tool_catalog(_: AuthContext = Depends(require_auth)) -> dict:
    """Return non-secret registry metadata; do not probe or execute providers."""
    tools = [tool.public() for tool in TOOL_REGISTRY]
    return {
        "count": len(tools),
        "tools": tools,
        "side_effects": "none",
        "summary": {
            "ready": sum(tool["availability"] == "ready" for tool in tools),
            "unavailable": sum(tool["availability"] != "ready" for tool in tools),
            "by_stage": {
                stage: sum(tool["stage"] == stage for tool in tools)
                for stage in sorted({tool["stage"] for tool in tools})
            },
        },
    }


@router.post("/tenants/{tenant_id}/tools/coverage", tags=["tools"])
async def tool_coverage(
    tenant_id: str,
    payload: dict = Body(default={}),
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    """Plan tool coverage without network, subprocess, DNS, email or AI calls."""
    stage = str(payload.get("stage") or "research")
    if stage not in {
        "configure", "discover", "research", "personalize", "outreach",
        "converse", "operations", "analytics",
    }:
        raise HTTPException(status_code=400, detail="Unsupported coverage stage")
    capabilities = payload.get("capabilities")
    if capabilities is not None and (
        not isinstance(capabilities, list)
        or not all(isinstance(item, str) for item in capabilities)
    ):
        raise HTTPException(status_code=400, detail="capabilities must be a list of strings")
    module = {
        "configure": "knowledge",
        "discover": "discovery",
        "research": "research",
        "personalize": "personalization",
        "outreach": "outreach",
        "converse": "conversations",
    }.get(stage, "settings")
    async with session_scope() as session:
        await module_gate(session, auth.tenant_id, module)
    try:
        plan = build_coverage_plan(
            context=ToolContext.from_mapping(payload),
            stage=stage,
            capabilities=capabilities,
        )
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"tenant_id": auth.tenant_id, "executed": False, "plan": plan}


@router.get("/tenants/{tenant_id}/tools/executions", tags=["tools"])
async def list_tool_executions(
    tenant_id: str,
    subject_id: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    async with session_scope() as session:
        await module_gate(session, auth.tenant_id, "research")
        conditions = [ToolExecution.tenant_id == auth.tenant_id]
        if subject_id:
            conditions.append(ToolExecution.subject_id == subject_id)
        rows = (
            await session.execute(
                select(ToolExecution)
                .where(*conditions)
                .order_by(ToolExecution.started_at.desc())
                .limit(limit)
                .offset(offset)
            )
        ).scalars().all()
        total = (
            await session.execute(
                select(func.count()).select_from(ToolExecution).where(*conditions)
            )
        ).scalar_one()
    return {"data": [tool_execution(row) for row in rows], "total": int(total)}


@router.get("/tenants/{tenant_id}/tools/executions/{execution_id}", tags=["tools"])
async def get_tool_execution(
    tenant_id: str,
    execution_id: str,
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    async with session_scope() as session:
        await module_gate(session, auth.tenant_id, "research")
        execution = await session.get(ToolExecution, execution_id)
        if execution is None or execution.tenant_id != auth.tenant_id:
            raise HTTPException(status_code=404, detail="Tool execution not found")
        attempts = (
            await session.execute(
                select(ToolAttempt)
                .where(ToolAttempt.execution_id == execution.id)
                .order_by(ToolAttempt.position)
            )
        ).scalars().all()
    return tool_execution(execution, list(attempts))


@router.get("/tenants/{tenant_id}/mail/provider", tags=["mail"])
async def mail_provider(
    tenant_id: str, auth: AuthContext = Depends(resolve_workspace)
) -> dict:
    async with session_scope() as session:
        await module_gate(session, auth.tenant_id, "settings")
        return {"mail": await GoogleWorkspaceInboundService(session).mail_config(auth.tenant_id)}


@router.put("/tenants/{tenant_id}/mail/provider", tags=["mail"])
async def set_mail_provider(
    tenant_id: str,
    payload: dict = Body(...),
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    require_role(auth, "operator")
    async with session_scope() as session:
        await module_gate(session, auth.tenant_id, "settings")
        return {
            "mail": await GoogleWorkspaceInboundService(session).save_mail_config(
                auth.tenant_id, payload
            )
        }


@router.post("/tenants/{tenant_id}/mail/google-workspace/poll", tags=["mail"])
async def poll_google_workspace(
    tenant_id: str, auth: AuthContext = Depends(resolve_workspace)
) -> dict:
    require_role(auth, "operator")
    async with session_scope() as session:
        await module_gate(session, auth.tenant_id, "inbox")
        return await GoogleWorkspaceInboundService(session).poll(auth.tenant_id)


__all__ = ["router"]
