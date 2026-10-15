"""Serialization of canonical models into the JSON shapes the client
workspace consumes. One serializer per model — the API and the workflow
runtime read the same payload, so a UI field can never drift from the
stored record.
"""

from __future__ import annotations

from typing import Any

from .models import (
    ActivityLog,
    BusinessProfile,
    ConfigVersion,
    Conversation,
    DeliveryEvent,
    DraftVersion,
    EvidenceItem,
    IcpDefinition,
    InboundReply,
    MessageDraft,
    Offer,
    OfferMatch,
    Prospect,
    QualificationResult,
    SentMessage,
    StageRun,
    SuppressionRecord,
    Tenant,
)


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return value.isoformat()


def prospect(rec: Prospect) -> dict:
    return {
        "id": rec.id,
        "tenant_id": rec.tenant_id,
        "first_name": rec.first_name,
        "last_name": rec.last_name,
        "full_name": f"{rec.first_name} {rec.last_name}".strip(),
        "email": rec.email,
        "phone": rec.phone,
        "company_name": rec.company_name,
        "company_domain": rec.company_domain,
        "job_title": rec.job_title,
        "linkedin_url": rec.linkedin_url,
        "company_size": rec.company_size,
        "location": rec.location,
        "source": rec.source,
        "source_ref": rec.source_ref,
        "source_detail": rec.source_detail or {},
        "status": rec.status,
        "status_reason": rec.status_reason,
        "qualification_score": rec.qualification_score,
        "profile_id": rec.profile_id,
        "profile_version": rec.profile_version,
        "icp_id": rec.icp_id,
        "icp_version": rec.icp_version,
        "offer_id": rec.offer_id,
        "discovered_by": rec.discovered_by,
        "discovered_at": _iso(rec.discovered_at),
        "updated_at": _iso(rec.updated_at),
    }


def profile(rec: BusinessProfile) -> dict:
    return {
        "id": rec.id,
        "tenant_id": rec.tenant_id,
        "legal_name": rec.legal_name,
        "website_url": rec.website_url,
        "industry": rec.industry,
        "company_description": rec.company_description,
        "core_value_prop": rec.core_value_prop,
        "markets_served": rec.markets_served or [],
        "target_roles": rec.target_roles or [],
        "brand_voice": rec.brand_voice,
        "version": rec.version,
        "is_active": rec.is_active,
        "created_by": rec.created_by,
        "created_at": _iso(rec.created_at),
        "updated_at": _iso(rec.updated_at),
    }


def offer(rec: Offer) -> dict:
    return {
        "id": rec.id,
        "tenant_id": rec.tenant_id,
        "profile_id": rec.profile_id,
        "name": rec.name,
        "summary": rec.summary,
        "pain_points_solved": rec.pain_points_solved or [],
        "target_persona": rec.target_persona,
        "proof_points": rec.proof_points or [],
        "version": rec.version,
        "is_active": rec.is_active,
        "created_by": rec.created_by,
        "created_at": _iso(rec.created_at),
        "updated_at": _iso(rec.updated_at),
    }


def icp(rec: IcpDefinition) -> dict:
    return {
        "id": rec.id,
        "tenant_id": rec.tenant_id,
        "profile_id": rec.profile_id,
        "name": rec.name,
        "industries": rec.industries or [],
        "company_size_min": rec.company_size_min,
        "company_size_max": rec.company_size_max,
        "geographies": rec.geographies or [],
        "target_roles": rec.target_roles or [],
        "required_signals": rec.required_signals or [],
        "exclusion_keywords": rec.exclusion_keywords or [],
        "qualify_threshold": rec.qualify_threshold,
        "version": rec.version,
        "is_active": rec.is_active,
        "created_by": rec.created_by,
        "created_at": _iso(rec.created_at),
        "updated_at": _iso(rec.updated_at),
    }


def config_version(rec: ConfigVersion) -> dict:
    return {
        "id": rec.id,
        "tenant_id": rec.tenant_id,
        "entity_type": rec.entity_type,
        "entity_id": rec.entity_id,
        "version": rec.version,
        "snapshot": rec.snapshot or {},
        "actor": rec.actor,
        "reason": rec.reason,
        "created_at": _iso(rec.created_at),
    }


def evidence(rec: EvidenceItem) -> dict:
    return {
        "id": rec.id,
        "tenant_id": rec.tenant_id,
        "prospect_id": rec.prospect_id,
        "evidence_type": rec.evidence_type,
        "claim_text": rec.claim_text,
        "source_url": rec.source_url,
        "source_name": rec.source_name,
        "confidence": rec.confidence,
        "verification_status": rec.verification_status,
        "collector": rec.collector,
        "retrieved_by": rec.retrieved_by,
        "retrieved_at": _iso(rec.retrieved_at),
    }


def qualification(rec: QualificationResult) -> dict:
    return {
        "id": rec.id,
        "tenant_id": rec.tenant_id,
        "prospect_id": rec.prospect_id,
        "icp_id": rec.icp_id,
        "icp_version": rec.icp_version,
        "profile_version": rec.profile_version,
        "score": rec.score,
        "is_qualified": rec.is_qualified,
        "matching_criteria": rec.matching_criteria or [],
        "missing_criteria": rec.missing_criteria or [],
        "explanation": rec.explanation,
        "evaluator": rec.evaluator,
        "evaluated_by": rec.evaluated_by,
        "evaluated_at": _iso(rec.evaluated_at),
    }


def offer_match(rec: OfferMatch) -> dict:
    return {
        "id": rec.id,
        "tenant_id": rec.tenant_id,
        "prospect_id": rec.prospect_id,
        "offer_id": rec.offer_id,
        "offer_version": rec.offer_version,
        "rationale": rec.rationale,
        "evidence_ids": rec.evidence_ids or [],
        "score": rec.score,
        "is_selected": rec.is_selected,
        "matched_by": rec.matched_by,
        "matched_at": _iso(rec.matched_at),
    }


def draft(rec: MessageDraft) -> dict:
    return {
        "id": rec.id,
        "tenant_id": rec.tenant_id,
        "prospect_id": rec.prospect_id,
        "offer_id": rec.offer_id,
        "qualification_id": rec.qualification_id,
        "subject": rec.subject,
        "body": rec.body,
        "version": rec.version,
        "status": rec.status,
        "attributed_evidence_ids": rec.attributed_evidence_ids or [],
        "human_edited": rec.human_edited,
        "profile_version": rec.profile_version,
        "approved_by": rec.approved_by,
        "approved_at": _iso(rec.approved_at),
        "approval_note": rec.approval_note,
        "rejected_by": rec.rejected_by,
        "rejected_reason": rec.rejected_reason,
        "created_by": rec.created_by,
        "created_at": _iso(rec.created_at),
        "updated_at": _iso(rec.updated_at),
    }


def draft_version(rec: DraftVersion) -> dict:
    return {
        "id": rec.id,
        "tenant_id": rec.tenant_id,
        "draft_id": rec.draft_id,
        "version": rec.version,
        "subject": rec.subject,
        "body": rec.body,
        "change_reason": rec.change_reason,
        "changed_by": rec.changed_by,
        "is_human_edit": rec.is_human_edit,
        "created_at": _iso(rec.created_at),
    }


def sent_message(rec: SentMessage) -> dict:
    return {
        "id": rec.id,
        "tenant_id": rec.tenant_id,
        "draft_id": rec.draft_id,
        "draft_version": rec.draft_version,
        "prospect_id": rec.prospect_id,
        "sender_email": rec.sender_email,
        "recipient_email": rec.recipient_email,
        "message_id": rec.message_id,
        "transport": rec.transport,
        "delivery_status": rec.delivery_status,
        "attempt": rec.attempt,
        "error_code": rec.error_code,
        "error_message": rec.error_message,
        "authorized_by": rec.authorized_by,
        "queued_at": _iso(rec.queued_at),
        "sent_at": _iso(rec.sent_at),
        "status_updated_at": _iso(rec.status_updated_at),
    }


def delivery_event(rec: DeliveryEvent) -> dict:
    return {
        "id": rec.id,
        "tenant_id": rec.tenant_id,
        "sent_message_id": rec.sent_message_id,
        "prospect_id": rec.prospect_id,
        "event_type": rec.event_type,
        "provider": rec.provider,
        "detail": rec.detail,
        "payload": rec.payload or {},
        "occurred_at": _iso(rec.occurred_at),
        "recorded_by": rec.recorded_by,
    }


def conversation(rec: Conversation) -> dict:
    return {
        "id": rec.id,
        "tenant_id": rec.tenant_id,
        "prospect_id": rec.prospect_id,
        "subject": rec.subject,
        "thread_id": rec.thread_id,
        "state": rec.state,
        "intent": rec.intent,
        "intent_confidence": rec.intent_confidence,
        "requires_action": rec.requires_action,
        "last_message_at": _iso(rec.last_message_at),
        "created_at": _iso(rec.created_at),
    }


def reply(rec: InboundReply) -> dict:
    return {
        "id": rec.id,
        "tenant_id": rec.tenant_id,
        "conversation_id": rec.conversation_id,
        "prospect_id": rec.prospect_id,
        "sent_message_id": rec.sent_message_id,
        "sender_email": rec.sender_email,
        "subject": rec.subject,
        "body": rec.body,
        "thread_id": rec.thread_id,
        "intent": rec.intent,
        "intent_confidence": rec.intent_confidence,
        "requires_action": rec.requires_action,
        "recommended_action": rec.recommended_action,
        "received_by": rec.received_by,
        "received_at": _iso(rec.received_at),
    }


def suppression(rec: SuppressionRecord) -> dict:
    return {
        "id": rec.id,
        "tenant_id": rec.tenant_id,
        "email": rec.email,
        "domain": rec.domain,
        "reason": rec.reason,
        "note": rec.note,
        "suppressed_by": rec.suppressed_by,
        "suppressed_at": _iso(rec.suppressed_at),
    }


def stage_run(rec: StageRun) -> dict:
    return {
        "id": rec.id,
        "tenant_id": rec.tenant_id,
        "run_key": rec.run_key,
        "stage": rec.stage,
        "subject_type": rec.subject_type,
        "subject_id": rec.subject_id,
        "status": rec.status,
        "attempt": rec.attempt,
        "max_attempts": rec.max_attempts,
        "reason": ", ".join(rec.needs_review or [])
        or rec.error_code
        or "",
        "needs_review": list(rec.needs_review or []),
        "from_status": rec.from_status,
        "to_status": rec.to_status,
        "error_code": rec.error_code,
        "error_message": rec.error_message,
        "recovery_action": rec.recovery_action,
        "retryable": rec.error_code in RETRYABLE_CODES if rec.error_code else False,
        "triggered_by": rec.triggered_by,
        "input_snapshot": rec.input_snapshot or {},
        "output_snapshot": rec.output_snapshot or {},
        "started_at": _iso(rec.started_at),
        "finished_at": _iso(rec.finished_at),
    }


def activity(rec: ActivityLog) -> dict:
    return {
        "id": rec.id,
        "tenant_id": rec.tenant_id,
        "actor": rec.actor,
        "actor_role": rec.actor_role,
        "action": rec.action,
        "entity_type": rec.entity_type,
        "entity_id": rec.entity_id,
        "prospect_id": rec.prospect_id,
        "stage": rec.stage,
        "run_id": rec.run_id,
        "summary": rec.summary,
        "reason": rec.reason,
        "details": rec.details or {},
        "created_at": _iso(rec.created_at),
    }


def tenant(rec: Tenant) -> dict:
    return {
        "id": rec.id,
        "name": rec.name,
        "slug": rec.slug,
        "plan_tier": rec.plan_tier,
        "autonomy_level": rec.autonomy_level,
        "is_active": rec.is_active,
        "created_at": _iso(rec.created_at),
    }


from .errors import RETRYABLE as RETRYABLE_CODES  # noqa: E402  (circular-safe)
