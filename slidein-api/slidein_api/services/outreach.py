"""Outreach — approval, sending policy, dispatch and delivery events.

Sending is authorized, never implicit:

  1. the draft must be in `approved` (the Authorization step),
  2. the recipient must not be suppressed,
  3. the tenant's sending policy (daily cap, quiet hours, rate) must pass.

Only then does the transport run. The default transport is `dry_run`,
which records the full dispatch and delivery lifecycle but does not put
bytes on the wire — real sending requires an explicit `SLIDEIN_TRANSPORT`
and credentials, per the repo's live-sending policy.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import ConfigService
from .deliverability_guard import DeliverabilityGuard
from .discovery import normalize_domain
from .suppression import SuppressionService
from .transport import get_transport
from ..errors import ConfigError, NotFoundError, SlideinError, SuppressedError
from ..ids import new_id
from ..models import (
    DeliveryEvent,
    DeliveryEventType,
    DraftStatus,
    MessageDraft,
    Prospect,
    ProspectStatus,
    SentMessage,
    SentStatus,
    utcnow,
)
from ..serialize import (
    delivery_event,
    draft,
    prospect,
    sent_message,
    suppression,
)

DEFAULT_POLICY: dict[str, Any] = {
    "require_approval": True,
    "daily_limit": 50,
    "hourly_limit": 10,
    "max_attempts": 3,
    "send_window": "00:00-23:59",
    "allowed_senders": [],
    "physical_postal_address": "Suite 400, 100 Pine Street, San Francisco, CA 94111",
    "lawful_basis": "b2b_legitimate_interest",
    "quarantined": False,
}


class TransportError(SlideinError):
    code = "transport_rejected"


class OutreachService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # -- policy -----------------------------------------------------------

    async def policy(self, tenant_id: str) -> dict:
        """Sending policy for a tenant. Persisted overrides merge onto the
        defaults, so 'no policy' still means 'safe'."""
        from ..models import Tenant, utcnow  # noqa: F401  (utcnow re-exported below)

        row = await self.session.get(Tenant, tenant_id)
        if row is None:
            await ConfigService(self.session).ensure_tenant(tenant_id)
            row = await self.session.get(Tenant, tenant_id)
        stored = dict(getattr(row, "settings", None) or {}) if row is not None else {}
        merged = dict(DEFAULT_POLICY)
        merged.update({k: v for k, v in stored.items() if v is not None})
        return merged

    async def save_policy(self, tenant_id: str, updates: dict, *, actor: str) -> dict:
        from ..models import Tenant

        await self.policy(tenant_id)  # ensures the workspace row exists
        row = await self.session.get(Tenant, tenant_id)
        if row is None:
            raise NotFoundError(f"Workspace {tenant_id!r} does not exist")
        current = await self.policy(tenant_id)
        merged = {**current, **{k: v for k, v in updates.items() if v is not None}}
        row.settings = merged
        await self.session.flush()
        return await self.policy(tenant_id)

    # -- approval ---------------------------------------------------------

    async def approve_draft(
        self, *, tenant_id: str, draft_id: str, actor: str, note: str = ""
    ) -> dict:
        row = await self.session.get(MessageDraft, draft_id)
        if row is None or row.tenant_id != tenant_id:
            raise NotFoundError(f"Draft {draft_id!r} does not exist in this workspace")
        if row.status == DraftStatus.SENT.value:
            raise SlideinError(
                "This draft has already been sent",
                code="draft_not_found",
                recovery_action="review_draft",
            )
        if row.status == DraftStatus.REJECTED.value:
            raise SlideinError(
                "This draft was rejected and must be regenerated",
                code="draft_not_found",
                recovery_action="regenerate_draft",
            )
        if row.status != DraftStatus.PENDING_REVIEW.value:
            raise SlideinError(
                f"Draft is {row.status!r}; only pending_review drafts can be approved",
                code="approval_required",
                recovery_action="approve_draft",
            )
        row.status = DraftStatus.APPROVED.value
        row.approved_by = actor
        row.approved_at = utcnow()
        row.approval_note = note
        await self.session.flush()
        return draft(row)

    async def revoke_approval(self, *, tenant_id: str, draft_id: str, actor: str) -> dict:
        row = await self.session.get(MessageDraft, draft_id)
        if row is None or row.tenant_id != tenant_id:
            raise NotFoundError(f"Draft {draft_id!r} does not exist in this workspace")
        if row.status != DraftStatus.APPROVED.value:
            raise SlideinError(
                f"Draft is {row.status!r}; only approved drafts can be un-approved",
                code="draft_not_found",
                recovery_action="review_draft",
            )
        row.status = DraftStatus.PENDING_REVIEW.value
        row.approved_by = ""
        row.approved_at = None
        await self.session.flush()
        return draft(row)

    # -- sending ----------------------------------------------------------

    async def send_draft(
        self,
        *,
        tenant_id: str,
        draft_id: str,
        actor: str,
        sender_email: str = "",
        transport_config: dict | None = None,
    ) -> dict:
        row = await self.session.get(MessageDraft, draft_id)
        if row is None or row.tenant_id != tenant_id:
            raise NotFoundError(f"Draft {draft_id!r} does not exist in this workspace")

        policy = await self.policy(tenant_id)
        if row.status == DraftStatus.SENT.value:
            raise SlideinError(
                "This draft has already been sent",
                code="draft_not_found",
                details={"draft_status": row.status},
                recovery_action="review_draft",
            )
        if row.status == DraftStatus.REJECTED.value:
            raise SlideinError(
                "This draft was rejected",
                code="draft_not_found",
                details={"draft_status": row.status},
                recovery_action="regenerate_draft",
            )
        if row.status == DraftStatus.CANCELLED.value:
            raise SlideinError(
                "This draft was cancelled",
                code="draft_not_found",
                details={"draft_status": row.status},
                recovery_action="regenerate_draft",
            )
        if policy.get("require_approval") and row.status != DraftStatus.APPROVED.value:
            raise SlideinError(
                "This draft has not been approved, so it may not be sent",
                code="approval_required",
                details={"draft_status": row.status},
                recovery_action="approve_draft",
            )

        prospect_row = await self.session.get(Prospect, row.prospect_id)
        if prospect_row is None:
            raise NotFoundError(
                "The prospect this draft belongs to no longer exists",
                code="prospect_not_found",
                recovery_action="return_to_discovery",
            )

        suppression_service = SuppressionService(self.session)
        blocked = await suppression_service.is_suppressed(tenant_id, prospect_row.email)
        if blocked is not None:
            raise SuppressedError(
                f"{prospect_row.email} is suppressed ({blocked['reason']})",
                details={"suppression": blocked},
                recovery_action="review_suppression",
            )

        limit_error = await self._check_limits(tenant_id, policy)
        if limit_error is not None:
            raise limit_error

        guard = DeliverabilityGuard(tenant_id)
        guard.validate_pre_send_compliance(policy)

        configured_sender = sender_email or await self._default_sender(tenant_id, policy)
        if not configured_sender:
            raise ConfigError(
                "No sending identity is configured for this workspace",
                code="provider_unavailable",
                recovery_action="retry_stage",
            )

        compliance_headers = guard.build_compliance_headers(
            tenant_id=tenant_id,
            sender_email=configured_sender,
            recipient_email=prospect_row.email,
        )
        address = str(policy.get("physical_postal_address") or "").strip()
        formatted_body = guard.format_compliant_body(row.body, physical_address=address)

        transport = get_transport(transport_config)
        result = transport.dispatch(
            sender=configured_sender,
            recipient=prospect_row.email,
            subject=row.subject,
            body=formatted_body,
            headers={"X-Slidein-Draft-Id": row.id, "X-Slidein-Tenant": tenant_id, **compliance_headers},
        )

        sent = SentMessage(
            id=new_id("sent"),
            tenant_id=tenant_id,
            draft_id=row.id,
            draft_version=row.version,
            prospect_id=prospect_row.id,
            sender_email=configured_sender,
            recipient_email=prospect_row.email,
            message_id=result.message_id or f"<{new_id('sent')}@{tenant_id}>",
            transport=transport.name,
            delivery_status=(
                SentStatus.SUBMITTED.value if result.ok else SentStatus.FAILED.value
            ),
            attempt=1,
            error_code=result.error_code,
            error_message=result.detail if not result.ok else "",
            authorized_by=row.approved_by or actor,
        )
        self.session.add(sent)
        await self.session.flush()

        self.session.add(
            DeliveryEvent(
                id=new_id("delivery_event"),
                tenant_id=tenant_id,
                sent_message_id=sent.id,
                prospect_id=prospect_row.id,
                event_type=(
                    DeliveryEventType.SUBMITTED.value
                    if result.ok
                    else DeliveryEventType.BOUNCED.value
                ),
                provider=transport.provider,
                detail=result.detail,
                payload={"sender": configured_sender, "recipient": prospect_row.email},
                recorded_by=actor,
            )
        )
        await self.session.flush()

        if result.ok:
            from .discovery import DiscoveryService

            row.status = DraftStatus.SENT.value
            await DiscoveryService(self.session).apply_transition(
                prospect_row,
                to_status=ProspectStatus.IN_CAMPAIGN.value,
                reason=f"sent by {actor} via {transport.name}",
                actor=actor,
                stage="outreach",
            )
            await self.session.flush()
        else:
            raise TransportError(
                f"Transport rejected the message: {result.detail}",
                code=result.error_code or "transport_rejected",
                details={
                    "sent_message_id": sent.id,
                    "draft_id": row.id,
                    "retryable": result.retryable,
                },
                recovery_action="retry_stage",
            )

        return {
            "draft": draft(row),
            "sent_message": sent_message(sent),
            "transport": transport.name,
            "provider": transport.provider,
            "sender_email": configured_sender,
        }

    async def _check_limits(self, tenant_id: str, policy: dict) -> SlideinError | None:
        now = utcnow()

        daily_limit = int(policy.get("daily_limit") or 0)
        if daily_limit > 0:
            day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            sent_today = (
                await self.session.execute(
                    select(func.count())
                    .select_from(SentMessage)
                    .where(
                        SentMessage.tenant_id == tenant_id,
                        SentMessage.queued_at >= day_start,
                        SentMessage.delivery_status != SentStatus.FAILED.value,
                    )
                )
            ).scalar_one()
            if sent_today >= daily_limit:
                return SlideinError(
                    f"Daily sending limit of {daily_limit} reached",
                    code="rate_limited",
                    details={"sent_today": int(sent_today), "daily_limit": daily_limit},
                    recovery_action="retry_stage_later",
                )

        hourly_limit = int(policy.get("hourly_limit") or 0)
        if hourly_limit > 0:
            hour_start = now.replace(minute=0, second=0, microsecond=0)
            sent_hour = (
                await self.session.execute(
                    select(func.count())
                    .select_from(SentMessage)
                    .where(
                        SentMessage.tenant_id == tenant_id,
                        SentMessage.queued_at >= hour_start,
                        SentMessage.delivery_status != SentStatus.FAILED.value,
                    )
                )
            ).scalar_one()
            if sent_hour >= hourly_limit:
                return SlideinError(
                    f"Hourly sending limit of {hourly_limit} reached",
                    code="rate_limited",
                    details={"sent_this_hour": int(sent_hour), "hourly_limit": hourly_limit},
                    recovery_action="retry_stage_later",
                )
        return None

    async def _default_sender(self, tenant_id: str, policy: dict) -> str:
        """The sending identity.

        Preference order: an explicitly allowed sender, then the address
        derived from the business profile's own domain, then a workspace
        placeholder. The sender is always the tenant's own address — a
        message is never dispatched from an address the tenant does not own.
        """
        allowed = policy.get("allowed_senders") or []
        if allowed:
            return str(allowed[0])

        profile = await ConfigService(self.session).active_profile(tenant_id)
        if profile is not None:
            domain = normalize_domain(profile.get("website_url"))
            if domain:
                local = profile.get("legal_name", "hello").split()[0].lower() or "hello"
                local = "".join(ch for ch in local if ch.isalnum()) or "hello"
                return f"{local}@{domain}"

        from ..services.suppression import SuppressionService  # noqa: F401

        return f"hello@{tenant_id.replace('_', '-')}.slidein.local"

    # -- provider events --------------------------------------------------

    async def record_event(
        self,
        *,
        tenant_id: str,
        sent_message_id: str | None = None,
        message_id: str | None = None,
        recipient_email: str,
        event_type: str,
        provider: str = "",
        detail: str = "",
        payload: dict | None = None,
        actor: str = "system",
    ) -> dict:
        """Apply a provider event to the sent message and the prospect."""
        sent: SentMessage | None = None
        if sent_message_id:
            sent = await self.session.get(SentMessage, sent_message_id)
            if sent is not None and sent.tenant_id != tenant_id:
                sent = None
        if sent is None and message_id:
            sent = (
                await self.session.execute(
                    select(SentMessage).where(
                        SentMessage.tenant_id == tenant_id, SentMessage.message_id == message_id
                    )
                )
            ).scalars().first()
        if sent is None:
            raise NotFoundError(
                f"No sent message matches {message_id or sent_message_id!r}",
                code="prospect_not_found",
                recovery_action="return_to_discovery",
            )

        row = DeliveryEvent(
            id=new_id("delivery_event"),
            tenant_id=tenant_id,
            sent_message_id=sent.id,
            prospect_id=sent.prospect_id,
            event_type=event_type,
            provider=provider or "webhook",
            detail=detail,
            payload=payload or {},
            recorded_by=actor,
        )
        self.session.add(row)
        await self.session.flush()

        event = delivery_event(row)

        if event_type == DeliveryEventType.BOUNCED.value:
            sent.delivery_status = SentStatus.BOUNCED.value
            await self._suppress(
                tenant_id=tenant_id, email=recipient_email, reason="hard_bounce",
                actor=actor, note=f"bounced: {detail}",
            )
        elif event_type == DeliveryEventType.COMPLAINED.value:
            sent.delivery_status = SentStatus.COMPLAINED.value
            await self._suppress(
                tenant_id=tenant_id, email=recipient_email, reason="spam_complaint",
                actor=actor, note=f"complaint: {detail}",
            )
        elif event_type == DeliveryEventType.DEFERRED.value:
            sent.delivery_status = SentStatus.DEFERRED.value
        elif event_type == DeliveryEventType.ACCEPTED.value:
            sent.delivery_status = SentStatus.ACCEPTED.value
        elif event_type == DeliveryEventType.DELIVERED.value:
            sent.delivery_status = SentStatus.DELIVERED.value
        elif event_type == DeliveryEventType.UNSUBSCRIBED.value:
            await self._suppress(
                tenant_id=tenant_id, email=recipient_email, reason="opt_out",
                actor=actor, note=detail,
            )
        elif event_type in (
            DeliveryEventType.OPENED.value,
            DeliveryEventType.CLICKED.value,
        ):
            pass
        else:
            raise SlideinError(
                f"Unknown delivery event {event_type!r}",
                code="provider_unavailable",
                recovery_action="retry_stage",
            )
        await self.session.flush()

        return {"event": event, "sent_message": sent_message(sent)}

    async def _suppress(
        self, *, tenant_id: str, email: str, reason: str, actor: str, note: str = ""
    ) -> dict:
        service = SuppressionService(self.session)
        return await service.add(
            tenant_id=tenant_id, email=email, reason=reason, note=note, actor=actor
        )

    # -- reads ------------------------------------------------------------

    async def list_sent(
        self, tenant_id: str, *, limit: int = 50, offset: int = 0, status: str | None = None
    ) -> tuple[list[dict], int]:
        query = SentMessage.__table__.select().where(SentMessage.tenant_id == tenant_id)
        if status:
            query = query.where(SentMessage.delivery_status == status)
        query = query.order_by(SentMessage.queued_at.desc()).limit(limit).offset(offset)
        rows = (await self.session.execute(query)).mappings().all()
        total = (
            await self.session.execute(
                select(func.count()).select_from(SentMessage).where(
                    SentMessage.tenant_id == tenant_id
                )
            )
        ).scalar_one()
        return [dict(r) for r in rows], total

    async def list_events(
        self, tenant_id: str, *, sent_message_id: str | None = None, limit: int = 50
    ) -> list[dict]:
        from sqlalchemy import select

        query = (
            select(DeliveryEvent)
            .where(DeliveryEvent.tenant_id == tenant_id)
            .order_by(DeliveryEvent.occurred_at.desc())
        )
        if sent_message_id:
            query = query.where(DeliveryEvent.sent_message_id == sent_message_id)
        rows = (await self.session.execute(query.limit(limit))).scalars().all()
        return [delivery_event(r) for r in rows]

    async def delivery_counts(self, tenant_id: str) -> dict[str, int]:
        rows = (
            await self.session.execute(
                select(SentMessage.delivery_status).where(
                    SentMessage.tenant_id == tenant_id
                )
            )
        ).scalars().all()
        counts: dict[str, int] = {}
        for status in rows:
            counts[status] = counts.get(status, 0) + 1
        return counts

    async def list_suppression(
        self, tenant_id: str, *, limit: int = 100
    ) -> tuple[list[dict], int]:
        return await SuppressionService(self.session).list(tenant_id, limit=limit)

    async def add_suppression(
        self, *, tenant_id: str, email: str, reason: str, note: str = "", actor: str
    ) -> dict:
        return await SuppressionService(self.session).add(
            tenant_id=tenant_id, email=email, reason=reason, note=note, actor=actor
        )

    async def remove_suppression(self, tenant_id: str, suppression_id: str) -> bool:
        return await SuppressionService(self.session).remove(tenant_id, suppression_id)
