"""Factory tables: owners, assignments, field maps, connections, configs.

Industry-neutral: no mortgage/loan concepts here. A client with loan
officers is just a client with 15 team owners and a booking provider.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..json_types import JSONList, JSONMap
from ..models import Base, utcnow


class TeamOwner(Base):
    """One client team member who can own prospects and receive bookings."""

    __tablename__ = "team_owners"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False
    )
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    crm_provider: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    crm_owner_id: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    booking_provider: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    booking_url: Mapped[str] = mapped_column(String(1024), default="", nullable=False)
    booking_event_ref: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    booking_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    __table_args__ = (UniqueConstraint("tenant_id", "email", name="uq_owner_tenant_email"),)


class ProspectOwnerAssignment(Base):
    """Current owner of one prospect, with append-only history."""

    __tablename__ = "prospect_owner_assignments"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    prospect_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("prospects.id", ondelete="CASCADE"), unique=True,
        index=True, nullable=False,
    )
    owner_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("team_owners.id", ondelete="SET NULL"), nullable=True
    )
    source: Mapped[str] = mapped_column(String(32), default="manual", nullable=False)
    history: Mapped[list[dict]] = mapped_column(JSONList, default=list, nullable=False)
    assigned_by: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class CrmFieldMap(Base):
    """Canonical Slidein field <-> external CRM field, per client."""

    __tablename__ = "crm_field_maps"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    slidein_field: Mapped[str] = mapped_column(String(128), nullable=False)
    external_field: Mapped[str] = mapped_column(String(255), nullable=False)
    direction: Mapped[str] = mapped_column(String(8), default="both", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "provider", "slidein_field", name="uq_crm_map_field"
        ),
    )


class IntegrationConnection(Base):
    """A connected external system. Only the secret *reference* is stored."""

    __tablename__ = "integration_connections"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    secret_ref: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    scopes: Mapped[list[str]] = mapped_column(JSONList, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "provider", "label", name="uq_connection_label"
        ),
    )


class DeploymentConfig(Base):
    """Versioned, auditable deployment configuration. Never edited in place:
    save and rollback both append a new version and flip ``is_active``."""

    __tablename__ = "deployment_configs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False
    )
    blueprint_name: Mapped[str] = mapped_column(String(128), nullable=False)
    blueprint_version: Mapped[str] = mapped_column(String(32), nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONMap, default=dict, nullable=False)
    actor: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    note: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "version_no", name="uq_deploy_config_version"),
    )
