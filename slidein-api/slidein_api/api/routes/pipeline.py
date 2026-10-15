"""Pipeline routes: discovery, research, qualification, personalization.

Every route is a thin adapter: it authenticates, resolves the workspace,
opens one unit of work, hands the payload to the StageRunner with the
stage's executor, and returns the runner's outcome — including the failure
code, retryability and recovery action when the stage did not succeed.
"""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from starlette import status as http_status

from ...contracts import StageName
from ...db import session_scope
from ...errors import NotFoundError, SlideinError
from ...runtime import StageRunner
from ...security import AuthContext, require_role, resolve_workspace
from ...services.config import ConfigService
from ...services.discovery import DiscoveryService
from ...services.overview import OverviewService
from ...services.personalization import PersonalizationService
from ...services.qualification import QualificationService
from ...services.research import ResearchService
from ...services.suppression import SuppressionService

router = APIRouter()


_STATUS_BY_CODE = {
    "not_found": http_status.HTTP_404_NOT_FOUND,
    "tenant_forbidden": http_status.HTTP_404_NOT_FOUND,
    "prospect_not_found": http_status.HTTP_404_NOT_FOUND,
    "not_authorized": http_status.HTTP_403_FORBIDDEN,
    "suppressed": http_status.HTTP_409_CONFLICT,
    "approval_required": http_status.HTTP_409_CONFLICT,
    "rate_limited": http_status.HTTP_429_TOO_MANY_REQUESTS,
}


def _error(exc: SlideinError) -> HTTPException:
    status = _STATUS_BY_CODE.get(exc.code, http_status.HTTP_400_BAD_REQUEST)
    return HTTPException(status_code=status, detail=exc.to_dict())


def _fail(outcome) -> None:
    raise _error(
        SlideinError(
            outcome.error_message,
            code=outcome.error_code,
            details=outcome.details,
            recovery_action=outcome.recovery_action,
        )
    )


def _outcome_response(outcome) -> dict:
    payload = outcome.to_dict()
    payload["ok"] = outcome.status != "failed"
    if outcome.status == "failed":
        payload["recovery_action"] = outcome.recovery_action
        payload["retryable"] = outcome.retryable
    return payload


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

@router.post("/tenants/{tenant_id}/discover", tags=["pipeline"])
async def discover(
    tenant_id: str,
    payload: dict = Body(...),
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    require_role(auth, "operator")
    records = payload.get("records") or []
    if not isinstance(records, list):
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_input", "message": "records must be a list"},
        )

    async def executor(stage_payload: dict, session) -> dict:
        discovery = DiscoveryService(session)
        config = ConfigService(session)

        icp_id = stage_payload.get("icp_id")
        if not icp_id:
            active = await config.active_icp(auth.tenant_id)
            if active is None:
                raise SlideinError(
                    "No active ICP to discover against",
                    code="icp_missing",
                    recovery_action="define_icp",
                )
            icp_id = active["id"]

        icp_rec = await config.get_icp(auth.tenant_id, icp_id)
        profile = await config.active_profile(auth.tenant_id)

        result = await discovery.create_records(
            auth.tenant_id,
            icp_id=icp_id,
            records=records,
            source=str(payload.get("source") or "manual"),
            source_ref=str(payload.get("source_ref") or ""),
            profile_id=profile["id"] if profile else None,
            profile_version=profile["version"] if profile else None,
            created_by=f"user:{auth.role}",
        )

        suppressions = SuppressionService(session)
        await suppressions.seed_defaults(auth.tenant_id)

        needs_review: list[str] = []
        if result["duplicates"]:
            needs_review.append(
                f"{result['duplicates']} record(s) already exist in this workspace"
            )
        if result["skipped"]:
            needs_review.append(
                f"{result['skipped']} record(s) were missing an email or company"
            )
        for record in records:
            if await suppressions.is_suppressed(auth.tenant_id, str(record.get("email", ""))):
                needs_review.append(
                    f"{record.get('email')} is on the suppression list"
                )

        return {
            "status": "succeeded",
            "outputs": result,
            "needs_review": needs_review,
            "from_status": "",
            "to_status": "discovered",
        }

    async with session_scope() as session:
        runner = StageRunner(session)
        outcome = await runner.run(
            StageName.DISCOVER,
            tenant_id=auth.tenant_id,
            payload=(
                {"icp_id": payload.get("icp_id"), "records": records}
                if payload.get("icp_id")
                else {"records": records}
            ),
            actor=f"user:{auth.role}",
            role=auth.role,
            executor=executor,
        )
    if outcome.status == "failed":
        _fail(outcome)
    return _outcome_response(outcome)


# ---------------------------------------------------------------------------
# Prospects
# ---------------------------------------------------------------------------

@router.get("/tenants/{tenant_id}/prospects", tags=["pipeline"])
async def list_prospects(
    tenant_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status: str | None = Query(None),
    search: str | None = Query(None),
    min_score: int | None = Query(None),
    source: str | None = Query(None),
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    async with session_scope() as session:
        rows, total = await DiscoveryService(session).list_prospects(
            auth.tenant_id,
            limit=limit,
            offset=offset,
            status=status,
            search=search,
            min_score=min_score,
            source=source,
        )
    return {"data": rows, "total": total, "limit": limit, "offset": offset}


@router.get("/tenants/{tenant_id}/prospects/{prospect_id}", tags=["pipeline"])
async def get_prospect(
    tenant_id: str, prospect_id: str, auth: AuthContext = Depends(resolve_workspace)
) -> dict:
    async with session_scope() as session:
        try:
            return await OverviewService(session).prospect_detail(auth.tenant_id, prospect_id)
        except SlideinError as exc:
            raise _error(exc)


@router.get("/tenants/{tenant_id}/prospects/{prospect_id}/evidence", tags=["pipeline"])
async def list_evidence(
    tenant_id: str, prospect_id: str, auth: AuthContext = Depends(resolve_workspace)
) -> dict:
    async with session_scope() as session:
        service = DiscoveryService(session)
        prospect = await service.get_prospect(auth.tenant_id, prospect_id)
        if prospect is None:
            raise _error(
                SlideinError(
                    "Prospect not found", code="prospect_not_found",
                    recovery_action="return_to_discovery",
                )
            )
        evidence = await ResearchService(session).list_evidence(auth.tenant_id, prospect_id)
        qualification = await QualificationService(session).latest_for_prospect(
            auth.tenant_id, prospect_id
        )
    return {"prospect_id": prospect_id, "evidence": evidence, "qualification": qualification}


# ---------------------------------------------------------------------------
# Research
# ---------------------------------------------------------------------------

@router.post("/tenants/{tenant_id}/prospects/{prospect_id}/research", tags=["pipeline"])
async def research(
    tenant_id: str,
    prospect_id: str,
    payload: dict = Body(default={}),
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    require_role(auth, "operator")
    depth = str(payload.get("depth") or "standard")
    claims = payload.get("claims") or []
    connector = str(payload.get("connector") or "website")

    async def executor(stage_payload: dict, session) -> dict:
        discovery = DiscoveryService(session)
        prospect = await discovery.get_prospect(auth.tenant_id, prospect_id)
        if prospect is None:
            raise NotFoundError(
                f"Prospect {prospect_id!r} does not exist in this workspace",
                code="prospect_not_found",
                recovery_action="return_to_discovery",
            )

        suppression = SuppressionService(session)
        blocked = await suppression.is_suppressed(auth.tenant_id, prospect.email)
        if blocked is not None:
            raise SlideinError(
                f"{prospect.email} is suppressed ({blocked['reason']})",
                code="suppressed",
                details={"suppression": blocked},
                recovery_action="review_suppression",
            )

        from_status = prospect.status
        already_advanced = from_status not in ("discovered", "researched")
        if not already_advanced:
            await discovery.apply_transition(
                prospect,
                to_status="researching",
                reason=f"research started by {auth.role}",
                actor=f"user:{auth.role}",
                stage=StageName.RESEARCH.value,
            )

        result = await ResearchService(session).collect_evidence(
            tenant_id=auth.tenant_id,
            prospect=prospect,
            depth=depth,
            supplied_claims=claims,
            connector=connector,
            actor=f"user:{auth.role}",
        )

        to_status = from_status
        if not already_advanced:
            await discovery.apply_transition(
                prospect,
                to_status="researched",
                reason=(
                    f"research completed with {result['evidence_count']} evidence item(s)"
                ),
                actor=f"user:{auth.role}",
                stage=StageName.RESEARCH.value,
            )
            to_status = "researched"

        needs_review: list[str] = []
        if result["verified_count"] == 0:
            needs_review.append("no verified evidence was collected")
        if already_advanced:
            needs_review.append(
                "prospect has already advanced past research; new evidence was attached"
            )

        return {
            "status": "succeeded",
            "outputs": result,
            "needs_review": needs_review,
            "from_status": from_status,
            "to_status": to_status,
        }

    async with session_scope() as session:
        runner = StageRunner(session)
        outcome = await runner.run(
            StageName.RESEARCH,
            tenant_id=auth.tenant_id,
            payload={
                "prospect_id": prospect_id,
                "depth": depth,
                "claims": claims,
                "connector": connector,
            },
            actor=f"user:{auth.role}",
            role=auth.role,
            subject_id=prospect_id,
            executor=executor,
        )
    if outcome.status == "failed":
        _fail(outcome)
    return _outcome_response(outcome)


# ---------------------------------------------------------------------------
# Qualification
# ---------------------------------------------------------------------------

@router.post("/tenants/{tenant_id}/prospects/{prospect_id}/qualify", tags=["pipeline"])
async def qualify(
    tenant_id: str,
    prospect_id: str,
    payload: dict = Body(default={}),
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    require_role(auth, "operator")

    async def executor(stage_payload: dict, session) -> dict:
        discovery = DiscoveryService(session)
        config = ConfigService(session)
        prospect = await discovery.get_prospect(auth.tenant_id, prospect_id)
        if prospect is None:
            raise NotFoundError(
                f"Prospect {prospect_id!r} does not exist in this workspace",
                code="prospect_not_found",
                recovery_action="return_to_discovery",
            )

        suppression = SuppressionService(session)
        blocked = await suppression.is_suppressed(auth.tenant_id, prospect.email)
        if blocked is not None:
            raise SlideinError(
                f"{prospect.email} is suppressed ({blocked['reason']})",
                code="suppressed",
                details={"suppression": blocked},
                recovery_action="review_suppression",
            )

        research = ResearchService(session)
        evidence_rows = await research.list_evidence(auth.tenant_id, prospect_id)
        if not evidence_rows:
            raise SlideinError(
                "Research has not produced any evidence for this prospect",
                code="stage_prerequisite",
                details={"stage": "research"},
                recovery_action="run_prerequisite_stage",
            )

        icp_id = stage_payload.get("icp_id") or prospect.icp_id
        icp_rec = await config.get_icp(auth.tenant_id, icp_id) if icp_id else None
        if icp_rec is None:
            active = await config.active_icp(auth.tenant_id)
            if active is None:
                raise SlideinError(
                    "No active ICP to qualify against",
                    code="icp_missing",
                    recovery_action="define_icp",
                )
            icp_rec = active

        from_status = prospect.status
        result = await QualificationService(session).record(
            tenant_id=auth.tenant_id,
            prospect=prospect,
            icp=icp_rec,
            evidence_rows=evidence_rows,
            actor=f"user:{auth.role}",
        )
        prospect.qualification_score = result["score"]
        prospect.icp_id = icp_rec["id"]
        prospect.icp_version = icp_rec.get("version")
        if result.get("offer_match"):
            prospect.offer_id = result["offer_match"]["offer_id"]
        await session.flush()

        if from_status != "researched":
            raise SlideinError(
                f"Qualification requires the prospect to be researched (it is "
                f"{from_status!r}); new evidence was attached but the score was "
                f"not applied.",
                code="stage_prerequisite",
                details={"stage": "research", "prospect_status": from_status},
                recovery_action="run_prerequisite_stage",
            )

        to_status = "qualified" if result["is_qualified"] else "disqualified"
        await discovery.apply_transition(
            prospect,
            to_status=to_status,
            reason=result["explanation"][:500],
            actor=f"user:{auth.role}",
            stage=StageName.QUALIFY.value,
        )

        needs_review: list[str] = []
        threshold = result.get("threshold", 70)
        if abs(result["score"] - threshold) <= 10:
            needs_review.append(
                f"score {result['score']} is within 10 points of the threshold {threshold}"
            )
        if result["is_qualified"] and result["missing_criteria"]:
            needs_review.append(
                f"{len(result['missing_criteria'])} criterion(a) missing but the score qualifies"
            )

        return {
            "status": "succeeded",
            "outputs": result,
            "needs_review": needs_review,
            "from_status": from_status,
            "to_status": to_status,
        }

    async with session_scope() as session:
        runner = StageRunner(session)
        outcome = await runner.run(
            StageName.QUALIFY,
            tenant_id=auth.tenant_id,
            payload={
                "prospect_id": prospect_id,
                "icp_id": payload.get("icp_id"),
                "offer_id": payload.get("offer_id"),
            },
            actor=f"user:{auth.role}",
            role=auth.role,
            subject_id=prospect_id,
            executor=executor,
        )
    if outcome.status == "failed":
        _fail(outcome)
    return _outcome_response(outcome)


# ---------------------------------------------------------------------------
# Personalization
# ---------------------------------------------------------------------------

@router.post("/tenants/{tenant_id}/prospects/{prospect_id}/personalize", tags=["pipeline"])
async def personalize(
    tenant_id: str,
    prospect_id: str,
    payload: dict = Body(default={}),
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    require_role(auth, "operator")

    async def executor(stage_payload: dict, session) -> dict:
        discovery = DiscoveryService(session)
        prospect = await discovery.get_prospect(auth.tenant_id, prospect_id)
        if prospect is None:
            raise NotFoundError(
                f"Prospect {prospect_id!r} does not exist in this workspace",
                code="prospect_not_found",
                recovery_action="return_to_discovery",
            )

        if prospect.status != "qualified":
            raise SlideinError(
                f"Personalization requires a qualified prospect (status is "
                f"{prospect.status!r})",
                code="stage_prerequisite",
                details={"stage": "qualify", "prospect_status": prospect.status},
                recovery_action="run_prerequisite_stage",
            )

        result = await PersonalizationService(session).generate_draft(
            tenant_id=auth.tenant_id,
            prospect=prospect,
            actor=f"user:{auth.role}",
            offer_id=stage_payload.get("offer_id"),
            qualification_id=stage_payload.get("qualification_id"),
        )

        await discovery.apply_transition(
            prospect,
            to_status="draft_ready",
            reason=f"draft v{result['version']} prepared",
            actor=f"user:{auth.role}",
            stage=StageName.PERSONALIZE.value,
        )

        coverage = result.get("evidence_coverage", 1.0)
        floor = result.get("evidence_coverage_floor", 0.5)
        needs_review: list[str] = []
        if coverage < floor:
            needs_review.append(
                f"evidence coverage {coverage:.0%} is below the {floor:.0%} floor"
            )
        if result["version"] > 1:
            needs_review.append("draft regenerated; earlier versions are kept")

        return {
            "status": "succeeded",
            "outputs": result,
            "needs_review": needs_review,
            "from_status": "qualified",
            "to_status": "draft_ready",
        }

    async with session_scope() as session:
        runner = StageRunner(session)
        outcome = await runner.run(
            StageName.PERSONALIZE,
            tenant_id=auth.tenant_id,
            payload={
                "prospect_id": prospect_id,
                "offer_id": payload.get("offer_id"),
                "qualification_id": payload.get("qualification_id"),
            },
            actor=f"user:{auth.role}",
            role=auth.role,
            subject_id=prospect_id,
            executor=executor,
        )
    if outcome.status == "failed":
        _fail(outcome)
    return _outcome_response(outcome)


@router.get("/tenants/{tenant_id}/qualifications", tags=["pipeline"])
async def list_qualifications(
    tenant_id: str,
    qualified_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    async with session_scope() as session:
        rows, total = await QualificationService(session).list_results(
            auth.tenant_id, qualified_only=qualified_only, limit=limit
        )
    return {"data": rows, "total": total}
