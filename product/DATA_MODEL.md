# Data Model

> This document defines the PostgreSQL schema for Acquisition OS.
> Every table includes `tenant_id` for strong multi-tenant isolation.
> The product layer owns these tables. Infrastructure tables are separate.

---

## 1. Core entities

### organizations

```sql
CREATE TABLE organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,  -- logical tenant (org)

    -- Brand
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(100) UNIQUE NOT NULL,
    logo_url TEXT,
    primary_color VARCHAR(7),
    custom_domain VARCHAR(255),

    -- Plan
    plan VARCHAR(50) NOT NULL DEFAULT 'starter',  -- starter, growth, business, enterprise
    plan_status VARCHAR(50) NOT NULL DEFAULT 'active',

    -- Settings
    settings JSONB NOT NULL DEFAULT '{}',  -- AI policy, voice, ICP, compliance

    -- Limits
    monthly_send_limit INTEGER NOT NULL DEFAULT 5000,
    monthly_opportunity_limit INTEGER NOT NULL DEFAULT 500,

    -- Metadata
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ,

    CONSTRAINT unique_tenant_id UNIQUE (tenant_id)
);

CREATE INDEX idx_organizations_tenant_id ON organizations(tenant_id);
CREATE INDEX idx_organizations_slug ON organizations(slug);
```

### users

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL,

    -- Identity
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    avatar_url TEXT,

    -- Auth
    password_hash VARCHAR(255),
    email_verified BOOLEAN NOT NULL DEFAULT FALSE,
    email_verification_token VARCHAR(255),
    password_reset_token VARCHAR(255),
    password_reset_expires_at TIMESTAMPTZ,

    -- Role
    role VARCHAR(50) NOT NULL DEFAULT 'advisor',  -- admin, manager, advisor, viewer

    -- Advisor-specific
    calendar_provider VARCHAR(50),  -- google, calendly, acuity
    calendar_id VARCHAR(255),
    calendar_credentials JSONB,

    -- Status
    active BOOLEAN NOT NULL DEFAULT TRUE,
    last_login_at TIMESTAMPTZ,

    -- Metadata
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ
);

CREATE INDEX idx_users_org_id ON users(org_id);
CREATE INDEX idx_users_tenant_id ON users(tenant_id);
CREATE INDEX idx_users_email ON users(email);
```

### sending_identities

```sql
CREATE TABLE sending_identities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL,

    -- Identity
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL,
    display_name VARCHAR(255),

    -- DKIM
    dkim_selector VARCHAR(100),
    dkim_public_key TEXT,

    -- Status
    active BOOLEAN NOT NULL DEFAULT TRUE,
    warmup_complete BOOLEAN NOT NULL DEFAULT FALSE,
    reputation_score INTEGER CHECK (reputation_score >= 0 AND reputation_score <= 100),

    -- Metadata
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT unique_org_email UNIQUE (org_id, email)
);

CREATE INDEX idx_sending_identities_org_id ON sending_identities(org_id);
```

---

## 2. Opportunity Graph

### opportunities

```sql
CREATE TABLE opportunities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL,

    -- Person
    person JSONB NOT NULL,  -- {name, email, phone, location, household_size, income_range}

    -- Fit & Scoring
    opportunity_score INTEGER NOT NULL DEFAULT 0 CHECK (opportunity_score >= 0 AND opportunity_score <= 100),
    fit JSONB NOT NULL DEFAULT '{}',  -- {icp_match, location_match, purchase_timeframe, property_range, segment, total}

    -- Intent
    intent JSONB NOT NULL DEFAULT '{}',  -- {level, signals[], objections[], questions[]}

    -- State
    state VARCHAR(50) NOT NULL DEFAULT 'discovered',
    state_history JSONB NOT NULL DEFAULT '[]',  -- [{state, entered_at, exited_at, reason}]

    -- Qualification
    qualification JSONB NOT NULL DEFAULT '{}',  -- {answers{}, stage, recommended_angle}

    -- Conversation
    conversation JSONB NOT NULL DEFAULT '[]',  -- [{id, direction, channel, subject, body, timestamp, intent, signals[]}]

    -- Appointment
    appointment JSONB,

    -- Provenance
    provenance JSONB NOT NULL DEFAULT '{}',  -- {source, discovery_signals[], research_evidence[], confidence}

    -- Lifecycle timestamps
    discovered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_contacted_at TIMESTAMPTZ,
    last_engaged_at TIMESTAMPTZ,
    next_action_at TIMESTAMPTZ,
    next_best_action TEXT,
    next_best_action_reason TEXT,

    -- Tags & custom
    tags TEXT[] NOT NULL DEFAULT '{}',
    custom_fields JSONB NOT NULL DEFAULT '{}',

    -- Metadata
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    version INTEGER NOT NULL DEFAULT 1,

    CONSTRAINT unique_org_email UNIQUE (org_id, (person->>'email')::text)
);

CREATE INDEX idx_opportunities_org_id ON opportunities(org_id);
CREATE INDEX idx_opportunities_tenant_id ON opportunities(tenant_id);
CREATE INDEX idx_opportunities_state ON opportunities(state);
CREATE INDEX idx_opportunities_opportunity_score ON opportunities(opportunity_score DESC);
CREATE INDEX idx_opportunities_next_action_at ON opportunities(next_action_at);
CREATE INDEX idx_opportunities_discovered_at ON opportunities(discovered_at);
CREATE INDEX idx_opportunities_tags ON opportunities USING GIN (tags);
```

### opportunity_events (event sourcing)

```sql
CREATE TABLE opportunity_events (
    id BIGSERIAL PRIMARY KEY,
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL,
    opportunity_id UUID NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,

    event_type VARCHAR(100) NOT NULL,  -- state_changed, message_sent, reply_received, score_updated
    event_data JSONB NOT NULL DEFAULT '{}',

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_opportunity_events_opportunity_id ON opportunity_events(opportunity_id);
CREATE INDEX idx_opportunity_events_org_id ON opportunity_events(org_id);
CREATE INDEX idx_opportunity_events_created_at ON opportunity_events(created_at);
```

### research_dossiers

```sql
CREATE TABLE research_dossiers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL,
    opportunity_id UUID NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,

    dossier JSONB NOT NULL,  -- {who_are_they, why_they_matter, fit_indicators[], recent_signals[], what_they_might_care_about}
    evidence JSONB NOT NULL DEFAULT '[]',  -- [{source, summary, url, confidence}]
    confidence VARCHAR(20) NOT NULL,  -- high, medium, low
    provenance_note TEXT,

    -- Metadata
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_research_dossiers_opportunity_id ON research_dossiers(opportunity_id);
CREATE INDEX idx_research_dossiers_org_id ON research_dossiers(org_id);
```

---

## 3. Content graph

### content

```sql
CREATE TABLE content (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL,

    -- Content
    title VARCHAR(500) NOT NULL,
    type VARCHAR(50) NOT NULL,  -- article, linkedin_post, video_script, lead_magnet, calculator, email, landing_page
    body TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}',  -- {tags, topic, seasonality, target_segment, etc.}

    -- Publishing
    published BOOLEAN NOT NULL DEFAULT FALSE,
    published_at TIMESTAMPTZ,
    published_channels JSONB DEFAULT '[]',

    -- Content graph
    related_content_ids UUID[] NOT NULL DEFAULT '{}',

    -- Attribution (content → pipeline)
    attribution JSONB NOT NULL DEFAULT '{}',  -- {views, calculator_visits, leads, qualified_opportunities, conversations, meetings, estimated_pipeline}

    -- Metadata
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID REFERENCES users(id)
);

CREATE INDEX idx_content_org_id ON content(org_id);
CREATE INDEX idx_content_type ON content(type);
CREATE INDEX idx_content_published ON content(published);
```

---

## 4. Campaigns & Automations

### campaigns

```sql
CREATE TABLE campaigns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL,

    -- Identity
    name VARCHAR(255) NOT NULL,
    description TEXT,
    type VARCHAR(50) NOT NULL,  -- inbound, proactive, nurture, content

    -- Targeting
    segment VARCHAR(255),
    filters JSONB NOT NULL DEFAULT '{}',  -- {location, fit_score_min, state, tags, etc.}

    -- Content & messaging
    content_ids UUID[] NOT NULL DEFAULT '{}',
    message_template_id UUID,

    -- Automation
    automation_id UUID,

    -- Metrics
    metrics JSONB NOT NULL DEFAULT '{}',  -- {discovered, researched, qualified, contacted, engaged, intent, booking, meeting, opportunity, customer}

    -- Status
    active BOOLEAN NOT NULL DEFAULT TRUE,

    -- Metadata
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID REFERENCES users(id)
);

CREATE INDEX idx_campaigns_org_id ON campaigns(org_id);
CREATE INDEX idx_campaigns_type ON campaigns(type);
CREATE INDEX idx_campaigns_active ON campaigns(active);
```

### automations

```sql
CREATE TABLE automations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL,

    -- Identity
    name VARCHAR(255) NOT NULL,
    description TEXT,
    active BOOLEAN NOT NULL DEFAULT TRUE,

    -- Workflow
    trigger_type VARCHAR(100) NOT NULL,  -- opportunity_state_changed, message_received, behavior_detected, scheduled
    trigger_config JSONB NOT NULL DEFAULT '{}',
    steps JSONB NOT NULL DEFAULT '[]',  -- [{type, config}] -- type: trigger, condition, action, wait

    -- Versioning
    version INTEGER NOT NULL DEFAULT 1,
    parent_id UUID,  -- for version history

    -- Metadata
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID REFERENCES users(id)
);

CREATE INDEX idx_automations_org_id ON automations(org_id);
CREATE INDEX idx_automations_active ON automations(active);
```

### missions

```sql
CREATE TABLE missions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL,

    -- Identity
    name VARCHAR(255) NOT NULL,
    description TEXT,
    active BOOLEAN NOT NULL DEFAULT TRUE,

    -- Target
    target_segment VARCHAR(255) NOT NULL,
    location VARCHAR(255) NOT NULL,
    property_range VARCHAR(255),
    monthly_goal INTEGER NOT NULL,

    -- Preferred action
    preferred_action VARCHAR(100) NOT NULL,  -- calendar_booking, phone_call, consultation
    advisor_id UUID REFERENCES users(id),
    calendar_id VARCHAR(255),

    -- Brand
    brand_id UUID,  -- reference to brand settings (can be embedded in org.settings)

    -- Generated automation
    generated_automation_id UUID REFERENCES automations(id),

    -- Metadata
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID REFERENCES users(id)
);

CREATE INDEX idx_missions_org_id ON missions(org_id);
CREATE INDEX idx_missions_active ON missions(active);
```

---

## 5. Conversations

### conversations

```sql
CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL,
    opportunity_id UUID NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,

    -- Conversation metadata
    channel VARCHAR(50) NOT NULL,  -- email, sms, chat, call
    state VARCHAR(50) NOT NULL DEFAULT 'active',  -- active, closed, escalated
    intent VARCHAR(100),
    intent_confidence FLOAT CHECK (intent_confidence >= 0.0 AND intent_confidence <= 1.0),

    -- Advisor assignment
    assigned_to UUID REFERENCES users(id),

    -- Metadata
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_message_at TIMESTAMPTZ
);

CREATE INDEX idx_conversations_opportunity_id ON conversations(opportunity_id);
CREATE INDEX idx_conversations_org_id ON conversations(org_id);
CREATE INDEX idx_conversations_state ON conversations(state);
CREATE INDEX idx_conversations_assigned_to ON conversations(assigned_to);
```

### messages

```sql
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL,
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    opportunity_id UUID NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,

    -- Message
    direction VARCHAR(20) NOT NULL,  -- inbound, outbound
    channel VARCHAR(50) NOT NULL,
    subject VARCHAR(500),
    body TEXT NOT NULL,

    -- Classification
    intent VARCHAR(100),
    signals JSONB NOT NULL DEFAULT '[]',  -- [{type, text, confidence}]
    classification JSONB,

    -- Sending
    message_id VARCHAR(255),  -- provider message ID
    from_address VARCHAR(255),
    to_address VARCHAR(255),

    -- AI
    ai_draft BOOLEAN NOT NULL DEFAULT FALSE,
    ai_approved BOOLEAN,
    ai_confidence FLOAT,

    -- Metadata
    sent_at TIMESTAMPTZ,
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_messages_conversation_id ON messages(conversation_id);
CREATE INDEX idx_messages_opportunity_id ON messages(opportunity_id);
CREATE INDEX idx_messages_org_id ON messages(org_id);
CREATE INDEX idx_messages_received_at ON messages(received_at DESC);
```

---

## 6. System Activity & Health

### system_activities

```sql
CREATE TABLE system_activities (
    id BIGSERIAL PRIMARY KEY,
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL,

    -- Activity
    type VARCHAR(100) NOT NULL,
    description TEXT NOT NULL,
    entity_id UUID,  -- opportunity_id, content_id, etc.
    entity_type VARCHAR(100),
    metadata JSONB NOT NULL DEFAULT '{}',

    -- Metadata
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_system_activities_org_id ON system_activities(org_id);
CREATE INDEX idx_system_activities_timestamp ON system_activities(timestamp DESC);
CREATE INDEX idx_system_activities_type ON system_activities(type);
```

### acquisition_health

```sql
CREATE TABLE acquisition_health (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL,

    -- Health metrics
    metrics JSONB NOT NULL DEFAULT '[]',  -- [{metric, status, value, target, trend, detail}]

    -- Recommendation
    recommendation TEXT,

    -- Metadata
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_acquisition_health_org_id ON acquisition_health(org_id);
CREATE INDEX idx_acquisition_health_generated_at ON acquisition_health(generated_at DESC);
```

---

## 7. Integrations

### integrations

```sql
CREATE TABLE integrations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL,

    -- Integration
    type VARCHAR(50) NOT NULL,  -- google_calendar, calendly, hubspot, salesforce, webhook
    name VARCHAR(255) NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,

    -- Credentials (encrypted at rest)
    credentials JSONB NOT NULL DEFAULT '{}',

    -- Configuration
    config JSONB NOT NULL DEFAULT '{}',

    -- Status
    last_sync_at TIMESTAMPTZ,
    last_error TEXT,

    -- Metadata
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_integrations_org_id ON integrations(org_id);
CREATE INDEX idx_integrations_type ON integrations(type);
```

---

## 8. Billing (future)

### subscriptions

```sql
CREATE TABLE subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL,

    -- Plan
    plan VARCHAR(50) NOT NULL,
    plan_amount DECIMAL(10, 2) NOT NULL,
    currency VARCHAR(3) NOT NULL DEFAULT 'USD',

    -- Billing cycle
    billing_cycle VARCHAR(50) NOT NULL DEFAULT 'monthly',
    current_period_start TIMESTAMPTZ NOT NULL,
    current_period_end TIMESTAMPTZ NOT NULL,

    -- Status
    status VARCHAR(50) NOT NULL DEFAULT 'active',
    cancel_at_period_end BOOLEAN NOT NULL DEFAULT FALSE,

    -- External
    stripe_subscription_id VARCHAR(255),
    stripe_customer_id VARCHAR(255),

    -- Metadata
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_subscriptions_org_id ON subscriptions(org_id);
```

### usage_records

```sql
CREATE TABLE usage_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL,

    -- Usage
    metric VARCHAR(100) NOT NULL,  -- emails_sent, opportunities_created, ai_calls, seats
    quantity INTEGER NOT NULL,
    period_start TIMESTAMPTZ NOT NULL,
    period_end TIMESTAMPTZ NOT NULL,

    -- Metadata
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_usage_records_org_id ON usage_records(org_id);
CREATE INDEX idx_usage_records_period ON usage_records(period_start, period_end);
```

---

## 9. Infrastructure bridge tables

These tables reference infrastructure-owned data. They are owned by the product layer but contain IDs from the infrastructure layer.

### sent_messages

```sql
CREATE TABLE sent_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL,
    opportunity_id UUID REFERENCES opportunities(id) ON DELETE SET NULL,
    conversation_id UUID REFERENCES conversations(id) ON DELETE SET NULL,

    -- Message
    direction VARCHAR(20) NOT NULL,  -- outbound, inbound
    channel VARCHAR(50) NOT NULL,
    from_address VARCHAR(255) NOT NULL,
    to_address VARCHAR(255) NOT NULL,
    subject VARCHAR(500),
    body TEXT,

    -- Provider
    provider_message_id VARCHAR(255),
    provider VARCHAR(50),  -- kumomta, sendgrid, smtp

    -- Status
    status VARCHAR(50) NOT NULL,  -- queued, sent, delivered, opened, clicked, bounced, complained, replied
    status_updated_at TIMESTAMPTZ,

    -- Timestamps
    queued_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    sent_at TIMESTAMPTZ,
    delivered_at TIMESTAMPTZ,
    opened_at TIMESTAMPTZ,
    clicked_at TIMESTAMPTZ,
    replied_at TIMESTAMPTZ,
    bounced_at TIMESTAMPTZ,
    complained_at TIMESTAMPTZ,

    -- Metadata
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_sent_messages_org_id ON sent_messages(org_id);
CREATE INDEX idx_sent_messages_opportunity_id ON sent_messages(opportunity_id);
CREATE INDEX idx_sent_messages_conversation_id ON sent_messages(conversation_id);
CREATE INDEX idx_sent_messages_status ON sent_messages(status);
CREATE INDEX idx_sent_messages_sent_at ON sent_messages(sent_at DESC);
```

### content_attribution

```sql
CREATE TABLE content_attribution (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL,
    content_id UUID NOT NULL REFERENCES content(id) ON DELETE CASCADE,
    opportunity_id UUID REFERENCES opportunities(id) ON DELETE SET NULL,

    -- Attribution
    event_type VARCHAR(100) NOT NULL,  -- view, calculator_use, lead_capture, qualified, conversation, meeting
    value DECIMAL(10, 2),  -- estimated pipeline value

    -- Timestamps
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Metadata
    metadata JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX idx_content_attribution_content_id ON content_attribution(content_id);
CREATE INDEX idx_content_attribution_opportunity_id ON content_attribution(opportunity_id);
CREATE INDEX idx_content_attribution_event_type ON content_attribution(event_type);
CREATE INDEX idx_content_attribution_occurred_at ON content_attribution(occurred_at DESC);
```

---

## 10. Row-level security (RLS)

For strong tenant isolation, enable RLS on all product tables:

```sql
-- Enable RLS
ALTER TABLE organizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE opportunities ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE content ENABLE ROW LEVEL SECURITY;
ALTER TABLE campaigns ENABLE ROW LEVEL SECURITY;
ALTER TABLE automations ENABLE ROW LEVEL SECURITY;
ALTER TABLE missions ENABLE ROW LEVEL SECURITY;
ALTER TABLE system_activities ENABLE ROW LEVEL SECURITY;
ALTER TABLE acquisition_health ENABLE ROW LEVEL SECURITY;

-- Policies (example for opportunities)
CREATE POLICY tenant_isolation ON opportunities
    FOR ALL
    USING (tenant_id = current_setting('app.current_tenant_id')::UUID);

-- Set tenant context per request
SET app.current_tenant_id = 'org-tenant-uuid';
```

---

*End of Data Model*
