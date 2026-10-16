"""Outreach routes: drafts, approval, dispatch, delivery events, policy."""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from starlette import status as http_status

from ...contracts import StageName
from ...db import session_scope
from ...errors import NotFoundError, SlideinError
from ...runtime import StageRunner
from ...security import AuthContext, require_auth, require_role, resolve_workspace
from ..deps import module_gate
from ...services.conversations import ConversationService
from ...services.deliverability_guard import DeliverabilityGuard
from ...services.discovery import DiscoveryService
from ...services.outreach import OutreachService
from ...services.personalization import PersonalizationService

router = APIRouter()


_STATUS_BY_CODE = {
    "not_found": http_status.HTTP_404_NOT_FOUND,
    "tenant_forbidden": http_status.HTTP_404_NOT_FOUND,
    "prospect_not_found": http_status.HTTP_404_NOT_FOUND,
    "not_authorized": http_status.HTTP_403_FORBIDDEN,
    "suppressed": http_status.HTTP_409_CONFLICT,
    "approval_required": http_status.HTTP_409_CONFLICT,
    "tenant_dispatch_quarantined": http_status.HTTP_409_CONFLICT,
    "not_quarantined": http_status.HTTP_409_CONFLICT,
    "rate_limited": http_status.HTTP_429_TOO_MANY_REQUESTS,
}


def _error(exc: SlideinError) -> HTTPException:
    status = _STATUS_BY_CODE.get(exc.code, http_status.HTTP_400_BAD_REQUEST)
    return HTTPException(status_code=status, detail=exc.to_dict())


def _outcome_response(outcome) -> dict:
    payload = outcome.to_dict()
    payload["ok"] = outcome.status != "failed"
    if outcome.status == "failed":
        payload["recovery_action"] = outcome.recovery_action
        payload["retryable"] = outcome.retryable
    return payload


# ---------------------------------------------------------------------------
# Drafts
# ---------------------------------------------------------------------------

@router.get("/tenants/{tenant_id}/drafts", tags=["outreach"])
async def list_drafts(
    tenant_id: str,
    status: str | None = Query(None),
    prospect_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    async with session_scope() as session:
        await module_gate(session, auth.tenant_id, "personalization", "outreach")
        rows, total = await PersonalizationService(session).list_drafts(
            auth.tenant_id, limit=limit, status=status, prospect_id=prospect_id
        )
    return {"data": rows, "total": total}


@router.get("/tenants/{tenant_id}/drafts/{draft_id}", tags=["outreach"])
async def get_draft(
    tenant_id: str, draft_id: str, auth: AuthContext = Depends(resolve_workspace)
) -> dict:
    async with session_scope() as session:
        await module_gate(session, auth.tenant_id, "personalization", "outreach")
        try:
            return await PersonalizationService(session).draft_detail(
                auth.tenant_id, draft_id
            )
        except SlideinError as exc:
            raise _error(exc)


@router.post("/tenants/{tenant_id}/drafts/{draft_id}/edit", tags=["outreach"])
async def edit_draft(
    tenant_id: str,
    draft_id: str,
    payload: dict = Body(...),
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    require_role(auth, "operator")
    async with session_scope() as session:
        await module_gate(session, auth.tenant_id, "personalization")
        try:
            row = await PersonalizationService(session).edit_draft(
                tenant_id=auth.tenant_id,
                draft_id=draft_id,
                subject=str(payload.get("subject") or ""),
                body=str(payload.get("body") or ""),
                actor=f"user:{auth.role}",
                change_reason=str(payload.get("change_reason") or "human edit"),
            )
            detail = await PersonalizationService(session).draft_detail(
                auth.tenant_id, draft_id
            )
        except SlideinError as exc:
            raise _error(exc)
    return {"draft": row, "detail": detail}


@router.post("/tenants/{tenant_id}/drafts/{draft_id}/approve", tags=["outreach"])
async def approve_draft(
    tenant_id: str,
    draft_id: str,
    payload: dict = Body(default={}),
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    require_role(auth, "operator")
    async with session_scope() as session:
        await module_gate(session, auth.tenant_id, "outreach")
        service = PersonalizationService(session)
        try:
            row = await OutreachService(session).approve_draft(
                tenant_id=auth.tenant_id,
                draft_id=draft_id,
                actor=f"user:{auth.role}",
                note=str(payload.get("note") or ""),
            )
        except SlideinError as exc:
            raise _error(exc)
    return {"draft": row}


@router.post("/tenants/{tenant_id}/drafts/{draft_id}/revoke-approval", tags=["outreach"])
async def revoke_approval(
    tenant_id: str, draft_id: str, auth: AuthContext = Depends(resolve_workspace)
) -> dict:
    require_role(auth, "operator")
    async with session_scope() as session:
        await module_gate(session, auth.tenant_id, "outreach")
        try:
            row = await OutreachService(session).revoke_approval(
                tenant_id=auth.tenant_id, draft_id=draft_id, actor=f"user:{auth.role}"
            )
        except SlideinError as exc:
            raise _error(exc)
    return {"draft": row}


@router.post("/tenants/{tenant_id}/drafts/{draft_id}/reject", tags=["outreach"])
async def reject_draft(
    tenant_id: str,
    draft_id: str,
    payload: dict = Body(...),
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    require_role(auth, "operator")
    async with session_scope() as session:
        await module_gate(session, auth.tenant_id, "outreach")
        try:
            row = await PersonalizationService(session).reject_draft(
                tenant_id=auth.tenant_id,
                draft_id=draft_id,
                reason=str(payload.get("reason") or ""),
                actor=f"user:{auth.role}",
            )
        except SlideinError as exc:
            raise _error(exc)
    return {"draft": row}


@router.post("/tenants/{tenant_id}/drafts/{draft_id}/send", tags=["outreach"])
async def send_draft(
    tenant_id: str,
    draft_id: str,
    payload: dict = Body(default={}),
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    """Authorized dispatch. `approved: false` runs the policy checks only and
    returns the blocking reason without sending."""
    require_role(auth, "operator")
    attempt_send = payload.get("approved", True)

    async def executor(stage_payload: dict, session) -> dict:
        outreach = OutreachService(session)
        policy = await outreach.policy(auth.tenant_id)
        draft_row = await PersonalizationService(session).get_draft(
            auth.tenant_id, draft_id
        )
        if draft_row is None:
            raise NotFoundError(
                f"Draft {draft_id!r} does not exist in this workspace",
                code="draft_not_found",
                recovery_action="regenerate_draft",
            )

        if not attempt_send:
            blocked = await _policy_block(session, auth.tenant_id, policy, draft_row)
            if blocked is not None:
                return {
                    "status": "failed",
                    "error": {
                        "code": blocked[0],
                        "message": blocked[1],
                        "recovery_action": blocked[2],
                    },
                    "from_status": draft_row["status"],
                    "to_status": draft_row["status"],
                }
            return {
                "status": "succeeded",
                "outputs": {
                    "policy": policy,
                    "draft_status": draft_row["status"],
                    "checks_passed": True,
                },
                "needs_review": [],
                "from_status": draft_row["status"],
                "to_status": draft_row["status"],
            }

        result = await outreach.send_draft(
            tenant_id=auth.tenant_id,
            draft_id=draft_id,
            actor=f"user:{auth.role}",
            sender_email=str(payload.get("sender_email") or ""),
            transport_config=payload.get("transport") or {},
        )
        return {
            "status": "succeeded",
            "outputs": result,
            "needs_review": [],
            "from_status": "draft_ready",
            "to_status": "in_campaign",
        }

    async with session_scope() as session:
        await module_gate(session, auth.tenant_id, "outreach")
        runner = StageRunner(session)
        outcome = await runner.run(
            StageName.OUTREACH,
            tenant_id=auth.tenant_id,
            payload={"draft_id": draft_id, "approved": bool(attempt_send)},
            actor=f"user:{auth.role}",
            role=auth.role,
            subject_type="draft",
            subject_id=draft_id,
            executor=executor,
        )
    if outcome.status == "failed":
        raise _error(
            SlideinError(
                outcome.error_message,
                code=outcome.error_code,
                details=outcome.details,
                recovery_action=outcome.recovery_action,
            )
        )
    return _outcome_response(outcome)


async def _policy_block(session, tenant_id: str, policy: dict, draft_row: dict) -> tuple[str, str, str] | None:
    from ...services.suppression import SuppressionService

    outreach = OutreachService(session)
    if policy.get("require_approval") and draft_row["status"] != "approved":
        return (
            "approval_required",
            "This draft has not been approved, so it may not be sent",
            "approve_draft",
        )
    suppressions = SuppressionService(session)
    discovery = DiscoveryService(session)
    prospect = await discovery.get_prospect(tenant_id, draft_row["prospect_id"])
    if prospect is not None:
        blocked = await suppressions.is_suppressed(tenant_id, prospect.email)
        if blocked is not None:
            return ("suppressed", f"{prospect.email} is suppressed", "review_suppression")
    limit_error = await outreach._check_limits(tenant_id, policy)
    if limit_error is not None:
        return (limit_error.code, limit_error.message, limit_error.recovery_action)
    if not await outreach._default_sender(tenant_id, policy):
        return (
            "provider_unavailable",
            "No sending identity is configured for this workspace",
            "retry_stage",
        )
    try:
        DeliverabilityGuard(tenant_id).validate_pre_send_compliance(policy)
    except SlideinError as exc:
        return (exc.code, exc.message, exc.recovery_action)
    return None


# ---------------------------------------------------------------------------
# Sending policy + suppression
# ---------------------------------------------------------------------------

@router.get("/tenants/{tenant_id}/policy", tags=["outreach"])
async def get_policy(tenant_id: str, auth: AuthContext = Depends(resolve_workspace)) -> dict:
    async with session_scope() as session:
        await module_gate(session, auth.tenant_id, "outreach")
        return {"policy": await OutreachService(session).policy(auth.tenant_id)}


@router.put("/tenants/{tenant_id}/policy", tags=["outreach"])
async def save_policy(
    tenant_id: str,
    payload: dict = Body(...),
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    require_role(auth, "admin")
    async with session_scope() as session:
        await module_gate(session, auth.tenant_id, "outreach")
        return {"policy": await OutreachService(session).save_policy(
            auth.tenant_id, payload, actor=f"user:{auth.role}"
        )}


@router.get("/tenants/{tenant_id}/deliverability", tags=["outreach"])
async def deliverability_status(
    tenant_id: str, auth: AuthContext = Depends(resolve_workspace)
) -> dict:
    """Shared-IP isolation state: quarantine flag, rolling bounce/complaint
    rates against the trip thresholds, and the per-tenant send caps."""
    async with session_scope() as session:
        await module_gate(session, auth.tenant_id, "outreach")
        return {"deliverability": await OutreachService(session).deliverability_status(
            auth.tenant_id
        )}


@router.post("/tenants/{tenant_id}/quarantine/resolve", tags=["outreach"])
async def resolve_quarantine(
    tenant_id: str,
    payload: dict = Body(default={}),
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    """Abuse review: after inspecting the workspace's delivery metrics, an
    admin clears the sending quarantine. The decision and the reviewer are
    recorded in the activity log."""
    require_role(auth, "admin")
    async with session_scope() as session:
        await module_gate(session, auth.tenant_id, "outreach")
        try:
            return {"policy": await OutreachService(session).resolve_quarantine(
                auth.tenant_id,
                actor=f"user:{auth.role}",
                note=str(payload.get("note") or ""),
            )}
        except SlideinError as exc:
            raise _error(exc)


@router.get("/tenants/{tenant_id}/sending", tags=["outreach"])
async def sending_status(
    tenant_id: str, auth: AuthContext = Depends(resolve_workspace)
) -> dict:
    """Tenant sending configuration and reputation-isolation status.

    Shows the sending mode, the assigned egress pool / provider route,
    whether that route has been verified, and the current
    circuit-breaker state — with honest wording about what is *not*
    isolated.
    """
    async with session_scope() as session:
        await module_gate(session, auth.tenant_id, "outreach")
        outreach = OutreachService(session)
        return {
            "sending": await outreach.sending.get_config(auth.tenant_id),
            "circuit": await outreach.circuit_breaker.get_circuit_state(auth.tenant_id),
        }


@router.put("/tenants/{tenant_id}/sending", tags=["outreach"])
async def save_sending_config(
    tenant_id: str,
    payload: dict = Body(...),
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    """Operator update of the tenant's sending configuration.

    Sets the sending mode, the assigned egress pool or provider route,
    and whether that route has been verified. Shared mode always clears
    any dedicated assignment.
    """
    require_role(auth, "admin")
    async with session_scope() as session:
        await module_gate(session, auth.tenant_id, "outreach")
        try:
            return {
                "sending": await OutreachService(session).sending.save_config(
                    auth.tenant_id,
                    payload,
                    actor=f"user:{auth.role}",
                )
            }
        except SlideinError as exc:
            raise _error(exc)


@router.post("/tenants/{tenant_id}/circuit/pause", tags=["outreach"])
async def pause_circuit(
    tenant_id: str,
    payload: dict = Body(default={}),
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    """Operator pause: stop this tenant's outbound mail until an abuse
    review. Only this tenant's circuit is affected."""
    require_role(auth, "admin")
    async with session_scope() as session:
        await module_gate(session, auth.tenant_id, "outreach")
        try:
            return {
                "circuit": await OutreachService(session).circuit_breaker.open(
                    auth.tenant_id,
                    reason=str(payload.get("reason") or "operator pause"),
                    opened_by=f"user:{auth.role}",
                )
            }
        except SlideinError as exc:
            raise _error(exc)


@router.post("/tenants/{tenant_id}/circuit/probe", tags=["outreach"])
async def start_probe(
    tenant_id: str,
    payload: dict = Body(default={}),
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    """Operator start of recovery: allow a limited probe batch after an
    abuse review."""
    require_role(auth, "admin")
    async with session_scope() as session:
        await module_gate(session, auth.tenant_id, "outreach")
        try:
            return {
                "circuit": await OutreachService(session).circuit_breaker.start_recovery_probe(
                    auth.tenant_id,
                    started_by=f"user:{auth.role}",
                )
            }
        except SlideinError as exc:
            raise _error(exc)


@router.post("/tenants/{tenant_id}/circuit/resume", tags=["outreach"])
async def resume_circuit(
    tenant_id: str,
    payload: dict = Body(default={}),
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    """Operator resume: this tenant may send again after an abuse review."""
    require_role(auth, "admin")
    async with session_scope() as session:
        await module_gate(session, auth.tenant_id, "outreach")
        try:
            return {
                "circuit": await OutreachService(session).circuit_breaker.resolve(
                    auth.tenant_id,
                    resolved_by=f"user:{auth.role}",
                    note=str(payload.get("note") or ""),
                )
            }
        except SlideinError as exc:
            raise _error(exc)


@router.get("/tenants/{tenant_id}/suppression", tags=["outreach"])
async def list_suppression(
    tenant_id: str,
    limit: int = Query(100, ge=1, le=500),
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    async with session_scope() as session:
        await module_gate(session, auth.tenant_id, "outreach")
        rows, total = await OutreachService(session).list_suppression(
            auth.tenant_id, limit=limit
        )
    return {"data": rows, "total": total}


@router.post("/tenants/{tenant_id}/suppression", tags=["outreach"])
async def add_suppression(
    tenant_id: str,
    payload: dict = Body(...),
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    require_role(auth, "operator")
    async with session_scope() as session:
        await module_gate(session, auth.tenant_id, "outreach")
        try:
            row = await OutreachService(session).add_suppression(
                tenant_id=auth.tenant_id,
                email=str(payload.get("email") or ""),
                reason=str(payload.get("reason") or "manual_admin"),
                note=str(payload.get("note") or ""),
                actor=f"user:{auth.role}",
            )
        except SlideinError as exc:
            raise _error(exc)
    return {"record": row}


@router.delete("/tenants/{tenant_id}/suppression/{suppression_id}", tags=["outreach"])
async def remove_suppression(
    tenant_id: str,
    suppression_id: str,
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    require_role(auth, "operator")
    async with session_scope() as session:
        await module_gate(session, auth.tenant_id, "outreach")
        removed = await OutreachService(session).remove_suppression(
            auth.tenant_id, suppression_id
        )
        if not removed:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail={"code": "not_found", "message": "Suppression record not found"},
            )
    return {"removed": True}


# ---------------------------------------------------------------------------
# Sent messages + provider events
# ---------------------------------------------------------------------------

@router.get("/tenants/{tenant_id}/sent", tags=["outreach"])
async def list_sent(
    tenant_id: str,
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    async with session_scope() as session:
        await module_gate(session, auth.tenant_id, "outreach")
        rows, total = await OutreachService(session).list_sent(
            auth.tenant_id, limit=limit, status=status
        )
        counts = await OutreachService(session).delivery_counts(auth.tenant_id)
    return {"data": rows, "total": total, "counts": counts}


@router.post("/tenants/{tenant_id}/events", tags=["outreach"])
async def record_event(
    tenant_id: str,
    payload: dict = Body(...),
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    """Provider webhook: delivery/bounce/complaint/unsubscribe events."""
    require_role(auth, "service")
    async with session_scope() as session:
        await module_gate(session, auth.tenant_id, "outreach")
        try:
            result = await OutreachService(session).record_event(
                tenant_id=auth.tenant_id,
                sent_message_id=payload.get("sent_message_id"),
                message_id=payload.get("message_id"),
                recipient_email=str(payload.get("recipient_email") or ""),
                event_type=str(payload.get("event_type") or ""),
                provider=str(payload.get("provider") or ""),
                detail=str(payload.get("detail") or ""),
                payload=payload.get("payload") or {},
                actor=f"webhook:{auth.role}",
            )
        except SlideinError as exc:
            raise _error(exc)
    return result


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------

@router.get("/tenants/{tenant_id}/conversations", tags=["conversations"])
async def list_conversations(
    tenant_id: str,
    requires_action: bool | None = Query(None),
    intent: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    async with session_scope() as session:
        await module_gate(session, auth.tenant_id, "inbox")
        rows, total = await ConversationService(session).list_conversations(
            auth.tenant_id,
            limit=limit,
            requires_action=requires_action,
            intent=intent,
        )
    return {"data": rows, "total": total}


@router.get("/tenants/{tenant_id}/conversations/{conversation_id}", tags=["conversations"])
async def get_conversation(
    tenant_id: str, conversation_id: str, auth: AuthContext = Depends(resolve_workspace)
) -> dict:
    async with session_scope() as session:
        await module_gate(session, auth.tenant_id, "inbox")
        try:
            return await ConversationService(session).conversation_detail(
                auth.tenant_id, conversation_id
            )
        except SlideinError as exc:
            raise _error(exc)


@router.post("/tenants/{tenant_id}/conversations/{conversation_id}/close", tags=["conversations"])
async def close_conversation(
    tenant_id: str, conversation_id: str, auth: AuthContext = Depends(resolve_workspace)
) -> dict:
    require_role(auth, "operator")
    async with session_scope() as session:
        await module_gate(session, auth.tenant_id, "inbox")
        try:
            row = await ConversationService(session).close_conversation(
                tenant_id=auth.tenant_id, conversation_id=conversation_id,
                actor=f"user:{auth.role}",
            )
        except SlideinError as exc:
            raise _error(exc)
    return {"conversation": row}


@router.post("/tenants/{tenant_id}/conversations/{conversation_id}/reopen", tags=["conversations"])
async def reopen_conversation(
    tenant_id: str, conversation_id: str, auth: AuthContext = Depends(resolve_workspace)
) -> dict:
    require_role(auth, "operator")
    async with session_scope() as session:
        await module_gate(session, auth.tenant_id, "inbox")
        try:
            row = await ConversationService(session).reopen_conversation(
                tenant_id=auth.tenant_id, conversation_id=conversation_id,
                actor=f"user:{auth.role}",
            )
        except SlideinError as exc:
            raise _error(exc)
    return {"conversation": row}


@router.post("/webhooks/inbound", tags=["conversations"])
async def inbound_webhook(
    payload: dict = Body(...),
    auth: AuthContext = Depends(require_auth),
) -> dict:
    """Inbound reply ingest. Threads to the outbound message, classifies
    intent, applies policy and records the reply on the same prospect."""
    require_role(auth, "service")

    async def executor(stage_payload: dict, session) -> dict:
        result = await ConversationService(session).handle_reply(
            tenant_id=auth.tenant_id,
            sender_email=stage_payload.get("sender_email", ""),
            subject=stage_payload.get("subject", ""),
            body=stage_payload.get("body", ""),
            in_reply_to=stage_payload.get("in_reply_to", ""),
            thread_id=stage_payload.get("thread_id", ""),
            actor=f"webhook:{auth.role}",
        )
        needs_review = []
        if result["intent_confidence"] < 0.5:
            needs_review.append("intent could not be classified with confidence")
        if result["threaded_to"] is None:
            needs_review.append("reply did not match a tracked outbound message")
        return {
            "status": "succeeded",
            "outputs": result,
            "needs_review": needs_review,
            "from_status": "in_campaign",
            "to_status": (
                "opted_out" if result["suppressed"] else "replied"
            ),
        }

    async with session_scope() as session:
        runner = StageRunner(session)
        outcome = await runner.run(
            StageName.CONVERSE,
            tenant_id=auth.tenant_id,
            payload={
                "sender_email": str(payload.get("sender_email") or payload.get("from") or ""),
                "subject": str(payload.get("subject") or ""),
                "body": str(payload.get("body") or ""),
                "in_reply_to": str(payload.get("in_reply_to") or ""),
                "thread_id": str(payload.get("thread_id") or ""),
            },
            actor=f"webhook:{auth.role}",
            role=auth.role,
            executor=executor,
        )
    if outcome.status == "failed":
        raise _error(
            SlideinError(
                outcome.error_message,
                code=outcome.error_code,
                details=outcome.details,
                recovery_action=outcome.recovery_action,
            )
        )
    return _outcome_response(outcome)
