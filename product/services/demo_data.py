"""
Acquisition OS — Demo Data Service
Seeds realistic demo data for demonstrations.
"""

from datetime import datetime, timedelta
from typing import Dict, Any
import json


class DemoDataService:
    """Service for seeding demo data."""

    def __init__(self, session, org_id: str, tenant_id: str):
        self.session = session
        self.org_id = org_id
        self.tenant_id = tenant_id
        self.now = datetime.utcnow()

    async def seed_all(self) -> Dict[str, Any]:
        """Seed all demo data."""
        await self.seed_opportunities()
        await self.seed_missions()
        await self.seed_automations()
        await self.seed_content()
        await self.seed_activities()
        return {"status": "seeded", "org_id": self.org_id}

    async def seed_opportunities(self):
        """Seed demo opportunities using raw SQL."""
        from product.db.models import Opportunity
        from sqlalchemy import insert as sa_insert

        opps = [
            {
                "id": "opp_demo_1",
                "org_id": self.org_id,
                "tenant_id": self.tenant_id,
                "person": {"name": "Sarah Johnson", "email": "sarah@example.com", "phone": "+1-555-0001", "location": "Austin, TX", "household_size": 2, "income_range": "120k-150k"},
                "opportunity_score": 85,
                "fit": {"icp_match": 25, "location_match": 20, "purchase_timeframe": 15, "property_range": 10, "segment": "first_time_buyer", "total": 70},
                "intent": {"level": "high", "signals": [{"type": "buying_signal", "text": "Planning to buy within 3 months"}], "objections": [], "questions": ["Do I need 20% down?"]},
                "state": "engaged",
                "qualification": {"stage": "qualified", "recommended_angle": "Discuss first-time buyer programs"},
                "next_best_action": "offer_consultation",
                "next_best_action_reason": "Strong purchase intent + active conversation + defined timeframe",
                "next_action_at": self.now + timedelta(hours=2),
                "tags": ["first_time_buyer", "austin", "hot"],
                "behavior": [
                    {"type": "content_consumed", "content_title": "Austin First-Time Buyer Guide", "timestamp": (self.now - timedelta(days=3)).isoformat()},
                    {"type": "calculator_use", "content_title": "Affordability Calculator", "timestamp": (self.now - timedelta(days=2)).isoformat()},
                ],
                "conversation": [
                    {"id": "msg_1", "direction": "outbound", "channel": "email", "subject": "Welcome to ABC Mortgage", "body": "Hi Sarah, welcome!", "timestamp": (self.now - timedelta(days=1)).isoformat()},
                    {"id": "msg_2", "direction": "inbound", "channel": "email", "subject": "Re: Welcome to ABC Mortgage", "body": "Thanks! I'm planning to buy within 3 months.", "timestamp": (self.now - timedelta(hours=5)).isoformat()},
                ],
                "appointment": None,
                "provenance": {"source": "inbound", "discovery_signals": ["downloaded_affordability_report"], "research_evidence": [{"source": "calculator", "summary": "Used affordability calculator"}], "confidence": "high"},
                "lifecycle": {"discovered_at": (self.now - timedelta(days=7)).isoformat(), "last_contacted_at": (self.now - timedelta(hours=5)).isoformat(), "last_engaged_at": (self.now - timedelta(hours=5)).isoformat(), "next_action_at": (self.now + timedelta(hours=2)).isoformat(), "state": "engaged", "state_history": [{"state": "discovered", "entered_at": (self.now - timedelta(days=7)).isoformat(), "exited_at": (self.now - timedelta(days=6)).isoformat()}, {"state": "researched", "entered_at": (self.now - timedelta(days=6)).isoformat(), "exited_at": (self.now - timedelta(days=5)).isoformat()}, {"state": "qualified", "entered_at": (self.now - timedelta(days=5)).isoformat(), "exited_at": (self.now - timedelta(days=4)).isoformat()}, {"state": "contacted", "entered_at": (self.now - timedelta(days=4)).isoformat(), "exited_at": (self.now - timedelta(days=3)).isoformat()}, {"state": "engaged", "entered_at": (self.now - timedelta(days=3)).isoformat(), "exited_at": None}]},
                "research_dossier": {"who_are_they": "First-time homebuyer in Austin, TX", "why_they_matter": "Strong intent to purchase within 3 months", "fit_indicators": ["location_match", "engaged_with_content"], "recent_signals": ["Downloaded affordability report", "Used calculator 5 times"], "evidence": [{"source": "calculator", "summary": "Used calculator 5 times", "confidence": 0.9}], "confidence": "high"},
                "created_at": self.now - timedelta(days=7),
                "updated_at": self.now,
                "version": 5,
            },
            {
                "id": "opp_demo_2",
                "org_id": self.org_id,
                "tenant_id": self.tenant_id,
                "person": {"name": "Mike Chen", "email": "mike@example.com", "phone": "+1-555-0002", "location": "Round Rock, TX", "household_size": 3, "income_range": "150k-200k"},
                "opportunity_score": 72,
                "fit": {"icp_match": 20, "location_match": 15, "purchase_timeframe": 10, "property_range": 15, "segment": "move_up_buyer", "total": 60},
                "intent": {"level": "medium", "signals": [{"type": "question", "text": "Asked about refinance options"}], "objections": [], "questions": ["What are current rates?"]},
                "state": "contacted",
                "qualification": {"stage": "qualified", "recommended_angle": "Discuss refinance options"},
                "next_best_action": "send_refinance_report",
                "next_best_action_reason": "Question about refinance options; strong fit",
                "next_action_at": self.now + timedelta(hours=4),
                "tags": ["refinance", "round_rock"],
                "behavior": [{"type": "email_open", "content_title": "Refinance rates email", "timestamp": (self.now - timedelta(days=2)).isoformat()}],
                "conversation": [],
                "appointment": None,
                "provenance": {"source": "proactive", "discovery_signals": ["icp_match"], "research_evidence": [], "confidence": "medium"},
                "lifecycle": {"discovered_at": (self.now - timedelta(days=5)).isoformat(), "last_contacted_at": (self.now - timedelta(days=2)).isoformat(), "last_engaged_at": (self.now - timedelta(days=2)).isoformat(), "next_action_at": (self.now + timedelta(hours=4)).isoformat(), "state": "contacted", "state_history": [{"state": "discovered", "entered_at": (self.now - timedelta(days=5)).isoformat(), "exited_at": (self.now - timedelta(days=4)).isoformat()}, {"state": "qualified", "entered_at": (self.now - timedelta(days=4)).isoformat(), "exited_at": (self.now - timedelta(days=3)).isoformat()}, {"state": "contacted", "entered_at": (self.now - timedelta(days=3)).isoformat(), "exited_at": None}]},
                "research_dossier": None,
                "created_at": self.now - timedelta(days=5),
                "updated_at": self.now - timedelta(days=2),
                "version": 3,
            },
            {
                "id": "opp_demo_3",
                "org_id": self.org_id,
                "tenant_id": self.tenant_id,
                "person": {"name": "Emily Davis", "email": "emily@example.com", "phone": "+1-555-0003", "location": "Austin, TX", "household_size": 1, "income_range": "100k-130k"},
                "opportunity_score": 91,
                "fit": {"icp_match": 25, "location_match": 20, "purchase_timeframe": 20, "property_range": 15, "segment": "first_time_buyer", "total": 80},
                "intent": {"level": "high", "signals": [{"type": "buying_signal", "text": "Ready to speak with advisor"}], "objections": [], "questions": []},
                "state": "booking",
                "qualification": {"stage": "qualified", "recommended_angle": "Schedule consultation"},
                "next_best_action": "send_calendar_link",
                "next_best_action_reason": "Ready to speak + strong fit + defined timeframe",
                "next_action_at": self.now + timedelta(hours=1),
                "tags": ["first_time_buyer", "austin", "hot"],
                "behavior": [{"type": "calculator_use", "content_title": "Affordability Calculator", "timestamp": (self.now - timedelta(days=4)).isoformat()}, {"type": "content_consumed", "content_title": "First-Time Buyer Checklist", "timestamp": (self.now - timedelta(days=3)).isoformat()}],
                "conversation": [],
                "appointment": {"status": "proposed", "proposed_times": [{"start": "2026-10-10T14:00:00Z", "end": "2026-10-10T14:30:00Z"}]},
                "provenance": {"source": "inbound", "discovery_signals": ["calculator_use", "content_download"], "research_evidence": [{"source": "calculator", "summary": "High engagement with affordability tools"}], "confidence": "high"},
                "lifecycle": {"discovered_at": (self.now - timedelta(days=10)).isoformat(), "last_contacted_at": (self.now - timedelta(hours=2)).isoformat(), "last_engaged_at": (self.now - timedelta(hours=2)).isoformat(), "next_action_at": (self.now + timedelta(hours=1)).isoformat(), "state": "booking", "state_history": [{"state": "discovered", "entered_at": (self.now - timedelta(days=10)).isoformat(), "exited_at": (self.now - timedelta(days=9)).isoformat()}, {"state": "researched", "entered_at": (self.now - timedelta(days=9)).isoformat(), "exited_at": (self.now - timedelta(days=8)).isoformat()}, {"state": "qualified", "entered_at": (self.now - timedelta(days=8)).isoformat(), "exited_at": (self.now - timedelta(days=7)).isoformat()}, {"state": "contacted", "entered_at": (self.now - timedelta(days=7)).isoformat(), "exited_at": (self.now - timedelta(days=6)).isoformat()}, {"state": "engaged", "entered_at": (self.now - timedelta(days=6)).isoformat(), "exited_at": (self.now - timedelta(days=5)).isoformat()}, {"state": "intent_detected", "entered_at": (self.now - timedelta(days=5)).isoformat(), "exited_at": (self.now - timedelta(days=4)).isoformat()}, {"state": "booking", "entered_at": (self.now - timedelta(days=4)).isoformat(), "exited_at": None}]},
                "research_dossier": {"who_are_they": "Young professional in Austin, TX", "why_they_matter": "Ready to buy within 1-3 months, strong engagement", "fit_indicators": ["location_match", "high_engagement"], "recent_signals": ["Requested consultation", "Replied to email"], "evidence": [{"source": "conversation", "summary": "Expressed readiness to speak with advisor", "confidence": 0.95}], "confidence": "high"},
                "created_at": self.now - timedelta(days=10),
                "updated_at": self.now - timedelta(hours=2),
                "version": 7,
            },
        ]

        for opp in opps:
            await self.session.execute(Opportunity.__table__.insert().values(**opp))
        await self.session.flush()

    async def seed_missions(self):
        """Seed demo missions."""
        from product.db.models import Mission

        mission = {
            "id": "mission_demo_1",
            "org_id": self.org_id,
            "tenant_id": self.tenant_id,
            "name": "Austin First-Time Buyer Acquisition",
            "description": "Generate 20 qualified first-time-homebuyer conversations per month in Austin",
            "active": True,
            "target_segment": "first_time_buyer",
            "location": "Austin, TX",
            "property_range": "$400k-$800k",
            "monthly_goal": 20,
            "preferred_action": "calendar_booking",
            "advisor_id": "user_demo_1",
            "calendar_id": "cal_demo_1",
            "created_at": self.now,
            "updated_at": self.now,
        }
        await self.session.execute(Mission.__table__.insert().values(**mission))
        await self.session.flush()

    async def seed_automations(self):
        """Seed demo automations."""
        from product.db.models import Automation

        auto = {
            "id": "auto_demo_1",
            "org_id": self.org_id,
            "tenant_id": self.tenant_id,
            "name": "First-Time Buyer Nurture",
            "description": "Nurture first-time buyers through qualification to booking",
            "active": True,
            "trigger_type": "opportunity_state_changed",
            "trigger_config": {"from_state": "qualified", "to_state": "contacted"},
            "steps": [
                {"type": "action", "config": {"action": "send_message", "template": "qualification_questionnaire"}},
                {"type": "wait", "config": {"duration": 86400, "unit": "seconds"}},
                {"type": "condition", "config": {"field": "intent.level", "operator": "equals", "value": "high"}},
                {"type": "action", "config": {"action": "update_state", "state": "intent_detected"}},
            ],
            "version": 1,
            "execution_history": [],
            "created_at": self.now,
            "updated_at": self.now,
        }
        await self.session.execute(Automation.__table__.insert().values(**auto))
        await self.session.flush()

    async def seed_content(self):
        """Seed demo content."""
        from product.db.models import Content

        contents = [
            {
                "id": "content_demo_1",
                "org_id": self.org_id,
                "tenant_id": self.tenant_id,
                "title": "Austin First-Time Buyer's Guide to Down Payment Assistance",
                "type": "article",
                "body": "# Austin First-Time Buyer's Guide\n\n## Introduction\n\nIf you're a first-time homebuyer in Austin, TX...",
                "metadata": {"topic": "down_payment_assistance", "target_segment": "first_time_buyer", "geography": ["Austin, TX"]},
                "published": True,
                "published_at": self.now - timedelta(days=7),
                "attribution": {"views": 1823, "calculator_visits": 94, "leads": 31, "qualified_opportunities": 12, "conversations": 5, "meetings_booked": 2, "estimated_pipeline": 240000},
                "created_at": self.now - timedelta(days=7),
                "updated_at": self.now - timedelta(days=7),
            },
            {
                "id": "content_demo_2",
                "org_id": self.org_id,
                "tenant_id": self.tenant_id,
                "title": "Refinance Guide: When to Refinance in 2026",
                "type": "article",
                "body": "# Refinance Guide\n\n## Introduction\n\nCurrent market conditions present opportunities...",
                "metadata": {"topic": "refinance", "target_segment": "existing_homeowners", "geography": ["Austin, TX"]},
                "published": True,
                "published_at": self.now - timedelta(days=14),
                "attribution": {"views": 1245, "calculator_visits": 56, "leads": 18, "qualified_opportunities": 8, "conversations": 3, "meetings_booked": 1, "estimated_pipeline": 120000},
                "created_at": self.now - timedelta(days=14),
                "updated_at": self.now - timedelta(days=14),
            },
        ]
        for content in contents:
            await self.session.execute(Content.__table__.insert().values(**content))
        await self.session.flush()

    async def seed_activities(self):
        """Seed demo system activities."""
        from product.db.models import SystemActivity

        activities = [
            {"org_id": self.org_id, "tenant_id": self.tenant_id, "type": "opportunity_discovered", "description": "New opportunity discovered: Sarah Johnson", "entity_id": "opp_demo_1", "timestamp": self.now - timedelta(hours=8)},
            {"org_id": self.org_id, "tenant_id": self.tenant_id, "type": "opportunity_researched", "description": "Opportunity researched: Sarah Johnson", "entity_id": "opp_demo_1", "timestamp": self.now - timedelta(hours=7)},
            {"org_id": self.org_id, "tenant_id": self.tenant_id, "type": "high_intent_detected", "description": "High intent detected: Emily Davis", "entity_id": "opp_demo_3", "timestamp": self.now - timedelta(hours=2)},
            {"org_id": self.org_id, "tenant_id": self.tenant_id, "type": "message_sent", "description": "Message sent to Emily Davis", "entity_id": "opp_demo_3", "timestamp": self.now - timedelta(hours=1)},
            {"org_id": self.org_id, "tenant_id": self.tenant_id, "type": "appointment_booked", "description": "Appointment booked: Emily Davis", "entity_id": "opp_demo_3", "timestamp": self.now - timedelta(minutes=30)},
        ]
        for activity in activities:
            await self.session.execute(SystemActivity.__table__.insert().values(**activity))
        await self.session.flush()
