# Acquisition OS — Product Layer

> **Acquisition Operating System** — The product layer that turns infrastructure into a premium acquisition platform.
>
> This is the **product** layer: UX, API, AI orchestration, automation, business logic.
> The **infrastructure** layer (KumoMTA, deliverability engine, DNS, warmup) is owned by a separate engineering agent.

## What Was Built

### 1. Product Architecture (`product/ARCHITECTURE.md`)
- Complete system architecture for the Acquisition OS
- Two acquisition sides (Inbound + Proactive)
- AI Acquisition Team design (9 specialized agents)
- Multi-tenancy model with strong isolation
- Human-in-the-loop autonomy levels (Assist / Co-Pilot / Autonomous)
- Integration layer contract with infrastructure
- Build tiers (Tier 1 MVP, Tier 2, Tier 3)

### 2. Core Abstractions (`product/CORE_ABSTRACTIONS.md`)
- **Opportunity Profile** — replaces flat CRM records with rich, evolving profiles
- **Acquisition Engine** — finite-state machine governing opportunity lifecycle
- **Mission** — high-level acquisition goals translated into automation
- **Automation** — visual workflow engine (trigger → condition → action → wait)
- **Content** — content graph with attribution
- **Campaign** — coordinated outreach campaigns
- **System Activity** — real-time activity feed
- **Acquisition Health** — system health metrics with recommendations

### 3. AI Agents Design (`product/AGENTS_DESIGN.md`)
- **Research Agent** — finds and summarizes opportunity-relevant information
- **Qualification Agent** — determines ICP fit with explainable scoring
- **Personalization Agent** — converts research into genuine, specific context (no fake compliments)
- **Message Agent** — creates actual communication content
- **Conversation Agent** — handles authorized replies within business rules
- **Nurture Agent** — determines next interaction for non-ready prospects (responds to behavior, not calendar)
- **Booking Agent** — moves qualified prospects toward appointments
- **Content Agent** — creates authority content with content graph
- **Optimization Agent** — analyzes and improves acquisition performance
- **Business Policy Layer** — configurable compliance rules and guardrails

### 4. Data Model (`product/DATA_MODEL.md`)
- Complete PostgreSQL schema with `tenant_id` on every row
- Row-level security (RLS) policies for strong tenant isolation
- Opportunity Graph: Person + Company + Property + Location + Intent + Behavior + Conversation + Content + Timeline + Qualification + Appointment
- Event sourcing via `opportunity_events` table
- Content attribution graph
- Infrastructure bridge tables (`sent_messages`, `content_attribution`)

### 5. API Specification (`product/API_SPEC.md`)
- REST API v1 with org-scoped paths
- Complete endpoint specification for:
  - Opportunities (CRUD, research, qualify, personalize, message, send, book, pipeline)
  - Command Center
  - Conversations
  - Content
  - Campaigns
  - Missions
  - Automations
  - Acquisition Health
  - Analytics (pipeline, content attribution, acquisition efficiency)
  - Command Palette / AI Assistant
- Error format specification
- Pagination patterns

### 6. UX Patterns (`product/UX_PATTERNS.md`)
- Design language: Bloomberg intelligence + Linear simplicity + Stripe polish
- Complete component system (buttons, cards, tables, timelines)
- Color system with semantic colors
- Typography scale
- Spacing system
- Key screen mockups:
  - Command Center
  - Pipeline view
  - Opportunity Profile
  - Conversation Intelligence

## Implementation Status

### Completed
| Component | Status | Description |
|-----------|--------|-------------|
| Product Architecture | ✅ Complete | `product/ARCHITECTURE.md` |
| Core Abstractions | ✅ Complete | `product/CORE_ABSTRACTIONS.md` |
| AI Agents Design | ✅ Complete | `product/AGENTS_DESIGN.md` |
| Data Model | ✅ Complete | `product/DATA_MODEL.md` |
| API Specification | ✅ Complete | `product/API_SPEC.md` |
| UX Patterns | ✅ Complete | `product/UX_PATTERNS.md` |
| FastAPI App | ✅ Complete | `product/api/main.py` |
| API Routes | ✅ Complete | Opportunities, Command Center, Health |
| Pydantic Schemas | ✅ Complete | All request/response models |
| Core Services | ✅ Complete | Acquisition Engine, Opportunity, Command Center, Health |
| Integration Layer | ✅ Complete | `product/integrations/` with clean boundary interfaces |
| AI Agents (mock) | ✅ Complete | Research, Qualification, Personalization, Message, Conversation, Nurture, Booking, Content, Optimization |
| AI Orchestrator | ✅ Complete | Coordinates all agents |
| Database Models | ✅ Complete | SQLAlchemy async models for PostgreSQL |
| Event System | ✅ Complete | EventBus with publisher/subscriber pattern |
| Workers | ✅ Complete | Discovery, Nurture, Analytics workers |

### Next Steps

1. **Replace mock implementations** with real services:
   - Connect AI agents to real LLM provider (OpenAI, Anthropic, etc.)
   - Connect to real database (PostgreSQL)
   - Connect to real infrastructure layer (KumoMTA, deliverability engine)

2. **Build the Next.js frontend:**
   - Command Center
   - Pipeline view
   - Opportunity Profile
   - Conversation Intelligence
   - System Activity Feed
   - Acquisition Health
   - Mission Builder
   - Automation Builder

3. **Implement Tier 2 features:**
   - Real Research Agent (web search + LLM synthesis)
   - Real Qualification Agent (LLM-based ICP evaluation)
   - Content Engine with content graph
   - Next Best Action engine
   - Smart Nurture with behavior-based triggers

4. **Implement Tier 3 features:**
   - Autonomous acquisition missions
   - Acquisition Intelligence Layer
   - Advanced optimization
   - Operator Console
   - Enterprise features (SSO, RBAC, audit logs, etc.)

## Running the Product API

### Prerequisites
```bash
# Python 3.11+
# PostgreSQL 15+
# Redis (for future workers)
```

### Setup
```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install fastapi uvicorn sqlalchemy asyncpg pydantic python-dotenv

# Set environment variables
export DATABASE_URL="postgresql+asyncpg://acquisition:acquisition@localhost:5432/acquisition_os"
export REDIS_URL="redis://localhost:6379"

# Run migrations (when Alembic is set up)
alembic upgrade head

# Start the API
uvicorn product.api.main:app --host 0.0.0.0 --port 8000 --reload
```

### Access
- API docs: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- Health: http://localhost:8000/health

## Architecture

```
product/
├── ARCHITECTURE.md          # System architecture
├── CORE_ABSTRACTIONS.md     # Core data models
├── AGENTS_DESIGN.md         # AI agents design
├── DATA_MODEL.md            # PostgreSQL schema
├── API_SPEC.md              # REST API specification
├── UX_PATTERNS.md           # Design system
├── README.md                # This file
│
├── api/                     # FastAPI product API
│   ├── main.py              # App factory, CORS, routes
│   ├── schemas/             # Pydantic models
│   └── routes/              # API route handlers
│       ├── opportunities.py # Opportunity CRUD + actions
│       ├── command_center.py # Command Center
│       └── health.py        # Acquisition health
│
├── services/                # Business logic layer
│   ├── acquisition_engine.py # Core pipeline FSM
│   ├── opportunity_service.py
│   ├── command_center.py
│   └── health.py
│
├── agents/                  # AI Acquisition Team
│   ├── base.py              # Base agent interface
│   ├── research_agent.py
│   ├── qualification_agent.py
│   ├── personalization_agent.py
│   ├── message_agent.py
│   ├── conversation_agent.py
│   ├── nurture_agent.py
│   ├── booking_agent.py
│   ├── content_agent.py
│   ├── optimization_agent.py
│   └── ai_orchestrator.py   # Agent coordinator
│
├── integrations/            # Infrastructure boundary
│   └── __init__.py          # Clean interfaces to MTA/infra
│
├── db/                      # Database layer
│   └── models.py            # SQLAlchemy async models
│
├── events/                  # Event system
│   └── __init__.py          # EventBus with pub/sub
│
└── workers/                 # Background workers
    └── worker.py            # Discovery, Nurture, Analytics
```

## Key Design Decisions

1. **Clean boundary with infrastructure**: Product layer never touches MTA internals directly. All communication flows through `product/integrations/`.

2. **Multi-tenant by design**: Every table has `tenant_id`. RLS policies enforce isolation. No cross-tenant leaks possible.

3. **Event-driven architecture**: Domain events flow through `EventBus`. Enables real-time updates, audit trails, and extensibility.

4. **Opportunity Profile as first-class citizen**: Replaces flat CRM records. Evolves over time. Contains Person + Fit + Intent + Behavior + Conversation + Qualification + Appointment + Provenance + Lifecycle.

5. **Acquisition Engine as core FSM**: All opportunity state changes flow through the finite-state machine. Valid transitions enforced. State history maintained.

6. **Explainable AI**: Every AI decision includes provenance and reasoning. "Why this lead?" is always answerable.

7. **Human-in-the-loop by default**: Three autonomy levels (Assist, Co-Pilot, Autonomous). Never fully autonomous without explicit opt-in.

8. **Business Policy Layer**: Configurable per-org rules governing AI behavior. Compliance built in, not bolted on.

## Integration with Infrastructure Agent

The infrastructure agent builds:
- KumoMTA configuration and management
- Deliverability engine (pre-send gate, seed testing, circuit breaker, warmup)
- DNS automation (SPF, DKIM, DMARC)
- Email sending and receiving
- Bounce/complaint handling
- Reputation monitoring

The product layer calls these through the Integration Layer:

```python
# product/integrations/__init__.py

infrastructure = InfrastructureIntegration()

# Send message
result = await infrastructure.send_message(
    org_id="org_123",
    opportunity_id="opp_456",
    from_identity_id="identity_123",
    subject="...",
    body="...",
    channel="email",
)

# Verify domain
result = await infrastructure.verify_domain(org_id="org_123", domain="example.com")

# Book calendar
result = await infrastructure.book_calendar(
    org_id="org_123",
    opportunity_id="opp_456",
    advisor_id="advisor_123",
    start_time="2026-10-10T14:00:00Z",
    end_time="2026-10-10T14:30:00Z",
)
```

The infrastructure agent implements these endpoints:
- `POST /v1/send`
- `GET /v1/send/{message_id}/status`
- `POST /v1/domains/{domain}/verify`
- `GET /v1/calendar/availability`
- `POST /v1/calendar/book`
- `POST /v1/content/publish`
- `GET /v1/analytics/*`

## License

Proprietary. All rights reserved.
