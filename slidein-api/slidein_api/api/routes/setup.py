"""One-shot client setup routes — THE setup entry point.

POST /v1/setup/client  {materials: [{source_ref, text}] | notes: "..."}
    -> business profile (confirmed vs inferred, source refs, gaps)
    -> validated workspace config (persisted, versioned)
    -> first workflow proposal (universal-flow validated)
    -> readiness status with grouped questions and honest blockers
GET  /v1/setup/status   -> current readiness state (survives restarts)

Operator flow (the screen at /setup in the client app):
GET  /v1/tenants/{tenant_id}/setup
    -> rich status: stage map, checklist, open questions, validation stages,
       connections, activation — the honest state the UI renders
POST /v1/tenants/{tenant_id}/setup/generate  {sources: [...]}
    -> deterministic extraction -> blueprint -> profile/offer/ICP saved
POST /v1/tenants/{tenant_id}/setup/answers   {answers: {key: value}}
    -> records decisions, regenerates from the same sources
"""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException
from starlette import status as http_status

from ...db import session_scope
from ...errors import SlideinError
from ...security import AuthContext, require_auth, require_role, resolve_workspace
from ... import setup_service as setup
from ... import workspace_store as wsp
from ...setup import SetupService
from . import workspace as ws_routes

router = APIRouter()


def _materials(body: dict) -> list[tuple[str, str]]:
    materials = [(m.get("source_ref", f"doc-{i+1}"), m.get("text", ""))
                 for i, m in enumerate(body.get("materials") or [])]
    if not materials and body.get("notes"):
        materials = [("notes", body["notes"])]
    return [(s, t) for s, t in materials if t.strip()]


@router.post("/setup/client")
async def setup_client(body: dict, auth: AuthContext = Depends(require_auth)):
    materials = _materials(body)
    if not materials:
        raise HTTPException(422, "provide materials (transcript/document text) or notes")
    tenant = auth.tenant_id
    await ws_routes._ensure(tenant)

    # 1. Understand the business
    profile = setup.extract_profile(materials)

    # 2. Record confirmed extraction as verified evidence (with provenance)
    ev_ids = []
    for fact in (*profile.offers, *profile.icp, *profile.goals):
        if fact.confirmed:
            item = ws_routes._adaptation.record_evidence(
                tenant_id=tenant, kind="explicit_fact",
                fact=f"client setup: {fact.key} = {fact.value}",
                source_ref=fact.source_ref, confidence=0.95, verified=True,
                caller_tenant_id=tenant, role=ws_routes._role(auth))
            ev_ids.append(item.evidence_id)

    # 3. Generate + validate + persist the workspace config
    current = ws_routes._workspaces.current(tenant, caller_tenant_id=tenant,
                                            role=ws_routes._role(auth))
    changes = setup.generate_workspace_config(profile, tenant_id=tenant,
                                              universal_config=current)
    from product.core.workspace import ChangeRisk
    proposal = ws_routes._workspaces.propose(
        tenant, changes=changes, evidence_refs=tuple(ev_ids),
        risk=ChangeRisk.LOW, rationale="client setup intake",
        caller_tenant_id=tenant, role=ws_routes._role(auth))
    cfg = ws_routes._workspaces.apply(tenant, proposal,
                                      caller_tenant_id=tenant,
                                      role=ws_routes._role(auth),
                                      auto_apply_low_risk=True)
    await wsp.persist_config(cfg)

    # 4. First workflow — universal-flow validated, approval-gated
    from ...canonical import assert_canonical_flow
    steps = assert_canonical_flow(setup.first_workflow_steps(profile))
    wf_prop = None
    if ev_ids:
        try:
            wf_prop = ws_routes._adaptation.propose_workflow(
                tenant_id=tenant, name="first_outreach",
                purpose="discover -> research -> qualify -> personalize"
                        + (" -> outreach" if "outreach" in steps else ""),
                steps=steps, trigger="manual",
                evidence_refs=(ev_ids[0],),
                caller_tenant_id=tenant, role=ws_routes._role(auth))
        except Exception:
            wf_prop = None

    # 5. Honest readiness
    blockers = []
    if profile.tools:
        for t in profile.tools:
            blockers.append(f"integration '{t.value}' ({t.source_ref}) needs "
                            f"connection before dependent workflows run")
    if profile.contradictions:
        blockers.extend(f"resolve contradiction: {c}" for c in profile.contradictions)
    state = ("blocked" if profile.contradictions
             else "integrations_pending" if profile.tools
             else "ready")
    questions = setup.review_questions(profile)
    status = setup.SetupStatus(
        tenant_id=tenant, state=state, profile_id=profile.profile_id,
        config_version=cfg.version,
        workflow_proposal_id=wf_prop.proposal_id if wf_prop else None,
        blockers=tuple(blockers), questions=questions,
        next_action=("Connect the listed integrations, then approve the "
                     "first workflow" if blockers else
                     "Review the short question list, then approve the "
                     "first workflow"))
    await wsp.persist_setup_status(status)

    return {
        "profile": {
            "profile_id": profile.profile_id,
            "business_name": profile.business_name,
            "industry": profile.industry,
            "offers": [f.value for f in profile.offers],
            "icp": [f.value for f in profile.icp],
            "goals": [f.value for f in profile.goals],
            "tools": [f.value for f in profile.tools],
            "missing": list(profile.missing),
            "contradictions": list(profile.contradictions),
            "sources": sorted({f.source_ref for f in
                               (*profile.offers, *profile.icp, *profile.goals)}),
        },
        "workspace": {"version": cfg.version,
                      "module_order": list(cfg.module_order)},
        "first_workflow": {"proposal_id": status.workflow_proposal_id,
                           "steps": list(steps), "approval_gate": True},
        "readiness": {"state": state, "blockers": blockers,
                      "questions": questions, "next_action": status.next_action},
    }


@router.get("/setup/status")
async def setup_status(auth: AuthContext = Depends(require_auth)):
    row = await wsp.load_setup_status(auth.tenant_id)
    if row is None:
        return {"state": "workspace_created",
                "next_action": "POST /v1/setup/client with the client's "
                               "transcript, documents, or notes"}
    return row


# --------------------------------------------------------------------------- #
# Operator flow backing the /setup screen: generate -> answer -> status.
# The intake endpoint above stays the single entry for a client transcript;
# these endpoints keep the richer per-stage state the screen renders.
# --------------------------------------------------------------------------- #

_STATUS_BY_CODE = {
    "not_found": http_status.HTTP_404_NOT_FOUND,
    "tenant_forbidden": http_status.HTTP_404_NOT_FOUND,
    "not_authorized": http_status.HTTP_403_FORBIDDEN,
}


def _rich_error(exc: SlideinError) -> HTTPException:
    code = _STATUS_BY_CODE.get(exc.code, http_status.HTTP_400_BAD_REQUEST)
    return HTTPException(status_code=code, detail=exc.to_dict())


@router.get("/tenants/{tenant_id}/setup", tags=["setup"])
async def setup_report(
    tenant_id: str,
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    """Current setup state for the screen: stages, questions, validation."""
    async with session_scope() as session:
        return await SetupService(session).status(tenant_id)


@router.post("/tenants/{tenant_id}/setup/generate", tags=["setup"])
async def setup_generate(
    tenant_id: str,
    payload: dict = Body(...),
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    require_role(auth, "operator")
    try:
        async with session_scope() as session:
            return await SetupService(session).generate(
                tenant_id, payload, actor=f"user:{auth.role}")
    except SlideinError as exc:
        raise _rich_error(exc)


@router.post("/tenants/{tenant_id}/setup/answers", tags=["setup"])
async def setup_answers(
    tenant_id: str,
    payload: dict = Body(...),
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    require_role(auth, "operator")
    answers = payload.get("answers") if isinstance(payload, dict) else None
    try:
        async with session_scope() as session:
            return await SetupService(session).answer(
                tenant_id, answers or {}, actor=f"user:{auth.role}")
    except SlideinError as exc:
        raise _rich_error(exc)
