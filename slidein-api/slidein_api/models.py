"""Slidein canonical domain models.

One model set backs every section of the client workspace. There are no
per-screen tables and no per-screen business rules: Discovery, Research,
Qualification, Personalization, Outreach, Conversations, Activity and
Overview all read and write these same rows.

Inventory (see docs/architecture/DATA_MODEL.md):

  configuration: tenants, business_profiles, offers, icp_definitions
  pipeline:      prospects, evidence_items, qualification_results,
                 offer_matches
  outreach:      message_drafts, draft_versions, sent_messages,
                 delivery_events, suppression_records
  conversations: conversations, inbound_replies
  workflow:      stage_runs, activity_logs, config_versions

Every mutable entity carries the configuration version it was produced
under, the actor that produced it, and an immutable history trail so a
record can always be traced back to the profile/ICP/offer revision that
authized it.
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from .json_types import JSONList, JSONMap


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Enumerations — the explicit lifecycle states
# ---------------------------------------------------------------------------

class ProspectStatus(str, enum.Enum):
    DISCOVERED = "discovered"
    RESEARCHING = "researching"
    RESEARCHED = "researched"
    QUALIFIED = "qualified"
    DISQUALIFIED = "disqualified"
    DRAFT_READY = "draft_ready"
    IN_CAMPAIGN = "in_campaign"
    REPLIED = "replied"
    OPTED_OUT = "opted_out"

    @property
    def is_terminal(self) -> bool:
        return self in (ProspectStatus.OPTED_OUT,)


class DraftStatus(str, enum.Enum):
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    SENT = "sent"
    CANCELLED = "cancelled"


class SentStatus(str, enum.Enum):
    QUEUED = "queued"
    SUBMITTED = "submitted"
    ACCEPTED = "accepted"
    DELIVERED = "delivered"
    BOUNCED = "bounced"
    DEFERRED = "deferred"
    COMPLAINED = "complained"
    FAILED = "failed"


class DeliveryEventType(str, enum.Enum):
    SUBMITTED = "submitted"
    ACCEPTED = "accepted"
    DELIVERED = "delivered"
    BOUNCED = "bounced"
    DEFERRED = "deferred"
    OPENED = "opened"
    CLICKED = "clicked"
    COMPLAINED = "complained"
    UNSUBSCRIBED = "unsubscribed"


class VerificationStatus(str, enum.Enum):
    VERIFIED = "verified"
    INFERRED = "inferred"
    UNVERIFIED = "unverified"


class RunStatus(str, enum.Enum):
    SUCCEEDED = "succeeded"
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"
    RUNNING = "running"
    RETRYING = "retrying"


class ConversationState(str, enum.Enum):
    OPEN = "open"
    AWAITING_REPLY = "awaiting_reply"
    CLOSED = "closed"


class ReplyIntent(str, enum.Enum):
    UNCLASSIFIED = "unclassified"
    INTERESTED = "interested"
    INFORMATION_REQUEST = "information_request"
    OBJECTION = "objection"
    OUT_OF_OFFICE = "out_of_office"
    UNSUBSCRIBE = "unsubscribe"
    NOT_INTERESTED = "not_interested"


class SuppressionReason(str, enum.Enum):
    OPT_OUT = "opt_out"
    HARD_BOUNCE = "hard_bounce"
    SPAM_COMPLAINT = "spam_complaint"
    MANUAL_ADMIN = "manual_admin"


class ActorRole(str, enum.Enum):
    VIEWER = "viewer"
    OPERATOR = "operator"
    ADMIN = "admin"
    SYSTEM = "system"


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    plan_tier: Mapped[str] = mapped_column(String(32), default="standard", nullable=False)
    autonomy_level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    #: Persisted sending policy (merged onto DEFAULT_POLICY at read time).
    settings: Mapped[dict] = mapped_column(JSONMap, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    profiles: Mapped[list["BusinessProfile"]] = relationship(back_populates="tenant")


class BusinessProfile(Base):
    """Versioned business configuration handed to Discovery.

    A new row is never edited in place: `save` writes a new version and
    flips `is_active` on the previous one, so downstream records keep a
    stable `profile_version` they can be traced to.
    """

    __tablename__ = "business_profiles"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False
    )
    legal_name: Mapped[str] = mapped_column(String(255), nullable=False)
    website_url: Mapped[str] = mapped_column(String(255), nullable=False)
    industry: Mapped[str] = mapped_column(String(128), nullable=False)
    company_description: Mapped[str] = mapped_column(Text, nullable=False)
    core_value_prop: Mapped[str] = mapped_column(Text, nullable=False)
    markets_served: Mapped[list[str]] = mapped_column(JSONList, default=list, nullable=False)
    target_roles: Mapped[list[str]] = mapped_column(JSONList, default=list, nullable=False)
    brand_voice: Mapped[str] = mapped_column(Text, default="", nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    tenant: Mapped[Tenant] = relationship(back_populates="profiles")

    __table_args__ = (
        Index("ix_business_profiles_tenant_active", "tenant_id", "is_active"),
    )


class Offer(Base):
    __tablename__ = "offers"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False
    )
    profile_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("business_profiles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    pain_points_solved: Mapped[list[str]] = mapped_column(JSONList, default=list, nullable=False)
    target_persona: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    proof_points: Mapped[list[str]] = mapped_column(JSONList, default=list, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class IcpDefinition(Base):
    __tablename__ = "icp_definitions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False
    )
    profile_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("business_profiles.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    industries: Mapped[list[str]] = mapped_column(JSONList, default=list, nullable=False)
    company_size_min: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    company_size_max: Mapped[int] = mapped_column(Integer, default=5000, nullable=False)
    geographies: Mapped[list[str]] = mapped_column(JSONList, default=list, nullable=False)
    target_roles: Mapped[list[str]] = mapped_column(JSONList, default=list, nullable=False)
    required_signals: Mapped[list[str]] = mapped_column(JSONList, default=list, nullable=False)
    exclusion_keywords: Mapped[list[str]] = mapped_column(JSONList, default=list, nullable=False)
    qualify_threshold: Mapped[int] = mapped_column(Integer, default=70, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class ConfigVersion(Base):
    """Immutable snapshot of a configuration revision."""

    __tablename__ = "config_versions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSONMap, default=dict, nullable=False)
    actor: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "entity_type", "entity_id", "version",
                         name="uq_config_version"),
    )


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

class Prospect(Base):
    __tablename__ = "prospects"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False
    )
    first_name: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    last_name: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    company_name: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    company_domain: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    job_title: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    linkedin_url: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    company_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    location: Mapped[str] = mapped_column(String(255), default="", nullable=False)

    # Source attribution — where this record came from, never re-derived.
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    source_ref: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    source_detail: Mapped[dict] = mapped_column(JSONMap, default=dict, nullable=False)

    status: Mapped[str] = mapped_column(String(32), default=ProspectStatus.DISCOVERED.value, nullable=False)
    status_reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    #: Append-only lifecycle trail — never edited, only appended to.
    state_history: Mapped[list[dict]] = mapped_column(JSONList, default=list, nullable=False)
    qualification_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Configuration this record was produced/advanced under.
    profile_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    profile_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    icp_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    icp_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    offer_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    discovered_by: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="uq_prospect_tenant_email"),
        Index("ix_prospects_tenant_status", "tenant_id", "status"),
    )


class EvidenceItem(Base):
    """A source-backed claim. Nothing downstream may cite a claim that is
    not one of these rows (see `attributed_evidence_ids`)."""

    __tablename__ = "evidence_items"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    prospect_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("prospects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    evidence_type: Mapped[str] = mapped_column(String(64), nullable=False)
    claim_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str] = mapped_column(String(1024), default="", nullable=False)
    source_name: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    verification_status: Mapped[str] = mapped_column(
        String(32), default=VerificationStatus.VERIFIED.value, nullable=False
    )
    collector: Mapped[str] = mapped_column(String(64), default="research_stage", nullable=False)
    retrieved_by: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class QualificationResult(Base):
    __tablename__ = "qualification_results"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    prospect_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("prospects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    icp_id: Mapped[str] = mapped_column(String(64), nullable=False)
    icp_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    profile_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    is_qualified: Mapped[bool] = mapped_column(Boolean, nullable=False)
    matching_criteria: Mapped[list[dict]] = mapped_column(JSONList, default=list, nullable=False)
    missing_criteria: Mapped[list[dict]] = mapped_column(JSONList, default=list, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, default="", nullable=False)
    evaluator: Mapped[str] = mapped_column(String(64), default="rule_engine", nullable=False)
    evaluated_by: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class OfferMatch(Base):
    """Why a specific offer fits a specific prospect, with the evidence
    rows that justify the match."""

    __tablename__ = "offer_matches"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    prospect_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("prospects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    offer_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("offers.id", ondelete="CASCADE"), nullable=False
    )
    offer_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rationale: Mapped[str] = mapped_column(Text, default="", nullable=False)
    evidence_ids: Mapped[list[str]] = mapped_column(JSONList, default=list, nullable=False)
    score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_selected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    matched_by: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    matched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        Index("ix_offer_matches_prospect", "tenant_id", "prospect_id"),
    )


# ---------------------------------------------------------------------------
# Outreach
# ---------------------------------------------------------------------------

class MessageDraft(Base):
    __tablename__ = "message_drafts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    prospect_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("prospects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    offer_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("offers.id", ondelete="SET NULL"), nullable=True
    )
    qualification_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    subject: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=DraftStatus.PENDING_REVIEW.value, nullable=False)
    attributed_evidence_ids: Mapped[list[str]] = mapped_column(JSONList, default=list, nullable=False)
    human_edited: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    profile_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    approved_by: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approval_note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    rejected_by: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    rejected_reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_by: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    __table_args__ = (
        Index("ix_message_drafts_tenant_status", "tenant_id", "status"),
    )


class DraftVersion(Base):
    """Every revision of a draft, human or system, kept forever."""

    __tablename__ = "draft_versions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    draft_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("message_drafts.id", ondelete="CASCADE"), index=True, nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    subject: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    change_reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    changed_by: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    is_human_edit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("draft_id", "version", name="uq_draft_version"),
    )


class SentMessage(Base):
    __tablename__ = "sent_messages"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    draft_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    draft_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    prospect_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    sender_email: Mapped[str] = mapped_column(String(255), nullable=False)
    recipient_email: Mapped[str] = mapped_column(String(255), nullable=False)
    message_id: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    transport: Mapped[str] = mapped_column(String(64), nullable=False)
    delivery_status: Mapped[str] = mapped_column(String(32), default=SentStatus.SUBMITTED.value, nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    error_code: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    error_message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    authorized_by: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        Index("ix_sent_messages_tenant_status", "tenant_id", "delivery_status"),
    )


class DeliveryEvent(Base):
    __tablename__ = "delivery_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    sent_message_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sent_messages.id", ondelete="CASCADE"), index=True, nullable=False
    )
    prospect_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    detail: Mapped[str] = mapped_column(Text, default="", nullable=False)
    payload: Mapped[dict] = mapped_column(JSONMap, default=dict, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    recorded_by: Mapped[str] = mapped_column(String(128), default="", nullable=False)

    __table_args__ = (
        Index("ix_delivery_events_message", "sent_message_id", "occurred_at"),
    )


class SuppressionRecord(Base):
    __tablename__ = "suppression_records"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    domain: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    reason: Mapped[str] = mapped_column(String(64), nullable=False)
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    suppressed_by: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    suppressed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="uq_suppression_tenant_email"),
    )


# ---------------------------------------------------------------------------
# Sending reputation isolation
#
# These tables carry the tenant-level view of *how* this tenant's mail is
# sent and whether that route is isolated. They are deliberately separate
# from Tenant.settings: settings is the human-editable sending policy
# (limits, lawful basis), while these rows record the routing decision that
# governs which infrastructure actually carries the bytes.
# ---------------------------------------------------------------------------


class SendingMode(str, enum.Enum):
    """How this tenant's outbound mail leaves the building.

    `shared` — every tenant on this installation shares one public IP, so
        the tenant's reputation is *not* isolated.
    `dedicated` — this tenant has its own public egress (a dedicated IP
        or pool) and its reputation is isolated on that IP.
    `provider_managed` — mail leaves through an external provider's own
        infrastructure; isolation depends on the provider account/IP
        configuration.
    """

    SHARED = "shared"
    DEDICATED = "dedicated"
    PROVIDER_MANAGED = "provider_managed"


class TenantSendingConfig(Base):
    """The routing decision for one tenant's outbound mail.

    One row per tenant. `sending_mode` decides the isolation story and the
    remaining fields name the concrete route the tenant is assigned to.
    A dedicated assignment must name at least one egress source; a
    provider-managed assignment must name the provider account. Nothing
    here is trusted as proof of isolation — verification is an explicit,
    manually reviewed operator step.
    """

    __tablename__ = "tenant_sending_configs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False
    )
    sending_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    #: KumoMTA egress pool the tenant's messages are assigned to.
    egress_pool: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    #: External delivery provider (e.g. "smtp-relay", "resend").
    provider: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    #: Provider account identifier. Never contains credentials — only a
    #: non-secret label the operator chose (an account nickname).
    provider_account: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    #: Public IPs dedicated to this tenant, as assigned by the
    #: infrastructure owner. Empty while the tenant uses a shared or
    #: provider-managed route.
    dedicated_ips: Mapped[list[str]] = mapped_column(JSONList, default=list, nullable=False)
    #: Whether the outbound route has been verified against the real
    #: network. Set only by an operator after checking the live path.
    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    verified_by: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verification_note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_tenant_sending_config"),
        Index("ix_tenant_sending_mode", "sending_mode"),
    )


class CircuitBreakerState(Base):
    """Operator-visible circuit-breaker state for one tenant.

    `open` means no tenant traffic is leaving; `half-open` means recovery
    is being probed; `closed` means normal operation. Every transition is
    written by the operator or by the evaluation, and the reason plus the
    metrics that caused it are kept for audit.
    """

    __tablename__ = "circuit_breaker_states"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    metrics_json: Mapped[dict] = mapped_column(JSONMap, default=dict, nullable=False)
    opened_by: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolve_note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------

class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    prospect_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("prospects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    subject: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    thread_id: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    state: Mapped[str] = mapped_column(String(32), default=ConversationState.OPEN.value, nullable=False)
    intent: Mapped[str] = mapped_column(String(64), default=ReplyIntent.UNCLASSIFIED.value, nullable=False)
    intent_confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    requires_action: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class InboundReply(Base):
    __tablename__ = "inbound_replies"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    conversation_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("conversations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    prospect_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    sent_message_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sender_email: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    thread_id: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    intent: Mapped[str] = mapped_column(String(64), default=ReplyIntent.UNCLASSIFIED.value, nullable=False)
    intent_confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    requires_action: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    recommended_action: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    received_by: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        Index("ix_inbound_replies_conversation", "conversation_id", "received_at"),
    )


# ---------------------------------------------------------------------------
# Workflow runtime + audit
# ---------------------------------------------------------------------------

class StageRun(Base):
    """One execution of one stage against one subject. This is the audit
    trail that makes a failure recoverable: every run stores its inputs,
    its outputs, its failure code and the recovery action to take."""

    __tablename__ = "stage_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    run_key: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    stage: Mapped[str] = mapped_column(String(64), nullable=False)
    subject_type: Mapped[str] = mapped_column(String(64), default="prospect", nullable=False)
    subject_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=RunStatus.RUNNING.value, nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    #: Why a successful run is being held for a human. Persisted so the
    #: Activity section can filter on it without re-deriving anything.
    needs_review: Mapped[list[str]] = mapped_column(JSONList, default=list, nullable=False)
    from_status: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    to_status: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    error_code: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    error_message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    recovery_action: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    triggered_by: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    input_snapshot: Mapped[dict] = mapped_column(JSONMap, default=dict, nullable=False)
    output_snapshot: Mapped[dict] = mapped_column(JSONMap, default=dict, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_stage_runs_tenant_stage_status", "tenant_id", "stage", "status"),
    )


class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    actor: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    actor_role: Mapped[str] = mapped_column(String(32), default=ActorRole.SYSTEM.value, nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    prospect_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    stage: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    details: Mapped[dict] = mapped_column(JSONMap, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        Index("ix_activity_logs_tenant_created", "tenant_id", "created_at"),
    )


class AutopilotState(Base):
    """Per-workspace state of the autonomous agent loop (services/autopilot.py).

    One row per tenant: whether the loop may advance this workspace, what the
    last tick did, and cumulative totals. Individual stage work is already
    audited by `StageRun` + `ActivityLog`; this table only holds the loop's
    own control state so the dashboard can render it without replaying runs.
    """

    __tablename__ = "autopilot_state"

    tenant_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True
    )
    #: Master switch for THIS workspace (the env master switch is separate).
    enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    #: When auto-approval is on, autopilot approves the drafts it generates
    #: before sending. Suppression/limits/compliance still apply on every send.
    auto_approve: Mapped[bool] = mapped_column(default=True, nullable=False)
    #: Whether the send step dispatches (transport still resolves per env —
    #: dry_run records without putting bytes on the wire).
    send_enabled: Mapped[bool] = mapped_column(default=True, nullable=False)

    last_tick_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_status: Mapped[str] = mapped_column(String(32), default="never_run", nullable=False)
    last_error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    #: Counters from the most recent tick (ingested/researched/…).
    last_stats: Mapped[dict] = mapped_column(JSONMap, default=dict, nullable=False)
    #: Cumulative counters across ticks.
    totals: Mapped[dict] = mapped_column(JSONMap, default=dict, nullable=False)

    updated_by: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


# ---------------------------------------------------------------------------
# Identity — one login, two interfaces
# ---------------------------------------------------------------------------

class User(Base):
    """A person who signs in to Console or Dashboard for one client instance.

    `role` reuses the API's existing ladder (`viewer` / `operator` /
    `admin`) so every `require_role` guard applies unchanged to session
    callers. `service` stays machine-only and can never be a user role.
    """

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False
    )
    #: Login identifier, stored lowercase and unique across the instance.
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    role: Mapped[str] = mapped_column(String(16), default="viewer", nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (UniqueConstraint("tenant_id", "email", name="uq_user_tenant_email"),)


class UserSession(Base):
    """A signed-in session. The raw token only ever lives in the client's
    HttpOnly cookie; the database stores its digest so a leak of the table
    cannot be replayed."""

    __tablename__ = "user_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ApiKey(Base):
    """A server-to-server credential issued to one workspace (the BFF's
    fallback and any integration). Env keys in `SLIDEIN_API_KEYS` keep
    working exactly as before; these rows let provisioning issue a key
    without an env edit."""

    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False
    )
    label: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    role: Mapped[str] = mapped_column(String(16), default="operator", nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
