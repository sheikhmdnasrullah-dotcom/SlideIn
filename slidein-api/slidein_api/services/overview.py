"""Overview — the summarize stage.

Reads only persisted records and answers: what is in the pipeline, what
is stuck, what needs a human, and what the next action is per prospect.
No record is mutated here.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..contracts import HANDOFFS, StageName
from ..models import (
    ProspectStatus,
    Conversation,
    DraftStatus,
    InboundReply,
    MessageDraft,
    Prospect,
    RunStatus,
    SentMessage,
    StageRun,
)
from ..serialize import prospect

#: The ordered funnel the Overview renders.
FUNNEL: tuple[tuple[str, str], ...] = (
    ("discovered", "Discovered"),
    ("researched", "Researched"),
    ("qualified", "Qualified"),
    ("draft_ready", "Draft ready"),
    ("in_campaign", "In campaign"),
    ("replied", "Replied"),
)

STAGE_LABELS: dict[str, str] = {
    StageName.CONFIGURE.value: "Business Profile",
    StageName.DISCOVER.value: "Discovery",
    StageName.RESEARCH.value: "Research",
    StageName.QUALIFY.value: "Qualification",
    StageName.PERSONALIZE.value: "Personalization",
    StageName.OUTREACH.value: "Outreach",
    StageName.CONVERSE.value: "Conversations",
    StageName.SYNTHESIZE.value: "Overview",
}

NEXT_ACTION: dict[str, tuple[str, str]] = {
    "discovered": ("run_research", "Run research to gather evidence"),
    "researching": ("finish_research", "Research is in progress"),
    "researched": ("run_qualification", "Score this prospect against the ICP"),
    "qualified": ("prepare_draft", "Prepare a personalized draft"),
    "draft_ready": ("review_draft", "Review and approve the draft"),
    "in_campaign": ("await_reply", "Waiting for a reply"),
    "replied": ("handle_reply", "Handle the inbound reply"),
    "disqualified": ("no_action", "Disqualified"),
    "opted_out": ("no_action", "Opted out"),
}


class OverviewService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def summary(self, tenant_id: str, *, attention_limit: int = 8) -> dict:
        counts = await self._pipeline_counts(tenant_id)
        drafts = await self._draft_counts(tenant_id)
        delivery = await self._delivery_counts(tenant_id)
        health = await self._stage_health(tenant_id)
        attention = await self._attention(tenant_id, limit=attention_limit)
        next_actions = await self._next_actions(tenant_id, limit=attention_limit)
        sources = await self._source_breakdown(tenant_id)

        total = sum(counts.values())
        conversion = {}
        replied = counts.get("replied", 0)
        conversion["discovered_to_replied"] = (
            round(replied / total * 100, 1) if total else 0.0
        )
        qualified = counts.get("qualified", 0) + counts.get("draft_ready", 0) + counts.get(
            "in_campaign", 0
        ) + replied
        conversion["discovered_to_qualified"] = (
            round(qualified / total * 100, 1) if total else 0.0
        )
        answered = delivery.get("replied", 0) + 0  # replies tracked separately
        sent_total = (
            delivery.get("accepted", 0)
            + delivery.get("delivered", 0)
            + delivery.get("bounced", 0)
            + delivery.get("complained", 0)
            + delivery.get("submitted", 0)
        )
        conversion["sent_to_replied"] = (
            round(replied / sent_total * 100, 1) if sent_total else 0.0
        )

        return {
            "tenant_id": tenant_id,
            "counts": counts,
            "total_prospects": total,
            "funnel": [
                {"status": status, "label": label, "count": counts.get(status, 0)}
                for status, label in FUNNEL
            ],
            "drafts": drafts,
            "delivery": delivery,
            "stage_health": health,
            "attention": attention,
            "next_actions": next_actions,
            "sources": sources,
            "conversion": conversion,
            "replies_received": await self._reply_count(tenant_id),
            "open_conversations": await self._open_conversations(tenant_id),
            "cleared_replied": answered,
        }

    # -- aggregates --------------------------------------------------------

    async def _pipeline_counts(self, tenant_id: str) -> dict[str, int]:
        rows = (
            await self.session.execute(
                select(Prospect.status, func.count())
                .where(Prospect.tenant_id == tenant_id, Prospect.deleted_at.is_(None))
                .group_by(Prospect.status)
            )
        ).all()
        # Zero-fill so every section renders a stable set of buckets.
        counts = {status.value: 0 for status in ProspectStatus}
        counts.update({status: int(count) for status, count in rows})
        return counts

    async def _draft_counts(self, tenant_id: str) -> dict[str, int]:
        rows = (
            await self.session.execute(
                select(MessageDraft.status, func.count())
                .where(MessageDraft.tenant_id == tenant_id)
                .group_by(MessageDraft.status)
            )
        ).all()
        return {status: int(count) for status, count in rows}

    async def _delivery_counts(self, tenant_id: str) -> dict[str, int]:
        rows = (
            await self.session.execute(
                select(SentMessage.delivery_status, func.count())
                .where(SentMessage.tenant_id == tenant_id)
                .group_by(SentMessage.delivery_status)
            )
        ).all()
        return {status: int(count) for status, count in rows}

    async def _stage_health(self, tenant_id: str) -> dict[str, dict[str, int]]:
        rows = (
            await self.session.execute(
                select(StageRun.stage, StageRun.status, func.count())
                .where(StageRun.tenant_id == tenant_id)
                .group_by(StageRun.stage, StageRun.status)
            )
        ).all()
        health: dict[str, dict[str, int]] = {}
        for stage, status, count in rows:
            bucket = health.setdefault(
                stage, {"succeeded": 0, "needs_review": 0, "failed": 0}
            )
            key = (
                "succeeded"
                if status == RunStatus.SUCCEEDED.value
                else "needs_review"
                if status == RunStatus.NEEDS_REVIEW.value
                else "failed"
            )
            bucket[key] += int(count)
        return {stage: health[stage] for stage in sorted(health)}

    async def _source_breakdown(self, tenant_id: str) -> list[dict]:
        rows = (
            await self.session.execute(
                select(Prospect.source, func.count())
                .where(Prospect.tenant_id == tenant_id, Prospect.deleted_at.is_(None))
                .group_by(Prospect.source)
                .order_by(func.count().desc())
            )
        ).all()
        return [{"source": src, "count": int(count)} for src, count in rows]

    async def _reply_count(self, tenant_id: str) -> int:
        return int(
            (
                await self.session.execute(
                    select(func.count())
                    .select_from(InboundReply)
                    .where(InboundReply.tenant_id == tenant_id)
                )
            ).scalar_one()
        )

    async def _open_conversations(self, tenant_id: str) -> int:
        return int(
            (
                await self.session.execute(
                    select(func.count())
                    .select_from(Conversation)
                    .where(
                        Conversation.tenant_id == tenant_id,
                        Conversation.requires_action.is_(True),
                    )
                )
            ).scalar_one()
        )

    async def _attention(self, tenant_id: str, *, limit: int) -> list[dict]:
        """Real problems, each with the record and the recovery action."""
        from ..errors import RECOVERY_ACTION

        items: list[dict] = []

        failed_runs = (
            await self.session.execute(
                select(StageRun)
                .where(
                    StageRun.tenant_id == tenant_id,
                    StageRun.status == RunStatus.FAILED.value,
                )
                .order_by(StageRun.started_at.desc())
                .limit(limit)
            )
        ).scalars().all()
        for run in failed_runs:
            items.append(
                {
                    "kind": "stage_failed",
                    "severity": "danger",
                    "stage": run.stage,
                    "stage_label": STAGE_LABELS.get(run.stage, run.stage),
                    "subject_id": run.subject_id,
                    "subject_type": run.subject_type,
                    "title": f"{STAGE_LABELS.get(run.stage, run.stage)} failed",
                    "detail": run.error_message,
                    "reason": run.error_code,
                    "recovery_action": run.recovery_action
                    or RECOVERY_ACTION.get(run.error_code, "retry_stage"),
                    "retryable": run.error_code in ("source_unavailable", "provider_unavailable",
                                                    "rate_limited", "transport_rejected"),
                    "attempt": run.attempt,
                    "max_attempts": run.max_attempts,
                    "run_id": run.id,
                    "href": self._subject_href(run.subject_type, run.subject_id),
                    "created_at": run.started_at.isoformat() if run.started_at else None,
                }
            )

        pending_drafts = (
            await self.session.execute(
                select(MessageDraft)
                .where(
                    MessageDraft.tenant_id == tenant_id,
                    MessageDraft.status == DraftStatus.PENDING_REVIEW.value,
                )
                .order_by(MessageDraft.updated_at.desc())
                .limit(limit)
            )
        ).scalars().all()
        for d in pending_drafts:
            items.append(
                {
                    "kind": "draft_pending_approval",
                    "severity": "warn",
                    "stage": StageName.PERSONALIZE.value,
                    "stage_label": STAGE_LABELS[StageName.PERSONALIZE.value],
                    "subject_id": d.prospect_id,
                    "subject_type": "draft",
                    "title": "Draft waiting for approval",
                    "detail": d.subject,
                    "reason": "approval_required",
                    "recovery_action": "approve_draft",
                    "retryable": False,
                    "run_id": None,
                    "href": f"/outreach?draft={d.id}",
                    "draft_id": d.id,
                    "created_at": d.updated_at.isoformat() if d.updated_at else None,
                }
            )

        open_conversations = (
            await self.session.execute(
                select(Conversation)
                .where(
                    Conversation.tenant_id == tenant_id,
                    Conversation.requires_action.is_(True),
                )
                .order_by(Conversation.last_message_at.desc().nullslast())
                .limit(limit)
            )
        ).scalars().all()
        for c in open_conversations:
            items.append(
                {
                    "kind": "conversation_needs_action",
                    "severity": "info",
                    "stage": StageName.CONVERSE.value,
                    "stage_label": STAGE_LABELS[StageName.CONVERSE.value],
                    "subject_id": c.prospect_id,
                    "subject_type": "conversation",
                    "title": "Reply needs a response",
                    "detail": c.subject or "Inbound reply",
                    "reason": c.intent,
                    "recovery_action": "handle_reply",
                    "retryable": False,
                    "run_id": None,
                    "href": "/conversations",
                    "conversation_id": c.id,
                    "created_at": c.last_message_at.isoformat() if c.last_message_at else None,
                }
            )

        severity_rank = {"danger": 0, "warn": 1, "info": 2}
        items.sort(key=lambda i: severity_rank.get(i["severity"], 3))
        return items[:limit]

    async def _next_actions(self, tenant_id: str, *, limit: int) -> list[dict]:
        """One concrete next action per prospect that is actually blocked."""
        rows = (
            await self.session.execute(
                select(Prospect)
                .where(Prospect.tenant_id == tenant_id, Prospect.deleted_at.is_(None))
                .order_by(Prospect.updated_at.desc())
                .limit(200)
            )
        ).scalars().all()

        out: list[dict] = []
        for row in rows:
            action, label = NEXT_ACTION.get(row.status, ("no_action", "No action"))
            if action == "no_action":
                continue
            if row.status == "discovered" and not await self._has_evidence(row.id):
                pass
            out.append(
                {
                    "prospect_id": row.id,
                    "name": f"{row.first_name} {row.last_name}".strip() or row.email,
                    "company": row.company_name,
                    "status": row.status,
                    "action": action,
                    "action_label": label,
                    "score": row.qualification_score,
                    "href": f"/prospects/{row.id}",
                }
            )
            if len(out) >= limit:
                break
        return out

    async def _has_evidence(self, prospect_id: str) -> bool:
        from ..models import EvidenceItem

        return (
            await self.session.execute(
                select(func.count())
                .select_from(EvidenceItem)
                .where(EvidenceItem.prospect_id == prospect_id)
            )
        ).scalar_one() > 0

    @staticmethod
    def _subject_href(subject_type: str, subject_id: str) -> str:
        if subject_type == "draft":
            return f"/outreach?draft={subject_id}"
        return f"/prospects/{subject_id}"

    async def handoffs(self, tenant_id: str) -> list[dict]:
        """What each stage currently holds — the connected-workflow view."""
        counts = await self._pipeline_counts(tenant_id)
        drafts = await self._draft_counts(tenant_id)
        health = await self._stage_health(tenant_id)
        rows: list[dict] = []
        for handoff in HANDOFFS:
            items = []
            if handoff.from_stage is StageName.DISCOVER:
                items = [{"count": counts.get("discovered", 0), "label": "discovered"}]
            elif handoff.from_stage is StageName.RESEARCH:
                items = [{"count": counts.get("researched", 0), "label": "researched"}]
            elif handoff.from_stage is StageName.QUALIFY:
                items = [{"count": counts.get("qualified", 0), "label": "qualified"}]
            elif handoff.from_stage is StageName.PERSONALIZE:
                items = [{"count": drafts.get("pending_review", 0), "label": "pending review"}]
            elif handoff.from_stage is StageName.OUTREACH:
                items = [{"count": counts.get("in_campaign", 0), "label": "in campaign"}]
            elif handoff.from_stage is StageName.CONVERSE:
                items = [
                    {"count": await self._open_conversations(tenant_id), "label": "need action"}
                ]
            else:
                items = [{"count": counts.get("discovered", 0), "label": "discovered"}]

            stage_health = health.get(handoff.from_stage.value, {})
            rows.append(
                {
                    "from": handoff.from_stage.value,
                    "from_label": STAGE_LABELS.get(handoff.from_stage.value, handoff.from_stage.value),
                    "to": handoff.to_stage.value,
                    "to_label": STAGE_LABELS.get(handoff.to_stage.value, handoff.to_stage.value),
                    "carried": list(handoff.carried),
                    "blocked_by": list(handoff.blocked_by),
                    "waiting": items,
                    "health": stage_health,
                }
            )
        return rows

    async def prospect_detail(self, tenant_id: str, prospect_id: str) -> dict:
        """Everything the sections know about one prospect, in one payload."""
        from ..errors import NotFoundError
        from ..models import DeliveryEvent, EvidenceItem, OfferMatch, QualificationResult
        from ..runtime import StageRunner
        from ..serialize import (
            delivery_event,
            draft,
            evidence,
            offer_match,
            qualification,
            sent_message,
            stage_run,
        )
        from .activity import ActivityService
        from .conversations import ConversationService
        from .personalization import PersonalizationService

        row = await self.session.get(Prospect, prospect_id)
        if row is None or row.tenant_id != tenant_id:
            raise NotFoundError(
                f"Prospect {prospect_id!r} does not exist in this workspace",
                code="prospect_not_found",
                recovery_action="return_to_discovery",
            )

        evidence_rows = (
            await self.session.execute(
                select(EvidenceItem)
                .where(EvidenceItem.prospect_id == row.id)
                .order_by(EvidenceItem.retrieved_at.asc())
            )
        ).scalars().all()
        qualification_rows = (
            await self.session.execute(
                select(QualificationResult)
                .where(QualificationResult.prospect_id == row.id)
                .order_by(QualificationResult.evaluated_at.desc())
            )
        ).scalars().all()
        match_rows = (
            await self.session.execute(
                select(OfferMatch)
                .where(OfferMatch.prospect_id == row.id)
                .order_by(OfferMatch.matched_at.desc())
            )
        ).scalars().all()
        draft_rows = (
            await self.session.execute(
                select(MessageDraft)
                .where(MessageDraft.prospect_id == row.id)
                .order_by(MessageDraft.version.desc())
            )
        ).scalars().all()
        sent_rows = (
            await self.session.execute(
                select(SentMessage)
                .where(SentMessage.prospect_id == row.id)
                .order_by(SentMessage.queued_at.asc())
            )
        ).scalars().all()
        event_rows = (
            await self.session.execute(
                select(DeliveryEvent)
                .where(DeliveryEvent.prospect_id == row.id)
                .order_by(DeliveryEvent.occurred_at.asc())
            )
        ).scalars().all()
        run_rows = (
            await self.session.execute(
                select(StageRun)
                .where(StageRun.subject_id == row.id)
                .order_by(StageRun.started_at.asc())
            )
        ).scalars().all()

        activity_service = ActivityService(self.session)
        conversation_service = ConversationService(self.session)
        personalization = PersonalizationService(self.session)

        conversation_details: list[dict] = []
        conversations, _ = await conversation_service.list_conversations(tenant_id, limit=100)
        for conv in conversations:
            if conv.get("prospect_id") != row.id:
                continue
            conversation_details.append(
                await conversation_service.conversation_detail(tenant_id, conv["id"])
            )

        payload = prospect(row)
        payload["state_history"] = row.state_history or []
        payload["evidence"] = [evidence(r) for r in evidence_rows]
        payload["qualification"] = [qualification(r) for r in qualification_rows]
        payload["offer_matches"] = [offer_match(r) for r in match_rows]
        payload["drafts"] = [draft(r) for r in draft_rows]
        payload["draft_versions"] = {
            d.id: await personalization.list_versions(tenant_id, d.id) for d in draft_rows
        }
        payload["sent_messages"] = [sent_message(r) for r in sent_rows]
        payload["delivery_events"] = [delivery_event(r) for r in event_rows]
        payload["activity"] = await activity_service.for_prospect(tenant_id, row.id)
        payload["conversations"] = conversation_details
        payload["stage_runs"] = [stage_run(r) for r in run_rows]
        return payload


__all__ = ["FUNNEL", "STAGE_LABELS", "OverviewService"]
