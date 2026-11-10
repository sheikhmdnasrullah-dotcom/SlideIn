"""Console adaptation routes.

Exposes the adaptive layer that lets the Console learn and reorganize itself
without generating new code or new consoles. The surface vocabulary is the
validated module registry; this service only selects, orders, hides, and
renames sections, and proposes changes that deterministic code must approve.
"""

from __future__ import annotations

import time

from fastapi import APIRouter, Body, Depends, HTTPException
from starlette import status as http_status

from ...db import session_scope
from ...errors import SlideinError, ValidationError
from ...security import AuthContext, require_role, resolve_workspace
from ...services.adaptive import adaptive_service, Proposal
from ..deps import module_gate

router = APIRouter()

_SERVICE = adaptive_service()


def _err(exc: SlideinError):
    code = exc.code
    status = (
        http_status.HTTP_404_NOT_FOUND
        if code in ("not_found",)
        else http_status.HTTP_403_FORBIDDEN
        if code == "not_authorized"
        else http_status.HTTP_400_BAD_REQUEST
    )
    return HTTPException(status_code=status, detail=exc.to_dict())


@router.get("/tenants/{tenant_id}/console/sections", tags=["console"])
async def console_sections(
    tenant_id: str, auth: AuthContext = Depends(resolve_workspace)
) -> dict:
    """Current Console sections (render order, visibility, overrides)."""
    async with session_scope() as session:
        await module_gate(session, auth.tenant_id, "overview")
    sections = await _SERVICE.effective_sections(tenant_id)
    return {"sections": [s.to_dict() for s in sections]}


@router.put("/tenants/{tenant_id}/console/sections", tags=["console"])
async def set_console_sections(
    tenant_id: str,
    body: list[dict] = Body(embed=False),
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    """Explicitly set a workspace's Console layout (user or admin action).

    Every id is validated against the module registry; `settings` is pinned.
    """
    require_role(auth, "operator")
    async with session_scope() as session:
        await module_gate(session, auth.tenant_id, "settings")
        try:
            sections = await _SERVICE.apply_preferences(
                tenant_id, body, source=auth.email or "user"
            )
        except SlideinError as exc:
            raise _err(exc)
        except ValueError as exc:
            raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"message": str(exc)},
        )
    return {"sections": [s.to_dict() for s in sections]}


@router.post("/tenants/{tenant_id}/console/sections/propose", tags=["console"])
async def propose_console_section(
    tenant_id: str,
    payload: dict = Body(default={}),
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    """Record a behavior-driven proposal. Does NOT mutate Console state."""
    async with session_scope() as session:
        await module_gate(session, auth.tenant_id, "overview")
    action = payload.get("action")
    section_id = payload.get("section_id")
    evidence = payload.get("evidence", {}) or {}
    if not action or not section_id:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail={"message": "action and section_id are required"},
        )
    proposal = Proposal(
        section_id=str(section_id),
        action=str(action),
        evidence=evidence,
        reasoning=str(payload.get("reasoning", "")),
    )
    try:
        result = await _SERVICE.propose(auth.tenant_id, proposal)
    except ValueError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"message": str(exc)},
        )
    return result


@router.post(
    "/tenants/{tenant_id}/console/sections/{proposal_id}/approve",
    tags=["console"],
)
async def approve_proposal(
    proposal_id: str,
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    """Apply an approved proposal. Requires admin/operator role."""
    require_role(auth, "operator")
    async with session_scope() as session:
        await module_gate(session, auth.tenant_id, "settings")
        try:
            sections = await _SERVICE.approve(auth.tenant_id, proposal_id)
        except KeyError:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail={"message": "proposal not found"},
            )
        except SlideinError as exc:
            raise _err(exc)
        except ValueError as exc:
            raise _err(ValidationError(str(exc), code="validation_error"))
    return {"sections": [s.to_dict() for s in sections]}


@router.post(
    "/tenants/{tenant_id}/console/sections/{proposal_id}/reject",
    tags=["console"],
)
async def reject_proposal(
    proposal_id: str,
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    require_role(auth, "operator")
    async with session_scope() as session:
        await module_gate(session, auth.tenant_id, "settings")
        removed = await _SERVICE.reject(auth.tenant_id, proposal_id)
        if not removed:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail={"message": "proposal not found"},
            )
    return {"rejected": proposal_id}


@router.get("/tenants/{tenant_id}/console/proposals", tags=["console"])
async def list_proposals(auth: AuthContext = Depends(resolve_workspace)) -> dict:
    async with session_scope() as session:
        await module_gate(session, auth.tenant_id, "overview")
        proposals = await _SERVICE.list_proposals(auth.tenant_id)
    now = time.time()
    active = [p for p in proposals if p.get("expires_at", 0) > now]
    return {"proposals": active}


@router.post("/tenants/{tenant_id}/console/behavior", tags=["console"])
async def record_behavior(
    payload: dict = Body(default={}),
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    """Record a viewer behavior event used to propose future section changes.

    `kind` must be one of: shown, clicked, dismissed, hidden_by_user.
    Never acts on this alone — it only feeds proposals, which require approval.
    """
    async with session_scope() as session:
        await module_gate(session, auth.tenant_id, "overview")
    section_id = str(payload.get("section_id", ""))
    kind = str(payload.get("kind", ""))
    weight = float(payload.get("weight", 1.0))
    await _SERVICE.record_user_interaction(
        auth.tenant_id, section_id, kind, weight
    )
    return {"recorded": True}
