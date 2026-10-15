"""Conversations — inbound replies against the same prospect records.

A reply is threaded to the outbound message that produced it (by Message-ID
first, then by subject, then by sender). Reply handling applies policy:
an unsubscribe suppresses the address immediately and opts the prospect
out; otherwise the prospect moves to `replied` and the conversation is
flagged for a human when the intent is not clear.
"""

from __future__ import annotations

import re
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..errors import SlideinError
from ..ids import new_id
from ..models import (
    Conversation,
    ConversationState,
    InboundReply,
    Prospect,
    ProspectStatus,
    ReplyIntent,
    SentMessage,
)
from ..serialize import conversation, prospect, reply

#: Deterministic intent rules. A classifier can replace the scorer without
#: changing the contract or the state effects.
_INTENT_RULES: tuple[tuple[ReplyIntent, tuple[str, ...], str], ...] = (
    (ReplyIntent.UNSUBSCRIBE,
     ("unsubscribe", "remove me", "take me off", "stop emailing", "opt out",
      "do not contact"),
     "Recipient asked to stop receiving email."),
    (ReplyIntent.NOT_INTERESTED,
     ("not interested", "no thanks", "no thank you", "not a fit", "pass on this"),
     "Recipient declined."),
    (ReplyIntent.OUT_OF_OFFICE,
     ("out of office", "on annual leave", "on vacation", "away from my desk",
      "back on"),
     "Automatic out-of-office reply."),
    (ReplyIntent.INFORMATION_REQUEST,
     ("send me", "can you send", "more information", "more info", "1-pager",
      "one-pager", "deck", "pricing", "case study", "brochure"),
     "Recipient asked for information."),
    (ReplyIntent.OBJECTION,
     ("too expensive", "not the right time", "we already use", "no budget",
      "not now", "maybe later"),
     "Recipient raised an objection."),
    (ReplyIntent.INTERESTED,
     ("interested", "sounds good", "let's talk", "lets talk", "tell me more",
      "book a call", "schedule", "yes"),
     "Recipient expressed interest."),
)

_INTENT_ACTIONS: dict[str, str] = {
    ReplyIntent.INTERESTED.value: "Reply personally and offer a call",
    ReplyIntent.INFORMATION_REQUEST.value: "Send the requested material and follow up",
    ReplyIntent.OBJECTION.value: "Address the objection, then offer a short call",
    ReplyIntent.NOT_INTERESTED.value: "Close politely and stop follow-ups",
    ReplyIntent.OUT_OF_OFFICE.value: "No action — re-check after the return date",
    ReplyIntent.UNSUBSCRIBE.value: "Confirm opt-out; do not contact again",
    ReplyIntent.UNCLASSIFIED.value: "Read the reply and classify it",
}

MIN_INTENT_CONFIDENCE = 0.5


def classify(text: str) -> tuple[str, float, str]:
    """Deterministic keyword intent classification with a confidence score."""
    lowered = " ".join(str(text or "").lower().split())
    if not lowered:
        return ReplyIntent.UNCLASSIFIED.value, 0.0, "Empty reply body."

    best_intent = ReplyIntent.UNCLASSIFIED.value
    best_score = 0
    reason = "No intent keyword matched."
    for intent, keywords, description in _INTENT_RULES:
        hits = [k for k in keywords if k in lowered]
        if not hits:
            continue
        # Confidence grows with hits, capped below certainty.
        score = min(0.5 + 0.15 * len(hits), 0.95)
        if score > best_score:
            best_score = score
            best_intent = intent
            reason = f"{description} Matched: {', '.join(hits[:3])}."
    return best_intent.value, round(best_score, 2), reason


class ConversationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def handle_reply(
        self,
        *,
        tenant_id: str,
        sender_email: str,
        subject: str,
        body: str,
        in_reply_to: str = "",
        thread_id: str = "",
        actor: str = "inbound_webhook",
    ) -> dict:
        sender_email = str(sender_email or "").strip().lower()
        if not sender_email:
            raise SlideinError(
                "An inbound reply needs a sender address",
                code="prospect_invalid",
                recovery_action="fix_prospect_record",
            )

        prospect_row = await self._find_prospect(tenant_id, sender_email)
        if prospect_row is None:
            raise SlideinError(
                f"No prospect in this workspace matches {sender_email!r}",
                code="prospect_not_found",
                recovery_action="return_to_discovery",
            )

        outbound = await self._find_outbound(
            tenant_id=tenant_id,
            prospect_id=prospect_row.id,
            recipient_email=sender_email,
            in_reply_to=in_reply_to,
            subject=subject,
        )

        intent, confidence, reason = classify(f"{subject} {body}")
        requires_action = confidence < MIN_INTENT_CONFIDENCE or intent in (
            ReplyIntent.INTERESTED.value,
            ReplyIntent.INFORMATION_REQUEST.value,
            ReplyIntent.OBJECTION.value,
        )

        conv = await self._find_or_create_conversation(
            tenant_id=tenant_id,
            prospect=prospect_row,
            subject=subject,
            thread_id=thread_id or (outbound.message_id if outbound else ""),
        )
        conv.intent = intent
        conv.intent_confidence = confidence
        conv.requires_action = requires_action
        conv.state = (
            ConversationState.OPEN.value
            if requires_action
            else ConversationState.CLOSED.value
        )
        conv.last_message_at = None  # set by the DB default on flush

        reply_row = InboundReply(
            id=new_id("reply"),
            tenant_id=tenant_id,
            conversation_id=conv.id,
            prospect_id=prospect_row.id,
            sent_message_id=outbound.id if outbound else None,
            sender_email=sender_email,
            subject=str(subject or "")[:512],
            body=str(body or ""),
            thread_id=conv.thread_id,
            intent=intent,
            intent_confidence=confidence,
            requires_action=requires_action,
            recommended_action=_INTENT_ACTIONS.get(intent, "Read the reply and act"),
            received_by=actor,
        )
        self.session.add(reply_row)
        await self.session.flush()

        suppressed = False
        if intent == ReplyIntent.UNSUBSCRIBE.value:
            from .suppression import SuppressionService

            await SuppressionService(self.session).add(
                tenant_id=tenant_id,
                email=sender_email,
                reason="opt_out",
                note=f"unsubscribed by reply {reply_row.id}",
                actor=actor,
            )
            await self._transition(
                prospect_row, ProspectStatus.OPTED_OUT.value,
                reason=f"unsubscribed via inbound reply", actor=actor,
            )
            suppressed = True
        elif prospect_row.status in (
            ProspectStatus.IN_CAMPAIGN.value,
            ProspectStatus.REPLIED.value,
        ):
            await self._transition(
                prospect_row, ProspectStatus.REPLIED.value,
                reason=f"inbound reply classified as {intent}", actor=actor,
            )

        if outbound is not None:
            outbound.delivery_status = (
                outbound.delivery_status
                if outbound.delivery_status
                in ("bounced", "complained")
                else "delivered"
            )

        await self.session.flush()

        return {
            "conversation_id": conv.id,
            "conversation": conversation(conv),
            "reply_id": reply_row.id,
            "intent": intent,
            "intent_confidence": confidence,
            "intent_reason": reason,
            "requires_action": requires_action,
            "recommended_action": reply_row.recommended_action,
            "suppressed": suppressed,
            "threaded_to": outbound.id if outbound else None,
            "prospect_id": prospect_row.id,
        }

    # -- internals --------------------------------------------------------

    async def _find_prospect(self, tenant_id: str, email: str) -> Prospect | None:
        row = (
            await self.session.execute(
                select(Prospect).where(
                    Prospect.tenant_id == tenant_id,
                    Prospect.email == email,
                    Prospect.deleted_at.is_(None),
                )
            )
        ).scalars().first()
        return row

    async def _find_outbound(
        self,
        *,
        tenant_id: str,
        prospect_id: str,
        recipient_email: str,
        in_reply_to: str,
        subject: str,
    ) -> SentMessage | None:
        if in_reply_to:
            row = (
                await self.session.execute(
                    select(SentMessage).where(
                        SentMessage.tenant_id == tenant_id,
                        SentMessage.message_id == in_reply_to,
                    )
                )
            ).scalars().first()
            if row is not None:
                return row
        # Fall back to the most recent outbound message to this prospect.
        return (
            await self.session.execute(
                select(SentMessage)
                .where(
                    SentMessage.tenant_id == tenant_id,
                    SentMessage.prospect_id == prospect_id,
                    SentMessage.recipient_email == recipient_email,
                )
                .order_by(SentMessage.queued_at.desc())
            )
        ).scalars().first()

    @staticmethod
    def _normalize_subject(subject: str) -> str:
        text = str(subject or "").strip().lower()
        text = re.sub(r"^(re|fwd|fw)\s*:\s*", "", text)
        text = re.sub(r"^(re|fwd|fw)\s*\(\d+\)\s*:\s*", "", text)
        return text.strip()

    async def _find_or_create_conversation(
        self, *, tenant_id: str, prospect: Prospect, subject: str, thread_id: str
    ) -> Conversation:
        query = select(Conversation).where(
            Conversation.tenant_id == tenant_id, Conversation.prospect_id == prospect.id
        )
        if thread_id:
            query = query.where(Conversation.thread_id == thread_id)
        row = (await self.session.execute(query.order_by(Conversation.created_at.desc()))).scalars().first()
        if row is not None:
            return row
        row = Conversation(
            id=new_id("conversation"),
            tenant_id=tenant_id,
            prospect_id=prospect.id,
            subject=str(subject or "")[:512],
            thread_id=thread_id or new_id("conversation"),
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def _transition(
        self, prospect: Prospect, to_status: str, *, reason: str, actor: str
    ) -> bool:
        from .discovery import DiscoveryService

        if prospect.status == to_status:
            return False
        return await DiscoveryService(self.session).apply_transition(
            prospect, to_status=to_status, reason=reason, actor=actor
        )

    async def list_conversations(
        self, tenant_id: str, *, limit: int = 50, offset: int = 0,
        requires_action: bool | None = None, intent: str | None = None,
    ) -> tuple[list[dict], int]:
        query = Conversation.__table__.select().where(Conversation.tenant_id == tenant_id)
        if requires_action is not None:
            query = query.where(Conversation.requires_action.is_(requires_action))
        if intent:
            query = query.where(Conversation.intent == intent)
        query = query.order_by(Conversation.last_message_at.desc()).limit(limit).offset(offset)
        rows = (await self.session.execute(query)).mappings().all()
        total = (
            await self.session.execute(
                select(func.count()).select_from(Conversation).where(
                    Conversation.tenant_id == tenant_id
                )
            )
        ).scalar_one()
        return [dict(r) for r in rows], total

    async def conversation_detail(self, tenant_id: str, conversation_id: str) -> dict:
        from ..serialize import sent_message

        conv = await self.session.get(Conversation, conversation_id)
        if conv is None or conv.tenant_id != tenant_id:
            raise SlideinError(
                f"Conversation {conversation_id!r} does not exist in this workspace",
                code="prospect_not_found",
                recovery_action="return_to_discovery",
            )
        replies = (
            await self.session.execute(
                select(InboundReply)
                .where(InboundReply.conversation_id == conv.id)
                .order_by(InboundReply.received_at.asc())
            )
        ).scalars().all()
        prospect_row = await self.session.get(Prospect, conv.prospect_id)

        outbound: list[dict] = []
        if prospect_row is not None:
            outbound_rows = (
                await self.session.execute(
                    select(SentMessage)
                    .where(SentMessage.prospect_id == prospect_row.id)
                    .order_by(SentMessage.queued_at.asc())
                )
            ).scalars().all()
            outbound = [sent_message(r) for r in outbound_rows]

        return {
            "conversation": conversation(conv),
            "prospect": prospect(prospect_row) if prospect_row else None,
            "replies": [reply(r) for r in replies],
            "outbound": outbound,
        }

    async def close_conversation(
        self, *, tenant_id: str, conversation_id: str, actor: str
    ) -> dict:
        conv = await self.session.get(Conversation, conversation_id)
        if conv is None or conv.tenant_id != tenant_id:
            raise SlideinError(
                f"Conversation {conversation_id!r} does not exist in this workspace",
                code="prospect_not_found",
                recovery_action="return_to_discovery",
            )
        if conv.state == ConversationState.CLOSED.value:
            raise SlideinError(
                "Conversation is already closed",
                code="draft_not_found",
                recovery_action="review_draft",
            )
        conv.state = ConversationState.CLOSED.value
        conv.requires_action = False
        await self.session.flush()
        return conversation(conv)

    async def reopen_conversation(
        self, *, tenant_id: str, conversation_id: str, actor: str
    ) -> dict:
        conv = await self.session.get(Conversation, conversation_id)
        if conv is None or conv.tenant_id != tenant_id:
            raise SlideinError(
                f"Conversation {conversation_id!r} does not exist in this workspace",
                code="prospect_not_found",
                recovery_action="return_to_discovery",
            )
        conv.state = ConversationState.OPEN.value
        conv.requires_action = True
        await self.session.flush()
        return conversation(conv)


__all__ = ["ConversationService", "classify"]
