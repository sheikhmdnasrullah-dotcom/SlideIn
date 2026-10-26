"""Read-only tool catalog and side-effect-free capability coverage routes."""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import ValidationError

from ...db import session_scope
from ...integrations.tool_registry import TOOL_REGISTRY, ToolContext, build_coverage_plan
from ...security import AuthContext, require_auth, resolve_workspace
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
    if stage not in {"research", "personalize", "outreach", "operations"}:
        raise HTTPException(status_code=400, detail="Unsupported coverage stage")
    capabilities = payload.get("capabilities")
    if capabilities is not None and (
        not isinstance(capabilities, list)
        or not all(isinstance(item, str) for item in capabilities)
    ):
        raise HTTPException(status_code=400, detail="capabilities must be a list of strings")
    module = "research" if stage == "research" else "personalization" if stage == "personalize" else "outreach" if stage == "outreach" else "settings"
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


__all__ = ["router"]
