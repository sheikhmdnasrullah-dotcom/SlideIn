"""
Acquisition OS — API Schemas
Pydantic models for request/response validation.
"""

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, EmailStr, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class OpportunityState(str, Enum):
    DISCOVERED = "discovered"
    RESEARCHED = "researched"
    QUALIFIED = "qualified"
    CONTACTED = "contacted"
    ENGAGED = "engaged"
    INTENT_DETECTED = "intent_detected"
    BOOKING = "booking"
    MEETING_SCHEDULED = "meeting_scheduled"
    MEETING_COMPLETED = "meeting_completed"
    OPPORTUNITY = "opportunity"
    CUSTOMER = "customer"
    COOLING = "cooling"
    NURTURING = "nurturing"
    DISQUALIFIED = "disqualified"


class PersonSchema(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    email: EmailStr
    phone: Optional[str] = Field(None, max_length=50)
    location: Optional[str] = Field(None, max_length=255)
    household_size: Optional[int] = Field(None, ge=1)
    income_range: Optional[str] = Field(None, max_length=100)


class FitScoreSchema(BaseModel):
    icp_match: int = Field(ge=0, le=100)
    location_match: int = Field(ge=0, le=100)
    purchase_timeframe: int = Field(ge=0, le=100)
    property_range: int = Field(ge=0, le=100)
    segment: Optional[str] = None
    total: int = Field(ge=0, le=100)


class IntentSchema(BaseModel):
    level: str  # low, medium, high
    signals: List[Dict[str, Any]] = []
    objections: List[str] = []
    questions: List[str] = []


class OpportunityCreateSchema(BaseModel):
    person: PersonSchema
    source: str = Field("inbound", max_length=50)  # inbound, proactive, referral
    discovery_signals: List[str] = []
    custom_fields: Dict[str, Any] = {}


class OpportunityResponseSchema(BaseModel):
    id: str
    org_id: str
    person: PersonSchema
    opportunity_score: int = Field(ge=0, le=100)
    fit: FitScoreSchema
    intent: IntentSchema
    state: OpportunityState
    qualification: Dict[str, Any] = {}
    next_best_action: Optional[str] = None
    next_best_action_reason: Optional[str] = None
    next_action_at: Optional[datetime] = None
    tags: List[str] = []
    created_at: datetime
    updated_at: datetime
    version: int = 1

    model_config = ConfigDict(from_attributes=True)


class OpportunityDetailSchema(OpportunityResponseSchema):
    behavior: List[Dict[str, Any]] = []
    conversation: List[Dict[str, Any]] = []
    appointment: Optional[Dict[str, Any]] = None
    provenance: Dict[str, Any] = {}
    lifecycle: Dict[str, Any] = {}
    research_dossier: Optional[Dict[str, Any]] = None


class ResearchRequestSchema(BaseModel):
    depth: str = Field("standard", pattern="^(quick|standard|deep)$")
    sources: List[str] = ["linkedin", "public_records", "real_estate"]


class ResearchResponseSchema(BaseModel):
    opportunity_id: str
    dossier: Dict[str, Any]
    evidence: List[Dict[str, Any]] = []
    confidence: str  # high, medium, low
    opportunity_score: int = Field(ge=0, le=100)
    updated_at: datetime


class QualificationResponseSchema(BaseModel):
    opportunity_id: str
    fit_score: FitScoreSchema
    opportunity_score: int = Field(ge=0, le=100)
    qualification_stage: str
    reasoning: str
    recommended_angle: str
    updated_at: datetime


class PersonalizationRequestSchema(BaseModel):
    message_type: str = Field("initial_outreach", pattern="^(initial_outreach|follow_up|response)$")
    context: Dict[str, Any] = {}


class PersonalizationResponseSchema(BaseModel):
    opportunity_id: str
    personalization: Dict[str, Any]
    provenance: List[Dict[str, Any]] = []
    generated_at: datetime


class MessageRequestSchema(BaseModel):
    channel: str = Field("email", max_length=50)
    purpose: str = Field("initial_outreach", pattern="^(initial_outreach|follow_up|response)$")
    template_id: Optional[str] = None
    personalization_id: Optional[str] = None


class MessageResponseSchema(BaseModel):
    opportunity_id: str
    message: Dict[str, Any]
    generated_at: datetime


class SendRequestSchema(BaseModel):
    from_identity_id: str
    subject: str = Field(..., max_length=500)
    body: str
    channel: str = Field("email", max_length=50)
    schedule_at: Optional[datetime] = None


class SendResponseSchema(BaseModel):
    opportunity_id: str
    message_id: str
    status: str
    scheduled_at: Optional[datetime] = None
    metadata: Dict[str, Any] = {}


class BookRequestSchema(BaseModel):
    advisor_id: str
    calendar_id: str
    purpose: str = Field("initial_consultation", max_length=100)


class BookResponseSchema(BaseModel):
    opportunity_id: str
    recommendation: Dict[str, Any]
    generated_at: datetime


class PipelineResponseSchema(BaseModel):
    pipeline: Dict[str, Dict[str, Any]]
    conversion_rates: Dict[str, str]


class CommandCenterResponseSchema(BaseModel):
    greeting: str
    overnight_summary: Dict[str, int]
    todays_priorities: List[Dict[str, Any]]
    system_activity: List[Dict[str, Any]]
    generated_at: datetime


class HealthMetricSchema(BaseModel):
    metric: str
    status: str  # excellent, good, needs_attention, critical
    value: float
    target: float
    trend: str  # up, down, stable
    detail: str


class AcquisitionHealthResponseSchema(BaseModel):
    org_id: str
    metrics: List[HealthMetricSchema]
    recommendation: str
    generated_at: datetime


class ContentAttributionSchema(BaseModel):
    content_id: str
    title: str
    attribution: Dict[str, Any]


class ContentAttributionResponseSchema(BaseModel):
    content: ContentAttributionSchema


class EfficiencyResponseSchema(BaseModel):
    qualified_opportunities_per_cost: float
    meetings_per_1000_prospects: float
    cost_per_qualified_opportunity: float
    cost_per_meeting: float
    period: str
    generated_at: datetime


class CommandRequestSchema(BaseModel):
    command: str = Field(..., min_length=1)
    context: Dict[str, Any] = {}


class CommandResponseSchema(BaseModel):
    command: str
    interpreted: Dict[str, Any]
    results: List[Dict[str, Any]]
    suggestions: List[str]


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------

class PaginationParams(BaseModel):
    limit: int = Field(20, ge=1, le=100)
    offset: int = Field(0, ge=0)


class PaginatedResponse(BaseModel):
    data: List[Any]
    pagination: Dict[str, int]
