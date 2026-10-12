# API Specification

> REST API v1 for Acquisition OS.
> All endpoints are tenant-scoped. Authentication is via org-scoped API keys or OAuth2.
> Base path: `/v1/organizations/{org_id}`

---

## 1. Authentication

### Org-scoped API key

```
Authorization: Bearer org_<api_key>
```

### OAuth2 (future)

Standard OAuth2 authorization code flow with org-scoped tokens.

---

## 2. Organizations

### GET /v1/organizations/{org_id}

Get organization details.

**Response:**
```json
{
    "id": "org_123",
    "name": "ABC Mortgage",
    "slug": "abc-mortgage",
    "plan": "growth",
    "plan_status": "active",
    "settings": {
        "brand_voice": "professional_but_warm",
        "icp": {...},
        "compliance": {...}
    },
    "limits": {
        "monthly_send_limit": 10000,
        "monthly_opportunity_limit": 1000
    },
    "created_at": "2026-01-01T00:00:00Z"
}
```

### PATCH /v1/organizations/{org_id}

Update organization settings.

**Request:**
```json
{
    "name": "ABC Mortgage",
    "settings": {
        "brand_voice": "professional_but_warm",
        "ai_policy": {...}
    }
}
```

---

## 3. Opportunities

### GET /v1/organizations/{org_id}/opportunities

List opportunities.

**Query params:**
- `state` — filter by state
- `min_score` — minimum opportunity score
- `max_score` — maximum opportunity score
- `tags` — filter by tags (comma-separated)
- `assigned_to` — filter by assigned user
- `search` — search in person.name, person.email
- `from` — discovered after this date
- `to` — discovered before this date
- `order_by` — `discovered_at`, `opportunity_score`, `next_action_at`
- `order_dir` — `asc`, `desc`
- `limit` — page size (default 20, max 100)
- `offset` — page offset

**Response:**
```json
{
    "data": [
        {
            "id": "opp_123",
            "person": {
                "name": "John Smith",
                "email": "john@example.com",
                "phone": "+1-555-0123",
                "location": "Austin, TX"
            },
            "opportunity_score": 82,
            "fit": {
                "icp_match": 25,
                "location_match": 20,
                "purchase_timeframe": 15,
                "property_range": 10,
                "segment": "first_time_buyer",
                "total": 70
            },
            "intent": {
                "level": "high",
                "signals": [...],
                "objections": [...],
                "questions": [...]
            },
            "state": "booking",
            "qualification": {
                "stage": "qualified",
                "recommended_angle": "Discuss first-time buyer programs"
            },
            "next_best_action": "send_calendar_link",
            "next_best_action_reason": "Strong purchase intent + active conversation + defined timeframe",
            "next_action_at": "2026-10-06T10:00:00Z",
            "tags": ["first_time_buyer", "austin"],
            "created_at": "2026-10-01T00:00:00Z",
            "updated_at": "2026-10-05T10:00:00Z"
        }
    ],
    "pagination": {
        "total": 150,
        "limit": 20,
        "offset": 0
    }
}
```

### POST /v1/organizations/{org_id}/opportunities

Create opportunity (inbound or proactive).

**Request:**
```json
{
    "person": {
        "name": "John Smith",
        "email": "john@example.com",
        "phone": "+1-555-0123",
        "location": "Austin, TX"
    },
    "source": "inbound",  // or "proactive", "referral"
    "discovery_signals": ["downloaded_affordability_report", "visited_calculator"],
    "custom_fields": {}
}
```

### GET /v1/organizations/{org_id}/opportunities/{opportunity_id}

Get opportunity details with full profile.

**Response:**
```json
{
    "id": "opp_123",
    "person": {...},
    "opportunity_score": 82,
    "fit": {...},
    "intent": {...},
    "behavior": [...],
    "conversation": [...],
    "qualification": {...},
    "appointment": {...},
    "provenance": {
        "source": "inbound",
        "discovery_signals": [...],
        "research_evidence": [...],
        "confidence": "high"
    },
    "lifecycle": {
        "discovered_at": "2026-10-01T00:00:00Z",
        "last_contacted_at": "2026-10-05T10:00:00Z",
        "last_engaged_at": "2026-10-05T10:00:00Z",
        "next_action_at": "2026-10-06T10:00:00Z",
        "state": "booking",
        "state_history": [...]
    },
    "next_best_action": "send_calendar_link",
    "next_best_action_reason": "Strong purchase intent + active conversation + defined timeframe",
    "research_dossier": {
        "who_are_they": "...",
        "why_they_matter": "...",
        "fit_indicators": [...],
        "recent_signals": [...],
        "what_they_might_care_about": "...",
        "evidence": [...],
        "confidence": "high"
    },
    "tags": ["first_time_buyer", "austin"],
    "created_at": "2026-10-01T00:00:00Z",
    "updated_at": "2026-10-05T10:00:00Z",
    "version": 3
}
```

### POST /v1/organizations/{org_id}/opportunities/{opportunity_id}/research

Trigger research agent.

**Request:**
```json
{
    "depth": "standard",  // quick, standard, deep
    "sources": ["linkedin", "public_records", "real_estate"]
}
```

**Response:**
```json
{
    "opportunity_id": "opp_123",
    "research_dossier": {
        "who_are_they": "...",
        "why_they_matter": "...",
        "fit_indicators": [...],
        "recent_signals": [...],
        "what_they_might_care_about": "...",
        "evidence": [...],
        "confidence": "high"
    },
    "opportunity_score": 82,
    "updated_at": "2026-10-05T10:30:00Z"
}
```

### POST /v1/organizations/{org_id}/opportunities/{opportunity_id}/qualify

Trigger qualification agent.

**Response:**
```json
{
    "opportunity_id": "opp_123",
    "fit_score": {
        "icp_match": 25,
        "location_match": 20,
        "purchase_timeframe": 15,
        "property_range": 10,
        "segment": "first_time_buyer",
        "total": 70
    },
    "opportunity_score": 82,
    "qualification_stage": "qualified",
    "reasoning": "...",
    "recommended_angle": "...",
    "updated_at": "2026-10-05T10:30:00Z"
}
```

### POST /v1/organizations/{org_id}/opportunities/{opportunity_id}/personalize

Trigger personalization agent.

**Request:**
```json
{
    "message_type": "initial_outreach",  // initial_outreach, follow_up, response
    "context": {}
}
```

**Response:**
```json
{
    "opportunity_id": "opp_123",
    "personalization": {
        "opening_context": "...",
        "relevant_detail": "...",
        "genuine_relevance": "...",
        "avoid": ["fake_compliments", "generic_statements"]
    },
    "provenance": [...],
    "generated_at": "2026-10-05T10:30:00Z"
}
```

### POST /v1/organizations/{org_id}/opportunities/{opportunity_id}/message

Generate message.

**Request:**
```json
{
    "channel": "email",
    "purpose": "initial_outreach",  // initial_outreach, follow_up, response
    "template_id": "tmpl_123",  // optional
    "personalization_id": "pers_456"  // optional
}
```

**Response:**
```json
{
    "opportunity_id": "opp_123",
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

### POST /v1/organizations/{org_id}/opportunities/{opportunity_id}/send

Send message to opportunity.

**Request:**
```json
{
    "from_identity_id": "identity_123",
    "subject": "...",
    "body": "...",
    "channel": "email",
    "schedule_at": "2026-10-06T10:00:00Z"  // optional
}
```

**Response:**
```json
{
    "opportunity_id": "opp_123",
    "message_id": "msg_789",
    "status": "queued",
    "scheduled_at": "2026-10-06T10:00:00Z",
    "metadata": {}
}
```

### POST /v1/organizations/{org_id}/opportunities/{opportunity_id}/book

Trigger booking agent.

**Request:**
```json
{
    "advisor_id": "advisor_123",
    "calendar_id": "cal_456",
    "purpose": "initial_consultation"
}
```

**Response:**
```json
{
    "opportunity_id": "opp_123",
    "recommendation": {
        "action": "send_calendar_link",
        "calendar_link": "https://calendly.com/john-smith?utm_source=...",
        "proposed_times": [...],
        "personalization": "...",
        "reasoning": "..."
    },
    "generated_at": "2026-10-05T10:30:00Z"
}
```

### GET /v1/organizations/{org_id}/opportunities/pipeline

Get pipeline view.

**Query params:**
- `segment` — filter by segment
- `from` — date range
- `to` — date range

**Response:**
```json
{
    "pipeline": {
        "discovered": {"count": 150, "value": 0},
        "researched": {"count": 120, "value": 0},
        "qualified": {"count": 80, "value": 2400000},
        "contacted": {"count": 60, "value": 1800000},
        "engaged": {"count": 45, "value": 1350000},
        "intent_detected": {"count": 30, "value": 900000},
        "booking": {"count": 20, "value": 600000},
        "meeting_scheduled": {"count": 15, "value": 450000},
        "meeting_completed": {"count": 10, "value": 300000},
        "opportunity": {"count": 5, "value": 150000},
        "customer": {"count": 2, "value": 60000}
    },
    "conversion_rates": {
        "discovered_to_qualified": "53.3%",
        "qualified_to_meeting": "18.8%",
        "meeting_to_opportunity": "50.0%"
    }
}
```

---

## 4. Conversations

### GET /v1/organizations/{org_id}/conversations

List conversations.

**Query params:**
- `state` — active, closed, escalated
- `assigned_to` — user ID
- `intent` — intent classification
- `from` — date range
- `to` — date range
- `limit` — page size
- `offset` — page offset

### GET /v1/organizations/{org_id}/conversations/{conversation_id}

Get conversation with messages.

### POST /v1/organizations/{org_id}/conversations/{conversation_id}/reply

Generate AI response.

**Request:**
```json
{
    "message": "Thanks for reaching out. Can you tell me more about down payment assistance?",
    "channel": "email"
}
```

**Response:**
```json
{
    "conversation_id": "conv_123",
    "response": {
        "draft": "Hi John,\n\nGreat question! Down payment assistance programs...",
        "intent": "question",
        "confidence": 0.9,
        "signals": [...],
        "action": "send",
        "reasoning": "...",
        "next_best_action": "offer_consultation"
    },
    "generated_at": "2026-10-05T11:00:00Z"
}
```

### POST /v1/organizations/{org_id}/conversations/{conversation_id}/send

Send response (human-approved or autonomous).

**Request:**
```json
{
    "from_identity_id": "identity_123",
    "subject": "...",
    "body": "...",
    "channel": "email"
}
```

---

## 5. Content

### GET /v1/organizations/{org_id}/content

List content.

**Query params:**
- `type` — article, linkedin_post, etc.
- `published` — true/false
- `topic` — filter by topic
- `limit` — page size
- `offset` — page offset

### POST /v1/organizations/{org_id}/content

Create content.

### POST /v1/organizations/{org_id}/content/generate

Generate content with AI Content Agent.

**Request:**
```json
{
    "type": "article",
    "topic": "down_payment_assistance",
    "target_segment": "first_time_buyer",
    "geography": ["Austin, TX"]
}
```

### GET /v1/organizations/{org_id}/content/{content_id}

Get content with attribution.

---

## 6. Campaigns

### GET /v1/organizations/{org_id}/campaigns

List campaigns.

### POST /v1/organizations/{org_id}/campaigns

Create campaign.

### POST /v1/organizations/{org_id}/campaigns/{campaign_id}/start

Start campaign.

### POST /v1/organizations/{org_id}/campaigns/{campaign_id}/pause

Pause campaign.

---

## 7. Missions

### GET /v1/organizations/{org_id}/missions

List missions.

### POST /v1/organizations/{org_id}/missions

Create mission.

**Request:**
```json
{
    "name": "Austin First-Time Buyer Acquisition",
    "description": "Generate 20 qualified first-time-homebuyer conversations per month in Austin",
    "target_segment": "first_time_buyer",
    "location": "Austin, TX",
    "property_range": "$400k–$800k",
    "monthly_goal": 20,
    "preferred_action": "calendar_booking",
    "advisor_id": "advisor_123",
    "calendar_id": "cal_456"
}
```

**Response:**
```json
{
    "id": "mission_123",
    "org_id": "org_123",
    "name": "Austin First-Time Buyer Acquisition",
    "target_segment": "first_time_buyer",
    "location": "Austin, TX",
    "property_range": "$400k–$800k",
    "monthly_goal": 20,
    "preferred_action": "calendar_booking",
    "advisor_id": "advisor_123",
    "generated_automation_id": "automation_456",
    "created_at": "2026-10-05T00:00:00Z"
}
```

---

## 8. Automations

### GET /v1/organizations/{org_id}/automations

List automations.

### POST /v1/organizations/{org_id}/automations

Create automation.

### PATCH /v1/organizations/{org_id}/automations/{automation_id}

Update automation.

---

## 9. Command Center

### GET /v1/organizations/{org_id}/command-center

Get Command Center data.

**Response:**
```json
{
    "greeting": "Good morning, John",
    "overnight_summary": {
        "new_opportunities_discovered": 12,
        "high_fit_prospects_researched": 4,
        "active_conversations": 7,
        "strong_intent_prospects": 2,
        "meetings_booked": 1,
        "cooling_opportunities": 3
    },
    "todays_priorities": [
        {
            "rank": 1,
            "opportunity_id": "opp_123",
            "name": "Sarah",
            "state": "ready_to_discuss_financing",
            "action": "review_conversation",
            "reason": "Strong purchase intent + active conversation + defined timeframe"
        }
    ],
    "system_activity": [
        {
            "type": "content_published",
            "description": "Published today's article",
            "timestamp": "2026-10-05T08:00:00Z"
        },
        {
            "type": "prospect_replied",
            "description": "Sarah replied to qualification question",
            "timestamp": "2026-10-05T09:30:00Z"
        }
    ],
    "generated_at": "2026-10-05T10:00:00Z"
}
```

---

## 10. Acquisition Health

### GET /v1/organizations/{org_id}/health

Get acquisition health.

**Response:**
```json
{
    "org_id": "org_123",
    "metrics": [
        {
            "metric": "lead_flow",
            "status": "excellent",
            "value": 45,
            "target": 30,
            "trend": "up",
            "detail": "12 new opportunities discovered this week"
        },
        {
            "metric": "booking_rate",
            "status": "needs_attention",
            "value": "8.5%",
            "target": "15%",
            "trend": "down",
            "detail": "Conversion from qualified conversation to booked meeting has declined 18%"
        }
    ],
    "recommendation": "Your calculator is generating leads normally, but the conversion from qualified conversation to booked meeting has declined 18%. The strongest drop occurs after the first qualification question. Review the qualification flow.",
    "generated_at": "2026-10-05T10:00:00Z"
}
```

---

## 11. Analytics

### GET /v1/organizations/{org_id}/analytics/pipeline

Get pipeline metrics.

### GET /v1/organizations/{org_id}/analytics/content-attribution

Get content → pipeline attribution.

**Query params:**
- `content_id` — specific content
- `from` — date range
- `to` — date range

**Response:**
```json
{
    "content": {
        "id": "content_123",
        "title": "Should I Buy Before Rates Fall?",
        "attribution": {
            "views": 1823,
            "calculator_visits": 94,
            "leads": 31,
            "qualified_opportunities": 12,
            "conversations": 5,
            "meetings_booked": 2,
            "estimated_pipeline": 240000
        }
    }
}
```

### GET /v1/organizations/{org_id}/analytics/acquisition-efficiency

Get acquisition efficiency metrics.

**Response:**
```json
{
    "qualified_opportunities_per_cost": 2.4,
    "meetings_per_1000_prospects": 15.2,
    "cost_per_qualified_opportunity": 145.83,
    "cost_per_meeting": 62.50,
    "period": "2026-09",
    "generated_at": "2026-10-05T10:00:00Z"
}
```

---

## 12. Webhooks (outbound)

### POST /v1/organizations/{org_id}/webhooks

Register webhook.

### PATCH /v1/organizations/{org_id}/webhooks/{webhook_id}

Update webhook.

### POST /v1/webhooks/inbound

Receive inbound webhook events from infrastructure.

**Events:**
- `email.sent`
- `email.delivered`
- `email.opened`
- `email.clicked`
- `email.replied`
- `email.bounced`
- `email.complained`
- `meeting.booked`
- `meeting.cancelled`

---

## 13. Command Palette / AI Assistant

### POST /v1/organizations/{org_id}/command

Execute natural language command.

**Request:**
```json
{
    "command": "Show me high-intent borrowers from this week",
    "context": {}
}
```

**Response:**
```json
{
    "command": "Show me high-intent borrowers from this week",
    "interpreted": {
        "intent": "list_opportunities",
        "filters": {
            "state": "intent_detected",
            "from": "2026-09-28",
            "to": "2026-10-05"
        }
    },
    "results": [...],
    "suggestions": [
        "Show me conversations that need my attention",
        "Find the five strongest opportunities that haven't been contacted"
    ]
}
```

---

## 14. Error format

All errors return:

```json
{
    "error": {
        "code": "VALIDATION_ERROR",
        "message": "Invalid request",
        "details": [
            {"field": "person.email", "message": "Invalid email format"}
        ]
    }
}
```

---

*End of API Specification*
