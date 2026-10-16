# SLIDEIN USER JOURNEYS & INTERACTION PATTERNS

> **End-to-End Operational Paths for Internal Operators & Tenant Customers**  
> Status: Active Specification

---

## Journey 1: Internal Operator Onboards a New Client Deployment

```mermaid
sequenceDiagram
  autonumber
  actor Op as Internal Operator
  participant Dash as Fleet Console
  participant API as Slidein API
  participant DB as Tenant DB
  participant DNS as Infrastructure / MTA

  Op->>Dash: Create New Client Tenant ("Acme Corp", slug: acme)
  Dash->>API: POST /v1/tenants { name, slug, plan, monthly_quota }
  API->>DB: Provision isolated tenant & default workspace
  Op->>Dash: Input Business Profile & Upload Offers
  Dash->>API: POST /v1/tenants/acme/knowledge/business-profile
  Dash->>API: POST /v1/tenants/acme/knowledge/offers
  Op->>Dash: Configure Sending Identity (outbound@acme-outreach.com)
  Dash->>API: POST /v1/tenants/acme/identities
  API->>DNS: Verify SPF, DKIM, DMARC, MX records
  DNS-->>API: Authentication verified
  Op->>Dash: Run Pre-Flight Readiness Check
  Dash->>API: GET /v1/tenants/acme/readiness
  API-->>Dash: Readiness Score 100% (All 12 criteria green)
  Op->>Dash: Activate Deployment (Autonomy Level 1: Review Required)
  Dash->>API: POST /v1/tenants/acme/activate
```

---

## Journey 2: Customer Reviews Qualified Prospects & Approves Drafts

```mermaid
sequenceDiagram
  autonumber
  actor User as Customer / Sales Rep
  participant App as Workspace Dashboard
  participant API as Slidein API
  participant DB as Tenant DB

  User->>App: Opens Dashboard Overview
  App->>API: GET /v1/dashboard/summary
  API-->>App: 14 New Qualified Leads, 12 Drafts Awaiting Review
  User->>App: Clicks "Prospects" $\rightarrow$ filters by "Qualified"
  User->>App: Clicks on lead "Sarah Jenkins (VP Eng at FinTech Labs)"
  App->>API: GET /v1/prospects/lead_123/evidence
  API-->>App: Displays Sourced Evidence (Company funding, job posts, tech stack)
  App->>API: GET /v1/drafts/draft_456
  API-->>App: Displays Generated Draft & Evidence Attribution tags
  User->>App: Edits closing line in Draft Editor
  App->>API: PUT /v1/drafts/draft_456 { updated_body, user_edited: true }
  User->>App: Clicks "Approve & Schedule Dispatch"
  App->>API: POST /v1/drafts/draft_456/approve
  API->>DB: Status $\rightarrow$ APPROVED, Queued in Dispatch Pipeline
```

---

## Journey 3: Autonomous Scheduled Discovery & Deliverability-Gated Dispatch

1. **Cron Trigger:** Scheduled worker wakes up according to tenant's quiet-hours and dispatch window.
2. **Quota & Rate Gate:** Checks hourly rate limit ($< 25/\text{hr}$), daily budget ($< 150/\text{day}$), and current bounce rate ($< 2.0\%$).
3. **Suppression Verification:** Checks recipient email against global suppression table (`deliverability_state.db`).
4. **Transport Submission:** Formats MIME message with DKIM signing and submits via KumoMTA SMTP (port 2587).
5. **Event Logging:** Records delivery event in `sent_messages` with unique `message_id`.

---

## Journey 4: Inbound Reply Handling & Unsubscribe / Meeting Flow

```mermaid
sequenceDiagram
  autonumber
  actor Recipient as Email Recipient
  participant MTA as KumoMTA / Inbound MX
  participant Webhook as Slidein Webhook
  participant AI as Intent Classifier
  participant App as Customer Inbox
  actor User as Customer Rep

  Recipient->>MTA: Sends Reply ("Thanks for reaching out! Let's talk Thursday.")
  MTA->>Webhook: POST /v1/inbound/webhook (Raw MIME)
  Webhook->>Webhook: Parse In-Reply-To & Extract Thread
  Webhook->>AI: Classify Intent(subject, body)
  AI-->>Webhook: Intent: INTERESTED (Confidence: 0.94)
  Webhook->>App: Create Conversation & Notification
  App-->>User: Urgent Notification: "Sarah Jenkins replied - INTERESTED"
  User->>App: Opens Inbox view $\rightarrow$ Clicks "Suggest Meeting Time"
```

If recipient replies with *"Please unsubscribe me and take me off your list"*:
- Intent Classifier outputs: `UNSUBSCRIBE_REQUEST`.
- System instantly inserts recipient email and domain into `suppression_records`.
- Cancels any pending or future sequence follow-ups for this prospect.
- Emits audit log entry `SUPPRESSION_OPT_OUT`. No further outreach is possible.


---

## Journey 5: Prospect Engagement — Reply → Conversation → Booked Meeting (PROPOSED)

> Status: proposed; not built. Authoritative detail (branches FL-01…FL-12, tests):
> [`PROSPECT_ENGAGEMENT.md` §5](PROSPECT_ENGAGEMENT.md). Architecture:
> [`../architecture/ENGAGEMENT_ARCHITECTURE.md`](../architecture/ENGAGEMENT_ARCHITECTURE.md).

Roles: **Prospect** (email, chat link, later phone) · **Client representative** (inbox, approvals, handoff) ·
**Client admin** (approved knowledge, meeting types, autonomy) · **Platform operator** (health, kill switch).

1. Prospect replies to an outreach email (question, interest, meeting request, chat or call request, not interested, stop).
2. System ingests once, links the reply to tenant/prospect/campaign, filters auto-replies, classifies intent.
3. Stop → immediate suppression. Needs human or unknown answer → handoff with context.
4. Otherwise a grounded reply is drafted with citations; a representative approves (default) and it is sent through the normal pre-send gates.
5. Interested/meeting → reply includes a booking option; chat → a secure personalized link (M2).
6. Provider confirms booking → prospect and campaign status update, representative notified, conversation context preserved. The agent never claims a booking before confirmation.
7. Representative can take over at any point; the agent stops and the full history is visible.

Voice is limited to inbound/callback with consent (M3, opt-in); automated outbound calling is blocked pending legal review and approval.
