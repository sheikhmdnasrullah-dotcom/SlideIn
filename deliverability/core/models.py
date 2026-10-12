"""SlideIn Domain Models and Data Structures.

Enterprise multi-tenant data entities for workspaces, verified domains,
sender profiles, leads, two-way conversations, campaigns, and delivery telemetry.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional


class LeadStage(str, Enum):
    CAPTURED = "captured"
    ENGAGED = "engaged"
    QUALIFIED = "qualified"
    BOOKED = "booked"
    NURTURE = "nurture"
    UNSUBSCRIBED = "unsubscribed"
    BOUNCED = "bounced"


class MessageDirection(str, Enum):
    OUTBOUND = "outbound"
    INBOUND = "inbound"


class IntentType(str, Enum):
    READY_TO_BOOK = "ready_to_book"
    ASKING_RATES = "asking_rates"
    PURCHASE_TIMELINE = "purchase_timeline"
    PRE_APPROVAL_STATUS = "pre_approval_status"
    GENERAL_INQUIRY = "general_inquiry"
    NOT_INTERESTED = "not_interested"
    OUT_OF_OFFICE = "out_of_office"
    UNKNOWN = "unknown"


@dataclass
class Workspace:
    id: str = field(default_factory=lambda: f"ws_{uuid.uuid4().hex[:12]}")
    name: str = "Default Workspace"
    slug: str = "default"
    api_key: str = field(default_factory=lambda: f"sk_live_{uuid.uuid4().hex}")
    created_at: float = field(default_factory=time.time)
    settings: Dict[str, Any] = field(default_factory=lambda: {
        "daily_send_limit": 200,
        "speed_to_lead_enabled": True,
        "auto_qualify_enabled": True,
        "booking_url": "https://cal.com/mortgage-advisor/intro",
        "default_sender_id": None
    })

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DomainRecord:
    id: str = field(default_factory=lambda: f"dom_{uuid.uuid4().hex[:10]}")
    workspace_id: str = "default"
    domain: str = "nasrullahtanim.me"
    spf_record: str = "v=spf1 ip4:127.0.0.1 ~all"
    dkim_selector: str = "kumo"
    dkim_public_key: str = "v=DKIM1; k=rsa; p=MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8A..."
    dmarc_policy: str = "v=DMARC1; p=quarantine; rua=mailto:dmarc-reports@nasrullahtanim.me; pct=100"
    tracking_cname: str = "track.nasrullahtanim.me"
    status: str = "verified"  # verified, pending, failed
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SenderProfile:
    id: str = field(default_factory=lambda: f"snd_{uuid.uuid4().hex[:10]}")
    workspace_id: str = "default"
    name: str = "Nasrullah Tanim"
    email: str = "hello@nasrullahtanim.me"
    reply_to: str = "hello@nasrullahtanim.me"
    mua_fingerprint: str = "apple_mail"  # apple_mail, thunderbird, outlook_web
    daily_limit: int = 50
    sent_today: int = 0
    warmup_status: str = "active"  # ramp_up, steady, paused
    warmup_day: int = 14
    is_default: bool = True
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Lead:
    id: str = field(default_factory=lambda: f"lead_{uuid.uuid4().hex[:12]}")
    workspace_id: str = "default"
    email: str = ""
    first_name: str = ""
    last_name: str = ""
    phone: str = ""
    source: str = "calculator_funnel"  # calculator_funnel, web_lead, csv_import, api
    stage: str = LeadStage.CAPTURED.value
    loan_amount: Optional[float] = None
    property_type: Optional[str] = None
    purchase_timeline: Optional[str] = None
    credit_tier: Optional[str] = None
    custom_fields: Dict[str, Any] = field(default_factory=dict)
    is_suppressed: bool = False
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Message:
    id: str = field(default_factory=lambda: f"msg_{uuid.uuid4().hex[:14]}")
    conversation_id: str = ""
    workspace_id: str = "default"
    direction: str = MessageDirection.OUTBOUND.value
    from_addr: str = ""
    to_addr: str = ""
    subject: str = ""
    body_text: str = ""
    body_html: str = ""
    message_id_header: str = ""
    in_reply_to: Optional[str] = None
    references: Optional[str] = None
    intent: str = IntentType.UNKNOWN.value
    intent_confidence: float = 0.0
    deliverability_score: float = 100.0
    deliverability_grade: str = "A"
    status: str = "sent"  # sent, delivered, opened, clicked, replied, failed
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Conversation:
    id: str = field(default_factory=lambda: f"conv_{uuid.uuid4().hex[:12]}")
    workspace_id: str = "default"
    lead_id: str = ""
    lead_email: str = ""
    lead_name: str = ""
    subject: str = ""
    thread_root_msg_id: str = ""
    latest_message_at: float = field(default_factory=time.time)
    message_count: int = 1
    stage: str = LeadStage.ENGAGED.value
    latest_intent: str = IntentType.UNKNOWN.value
    booking_link_sent: bool = False
    is_closed: bool = False
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
