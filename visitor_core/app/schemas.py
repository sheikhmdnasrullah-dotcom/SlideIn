"""Schemas: ingestion payload (RudderStack-style), CRM envelope (exact spec),
visitor record."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Ingestion (client -> POST /api/v1/capture/track)
# --------------------------------------------------------------------------- #
class TrackerContext(BaseModel):
    ip: str | None = None
    user_agent: str | None = None
    page: dict = Field(default_factory=dict)          # {url, title, referrer}
    fingerprint: dict = Field(default_factory=dict)   # canvas/browser/hardware vectors
    screen: dict = Field(default_factory=dict)


class TrackPayload(BaseModel):
    """RudderStack-server-shaped track call, trimmed to what we consume."""
    type: str = "track"
    event: str = "page_view"
    anonymous_id: str | None = None
    user_id: str | None = None
    site_key: str                                  # issued per client site
    session_id: str | None = None                  # first-party cookie value
    query_marker_token: str | None = None          # intercepted ?he= value
    context: TrackerContext = Field(default_factory=TrackerContext)
    sent_at: datetime | None = None


# --------------------------------------------------------------------------- #
# CRM wire envelope (worker -> dashboard, EXACT layout)
# --------------------------------------------------------------------------- #
class ResolutionTier(str, Enum):
    COOKIE_STITCH = "COOKIE_STITCH"
    LOCAL_GEOIP = "LOCAL_GEOIP"
    RETENTION_API = "RETENTION_API"
    ANONYMOUS = "ANONYMOUS"


class CRMStatus(str, Enum):
    QUEUED = "QUEUED"
    TRACKING = "TRACKING"
    STITCHING = "STITCHING"
    FALLBACK_TRIGGERED = "FALLBACK_TRIGGERED"
    COMPLETED = "COMPLETED"


class CRMDelta(BaseModel):
    email: str | None = None
    company_domain: str | None = None
    prospect_name: str | None = None
    linkedin_url: str | None = None


class CRMEnvelope(BaseModel):
    task_id: str
    site_domain: str
    resolution_tier: ResolutionTier
    status: CRMStatus
    live_crm_delta: CRMDelta = Field(default_factory=CRMDelta)
    error_logs: str | None = None

    # routing metadata
    visitor_id: str | None = None
    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# --------------------------------------------------------------------------- #
# DB record
# --------------------------------------------------------------------------- #
class VisitorRecord(BaseModel):
    visitor_id: str
    site_key: str
    site_domain: str | None = None
    ip: str | None = None
    user_agent: str | None = None
    fingerprint_hash: str | None = None
    session_id: str | None = None
    resolution_tier: str = "ANONYMOUS"
    status: str = "COMPLETED"
    email: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    linkedin_url: str | None = None
    company_domain: str | None = None
    geo: dict = Field(default_factory=dict)
    error_logs: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
