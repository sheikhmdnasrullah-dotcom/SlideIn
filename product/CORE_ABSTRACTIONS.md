# Core Product Abstractions

> This document defines the canonical product abstractions for Acquisition OS.
> These are the building blocks from which the entire product is constructed.

---

## 1. Acquisition Engine (the pipeline)

```python
class AcquisitionEngine:
    """
    The core finite-state machine that governs opportunity lifecycle.
    Every opportunity flows through these states.
    """
    pass

# States (ordered)
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

# Valid transitions (partial)
TRANSITIONS = {
    DISCOVERED: [RESEARCHED, DISQUALIFIED],
    RESEARCHED: [QUALIFIED, DISQUALIFIED],
    QUALIFIED: [CONTACTED, NURTURING],
    CONTACTED: [ENGAGED, NURTURING],
    ENGAGED: [INTENT_DETECTED, NURTURING],
    INTENT_DETECTED: [BOOKING, ENGAGED, NURTURING],
    BOOKING: [MEETING_SCHEDULED, ENGAGED],
    MEETING_SCHEDULED: [MEETING_COMPLETED, BOOKING],
    MEETING_COMPLETED: [OPPORTUNITY, NURTURING],
    OPPORTUNITY: [CUSTOMER],
    CUSTOMER: [],
    COOLING: [NURTURING, DISQUALIFIED],
    NURTURING: [ENGAGED, DISQUALIFIED],
    DISQUALIFIED: [],
}
```

---

## 2. Opportunity Profile

```python
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

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

class Person(BaseModel):
    name: str
    email: str
    phone: Optional[str] = None
    location: Optional[str] = None
    household_size: Optional[int] = None
    income_range: Optional[str] = None

class FitScore(BaseModel):
    icp_match: int = Field(ge=0, le=100)
    location_match: int = Field(ge=0, le=100)
    purchase_timeframe: int = Field(ge=0, le=100)
    property_range: int = Field(ge=0, le=100)
    segment: Optional[str] = None
    total: int = Field(ge=0, le=100)

class IntentSignal(BaseModel):
    type: str  # buying_signal, objection, question, intent
    text: str
    source: str  # email, calculator, conversation, behavior
    timestamp: datetime
    confidence: float = Field(ge=0.0, le=1.0)

class BehaviorEvent(BaseModel):
    type: str  # content_consumed, calculator_use, email_open, link_click, reply
    content_id: Optional[str] = None
    content_title: Optional[str] = None
    timestamp: datetime
    metadata: Dict[str, Any] = {}

class ConversationMessage(BaseModel):
    id: str
    direction: str  # inbound, outbound
    channel: str  # email, sms, chat
    subject: Optional[str] = None
    body: str
    timestamp: datetime
    intent: Optional[str] = None
    signals: List[IntentSignal] = []

class QualificationAnswer(BaseModel):
    question: str
    answer: str
    timestamp: datetime

class Appointment(BaseModel):
    status: str  # proposed, confirmed, completed, cancelled
    proposed_times: List[datetime] = []
    confirmed_time: Optional[datetime] = None
    advisor_id: Optional[str] = None
    calendar_link: Optional[str] = None

class Provenance(BaseModel):
    source: str  # inbound, proactive, referral
    discovery_signals: List[str] = []
    research_evidence: List[Dict[str, str]] = []  # {source, summary, confidence}
    confidence: str  # high, medium, low

class Lifecycle(BaseModel):
    discovered_at: datetime
    last_contacted_at: Optional[datetime] = None
    last_engaged_at: Optional[datetime] = None
    next_action_at: Optional[datetime] = None
    state: OpportunityState
    state_history: List[Dict[str, Any]] = []  # {state, entered_at, exited_at, reason}

class OpportunityProfile(BaseModel):
    """
    The complete opportunity record. Replaces flat CRM records.
    """
    id: str
    org_id: str
    person: Person
    opportunity_score: int = Field(ge=0, le=100)
    fit: FitScore
    intent: Dict[str, Any]  # {level, signals[], objections[], questions[]}
    behavior: List[BehaviorEvent] = []
    conversation: List[ConversationMessage] = []
    qualification: Dict[str, Any]  # {answers{}, stage, recommended_angle}
    appointment: Optional[Appointment] = None
    provenance: Provenance
    lifecycle: Lifecycle
    next_best_action: Optional[str] = None
    next_best_action_reason: Optional[str] = None
    tags: List[str] = []
    custom_fields: Dict[str, Any] = {}
    created_at: datetime
    updated_at: datetime
    version: int = 1  # for optimistic concurrency / event sourcing
```

---

## 3. Mission (high-level acquisition goal)

```python
class Mission(BaseModel):
    """
    A high-level acquisition mission that the platform translates into automation.
    """
    id: str
    org_id: str
    name: str
    description: Optional[str] = None
    active: bool = True

    # Target definition
    target_segment: str  # e.g., "first-time-homebuyer"
    location: str  # e.g., "Austin, TX"
    property_range: Optional[str] = None  # e.g., "$400k–$800k"
    monthly_goal: int  # e.g., 20 qualified conversations

    # Preferred action
    preferred_action: str  # e.g., "calendar_booking"
    advisor_id: str
    calendar_id: str  # Google Calendar, Calendly, etc.

    # Brand
    brand_id: str

    # Automation output
    generated_automation_id: Optional[str] = None  # reference to created automation

    created_at: datetime
    updated_at: datetime
```

---

## 4. Automation (visual workflow)

```python
class AutomationStep(BaseModel):
    type: str  # trigger, condition, action, wait
    config: Dict[str, Any]

class Automation(BaseModel):
    id: str
    org_id: str
    name: str
    description: Optional[str] = None
    active: bool = True
    steps: List[AutomationStep]
    version: int = 1
    created_at: datetime
    updated_at: datetime
```

---

## 5. Content

```python
class ContentType(str, Enum):
    ARTICLE = "article"
    LINKEDIN_POST = "linkedin_post"
    VIDEO_SCRIPT = "video_script"
    LEAD_MAGNET = "lead_magnet"
    CALCULATOR = "calculator"
    EMAIL = "email"
    LANDING_PAGE = "landing_page"

class Content(BaseModel):
    id: str
    org_id: str
    title: str
    type: ContentType
    body: str
    metadata: Dict[str, Any] = {}  # tags, topic, seasonality, etc.
    published: bool = False
    published_at: Optional[datetime] = None
    related_content_ids: List[str] = []  # content graph
    attribution: Dict[str, Any] = {}  # views, leads, opportunities, meetings
    created_at: datetime
    updated_at: datetime
```

---

## 6. Campaign

```python
class CampaignType(str, Enum):
    INBOUND = "inbound"
    PROACTIVE = "proactive"
    NURTURE = "nurture"
    CONTENT = "content"

class Campaign(BaseModel):
    id: str
    org_id: str
    name: str
    type: CampaignType
    description: Optional[str] = None
    active: bool = True

    # Targeting
    segment: Optional[str] = None
    filters: Dict[str, Any] = {}  # location, fit_score_min, state, etc.

    # Content
    content_ids: List[str] = []
    message_template_id: Optional[str] = None

    # Automation
    automation_id: Optional[str] = None

    # Metrics
    metrics: Dict[str, Any] = {}  # sent, opened, replied, qualified, booked

    created_at: datetime
    updated_at: datetime
```

---

## 7. Acquisition Health

```python
class HealthMetric(str, Enum):
    LEAD_FLOW = "lead_flow"
    RESEARCH_COVERAGE = "research_coverage"
    CONVERSATION_HEALTH = "conversation_health"
    BOOKING_RATE = "booking_rate"
    CONTENT_PERFORMANCE = "content_performance"
    EMAIL_DELIVERABILITY = "email_deliverability"

class HealthStatus(str, Enum):
    EXCELLENT = "excellent"
    GOOD = "good"
    NEEDS_ATTENTION = "needs_attention"
    CRITICAL = "critical"

class HealthMetricResult(BaseModel):
    metric: HealthMetric
    status: HealthStatus
    value: float
    target: float
    trend: str  # up, down, stable
    detail: str

class AcquisitionHealth(BaseModel):
    org_id: str
    metrics: List[HealthMetricResult]
    recommendation: str
    generated_at: datetime
```

---

## 8. System Activity

```python
class ActivityType(str, Enum):
    OPPORTUNITY_DISCOVERED = "opportunity_discovered"
    OPPORTUNITY_RESEARCHED = "opportunity_researched"
    HIGH_INTENT_DETECTED = "high_intent_detected"
    MESSAGE_SENT = "message_sent"
    PROSPECT_REPLIED = "prospect_replied"
    CALENDAR_LINK_SENT = "calendar_link_sent"
    APPOINTMENT_BOOKED = "appointment_booked"
    CONTENT_PUBLISHED = "content_published"
    AUTOMATION_TRIGGERED = "automation_triggered"
    OPPORTUNITY_STATE_CHANGED = "opportunity_state_changed"

class SystemActivity(BaseModel):
    id: str
    org_id: str
    type: ActivityType
    description: str
    entity_id: Optional[str] = None  # opportunity_id, content_id, etc.
    metadata: Dict[str, Any] = {}
    timestamp: datetime
```

---

*End of Core Product Abstractions*
