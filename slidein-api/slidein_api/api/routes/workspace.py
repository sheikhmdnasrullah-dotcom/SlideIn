"""Adaptive workspace routes: persisted workspace config, adaptation
proposals, and LangGraph agent executions — tenant-bound via auth.

The stores are the product/core engine (in-process singletons; Postgres
persistence is a documented next slice). Every handler binds to the
authenticated tenant only; cross-tenant ids are unreachable by construction.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid

# `product` (the adaptive-workspace core) lives at the repo root next to
# slidein-api; make it importable regardless of launch directory.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                          "..", "..", "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from fastapi import APIRouter, Depends, HTTPException, Request

from ...security import AuthContext, require_auth
from ... import canonical
from product.core.adaptation import AdaptationEngine, EvidenceStore, InsufficientEvidence
from product.core.capabilities import CapabilityRegistry
from product.core.errors import CrossTenantAccess
from product.core.scopes import Role
from product.core.workspace import (ChangeRisk, InvalidWorkspaceConfig,
                                    WorkspaceStore, universal_workspace)
from product.services.agentic_workflow import AgenticWorkflowService

router = APIRouter()

_registry = CapabilityRegistry()
_workspaces = WorkspaceStore(_registry)
_evidence = EvidenceStore()
_adaptation = AdaptationEngine(_registry, _workspaces, _evidence)
_proposal_ledger: dict[str, dict[str, dict]] = {}
_executors: dict[str, AgenticWorkflowService] = {}
_CP_DIR = os.getenv("WORKSPACE_CP_DIR", "/tmp/slidein-workspace-cp")
os.makedirs(_CP_DIR, exist_ok=True)

_ROLE_MAP = {
    "admin": Role.TENANT_ADMIN, "tenant_admin": Role.TENANT_ADMIN,
    "member": Role.TENANT_MEMBER, "viewer": Role.TENANT_MEMBER,
    "service": Role.SYSTEM, "platform_admin": Role.PLATFORM_ADMIN,
}


def _role(auth: AuthContext) -> Role:
    return _ROLE_MAP.get((auth.role or "").lower(), Role.TENANT_MEMBER)


_hydrated: set[str] = set()


async def _ensure(tenant_id: str) -> None:
    """First touch for a tenant: hydrate persisted state (restart) or seed
    the universal workspace (fresh instance)."""
    if tenant_id in _hydrated:
        return
    _hydrated.add(tenant_id)
    from ... import workspace_store as wsp
    restored = await wsp.load_tenant(tenant_id, workspaces=_workspaces,
                                     evidence_store=_evidence,
                                     proposal_ledger=_proposal_ledger)
    if not restored:
        _workspaces.register(universal_workspace(tenant_id), role=Role.SYSTEM)
        await wsp.persist_config(_workspaces._current[tenant_id])


def _ledger(tenant_id: str) -> dict[str, dict]:
    return _proposal_ledger.setdefault(tenant_id, {})


def _executor(tenant_id: str) -> AgenticWorkflowService:
    if tenant_id not in _executors:
        raise RuntimeError("executor not initialised for tenant")
    return _executors[tenant_id]


async def _executor_for(tenant_id: str) -> AgenticWorkflowService:
    svc = _executors.get(tenant_id)
    if svc is None:
        svc = await AgenticWorkflowService.create(os.path.join(_CP_DIR, f"{tenant_id}.sqlite"))
        _executors[tenant_id] = svc
    return svc


def _to_http(exc: Exception) -> HTTPException:
    if isinstance(exc, CrossTenantAccess):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, (InvalidWorkspaceConfig, InsufficientEvidence, ValueError)):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, KeyError):
        return HTTPException(status_code=404, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


# --------------------------------------------------------------------------- #
# Workspace configuration
# --------------------------------------------------------------------------- #
@router.get("/workspace/config")
async def get_workspace_config(auth: AuthContext = Depends(require_auth)):
    await _ensure(auth.tenant_id)
    cfg = _workspaces.current(auth.tenant_id, caller_tenant_id=auth.tenant_id,
                              role=_role(auth))
    return {
        "tenant_id": cfg.tenant_id, "version": cfg.version,
        "enabled_modules": list(cfg.enabled_modules),
        "module_order": list(cfg.module_order),
        "nav_groups": {k: list(v) for k, v in cfg.nav_groups.items()},
        "widgets": [w.__dict__ for w in cfg.widgets],
        "integration_refs": list(cfg.integration_refs),
        "sections": canonical.project_navigation(cfg.enabled_modules),
    }


@router.get("/workspace/history")
async def get_workspace_history(auth: AuthContext = Depends(require_auth)):
    await _ensure(auth.tenant_id)
    history = _workspaces.history(auth.tenant_id, caller_tenant_id=auth.tenant_id,
                                  role=_role(auth))
    return {"versions": [{"version": c.version,
                          "modules": list(c.enabled_modules),
                          "module_order": list(c.module_order)}
                         for c in history]}


@router.post("/workspace/rollback")
async def rollback_workspace(body: dict, auth: AuthContext = Depends(require_auth)):
    await _ensure(auth.tenant_id)
    try:
        cfg = _workspaces.rollback(auth.tenant_id, int(body["to_version"]),
                                   caller_tenant_id=auth.tenant_id, role=_role(auth))
    except Exception as exc:
        raise _to_http(exc)
    from ... import workspace_store as _wsp
    await _wsp.persist_config(cfg)
    return {"version": cfg.version, "module_order": list(cfg.module_order)}


# --------------------------------------------------------------------------- #
# Evidence + adaptation proposals
# --------------------------------------------------------------------------- #
@router.post("/workspace/evidence")
async def record_evidence(body: dict, auth: AuthContext = Depends(require_auth)):
    # Spec §7.1: a caller must not mark its own evidence verified merely by
    # sending verified=true — only admin/platform roles may verify.
    role = _role(auth)
    caller_verified = bool(body.get("verified", False)) and role in (
        Role.TENANT_ADMIN, Role.PLATFORM_ADMIN, Role.SYSTEM)
    try:
        item = _adaptation.record_evidence(
            tenant_id=auth.tenant_id, kind=body["kind"], fact=body["fact"],
            source_ref=body.get("source_ref", "api"),
            confidence=float(body.get("confidence", 0.5)),
            verified=caller_verified,
            caller_tenant_id=auth.tenant_id, role=role)
    except Exception as exc:
        raise _to_http(exc)
    from ... import workspace_store as _wsp
    await _wsp.persist_evidence(item)
    return item.__dict__


@router.post("/workspace/adapt")
async def propose_adaptation(body: dict, auth: AuthContext = Depends(require_auth)):
    await _ensure(auth.tenant_id)
    try:
        proposal = _adaptation.propose_workspace_changes(
            tenant_id=auth.tenant_id, caller_tenant_id=auth.tenant_id,
            role=_role(auth), rationale=body.get("rationale", "api proposal"))
    except Exception as exc:
        raise _to_http(exc)
    pid = uuid.uuid4().hex[:12]
    entry = {"proposal_id": pid, "risk": proposal.risk.value,
             "changes": {k: (list(v) if isinstance(v, tuple) else v)
                         for k, v in proposal.changes.items()},
             "rationale": proposal.rationale, "status": proposal.status.value}
    _ledger(auth.tenant_id)[pid] = entry
    from ... import workspace_store as _wsp
    await _wsp.persist_proposal(entry, auth.tenant_id)
    return entry


@router.get("/workspace/proposals")
async def list_proposals(auth: AuthContext = Depends(require_auth)):
    return {"proposals": list(_ledger(auth.tenant_id).values())}


@router.post("/workspace/proposals/{proposal_id}/apply")
async def apply_proposal(proposal_id: str, body: dict,
                         auth: AuthContext = Depends(require_auth)):
    await _ensure(auth.tenant_id)
    entry = _ledger(auth.tenant_id).get(proposal_id)
    if not entry:
        raise HTTPException(status_code=404, detail="proposal not found")
    from product.core.workspace import ConfigProposal, ChangeRisk, ProposalStatus
    changes = {k: (tuple(v) if isinstance(v, list) else v)
               for k, v in entry["changes"].items()}
    if "widgets" in changes:  # rehydrate WidgetConfig tuples
        from product.core.workspace import WidgetConfig
        changes["widgets"] = tuple(
            w if isinstance(w, WidgetConfig) else WidgetConfig(**w)
            for w in changes["widgets"])
    proposal = ConfigProposal(
        tenant_id=auth.tenant_id, changes=changes,
        evidence_refs=(), risk=ChangeRisk(entry["risk"]),
        rationale=entry["rationale"],
        status=ProposalStatus(entry["status"]))
    try:
        # Owner decision (Canonical Convergence §3.4): adaptations require
        # approval — no auto-apply bypass, regardless of risk tier.
        if entry["status"] != "approved":
            raise CrossTenantAccess("adaptations require approval before apply")
        cfg = _workspaces.apply(auth.tenant_id, proposal,
                                caller_tenant_id=auth.tenant_id,
                                role=_role(auth),
                                auto_apply_low_risk=False)
    except Exception as exc:
        raise _to_http(exc)
    entry["status"] = "applied"
    from ... import workspace_store as _wsp
    await _wsp.persist_proposal(entry, auth.tenant_id)
    await _wsp.persist_config(cfg)
    return {"version": cfg.version, "module_order": list(cfg.module_order)}


# --------------------------------------------------------------------------- #
# Agent executions (LangGraph)
# --------------------------------------------------------------------------- #
@router.post("/agents/executions")
async def start_execution(body: dict, auth: AuthContext = Depends(require_auth)):
    if not body.get("person"):
        raise HTTPException(status_code=422, detail="person is required")
    try:
        svc = await _executor_for(auth.tenant_id)
        view = await svc.start(tenant_id=auth.tenant_id,
                               person=body["person"],
                               opportunity_id=body.get("opportunity_id"))
    except Exception as exc:
        raise _to_http(exc)
    return view


@router.get("/agents/executions/{execution_id}")
async def get_execution(execution_id: str, auth: AuthContext = Depends(require_auth)):
    try:
        svc = _executor(auth.tenant_id)
    except RuntimeError:
        raise HTTPException(status_code=404, detail="no executions for tenant")
    try:
        return await svc.get_execution(tenant_id=auth.tenant_id,
                                       execution_id=execution_id,
                                       caller_tenant_id=auth.tenant_id,
                                       role=_role(auth))
    except Exception as exc:
        raise _to_http(exc)


@router.post("/agents/executions/{execution_id}/resume")
async def resume_execution(execution_id: str, body: dict,
                           auth: AuthContext = Depends(require_auth)):
    try:
        svc = _executor(auth.tenant_id)
    except RuntimeError:
        raise HTTPException(status_code=404, detail="no executions for tenant")
    try:
        return await svc.resume(tenant_id=auth.tenant_id,
                                execution_id=execution_id,
                                approved=bool(body.get("approved")))
    except Exception as exc:
        raise _to_http(exc)
