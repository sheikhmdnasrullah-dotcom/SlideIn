"""Payments: purchase creation, confirmed credit grants, Stripe webhook.

Two provider paths, both honest:

* `manual` (default) — a purchase is recorded as pending; an admin confirms
  it after funds are verified out of band. No fake "payment succeeded".
* `stripe` — a webhook endpoint that verifies the Stripe signature and
  grants credits idempotently keyed on the provider payment id. Without a
  configured webhook secret the endpoint refuses to process anything.

Credits are granted exactly once per payment: the ledger grant is keyed on
`purchase:<payment_id>` and the payment row flips `credits_granted`.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..errors import ConfigError, PermissionDenied, ValidationError
from ..ids import new_id
from ..models import utcnow
from .ledger import LedgerService
from .models import CREDITS_PER_USD, Payment, PaymentStatus

logger = logging.getLogger("slidein.billing.payments")


def payment_provider() -> str:
    return (os.getenv("SLIDEIN_PAYMENT_PROVIDER") or "manual").strip().lower()


def stripe_webhook_secret() -> str:
    return (os.getenv("SLIDEIN_STRIPE_WEBHOOK_SECRET") or "").strip()


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def payment_dict(row: Payment) -> dict[str, Any]:
    return {
        "id": row.id,
        "tenant_id": row.tenant_id,
        "provider": row.provider,
        "provider_payment_id": row.provider_payment_id,
        "amount_cents": row.amount_cents,
        "currency": row.currency,
        "credits": row.credits,
        "status": row.status,
        "credits_granted": row.credits_granted,
        "idempotency_key": row.idempotency_key,
        "created_at": _iso(row.created_at),
        "confirmed_at": _iso(row.confirmed_at),
    }


class PaymentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_purchase(
        self,
        *,
        tenant_id: str,
        amount_cents: int,
        idempotency_key: str,
        created_by: str = "",
    ) -> dict[str, Any]:
        """Record a credit purchase intent. Returns the existing payment for
        a repeated idempotency key — never two payments, never two grants."""
        if amount_cents <= 0:
            raise ValidationError(
                "amount_cents must be positive", recovery_action="fix_request"
            )
        existing = await self._by_key(idempotency_key)
        if existing is not None:
            return payment_dict(existing)
        credits = amount_cents  # 1 credit = $0.01 = 1 cent
        provider = payment_provider()
        row = Payment(
            id=new_id("pay"),
            tenant_id=tenant_id,
            provider=provider,
            provider_payment_id=f"manual-{uuid.uuid4().hex[:20]}",
            amount_cents=amount_cents,
            credits=credits,
            status=PaymentStatus.PENDING.value,
            idempotency_key=idempotency_key,
            detail={"provider": provider},
            created_by=created_by,
        )
        self.session.add(row)
        try:
            async with self.session.begin_nested():
                await self.session.flush()
        except IntegrityError:
            existing = await self._by_key(idempotency_key)
            if existing is None:
                raise
            self.session.expunge(row)
            return payment_dict(existing)
        return payment_dict(row)

    async def confirm_purchase(
        self, *, tenant_id: str, payment_id: str, admin_actor: str
    ) -> dict[str, Any]:
        """Admin confirmation path for the manual provider. Grants credits
        exactly once; repeated calls are no-ops."""
        row = await self._get(payment_id)
        if row.tenant_id != tenant_id:
            raise PermissionDenied(
                "Payment not found", code="not_found", recovery_action="check_payment_id"
            )
        if not admin_actor:
            raise PermissionDenied(
                "Payment confirmation requires an admin actor",
                recovery_action="request_authorization",
            )
        if row.credits_granted:
            return payment_dict(row)
        ledger = LedgerService(self.session)
        await ledger.grant(
            tenant_id=tenant_id,
            amount=row.credits,
            entry_type="purchase",
            reason=f"Purchase {row.id} confirmed ({row.provider})",
            payment_id=row.id,
            idempotency_key=f"purchase:{row.id}",
            created_by=admin_actor,
        )
        row.credits_granted = True
        row.status = PaymentStatus.CONFIRMED.value
        row.confirmed_at = utcnow()
        await self.session.flush()
        return payment_dict(row)

    async def list_payments(self, tenant_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        rows = (
            await self.session.execute(
                select(Payment)
                .where(Payment.tenant_id == tenant_id)
                .order_by(Payment.created_at.desc())
                .limit(limit)
            )
        ).scalars().all()
        return [payment_dict(row) for row in rows]

    # -- Stripe webhook ---------------------------------------------------------

    def verify_stripe_signature(self, *, payload: bytes, signature_header: str) -> dict[str, Any]:
        """Stripe v1 signature check (t=<timestamp>,v1=<hmac>). Raises
        PermissionDenied on any mismatch."""
        secret = stripe_webhook_secret()
        if not secret:
            raise ConfigError(
                "Stripe webhook is not configured",
                code="payment_provider_unavailable",
                recovery_action="configure_payment_provider",
            )
        parts: dict[str, str] = {}
        for item in (signature_header or "").split(","):
            if "=" in item:
                key, _, value = item.partition("=")
                parts[key.strip()] = value.strip()
        timestamp = parts.get("t", "")
        signatures = [v for k, v in parts.items() if k == "v1"]
        if not timestamp or not signatures:
            raise PermissionDenied(
                "Malformed Stripe signature header",
                code="webhook_signature_invalid",
                recovery_action="retry_webhook",
            )
        signed = f"{timestamp}.".encode() + payload
        expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
        if not any(hmac.compare_digest(expected, sig) for sig in signatures):
            raise PermissionDenied(
                "Stripe signature verification failed",
                code="webhook_signature_invalid",
                recovery_action="retry_webhook",
            )
        try:
            return json.loads(payload.decode())
        except (ValueError, UnicodeDecodeError) as exc:
            raise PermissionDenied(
                "Stripe webhook payload is not valid JSON",
                code="webhook_payload_invalid",
                recovery_action="retry_webhook",
            ) from exc

    async def process_stripe_event(
        self, *, tenant_hint: str | None, event: dict[str, Any]
    ) -> dict[str, Any]:
        """Handle a signature-verified Stripe event. Only payment-success
        events grant credits, keyed on the provider payment id so retries
        cannot double-grant."""
        event_type = str(event.get("type") or "")
        obj = event.get("data", {}).get("object", {}) if isinstance(event.get("data"), dict) else {}
        if event_type not in ("checkout.session.completed", "payment_intent.succeeded"):
            return {"processed": False, "reason": f"ignored_event:{event_type}"}
        provider_ref = str(obj.get("id") or "")
        if not provider_ref:
            return {"processed": False, "reason": "missing_provider_ref"}
        # Resolve amount: checkout sessions carry amount_total (cents);
        # payment intents carry amount_received.
        amount = obj.get("amount_total") or obj.get("amount_received") or 0
        try:
            amount_cents = int(amount)
        except (TypeError, ValueError):
            amount_cents = 0
        if amount_cents <= 0:
            return {"processed": False, "reason": "missing_amount"}
        row = await self._by_provider_ref("stripe", provider_ref)
        if row is None:
            tenant_id = tenant_hint
            if not tenant_id:
                metadata = obj.get("metadata") or {}
                tenant_id = str(metadata.get("slidein_tenant_id") or "")
            if not tenant_id:
                return {"processed": False, "reason": "unknown_tenant"}
            row = Payment(
                id=new_id("pay"),
                tenant_id=tenant_id,
                provider="stripe",
                provider_payment_id=provider_ref,
                amount_cents=amount_cents,
                credits=amount_cents,  # 1 credit = 1 cent
                status=PaymentStatus.PENDING.value,
                idempotency_key=f"stripe:{provider_ref}",
                detail={"event_id": str(event.get("id") or ""), "event_type": event_type},
            )
            self.session.add(row)
            try:
                async with self.session.begin_nested():
                    await self.session.flush()
            except IntegrityError:
                row = await self._by_provider_ref("stripe", provider_ref)
                if row is None:
                    raise
        if row.credits_granted:
            return {"processed": True, "payment_id": row.id, "granted": False, "duplicate": True}
        ledger = LedgerService(self.session)
        await ledger.grant(
            tenant_id=row.tenant_id,
            amount=row.credits,
            entry_type="purchase",
            reason=f"Stripe payment {provider_ref} confirmed",
            payment_id=row.id,
            idempotency_key=f"purchase:{row.id}",
            created_by="stripe:webhook",
        )
        row.credits_granted = True
        row.status = PaymentStatus.CONFIRMED.value
        row.confirmed_at = utcnow()
        await self.session.flush()
        return {"processed": True, "payment_id": row.id, "granted": True}

    # -- internals ---------------------------------------------------------------

    async def _get(self, payment_id: str) -> Payment:
        row = await self.session.get(Payment, payment_id)
        if row is None:
            raise ValidationError(
                "Payment not found", code="not_found", recovery_action="check_payment_id"
            )
        return row

    async def _by_key(self, key: str) -> Payment | None:
        if not key:
            return None
        return (
            await self.session.execute(select(Payment).where(Payment.idempotency_key == key))
        ).scalars().first()

    async def _by_provider_ref(self, provider: str, ref: str) -> Payment | None:
        return (
            await self.session.execute(
                select(Payment).where(
                    Payment.provider == provider,
                    Payment.provider_payment_id == ref,
                )
            )
        ).scalars().first()


__all__ = ["PaymentService", "payment_dict", "payment_provider", "stripe_webhook_secret"]
