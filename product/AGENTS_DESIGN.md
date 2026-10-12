# AI Acquisition Team — Agent Design

> This document defines the AI agents that power the Acquisition OS.
> Each agent has a clear responsibility, input contract, and output contract.
> The agents are coordinated by an Acquisition Engine service.

---

## 1. Base Agent Interface

```python
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from datetime import datetime

class AcquisitionAgent(ABC):
    """
    Base class for all AI Acquisition Team agents.
    """
    org_id: str
    config: Dict[str, Any]  # org-specific policy, voice, rules

    @abstractmethod
    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the agent's primary function.
        Returns a structured result with provenance.
        """
        pass

    @abstractmethod
    def get_name(self) -> str:
        pass
```

---

## 2. Research Agent

**Responsibility:** Find and summarize relevant information about an opportunity.

**Input:**
```python
{
    "org_id": "org_123",
    "opportunity_id": "opp_456",
    "person": {"name": "John Smith", "location": "Austin, TX"},
    "depth": "quick" | "standard" | "deep",
    "sources": ["linkedin", "public_records", "real_estate", "social"]
}
```

**Output:**
```python
{
    "agent": "research",
    "opportunity_id": "opp_456",
    "dossier": {
        "who_are_they": "Software engineering manager at Acme Corp...",
        "why_they_matter": "Recently relocated to Austin, TX...",
        "fit_indicators": ["tech_income", "relocation", "rental_history"],
        "recent_signals": ["connected with real estate agent on LinkedIn", "searched homes in 78701"],
        "what_they_might_care_about": "Short commute to downtown, good school district..."
    },
    "evidence": [
        {"source": "linkedin", "summary": "Current role at Acme Corp", "url": "...", "confidence": 0.9},
        {"source": "public_records", "summary": "Property purchase in 78701", "url": "...", "confidence": 0.7}
    ],
    "confidence": "high",
    "provenance": "all_claims_backed_by_evidence",
    "generated_at": "2026-10-05T10:30:00Z"
}
```

**Constraints:**
- Never fabricate facts
- Only use information that is actually available and appropriate
- Include provenance for every claim
- Do not use information that would violate privacy norms

---

## 3. Qualification Agent

**Responsibility:** Determine whether an opportunity matches the customer's ICP.

**Input:**
```python
{
    "org_id": "org_123",
    "opportunity_id": "opp_456",
    "opportunity_profile": {...},
    "icp": {
        "segments": ["first_time_buyer", "move_up_buyer"],
        "locations": ["Austin, TX", "Round Rock, TX"],
        "property_range": {"min": 400000, "max": 800000},
        "income_range": {"min": 80000, "max": 200000},
        "timeframe": "2-6 months"
    }
}
```

**Output:**
```python
{
    "agent": "qualification",
    "opportunity_id": "opp_456",
    "fit_score": {
        "icp_match": 25,
        "location_match": 20,
        "purchase_timeframe": 15,
        "property_range": 10,
        "total": 70,
        "max": 100
    },
    "segment": "first_time_buyer",
    "qualification_stage": "qualified",
    "reasoning": "Strong location match; purchase timeframe aligns; within property range",
    "recommended_angle": "Discuss first-time buyer programs and down payment assistance",
    "generated_at": "2026-10-05T10:30:00Z"
}
```

---

## 4. Personalization Agent

**Responsibility:** Convert research into specific, genuine context for messaging.

**Input:**
```python
{
    "org_id": "org_123",
    "opportunity_id": "opp_456",
    "research_dossier": {...},
    "brand_voice": {"tone": "professional_but_warm", "do": [...], "dont": [...]},
    "message_type": "initial_outreach" | "follow_up" | "response"
}
```

**Output:**
```python
{
    "agent": "personalization",
    "opportunity_id": "opp_456",
    "personalization": {
        "opening_context": "You recently connected with a real estate agent in Austin...",
        "relevant_detail": "and mentioned looking at homes in the 78701 area",
        "genuine_relevance": "That area has seen some nice inventory lately...",
        "avoid": ["fake_compliments", "generic_statements", "unverified_claims"]
    },
    "provenance": [
        {"claim": "recently connected with real estate agent", "source": "linkedin_activity", "confidence": 0.9},
        {"claim": "looking at homes in 78701", "source": "zillow_search_history", "confidence": 0.7}
    ],
    "generated_at": "2026-10-05T10:30:00Z"
}
```

**Constraints:**
- Never use fake compliments ("I saw your amazing company...")
- Never invent research
- Only use verified, available information
- Never pretend personal acquaintance

---

## 5. Message Agent

**Responsibility:** Create the actual communication content.

**Input:**
```python
{
    "org_id": "org_123",
    "opportunity_id": "opp_456",
    "personalization": {...},
    "brand_voice": {...},
    "channel": "email" | "sms" | "linkedin",
    "template_id": Optional[str],
    "context": {"purpose": "initial_outreach" | "follow_up" | "response"}
}
```

**Output:**
```python
{
    "agent": "message",
    "opportunity_id": "opp_456",
    "message": {
        "subject": "Austin first-time buyer programs — quick question",
        "body": "Hi John,\n\nI saw you recently started looking at homes in Austin...",
        "channel": "email",
        "personalization_score": 0.85,
        "compliance_check": "passed"
    },
    "generated_at": "2026-10-05T10:30:00Z"
}
```

---

## 6. Conversation Agent

**Responsibility:** Handle authorized replies within strict business rules.

**Input:**
```python
{
    "org_id": "org_123",
    "conversation_id": "conv_789",
    "inbound_message": {
        "direction": "inbound",
        "channel": "email",
        "body": "Thanks for reaching out. Can you tell me more about down payment assistance?",
        "timestamp": "2026-10-05T11:00:00Z"
    },
    "conversation_history": [...],
    "business_policy": {...}
}
```

**Output:**
```python
{
    "agent": "conversation",
    "conversation_id": "conv_789",
    "response": {
        "draft": "Hi John,\n\nGreat question! Down payment assistance programs...",
        "intent": "question",
        "confidence": 0.9,
        "signals": [
            {"type": "question", "text": "down payment assistance", "confidence": 0.95}
        ],
        "action": "send" | "escalate" | "wait_human",
        "reasoning": "Legitimate question about general loan programs; within policy",
        "next_best_action": "offer_consultation"
    },
    "generated_at": "2026-10-05T11:00:00Z"
}
```

**Escalation triggers:**
- Specific underwriting questions
- Complex financial circumstances
- Requests for guaranteed approval/rates
- Legal/compliance-sensitive topics
- Negative sentiment

---

## 7. Nurture Agent

**Responsibility:** Determine when and how to engage non-ready prospects.

**Input:**
```python
{
    "org_id": "org_123",
    "opportunity_id": "opp_456",
    "opportunity_state": {
        "state": "nurturing",
        "last_engaged_at": "2026-09-15T10:00:00Z",
        "behavior": [...],
        "intent": {...},
        "disqualification_risk": True
    },
    "available_content": [...]
}
```

**Output:**
```python
{
    "agent": "nurture",
    "opportunity_id": "opp_456",
    "recommendation": {
        "action": "send_value_content" | "wait" | "re_engage" | "disqualify",
        "content_id": "content_123",
        "timing": "2026-10-12T10:00:00Z",
        "reasoning": "Prospect downloaded refinance report; returned to calculator 3 days later; renewed interest detected",
        "personalization": "Following up on your recent refinance research..."
    },
    "generated_at": "2026-10-05T10:30:00Z"
}
```

**Nurture logic:**
- Respond to behavior, not calendar
- Detect renewed interest
- Adjust timing based on engagement patterns
- Avoid repetitive content
- Escalate cooling opportunities to human review

---

## 8. Booking Agent

**Responsibility:** Move qualified prospects toward an appointment.

**Input:**
```python
{
    "org_id": "org_123",
    "opportunity_id": "opp_456",
    "opportunity_state": {
        "state": "booking",
        "qualification": {"stage": "qualified"},
        "conversation": [...],
        "intent": {"level": "high"}
    },
    "advisor": {
        "id": "advisor_123",
        "name": "John Smith",
        "calendar_id": "cal_456",
        "availability_url": "https://calendly.com/john-smith"
    }
}
```

**Output:**
```python
{
    "agent": "booking",
    "opportunity_id": "opp_456",
    "recommendation": {
        "action": "send_calendar_link",
        "calendar_link": "https://calendly.com/john-smith?utm_source=...",
        "proposed_times": [
            {"start": "2026-10-10T14:00:00Z", "end": "2026-10-10T14:30:00Z"},
            {"start": "2026-10-10T16:00:00Z", "end": "2026-10-10T16:30:00Z"}
        ],
        "personalization": "Based on what you're looking for, I'd recommend a 30-minute consultation...",
        "reasoning": "Strong purchase intent + active conversation + defined timeframe"
    },
    "generated_at": "2026-10-05T10:30:00Z"
}
```

---

## 9. Content Agent

**Responsibility:** Create authority content for the customer.

**Input:**
```python
{
    "org_id": "org_123",
    "customer_expertise": ["first_time_buyer", "refinance", "jumbo_loans"],
    "geography": ["Austin, TX", "Round Rock, TX"],
    "target_borrower": ["first_time_buyer", "move_up_buyer"],
    "products": ["FHA", "Conventional", "VA"],
    "previous_content": [...],
    "current_campaigns": [...],
    "seasonal_opportunities": ["back_to_school", "holiday_relocation"],
    "prospect_questions": ["Do I need 20% down?", "How much house can I afford?"]
}
```

**Output:**
```python
{
    "agent": "content",
    "content_plan": [
        {
            "title": "Austin First-Time Buyer's Guide to Down Payment Assistance",
            "type": "article",
            "topic": "down_payment_assistance",
            "summary": "Covers TDHCA programs, local Austin initiatives...",
            "related_content": ["affordability_calculator", "first_time_buyer_checklist"],
            "linkedin_post": "Just published a guide to Austin down payment assistance...",
            "lead_magnet": "Austin First-Time Buyer Checklist",
            "calculator": "down_payment_calculator",
            "email_follow_up": "3-email nurture sequence",
            "reasoning": "Top prospect question this month; seasonal back-to-school relocation peak"
        }
    ],
    "generated_at": "2026-10-05T10:30:00Z"
}
```

---

## 10. Optimization Agent

**Responsibility:** Analyze and improve acquisition performance.

**Input:**
```python
{
    "org_id": "org_123",
    "campaign_data": [...],
    "funnel_metrics": {
        "discovered": 150,
        "researched": 120,
        "qualified": 80,
        "contacted": 60,
        "engaged": 45,
        "intent": 30,
        "booking": 20,
        "meeting": 15,
        "opportunity": 10,
        "customer": 5
    },
    "content_performance": [...],
    "conversation_metrics": {...}
}
```

**Output:**
```python
{
    "agent": "optimization",
    "org_id": "org_123",
    "recommendations": [
        {
            "type": "funnel_optimization",
            "priority": "high",
            "title": "Qualification-to-booking conversion declined 18%",
            "detail": "The strongest drop occurs after the first qualification question. Review the qualification flow.",
            "action": "review_qualification_flow",
            "estimated_impact": "12 additional meetings/month"
        },
        {
            "type": "content_optimization",
            "priority": "medium",
            "title": "Strongest content topic this month: refinance savings",
            "detail": "Consider creating a refinance calculator campaign.",
            "action": "create_refinance_campaign"
        },
        {
            "type": "message_optimization",
            "priority": "medium",
            "title": "Prospects respond better when first email references timeframe",
            "detail": "Add purchase window to personalized opening.",
            "action": "update_message_template"
        }
    ],
    "generated_at": "2026-10-05T10:30:00Z"
}
```

---

## 11. Agent Orchestration

```python
class AcquisitionEngine:
    """
    Coordinates the AI Acquisition Team.
    """
    async def research_opportunity(self, org_id: str, opportunity_id: str) -> ResearchResult:
        research_agent = ResearchAgent(org_id=org_id, config=self.get_org_config(org_id))
        result = await research_agent.execute({"opportunity_id": opportunity_id})
        await self.update_opportunity_profile(org_id, opportunity_id, result)
        return result

    async def qualify_opportunity(self, org_id: str, opportunity_id: str) -> QualificationResult:
        opportunity = await self.get_opportunity(org_id, opportunity_id)
        qualification_agent = QualificationAgent(org_id=org_id, config=self.get_org_config(org_id))
        result = await qualification_agent.execute({
            "opportunity_profile": opportunity.dict(),
            "icp": await self.get_org_icp(org_id)
        })
        await self.update_fit_score(org_id, opportunity_id, result)
        return result

    async def personalize_message(self, org_id: str, opportunity_id: str, context: Dict) -> PersonalizationResult:
        personalization_agent = PersonalizationAgent(org_id=org_id, config=self.get_org_config(org_id))
        research = await self.get_research(org_id, opportunity_id)
        result = await personalization_agent.execute({
            "research_dossier": research.dict(),
            "brand_voice": await self.get_brand_voice(org_id),
            **context
        })
        return result

    # ... similar for other agents
```

---

## 12. Business Policy Layer

```python
class BusinessPolicy(BaseModel):
    """
    Configurable per-organization rules that govern AI behavior.
    """
    org_id: str
    allowed_actions: List[str] = [
        "explain_general_concepts",
        "collect_preliminary_info",
        "schedule_conversation"
    ]
    escalate_actions: List[str] = [
        "specific_underwriting_questions",
        "complex_financial_circumstances"
    ]
    forbidden_claims: List[str] = [
        "guaranteed_approval",
        "guaranteed_rates"
    ]
    identity_rules: Dict[str, Any] = {
        "do_not_impersonate_licensed_advisor": True,
        "real_human_sender_names": True,
        "sent_via_disclosure_required": False
    }
    compliance_rules: Dict[str, Any] = {
        "opt_out_mechanism": "reply_or_link",
        "consent_model": "b2b_opt_out",  # or "b2c_opt_in"
        "data_retention_days": 2555,
        "right_to_erasure": True
    }
    human_handoff_conditions: List[str] = [
        "negative_sentiment",
        "legal_question",
        "specific_underwriting",
        "complex_circumstances"
    ]

class PolicyEnforcer:
    """
    Enforces business policy on all AI-generated actions.
    """
    def check_action(self, action: Dict[str, Any], policy: BusinessPolicy) -> Dict[str, Any]:
        if action["type"] in policy.forbidden_claims:
            return {"allowed": False, "reason": "forbidden_claim", "action": "escalate"}
        if action["type"] in policy.escalate_actions:
            return {"allowed": True, "reason": "requires_human_review", "action": "escalate"}
        if action["type"] not in policy.allowed_actions:
            return {"allowed": False, "reason": "not_permitted", "action": "block"}
        return {"allowed": True, "action": "proceed"}
```

---

*End of AI Acquisition Team — Agent Design*
