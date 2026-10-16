# SLIDEIN INTEGRATIONS REGISTRY & CONTRACTS

> **External Provider Contracts, Authentication & Resilience**  
> Status: Authoritative Specification  
> Version: 1.0.0

---

## 1. Provider Adapter Registry

| Category | Provider | Purpose | Primary Interface | Fallback Strategy |
|---|---|---|---|---|
| **Email Submission** | KumoMTA | High-throughput SMTP submission, DKIM, per-domain rate limits | SMTP port 2587 (AUTH) | GoPhish API / Secondary Relay |
| **Deliverability Engine** | Slidein Server | Spam scoring, pre-send verification, suppression | REST port 8088 | Direct SQLite query |
| **Admin & Campaign** | GoPhish | Profile management, tracking, legacy campaigns | REST port 8333 | Direct SMTP |
| **Web Research** | Tavily / Search | Company signals, news, job listings, public executives | REST API | Headless browser / DuckDuckGo |
| **AI Models** | Anthropic / OpenAI | Extraction, qualification, personalized drafting | Vercel AI SDK (`ai`) | Fallback model / Cached response |
| **Database & Auth** | Supabase / Appwrite | User authentication, operational database | Client / Server SDKs | Local Postgres / SQLite |
| **Observability** | Langfuse / Datadog | Prompt evaluation, LLM cost tracking, error monitoring | Langfuse SDK / Datadog RUM | Local structured JSON logs |

---

## 2. Integration Contract Details

### 2.1 KumoMTA Submission Contract
- **Endpoint:** `smtp://169.58.207.75:2587` (or `localhost:2587` in lab)
- **Authentication:** PLAIN / LOGIN with tenant-scoped credentials (`outbound:<password>`)
- **Required Headers:**
  - `From: <authorized_identity@domain>`
  - `To: <prospect_email>`
  - `Subject: <subject>`
  - `X-Slidein-Tenant-ID: <tenant_id>`
  - `X-Slidein-Draft-ID: <draft_id>`
- **DKIM Signing:** Handled automatically in MTA policy (`kumomta-lab/policy/production_init.lua`) using 2048-bit RSA keys.

### 2.2 Web Research Contract (`ResearchAdapter`)
```typescript
export interface ResearchRequest {
  companyName: string;
  domain?: string;
  targetRole?: string;
  signalsToLookFor: string[];
}

export interface ResearchResult {
  evidence: Array<{
    claimText: string;
    sourceUrl: string;
    confidence: number;
    type: "company_news" | "hiring_signal" | "tech_stack" | "exec_quote";
  }>;
  durationMs: number;
}
```
- **Rate Limit Policy:** Max 60 requests/minute. On HTTP 429, sleep with exponential backoff (2s, 4s, 8s).

### 2.3 AI Prompt & Drafting Contract (`DraftingAdapter`)
- **Input:** `BusinessProfile` + `Offer` + `Prospect` + `EvidenceItem[]`.
- **System Constraints:**
  - "You are writing a 1-to-1 business introduction. You are forbidden from inventing facts not provided in the Evidence items."
  - "Keep body under 100 words. Single focused call to action."
- **Output Schema:** Zod-validated JSON `{ subject: string, body: string, cited_evidence_ids: string[] }`.


---

## 3. Proposed Engagement Integrations (NOT IMPLEMENTED — see `ENGAGEMENT_ARCHITECTURE.md`)

| Category | Provider | Purpose | Interface | Status |
|---|---|---|---|---|
| Inbound email | TBD (PD-01) | Deliver replies to `/webhooks/inbound` | MX / IMAP / provider webhook | Open decision (OQ-020) |
| Booking | TBD (PD-02) | Offer/confirm/reschedule/cancel meetings | `BookingProvider` adapter + webhooks | Open decision (OQ-004, OQ-021) |
| Notifications | TBD | Alert representatives | Email/Slack/etc. | Open (OQ-023) |
| Voice | TBD (PD-05) | Inbound/callback AI voice | Provider API + signed webhooks | Research; blocked on legal (OQ-009, OQ-041) |
| Chat hosting | `workspace-app` public route | Tenant-branded chat | HTTPS + session token | Proposed (M2) |

No provider in this section is selected or approved.
