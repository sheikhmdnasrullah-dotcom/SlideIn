"""Billing persistence: ledger, reservations, payments, price book, usage.

Balance is never stored as a mutable field — it is always derived:

    available = sum(ledger credits) - sum(ledger debits) - sum(held reservations)

Every mutation is an append-only row with a stable id, tenant, timestamp,
reason, amount and optional job/payment reference. Idempotency keys make
retried grants and duplicate webhooks safe.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..json_types import JSONList, JSONMap
from ..models import Base, utcnow

CREDIT_CURRENCY = "USD"
#: 1 credit = 1/100 USD. All amounts are integer credits.
CREDITS_PER_USD = 100


class LedgerEntryType(str, enum.Enum):
    #: Credits added: a confirmed purchase, an admin grant, or a reversal of
    #: a previous debit (refund).
    PURCHASE = "purchase"
    ADMIN_GRANT = "admin_grant"
    REFUND = "refund"
    ADJUSTMENT_CREDIT = "adjustment_credit"
    #: Credits consumed: a finalized job charge, or an admin correction.
    USAGE_CHARGE = "usage_charge"
    ADJUSTMENT_DEBIT = "adjustment_debit"


class LedgerEntry(Base):
    """One immutable balance mutation. Rows are never updated or deleted."""

    __tablename__ = "ledger_entries"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False
    )
    entry_type: Mapped[str] = mapped_column(String(32), nullable=False)
    #: Signed credit amount: positive adds credits, negative consumes them.
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default=CREDIT_CURRENCY, nullable=False)
    reason: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    job_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    payment_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    #: Admin corrections carry an audit note; customer rows leave it empty.
    admin_note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    #: Unique when set: retries with the same key return the existing row.
    idempotency_key: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    created_by: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        Index("ix_ledger_entries_tenant_created", "tenant_id", "created_at"),
    )


class ReservationState(str, enum.Enum):
    HELD = "held"
    CAPTURED = "captured"
    RELEASED = "released"


class CreditReservation(Base):
    """Credits held for a running job. Held amounts reduce the available
    balance; capture finalizes the charge via a USAGE_CHARGE ledger entry
    and release returns the remainder."""

    __tablename__ = "credit_reservations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False
    )
    job_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    product_id: Mapped[str] = mapped_column(String(64), nullable=False)
    price_version: Mapped[int] = mapped_column(Integer, nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(16), default=ReservationState.HELD.value, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    __table_args__ = (
        Index("ix_reservations_tenant_state", "tenant_id", "state"),
        Index("ix_reservations_job", "job_id"),
    )


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    REFUNDED = "refunded"
    DISPUTED = "disputed"


class Payment(Base):
    """A credit purchase attempt. Credits are granted only when the payment
    reaches a confirmed state through an authenticated channel (webhook or
    admin confirmation) — never from a client-supplied success flag."""

    __tablename__ = "payments"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    #: Provider's own payment identifier; unique per provider so a retried
    #: webhook cannot grant twice.
    provider_payment_id: Mapped[str] = mapped_column(String(128), nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="USD", nullable=False)
    credits: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default=PaymentStatus.PENDING.value, nullable=False)
    credits_granted: Mapped[bool] = mapped_column(default=False, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    #: Non-secret provider payload for audit (status, timestamps). Never
    #: store card numbers, tokens or secrets here.
    detail: Mapped[dict] = mapped_column(JSONMap, default=dict, nullable=False)
    created_by: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("provider", "provider_payment_id", name="uq_payment_provider_ref"),
    )


class PriceBookEntry(Base):
    """One versioned customer price. Prices live in the database, never
    hardcoded through the app; the seed only installs initial versions."""

    __tablename__ = "price_book"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    #: Stable product identifier, e.g. "prospect.research".
    product_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    #: What the customer is billed per unit of.
    billing_unit: Mapped[str] = mapped_column(String(64), nullable=False)
    #: Price per billing unit in credits (1 credit = $0.01).
    unit_price: Mapped[int] = mapped_column(Integer, nullable=False)
    #: For packages: fixed total price (unit_price stays the per-unit rate).
    package_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: Allowances included in a package, e.g. {"prospects": 350, "mailboxes": 2}.
    included_allowances: Mapped[dict] = mapped_column(JSONMap, default=dict, nullable=False)
    required_capabilities: Mapped[list[str]] = mapped_column(JSONList, default=list, nullable=False)
    usage_limits: Mapped[dict] = mapped_column(JSONMap, default=dict, nullable=False)
    eligibility: Mapped[dict] = mapped_column(JSONMap, default=dict, nullable=False)
    refund_policy: Mapped[str] = mapped_column(Text, default="", nullable=False)
    #: active = purchasable; restricted = visible, not publicly purchasable;
    #: draft/retired = not offered.
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    #: Internal cost model (low/expected/high scenarios). Never customer-facing
    #: as a charge; used to keep unvalidated packages restricted.
    cost_model: Mapped[dict] = mapped_column(JSONMap, default=dict, nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    created_by: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("product_id", "version", name="uq_price_product_version"),
    )


class ManagedResource(Base):
    """A recurring-cost resource provisioned for a tenant (mailbox, warm-up
    slot, dedicated egress). Internal cost only — customer-facing allowances
    come from the price book entry that authorized the resource."""

    __tablename__ = "managed_resources"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False
    )
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    state: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    allocation_period_days: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    #: Internal recurring cost per period, in cents. Never customer-facing.
    recurring_cost_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    included_allowance: Mapped[dict] = mapped_column(JSONMap, default=dict, nullable=False)
    campaign_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    product_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provisioned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class JobUsage(Base):
    """Metered usage for one job. `provider_cost_cents` is an internal cost
    figure with an explicit basis; `"actual"` only when the provider
    reported a charge, otherwise `"estimate"`."""

    __tablename__ = "job_usage"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False
    )
    job_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    product_id: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    units: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    unit_type: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    provider_cost_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_basis: Mapped[str] = mapped_column(String(16), default="estimate", nullable=False)
    detail: Mapped[dict] = mapped_column(JSONMap, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        Index("ix_job_usage_tenant_job", "tenant_id", "job_id"),
    )
