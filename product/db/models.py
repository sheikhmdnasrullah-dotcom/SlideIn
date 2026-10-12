"""
Acquisition OS — Database Models
SQLAlchemy 2.0 async models for PostgreSQL.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from sqlalchemy import (
    String, DateTime, Boolean, Integer, Float, Text,
    JSON, ForeignKey, Index, Enum as SQLEnum,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
import uuid

from sqlalchemy import Column, String, DateTime, Boolean, Integer, Float, Text, JSON, ForeignKey, Index, Enum as SQLEnum
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.sql import func
import uuid as uuid_module
from datetime import datetime
from typing import Optional, List, Dict, Any as DBAny


class Base(DeclarativeBase):
    pass


class TenantMixin:
    """Mixin for multi-tenant tables."""
    org_id = Column(String(255), nullable=False, index=True)
    tenant_id = Column(String(255), nullable=False, index=True)


class TimestampMixin:
    """Mixin for created_at / updated_at timestamps."""
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class Organization(TenantMixin, TimestampMixin, Base):
    __tablename__ = "organizations"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid_module.uuid4()))
    name = Column(String(255), nullable=False)
    slug = Column(String(100), unique=True, nullable=False, index=True)
    logo_url = Column(Text, nullable=True)
    primary_color = Column(String(7), nullable=True)
    custom_domain = Column(String(255), nullable=True)
    plan = Column(String(50), default="starter", nullable=False)
    plan_status = Column(String(50), default="active", nullable=False)
    settings = Column(JSON, default=dict, nullable=False)
    monthly_send_limit = Column(Integer, default=5000, nullable=False)
    monthly_opportunity_limit = Column(Integer, default=500, nullable=False)
    deleted_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_organizations_tenant_slug", "tenant_id", "slug", unique=True),
    )


class User(TenantMixin, TimestampMixin, Base):
    __tablename__ = "users"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid_module.uuid4()))
    org_id = Column(String(255), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    avatar_url = Column(Text, nullable=True)
    password_hash = Column(String(255), nullable=True)
    email_verified = Column(Boolean, default=False, nullable=False)
    email_verification_token = Column(String(255), nullable=True)
    password_reset_token = Column(String(255), nullable=True)
    password_reset_expires_at = Column(DateTime, nullable=True)
    role = Column(String(50), default="advisor", nullable=False)
    calendar_provider = Column(String(50), nullable=True)
    calendar_id = Column(String(255), nullable=True)
    calendar_credentials = Column(JSON, nullable=True)
    active = Column(Boolean, default=True, nullable=False)
    last_login_at = Column(DateTime, nullable=True)
    deleted_at = Column(DateTime, nullable=True)


class SendingIdentity(TenantMixin, TimestampMixin, Base):
    __tablename__ = "sending_identities"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid_module.uuid4()))
    org_id = Column(String(255), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    display_name = Column(String(255), nullable=True)
    dkim_selector = Column(String(100), nullable=True)
    dkim_public_key = Column(Text, nullable=True)
    active = Column(Boolean, default=True, nullable=False)
    warmup_complete = Column(Boolean, default=False, nullable=False)
    reputation_score = Column(Integer, nullable=True)

    __table_args__ = (
        Index("idx_sending_identities_org_email", "org_id", "email", unique=True),
    )


class Opportunity(TenantMixin, TimestampMixin, Base):
    __tablename__ = "opportunities"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid_module.uuid4()))
    org_id = Column(String(255), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    person = Column(JSON, nullable=False)
    opportunity_score = Column(Integer, default=0, nullable=False)
    fit = Column(JSON, default=dict, nullable=False)
    intent = Column(JSON, default=dict, nullable=False)
    state = Column(String(50), default="discovered", nullable=False, index=True)
    state_history = Column(JSON, default=list, nullable=False)
    qualification = Column(JSON, default=dict, nullable=False)
    conversation = Column(JSON, default=list, nullable=False)
    appointment = Column(JSON, nullable=True)
    provenance = Column(JSON, default=dict, nullable=False)
    behavior = Column(JSON, default=list, nullable=False)
    lifecycle = Column(JSON, default=dict, nullable=False)
    next_best_action = Column(String(255), nullable=True)
    next_best_action_reason = Column(Text, nullable=True)
    next_action_at = Column(DateTime, nullable=True, index=True)
    tags = Column(JSON, default=list, nullable=False)
    custom_fields = Column(JSON, default=dict, nullable=False)
    version = Column(Integer, default=1, nullable=False)
    deleted_at = Column(DateTime, nullable=True)
    research_dossier = Column(JSON, nullable=True)

    __table_args__ = (
        Index("idx_opportunities_org_state", "org_id", "state"),
        Index("idx_opportunities_org_score", "org_id", "opportunity_score"),
        Index("idx_opportunities_org_next_action", "org_id", "next_action_at"),
    )


class OpportunityEvent(TenantMixin, Base):
    __tablename__ = "opportunity_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    org_id = Column(String(255), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    opportunity_id = Column(String(255), ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False)
    event_type = Column(String(100), nullable=False, index=True)
    event_data = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_opportunity_events_opp", "opportunity_id", "created_at"),
        Index("idx_opportunity_events_org_created", "org_id", "created_at"),
    )


class ResearchDossier(TenantMixin, Base):
    __tablename__ = "research_dossiers"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid_module.uuid4()))
    org_id = Column(String(255), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    opportunity_id = Column(String(255), ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False, unique=True)
    dossier = Column(JSON, nullable=False)
    evidence = Column(JSON, default=list, nullable=False)
    confidence = Column(String(20), nullable=False)
    provenance_note = Column(Text, nullable=True)
    generated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Content(TenantMixin, TimestampMixin, Base):
    __tablename__ = "content"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid_module.uuid4()))
    org_id = Column(String(255), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(500), nullable=False)
    type = Column(String(50), nullable=False, index=True)
    body = Column(Text, nullable=False)
    metadata = Column(JSON, default=dict, nullable=False)
    published = Column(Boolean, default=False, nullable=False)
    published_at = Column(DateTime, nullable=True)
    published_channels = Column(JSON, default=list, nullable=False)
    related_content_ids = Column(JSON, default=list, nullable=False)
    attribution = Column(JSON, default=dict, nullable=False)
    created_by = Column(String(255), nullable=True)


class Campaign(TenantMixin, TimestampMixin, Base):
    __tablename__ = "campaigns"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid_module.uuid4()))
    org_id = Column(String(255), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    type = Column(String(50), nullable=False, index=True)
    segment = Column(String(255), nullable=True)
    filters = Column(JSON, default=dict, nullable=False)
    content_ids = Column(JSON, default=list, nullable=False)
    message_template_id = Column(String(255), nullable=True)
    automation_id = Column(String(255), nullable=True)
    metrics = Column(JSON, default=dict, nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    created_by = Column(String(255), nullable=True)


class Automation(TenantMixin, TimestampMixin, Base):
    __tablename__ = "automations"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid_module.uuid4()))
    org_id = Column(String(255), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    active = Column(Boolean, default=True, nullable=False)
    trigger_type = Column(String(100), nullable=False)
    trigger_config = Column(JSON, default=dict, nullable=False)
    steps = Column(JSON, default=list, nullable=False)
    version = Column(Integer, default=1, nullable=False)
    parent_id = Column(String(255), nullable=True)
    created_by = Column(String(255), nullable=True)
    dry_run_results = Column(JSON, nullable=True)
    execution_history = Column(JSON, default=list, nullable=False)


class Mission(TenantMixin, TimestampMixin, Base):
    __tablename__ = "missions"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid_module.uuid4()))
    org_id = Column(String(255), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    active = Column(Boolean, default=True, nullable=False)
    target_segment = Column(String(255), nullable=False)
    location = Column(String(255), nullable=False)
    property_range = Column(String(255), nullable=True)
    monthly_goal = Column(Integer, nullable=False)
    preferred_action = Column(String(100), nullable=False)
    advisor_id = Column(String(255), nullable=True)
    calendar_id = Column(String(255), nullable=True)
    generated_automation_id = Column(String(255), nullable=True)
    created_by = Column(String(255), nullable=True)


class Conversation(TenantMixin, TimestampMixin, Base):
    __tablename__ = "conversations"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid_module.uuid4()))
    org_id = Column(String(255), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    opportunity_id = Column(String(255), ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False)
    channel = Column(String(50), nullable=False)
    state = Column(String(50), default="active", nullable=False)
    intent = Column(String(100), nullable=True)
    intent_confidence = Column(Float, nullable=True)
    assigned_to = Column(String(255), nullable=True)
    last_message_at = Column(DateTime, nullable=True)


class Message(TenantMixin, Base):
    __tablename__ = "messages"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid_module.uuid4()))
    org_id = Column(String(255), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    conversation_id = Column(String(255), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    opportunity_id = Column(String(255), ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False)
    direction = Column(String(20), nullable=False)
    channel = Column(String(50), nullable=False)
    subject = Column(String(500), nullable=True)
    body = Column(Text, nullable=False)
    intent = Column(String(100), nullable=True)
    signals = Column(JSON, default=list, nullable=False)
    classification = Column(JSON, nullable=True)
    message_id = Column(String(255), nullable=True)
    from_address = Column(String(255), nullable=True)
    to_address = Column(String(255), nullable=True)
    ai_draft = Column(Boolean, default=False, nullable=False)
    ai_approved = Column(Boolean, nullable=True)
    ai_confidence = Column(Float, nullable=True)
    sent_at = Column(DateTime, nullable=True)
    received_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class SystemActivity(TenantMixin, Base):
    __tablename__ = "system_activities"

    id = Column(Integer, primary_key=True, autoincrement=True)
    org_id = Column(String(255), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    type = Column(String(100), nullable=False, index=True)
    description = Column(Text, nullable=False)
    entity_id = Column(String(255), nullable=True)
    entity_type = Column(String(100), nullable=True)
    metadata = Column(JSON, default=dict, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_system_activities_org_timestamp", "org_id", "timestamp"),
        Index("idx_system_activities_type", "type"),
    )


class AcquisitionHealth(TenantMixin, Base):
    __tablename__ = "acquisition_health"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid_module.uuid4()))
    org_id = Column(String(255), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    metrics = Column(JSON, default=list, nullable=False)
    recommendation = Column(Text, nullable=True)
    generated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Integration(TenantMixin, TimestampMixin, Base):
    __tablename__ = "integrations"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid_module.uuid4()))
    org_id = Column(String(255), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    type = Column(String(50), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    credentials = Column(JSON, default=dict, nullable=False)
    config = Column(JSON, default=dict, nullable=False)
    last_sync_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)


class SentMessage(TenantMixin, Base):
    __tablename__ = "sent_messages"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid_module.uuid4()))
    org_id = Column(String(255), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    opportunity_id = Column(String(255), ForeignKey("opportunities.id", ondelete="SET NULL"), nullable=True)
    conversation_id = Column(String(255), ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True)
    direction = Column(String(20), nullable=False)
    channel = Column(String(50), nullable=False)
    from_address = Column(String(255), nullable=False)
    to_address = Column(String(255), nullable=False)
    subject = Column(String(500), nullable=True)
    body = Column(Text, nullable=False)
    provider_message_id = Column(String(255), nullable=True)
    provider = Column(String(50), nullable=True)
    status = Column(String(50), nullable=False, index=True)
    status_updated_at = Column(DateTime, nullable=True)
    queued_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    sent_at = Column(DateTime, nullable=True)
    delivered_at = Column(DateTime, nullable=True)
    opened_at = Column(DateTime, nullable=True)
    clicked_at = Column(DateTime, nullable=True)
    replied_at = Column(DateTime, nullable=True)
    bounced_at = Column(DateTime, nullable=True)
    complained_at = Column(DateTime, nullable=True)
    metadata = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_sent_messages_org_status", "org_id", "status"),
        Index("idx_sent_messages_opportunity", "opportunity_id"),
        Index("idx_sent_messages_conversation", "conversation_id"),
    )


class ContentAttribution(TenantMixin, Base):
    __tablename__ = "content_attribution"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid_module.uuid4()))
    org_id = Column(String(255), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    content_id = Column(String(255), ForeignKey("content.id", ondelete="CASCADE"), nullable=False)
    opportunity_id = Column(String(255), ForeignKey("opportunities.id", ondelete="SET NULL"), nullable=True)
    event_type = Column(String(100), nullable=False, index=True)
    value = Column(Float, nullable=True)
    occurred_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    metadata = Column(JSON, default=dict, nullable=False)


class OnboardingStep(TenantMixin, Base):
    __tablename__ = "onboarding_steps"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid_module.uuid4()))
    org_id = Column(String(255), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    step = Column(String(100), nullable=False)
    status = Column(String(50), default="pending", nullable=False)
    completed_at = Column(DateTime, nullable=True)
    data = Column(JSON, default=dict, nullable=False)


class AutomationExecution(TenantMixin, Base):
    __tablename__ = "automation_executions"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid_module.uuid4()))
    org_id = Column(String(255), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    automation_id = Column(String(255), ForeignKey("automations.id", ondelete="CASCADE"), nullable=False)
    trigger_type = Column(String(100), nullable=False)
    trigger_data = Column(JSON, default=dict, nullable=False)
    steps_executed = Column(JSON, default=list, nullable=False)
    result = Column(JSON, default=dict, nullable=False)
    dry_run = Column(Boolean, default=False, nullable=False)
    status = Column(String(50), default="running", nullable=False)
    error = Column(Text, nullable=True)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)
