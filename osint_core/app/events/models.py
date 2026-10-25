"""Real-time event contract — worker → frontend wire schema (exact spec).

Frontend receives ONLY these envelopes over Redis Pub/Sub -> WS/SSE; every
field maps 1:1 to dashboard state. No simulated progress: percentages are
computed from real completed/total chunk counts, extracted_delta carries only
genuinely retrieved data fragments, error_logs carries true tracebacks.

Internal enums (ModuleName / ModuleStatus) drive the pipeline; they map onto
the wire names via `to_framework()` / `to_lifecycle()`.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class ModuleName(str, Enum):
    """active_framework values."""
    FIREENRICH = "FireEnrich"
    WEBSCRAPER = "WebsiteScraper"
    SPIDERFOOT = "Spiderfoot"
    SUBFINDER = "Subfinder"
    DNSRECON = "Dnsrecon"
    MAIGRET = "Maigret"
    BLACKBIRD = "Blackbird"
    HOLEHE = "Holehe"
    BOMKESH = "Bomkesh"
    MAILACCESS = "MailAccess"
    NOIMOSINY = "Noimosiny"
    BRIGHTDATA = "BrightData"
    GRAPH = "EntityGraph"
    AI_AGENT_REASONING = "AI-Agent-Reasoning"


FrameworkName = ModuleName  # wire alias


class ModuleStatus(str, Enum):
    """Internal lifecycle states (superset granularity of the wire enum)."""
    QUEUED = "QUEUED"
    INITIALIZED = "INITIALIZED"
    RESOLVING_PROXIES = "RESOLVING_PROXIES"
    EXTRACTING_DOM = "EXTRACTING_DOM"
    PIPELINING_GRAPH = "PIPELINING_GRAPH"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class LifecycleStatus(str, Enum):
    """Wire lifecycle_status values (exact spec)."""
    QUEUED = "QUEUED"
    ROUTING_PROXIES = "ROUTING_PROXIES"
    PARSING_DOM = "PARSING_DOM"
    PROCESSING_AI = "PROCESSING_AI"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

    @classmethod
    def from_module_status(cls, s: ModuleStatus) -> "LifecycleStatus":
        return {
            ModuleStatus.QUEUED: cls.QUEUED,
            ModuleStatus.INITIALIZED: cls.QUEUED,
            ModuleStatus.RESOLVING_PROXIES: cls.ROUTING_PROXIES,
            ModuleStatus.EXTRACTING_DOM: cls.PARSING_DOM,
            ModuleStatus.PIPELINING_GRAPH: cls.PROCESSING_AI,
            ModuleStatus.COMPLETED: cls.COMPLETED,
            ModuleStatus.FAILED: cls.FAILED,
        }[s]


class EventEnvelope(BaseModel):
    """Strict dashboard wire payload."""
    task_id: str
    active_framework: FrameworkName
    lifecycle_status: LifecycleStatus
    progress_percentage: float = Field(default=0.0, ge=0.0, le=100.0)
    extracted_delta: dict = Field(default_factory=dict)
    error_logs: str | None = None

    # routing metadata (extra keys beyond the core six — needed for fan-out)
    job_id: str | None = None
    lead_email: str | None = None
    chunk_progress: dict | None = None      # {"completed_chunks": 20, "total_chunks": 120}
    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
