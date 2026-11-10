"""Credit ledger: grants, atomic reservations, capture, release, refunds.

Balance is derived, never stored. All multi-step balance changes happen in
one transaction; per-tenant serialization uses the Tenant row lock, the
same pattern as `services/jobs.py` claims.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..errors import NotFoundError, ValidationError
from ..ids import new_id
from ..models import Tenant, utcnow
from .models import (
    CreditReservation,
    LedgerEntry,
    LedgerEntryType,
    Payment,
    PaymentStatus,
    ReservationState,
)

BILLING = "billing"


class InsufficientCreditsError(ValidationError):
    def __init__(self, available: int, required: int) -> None:
        super().__init__(
            f"Insufficient credits: {required} required, {available} available",
            code="insufficient_credits",
            details={"available": available, "required": required},
            recovery_action="purchase_credits",
            retryable=False,
        )
        self.available = available
        self.required = required


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def entry_dict(row: LedgerEntry) -> dict[str, Any]:
    return {
        "id": row.id,
        "tenant_id": row.tenant_id,
        "entry_type": row.entry_type,
        "amount": row.amount,
        "currency": row.currency,
        "reason": row.reason,
        "job_id": row.job_id,
        "payment_id": row.payment_id,
        "idempotency_key": row.idempotency_key,
        "created_by": row.created_by,
        "created_at": _iso(row.created_at),
    }


def reservation_dict(row: CreditReservation) -> dict[str, Any]:
    return {
        "id": row.id,
        "tenant_id": row.tenant_id,
        "job_id": row.job_id,
        "product_id": row.product_id,
        "price_version": row.price_version,
        "amount": row.amount,
        "state": row.state,
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


class LedgerService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _lock_tenant(self, tenant_id: str) -> None:
        await self.session.execute(
            select(Tenant.id).where(Tenant.id == tenant_id).with_for_update()
        )

    async def _ledger_totals(self, tenant_id: str) -> tuple[int, int]:
        """(credits, debits) in absolute credits."""
        credits = (
            await self.session.execute(
                select(func.coalesce(func.sum(LedgerEntry.amount), 0)).where(
                    LedgerEntry.tenant_id == tenant_id,
                    LedgerEntry.amount > 0,
                )
            )
        ).scalar_one()
        debits = (
            await self.session.execute(
                select(func.coalesce(func.sum(-LedgerEntry.amount), 0)).where(
                    LedgerEntry.tenant_id == tenant_id,
                    LedgerEntry.amount < 0,
                )
            )
        ).scalar_one()
        return int(credits), int(debits)

    async def _held_total(self, tenant_id: str) -> int:
        held = (
            await self.session.execute(
                select(func.coalesce(func.sum(CreditReservation.amount), 0)).where(
                    CreditReservation.tenant_id == tenant_id,
                    CreditReservation.state == ReservationState.HELD.value,
                )
            )
        ).scalar_one()
        return int(held)

    async def balance(self, tenant_id: str) -> dict[str, int]:
        credits, debits = await self._ledger_totals(tenant_id)
        held = await self._held_total(tenant_id)
        return {
            "purchased_credits": credits,
            "used_credits": debits,
            "held_credits": held,
            "available_credits": max(0, credits - debits - held),
        }

    # -- grants (purchases, admin grants, refunds, adjustments) ---------------

    async def grant(
        self,
        *,
        tenant_id: str,
        amount: int,
        entry_type: str = LedgerEntryType.ADMIN_GRANT.value,
        reason: str = "",
        payment_id: str | None = None,
        job_id: str | None = None,
        idempotency_key: str | None = None,
        admin_note: str = "",
        created_by: str = "",
    ) -> dict[str, Any]:
        """Add credits. Idempotent on `idempotency_key`: a retry returns the
        original row and never grants twice."""
        if amount <= 0:
            raise ValidationError(
                "Grant amount must be positive", recovery_action="fix_request"
            )
        if idempotency_key:
            existing = await self._entry_by_key(idempotency_key)
            if existing is not None:
                return entry_dict(existing)
        row = LedgerEntry(
            id=new_id("ledger"),
            tenant_id=tenant_id,
            entry_type=entry_type,
            amount=amount,
            reason=reason,
            payment_id=payment_id,
            job_id=job_id,
            idempotency_key=idempotency_key,
            admin_note=admin_note,
            created_by=created_by,
        )
        self.session.add(row)
        try:
            async with self.session.begin_nested():
                await self.session.flush()
        except IntegrityError:
            existing = await self._entry_by_key(idempotency_key or "")
            if existing is None:
                raise
            self.session.expunge(row)
            return entry_dict(existing)
        return entry_dict(row)

    async def charge(
        self,
        *,
        tenant_id: str,
        amount: int,
        reason: str = "",
        job_id: str | None = None,
        idempotency_key: str | None = None,
        admin_note: str = "",
        created_by: str = "",
    ) -> dict[str, Any]:
        """Consume credits directly (admin corrections). Idempotent on key."""
        if amount <= 0:
            raise ValidationError(
                "Charge amount must be positive", recovery_action="fix_request"
            )
        await self._lock_tenant(tenant_id)
        balance = await self.balance(tenant_id)
        if balance["available_credits"] < amount:
            raise InsufficientCreditsError(balance["available_credits"], amount)
        if idempotency_key:
            existing = await self._entry_by_key(idempotency_key)
            if existing is not None:
                return entry_dict(existing)
        row = LedgerEntry(
            id=new_id("ledger"),
            tenant_id=tenant_id,
            entry_type=LedgerEntryType.ADJUSTMENT_DEBIT.value,
            amount=-amount,
            reason=reason,
            job_id=job_id,
            idempotency_key=idempotency_key,
            admin_note=admin_note,
            created_by=created_by,
        )
        self.session.add(row)
        try:
            async with self.session.begin_nested():
                await self.session.flush()
        except IntegrityError:
            existing = await self._entry_by_key(idempotency_key or "")
            if existing is None:
                raise
            self.session.expunge(row)
            return entry_dict(existing)
        return entry_dict(row)

    async def refund(
        self,
        *,
        tenant_id: str,
        amount: int,
        reason: str,
        job_id: str | None = None,
        idempotency_key: str | None = None,
        admin_note: str = "",
        created_by: str = "",
    ) -> dict[str, Any]:
        return await self.grant(
            tenant_id=tenant_id,
            amount=amount,
            entry_type=LedgerEntryType.REFUND.value,
            reason=reason,
            job_id=job_id,
            idempotency_key=idempotency_key,
            admin_note=admin_note,
            created_by=created_by,
        )

    # -- reservations ----------------------------------------------------------

    async def reserve(
        self,
        *,
        tenant_id: str,
        job_id: str,
        product_id: str,
        price_version: int,
        amount: int,
    ) -> dict[str, Any]:
        """Atomically hold credits for a job. Fails closed when the available
        balance (after other holds) is insufficient."""
        if amount <= 0:
            raise ValidationError(
                "Reservation amount must be positive", recovery_action="fix_request"
            )
        await self._lock_tenant(tenant_id)
        balance = await self.balance(tenant_id)
        if balance["available_credits"] < amount:
            raise InsufficientCreditsError(balance["available_credits"], amount)
        row = CreditReservation(
            id=new_id("resv"),
            tenant_id=tenant_id,
            job_id=job_id,
            product_id=product_id,
            price_version=price_version,
            amount=amount,
        )
        self.session.add(row)
        await self.session.flush()
        return reservation_dict(row)

    async def get_reservation(self, reservation_id: str) -> CreditReservation:
        row = await self.session.get(CreditReservation, reservation_id)
        if row is None:
            raise NotFoundError(
                "Reservation not found", code="not_found", recovery_action="check_job_id"
            )
        return row

    async def reservation_for_job(self, job_id: str) -> CreditReservation | None:
        return (
            await self.session.execute(
                select(CreditReservation)
                .where(CreditReservation.job_id == job_id)
                .order_by(CreditReservation.created_at.desc())
            )
        ).scalars().first()

    async def capture(
        self,
        *,
        reservation_id: str,
        actual_amount: int,
        reason: str = "",
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Finalize the charge: debit `actual_amount`, release the rest.
        `actual_amount` may be zero (full refund of the hold)."""
        row = await self.get_reservation(reservation_id)
        if row.state != ReservationState.HELD.value:
            raise ValidationError(
                f"Reservation is {row.state}; only held reservations can be captured",
                code="reservation_invalid",
                recovery_action="check_job_id",
            )
        if actual_amount < 0 or actual_amount > row.amount:
            raise ValidationError(
                "Captured amount must be between 0 and the reserved amount",
                code="reservation_invalid",
                recovery_action="check_job_id",
            )
        await self._lock_tenant(row.tenant_id)
        if actual_amount > 0:
            entry_key = idempotency_key or f"capture:{row.id}"
            existing = await self._entry_by_key(entry_key)
            if existing is None:
                self.session.add(
                    LedgerEntry(
                        id=new_id("ledger"),
                        tenant_id=row.tenant_id,
                        entry_type=LedgerEntryType.USAGE_CHARGE.value,
                        amount=-actual_amount,
                        reason=reason or f"Charge for job {row.job_id}",
                        job_id=row.job_id,
                        idempotency_key=entry_key,
                    )
                )
        row.state = (
            ReservationState.CAPTURED.value if actual_amount > 0 else ReservationState.RELEASED.value
        )
        row.updated_at = utcnow()
        await self.session.flush()
        return reservation_dict(row)

    async def release(self, *, reservation_id: str, reason: str = "") -> dict[str, Any]:
        row = await self.get_reservation(reservation_id)
        if row.state != ReservationState.HELD.value:
            return reservation_dict(row)
        row.state = ReservationState.RELEASED.value
        row.updated_at = utcnow()
        await self.session.flush()
        return reservation_dict(row)

    # -- reads ------------------------------------------------------------------

    async def ledger(
        self, tenant_id: str, *, limit: int = 100, offset: int = 0
    ) -> list[dict[str, Any]]:
        rows = (
            await self.session.execute(
                select(LedgerEntry)
                .where(LedgerEntry.tenant_id == tenant_id)
                .order_by(LedgerEntry.created_at.desc(), LedgerEntry.id.desc())
                .limit(limit)
                .offset(offset)
            )
        ).scalars().all()
        return [entry_dict(row) for row in rows]

    async def reconcile(self, tenant_id: str) -> dict[str, Any]:
        """Recompute the balance straight from the ledger and compare it with
        any stored expectation. Discrepancies are reported, never hidden."""
        credits, debits = await self._ledger_totals(tenant_id)
        held = await self._held_total(tenant_id)
        available = credits - debits - held
        entry_count = (
            await self.session.execute(
                select(func.count()).select_from(LedgerEntry).where(
                    LedgerEntry.tenant_id == tenant_id
                )
            )
        ).scalar_one()
        return {
            "tenant_id": tenant_id,
            "purchased_credits": credits,
            "used_credits": debits,
            "held_credits": held,
            "available_credits": max(0, available),
            "ledger_entries": int(entry_count),
            "consistent": available >= 0,
        }

    async def mark_payment_granted(self, payment_id: str) -> None:
        await self.session.execute(
            update(Payment)
            .where(Payment.id == payment_id)
            .values(credits_granted=True, status=PaymentStatus.CONFIRMED.value, confirmed_at=utcnow())
        )

    async def _entry_by_key(self, key: str) -> LedgerEntry | None:
        if not key:
            return None
        return (
            await self.session.execute(
                select(LedgerEntry).where(LedgerEntry.idempotency_key == key)
            )
        ).scalars().first()


__all__ = [
    "InsufficientCreditsError",
    "LedgerService",
    "entry_dict",
    "reservation_dict",
]
