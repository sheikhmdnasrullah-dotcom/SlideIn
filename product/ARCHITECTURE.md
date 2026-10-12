# Acquisition OS — Architecture

> Owner: Nasrullah Tanim. Status: v0 architecture (2026-10-05).
> This is the canonical product architecture for the **Acquisition Operating System**.
> It supersedes the InboxForge cold-email design for the product layer.
> The underlying email/MTA infrastructure layer is owned by a separate engineering agent.

---

## 1. One-liner

**Acquisition OS** is a platform that continuously builds and operates a business's acquisition pipeline: it discovers opportunities, researches them, creates the right message, starts conversations, nurtures prospects, captures inbound leads, qualifies them, and moves qualified opportunities toward booked meetings.

The customer does not log in to "create a campaign." They log in to see what their acquisition system is doing today.

---

## 2. The Acquisition Engine (core abstraction)

The entire application revolves around a single pipeline abstraction:

```
DISCOVER → RESEARCH → QUALIFY → PERSONALIZE → ENGAGE → NURTURE → BOOK → CONVERT → LEARN
```

Every entity in the system (lead, opportunity, conversation, campaign, content) maps to a state in this pipeline.

### Entity model

- **Organization** — a customer company (tenant).
- **User** — a person in the organization (advisor, manager, admin).
- **Brand** — the organization's public identity (logo, colors, voice, domain).
- **Opportunity** — a person + evolving Opportunity Profile + current state in the Acquisition Engine.
- **Conversation** — an exchange between the system and an opportunity (email, SMS, call, chat).
- **Content** — articles, posts, videos, calculators, lead magnets.
- **Campaign** — a coordinated push to move a segment of opportunities through the engine.
- **Mission** — a high-level acquisition goal (e.g., "20 qualified first-time-homebuyer conversations in Austin this month").
- **Automation** — a visual workflow (trigger → condition → action → wait → ...).

### Opportunity Profile (the data structure that replaces a flat CRM record)

```
Opportunity {
  person: {
    name, email, phone, location, household_size, income_range
  }
  opportunity_score: 82
  fit: {
    icp_match, location_match, purchase_timeframe, property_range, segment
  }
  intent: {
    level, signals[], objections[], questions[]
  }
  behavior: {
    content_consumed[], calculator_uses[], email_engagement[], reply_history[]
  }
  conversation: {
    state, messages[], ai_recommendations[], next_best_action
  }
  qualification: {
    answers{}, stage, recommended_angle
  }
  appointment: {
    status, proposed_times[], confirmed_time
  }
  provenance: {
    source, discovery_signals[], research_evidence[], confidence
  }
  lifecycle: {
    discovered_at, last_contacted_at, next_action_at, state, state_history[]
  }
}
```

---

## 3. System topology

```
┌─────────────────────────────────────────────────────────────┐
│                    ACQUISITION OS                           │
│  ┌───────────────────────────────────────────────────────┐  │
│  │              PRODUCT LAYER (this repo)                 │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐  │  │
│  │  │   Command   │  │ Acquisition │  │   Content    │  │  │
│  │  │   Center    │  │   Engine    │  │   Engine     │  │  │
│  │  └─────────────┘  └─────────────┘  └──────────────┘  │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐  │  │
│  │  │    AI       │  │  Operator   │  │   Platform   │  │  │
│  │  │    Team     │  │   Console   │  │    API       │  │  │
│  │  └─────────────┘  └─────────────┘  └──────────────┘  │  │
│  └───────────────────────────────────────────────────────┘  │
│                            │                                │
│                            ▼                                │
│  ┌───────────────────────────────────────────────────────┐  │
│  │              INTEGRATION LAYER                         │  │
│  │  Send · Calendar · CRM · Webhook · Analytics           │  │
│  └───────────────────────────────────────────────────────┘  │
│                            │                                │
│                            ▼                                │
│  ┌───────────────────────────────────────────────────────┐  │
│  │          INFRASTRUCTURE (owned by infra agent)         │  │
│  │  KumoMTA · Deliverability Engine · DNS · Warmup       │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

**Boundary rule:** The product layer must never touch MTA internals directly. It communicates through the Integration Layer, which is owned by the infrastructure agent.

---

## 4. Two acquisition sides

### Side A — Inbound Acquisition

```
Content → Website → Tool/Calculator → Lead Capture → Immediate Response → Qualification → Conversation → Booking
```

### Side B — Proactive Acquisition

```
ICP Definition → Discover Prospects → Research → Evaluate Fit → Opportunity Profile → Personalized Outreach → Send → Monitor → Nurture → Book
```

The product must support both sides through the same Opportunity Profile and Acquisition Engine abstractions.

---

## 5. AI Acquisition Team

The AI layer is conceptualized as a team of specialized agents, each with a clear contract:

| Agent | Responsibility | Input | Output |
|-------|----------------|-------|--------|
| **Research** | Find and summarize opportunity-relevant information | Person, company, location | Research dossier, evidence sources, confidence |
| **Qualification** | Determine if opportunity matches ICP | Opportunity Profile | Fit score, qualification stage, reasoning |
| **Personalization** | Convert research into specific, genuine context | Research dossier, brand voice | Personalized message context, provenance |
| **Message** | Create the communication | Personalization context, brand, channel | Message content, channel selection |
| **Conversation** | Handle authorized replies within business rules | Inbound message, conversation history | Response draft, intent classification, escalation flag |
| **Nurture** | Determine next interaction for non-ready prospects | Opportunity state, behavior, intent | Next action, timing, content recommendation |
| **Booking** | Move qualified prospects toward appointment | Opportunity state, advisor availability | Calendar invitation, proposed times, confirmation |
| **Content** | Create authority content | Customer expertise, geography, campaign | Article, post, video script, lead magnet |
| **Optimization** | Analyze and improve acquisition performance | Campaign data, funnel metrics | Recommendations, A/B tests, alerts |

**AI Guardrails (Business Policy Layer)**

Configurable per-organization rules:
- Allowed: explain general loan concepts
- Allowed: collect preliminary information
- Allowed: schedule advisor conversations
- Escalate: specific underwriting questions
- Escalate: complex financial circumstances
- Do not claim: guaranteed approval
- Do not claim: guaranteed rates
- Do not impersonate: the licensed advisor

---

## 6. Multi-tenancy model

```
Platform
 └── Organization (tenant)
      ├── Brand
      ├── Users (advisors, managers, admins)
      ├── Domains (sending, website, calculator)
      ├── Sending Identities (hello@, talk@, connect@)
      ├── Missions
      ├── Opportunities
      ├── Conversations
      ├── Content
      ├── Campaigns
      ├── Automations
      ├── Integrations (calendar, CRM, webhook)
      └── Settings (AI policy, voice, ICP, compliance)
```

Strong tenant isolation at every layer:
- Data: `tenant_id` on every row, enforced at repository level
- API: tenant-scoped routes, org-scoped API keys
- Auth: org-aware sessions, role-based access per org
- Infrastructure: per-tenant transport config, separate rate limits, isolated seed pools (where applicable)
- Billing: per-org usage metering, plan tiers, overage handling

---

## 7. Human-in-the-loop autonomy levels

Every automation has three levels:

| Level | Behavior | Use case |
|-------|----------|----------|
| **Assist** | AI prepares everything; human approves before send | High-stakes conversations, new advisor onboarding |
| **Co-Pilot** | AI handles routine steps; human handles important decisions | Day-to-day nurturing, follow-ups |
| **Autonomous** | AI operates within strict rules and escalation boundaries | Fully trusted advisors, mature systems |

The level is configurable per automation, per user, per organization.

---

## 8. Command Center UX model

The homepage is a Command Center, not a metric dashboard.

```
GOOD MORNING, {first_name}
Your acquisition system worked overnight.
────────────────────────────────────
{new_opportunities_discovered} new opportunities discovered
{high_fit_prospects_researched} high-fit prospects researched
{active_conversations} borrower conversations active
{strong_intent_prospects} prospects showing strong intent
{meetings_booked} meetings booked
{cooling_prospects} opportunities are cooling down
────────────────────────────────────
TODAY'S PRIORITIES
① {name} — {state}, {reason}
   → {action}
② {name} — {state}, {reason}
   → {action}
────────────────────────────────────
SYSTEM ACTIVITY
✓ {activity_1}
✓ {activity_2}
✓ {activity_3}
```

---

## 9. System Activity Feed

A real-time stream showing what the machine is doing:

```
09:41  New borrower captured from affordability calculator
09:43  Opportunity researched
09:44  High intent detected
09:45  Personalized response generated
09:46  Message sent
10:12  Prospect replied
10:13  AI classified intent as: "Ready to speak"
10:14  Calendar link sent
10:26  Appointment booked
```

---

## 10. Acquisition Health view

```
ACQUISITION HEALTH
Lead Flow             Excellent
Research Coverage     Good
Conversation Health   Excellent
Booking Rate          Needs Attention
Content Performance   Excellent
Email Deliverability  Excellent

SYSTEM RECOMMENDATION
"Your calculator is generating leads normally,
but the conversion from qualified conversation
to booked meeting has declined 18%. The strongest
drop occurs after the first qualification question.
Review the qualification flow."
```

---

## 11. "Why this lead?" explanations

Every AI decision is explainable:

```
Lead Score: 87

+25 ICP match
+20 location match
+15 purchase timeframe
+10 calculator engagement
+10 reply intent
+7 property value match
```

---

## 12. Content → Pipeline attribution

```
Article: "Should I Buy Before Rates Fall?"
1,823 views
94 calculator visits
31 leads
12 qualified opportunities
5 conversations
2 booked meetings
$X estimated pipeline
```

---

## 13. API-first design

Everything important has an API. Stable service boundaries.

**Tenant-scoped base path:** `/v1/organizations/{org_id}/...`

**Core resources:**
- Opportunities
- Conversations
- Content
- Campaigns
- Missions
- Automations
- Integrations
- Analytics

**Authentication:** Org-scoped API keys + optional OAuth2/SSO.

---

## 14. Operator Console (internal)

Separate from the customer dashboard. Our team uses it to:
- Onboard customers
- Configure domains, sending, funnels, calculators, AI policy
- Inspect automation, review failures, impersonate/support users safely
- Manage subscriptions, monitor infrastructure

---

## 15. White-label support

Architecture supports:
- `customer-domain.com`
- `app.customer-domain.com`
- Customer branding: logo, colors, domain, company name, sender identity, content voice

---

## 16. Enterprise readiness (architect for, implement as needed)

- SSO (OAuth2, SAML)
- RBAC (roles, permissions, team seats)
- Audit logs
- Approval workflows
- Custom domains
- API access + webhooks
- Usage limits + metering
- White-labeling
- Data export + backups + retention
- Regional deployment

---

## 17. Build tiers

### Tier 1 (MVP)
- Multi-tenant foundation
- Lead capture
- Opportunity Profile
- Pipeline
- Conversation timeline
- Email integration
- Calendar integration
- Basic automation
- Command Center

### Tier 2
- Research Agent
- Personalization Agent
- Content Engine
- Nurture Agent
- Lead scoring
- Next Best Action

### Tier 3
- Autonomous acquisition missions
- Acquisition Intelligence Layer
- Advanced optimization
- Operator Console
- Enterprise features

---

## 18. Tech stack (proposed)

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| **Product API** | FastAPI (Python) | Reuses deliverability/core; async; type-safe |
| **Database** | PostgreSQL | Multi-tenant; JSONB for Opportunity Profiles; strong constraints |
| **Product UI** | Next.js 14 + shadcn/ui | Modern SaaS; real-time; premium feel |
| **Queue** | Redis + BullMQ | Background jobs (research, send, nurture) |
| **Cache** | Redis | Session, rate limit, real-time feed |
| **Storage** | S3-compatible | Attachments, reports, exports |
| **LLM** | OpenAI / Anthropic / local | AI agents |
| **Infra** | KumoMTA + existing deliverability core | Owned by infra agent |
| **Observability** | Prometheus + Grafana | Ops + acquisition health |

---

## 19. Key design principles

1. **The customer has an acquisition department running inside the software.** Every screen should reinforce this.
2. **Do not sell "send more emails."** Sell "we build and operate your pipeline."
3. **No fake personalization.** Only genuine, research-backed relevance.
4. **Every AI decision is explainable.** Trust through transparency.
5. **Human-in-the-loop by default.** Never fully autonomous without explicit opt-in.
6. **Measure business outcomes, not activity metrics.** Pipeline value, booked meetings, revenue influenced.
7. **Premium, calm, intelligent UX.** No clutter, no rainbow charts, no meaningless gradients.
8. **Clean interface boundaries.** The product layer never touches MTA internals directly.

---

## 20. File structure (product layer)

```
product/
├── DESIGN.md                    # This document
├── ARCHITECTURE.md              # System architecture
├── API_SPEC.md                  # REST API specification
├── DATA_MODEL.md                # Database schema and relationships
├── AGENTS_DESIGN.md             # AI Acquisition Team design
├── UX_PATTERNS.md               # Design system and UX patterns
├── README.md                    # Product layer overview
│
├── api/                         # FastAPI product API
│   ├── __init__.py
│   ├── main.py                  # App factory, middleware
│   ├── dependencies.py          # Shared dependencies (tenant, auth)
│   ├── routers/
│   │   ├── organizations.py     # Org CRUD, branding, settings
│   │   ├── opportunities.py     # Opportunity CRUD, scoring, pipeline
│   │   ├── conversations.py     # Conversation threads, messages
│   │   ├── campaigns.py         # Campaign management
│   │   ├── missions.py          # Mission CRUD, mission engine
│   │   ├── content.py           # Content CRUD, publishing
│   │   ├── automations.py       # Automation workflows
│   │   ├── integrations.py      # Calendar, CRM, webhooks
│   │   ├── analytics.py         # Acquisition metrics
│   │   ├── command.py           # Command center API
│   │   └── health.py            # Acquisition health API
│   ├── services/
│   │   ├── acquisition_engine.py # Core pipeline engine
│   │   ├── opportunity_service.py
│   │   ├── conversation_service.py
│   │   ├── mission_service.py
│   │   ├── automation_service.py
│   │   ├── content_service.py
│   │   └── analytics_service.py
│   └── models/
│       ├── organization.py
│       ├── opportunity.py
│       ├── conversation.py
│       ├── campaign.py
│       ├── mission.py
│       ├── content.py
│       ├── automation.py
│       ├── integration.py
│       └── event.py
│
├── agents/                      # AI Acquisition Team
│   ├── __init__.py
│   ├── base.py                  # Base agent interface
│   ├── research_agent.py
│   ├── qualification_agent.py
│   ├── personalization_agent.py
│   ├── message_agent.py
│   ├── conversation_agent.py
│   ├── nurture_agent.py
│   ├── booking_agent.py
│   ├── content_agent.py
│   └── optimization_agent.py
│
├── workers/                     # Background job workers
│   ├── __init__.py
│   ├── discovery_worker.py
│   ├── research_worker.py
│   ├── send_worker.py
│   ├── nurture_worker.py
│   ├── content_worker.py
│   └── analytics_worker.py
│
├── integrations/                # External service adapters
│   ├── __init__.py
│   ├── email.py                 # Email sending (via infra layer)
│   ├── calendar.py              # Calendar booking
│   ├── crm.py                   # CRM sync
│   ├── webhook.py               # Inbound/outbound webhooks
│   └── llm.py                   # LLM provider abstraction
│
├── db/                          # Database layer
│   ├── __init__.py
│   ├── session.py               # SQLAlchemy async session
│   ├── base.py                  # Declarative base
│   ├── migrations/              # Alembic migrations
│   └── repositories/            # Data access layer
│       ├── organization_repo.py
│       ├── opportunity_repo.py
│       ├── conversation_repo.py
│       └── ...
│
└── ui/                          # Next.js frontend
    ├── app/
    │   ├── (auth)/
    │   ├── (dashboard)/
    │   │   ├── layout.tsx
    │   │   ├── page.tsx           # Command Center
    │   │   ├── opportunities/
    │   │   ├── conversations/
    │   │   ├── campaigns/
    │   │   ├── content/
    │   │   ├── missions/
    │   │   ├── automations/
    │   │   ├── integrations/
    │   │   ├── analytics/
    │   │   └── settings/
    │   └── layout.tsx
    ├── components/
    │   ├── command-center/
    │   ├── acquisition-engine/
    │   ├── opportunity-profile/
    │   ├── pipeline/
    │   ├── conversation-timeline/
    │   ├── system-activity-feed/
    │   ├── acquisition-health/
    │   ├── mission-builder/
    │   ├── automation-builder/
    │   └── ...
    ├── lib/
    │   ├── api.ts
    │   ├── auth.ts
    │   ├── types.ts
    │   └── utils.ts
    └── public/
```

---

## 21. Integration layer contract (owned by infra agent)

The product layer depends on these stable interfaces. The infrastructure agent implements them.

```
INTEGRATION LAYER CONTRACT (v1)

1. SEND
   POST /v1/send
   Body: { org_id, opportunity_id, message, channel, from_identity }
   Returns: { message_id, status, scheduled_at, metadata }

2. WEBHOOK EVENTS
   POST /v1/webhooks/events
   Body: { event_type, org_id, opportunity_id, payload, timestamp }
   Events: email_sent, email_delivered, email_opened, link_clicked,
           email_replied, email_bounced, email_complained, meeting_booked

3. CALENDAR
   GET  /v1/calendar/availability?advisor={id}&date={date}
   POST /v1/calendar/book
   Body: { opportunity_id, advisor_id, start_time, end_time }

4. CONTENT PUBLISH
   POST /v1/content/publish
   Body: { org_id, content_id, channels[], scheduled_at }

5. ANALYTICS
   GET /v1/analytics/sends?org={org}&from={date}&to={date}
   GET /v1/analytics/pipeline?org={org}
   GET /v1/analytics/health?org={org}

6. AI
   POST /v1/ai/research
   Body: { org_id, opportunity_id, depth }
   Returns: { research_dossier, evidence[], confidence }

   POST /v1/ai/personalize
   Body: { org_id, opportunity_id, context }
   Returns: { personalized_message, provenance[] }

   POST /v1/ai/classify-intent
   Body: { org_id, conversation_id, message }
   Returns: { intent, confidence, reasoning }
```

The product layer implements the orchestration, the AI agents, the UX, and the business logic. The infrastructure layer implements delivery, DNS, warmup, and transport.

---

*End of Acquisition OS Architecture*
