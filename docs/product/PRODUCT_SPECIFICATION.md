# SLIDEIN PRODUCT SPECIFICATION

> **Detailed Functional Specification & System Boundaries**  
> Status: Active Specification  
> Version: 1.0.0

---

## 1. System Overview

Slidein operates as a dual-workspace software platform:
1. **Internal Operator Workspace:** Fleet operations, onboarding client deployments, configuring business knowledge, verifying sending domains, monitoring job queues, tracking provider costs, and overseeing tenant health.
2. **Customer Tenant Workspace:** Day-to-day prospecting overview, review of qualified leads, inspection of research evidence, approval and editing of personalized message drafts, campaign monitoring, reply/inbox management, and deliverability status.

---

## 2. Core Modules & Functional Capabilities

### Module 1: Business Knowledge Intake & Profile
- **Business Identity:** Legal name, brand, URL, core domain, value proposition, ICP summaries.
- **Offer Registry:** Granular catalog of products/services, pain points solved, verifiable proof points, target buyer persona, and commercial constraints.
- **Evidence Vault:** Approved case studies, customer references, public metrics, verified claims. Outbound copy generation is strictly barred from making claims outside this vault.
- **Targeting & Exclusion Rules:** Industry codes, headcount, geography, negative keywords, suppressed domains, competitor blacklist.
- **Readiness Assessor:** Deterministic pre-flight audit calculating deployment readiness score ($0-100\%$) across 12 criteria (Profile, Offers, ICP, Exclusions, Sending Identity, DNS authentication, Suppression List, Approval Mode, Rate Limits, Provider Health, Webhook endpoints, Cost thresholds).

### Module 2: Prospect Discovery & Identity Resolution
- **Source Adapters:**
  - `CSV Batch Import`: Ingestion with strict deduplication, email syntax validation, and field mapping.
  - `Directory / Web Search`: Permitted search via Tavily/Search API for companies and decision-maker roles.
  - `Email Crawler`: Deep link exploration on verified domains to discover public contact points.
- **Identity Resolution & Deduplication:** Account-level domain normalization (`acme.co` $\leftrightarrow$ `acme.com`), contact-level email hashing, fuzzy company name matching with confidence scoring.

### Module 3: Research & Traceable Qualification
- **Evidence Collector:** Gathers company profile, recent signals (hiring, product launches, tech stack), executive bio, business positioning.
- **Traceability Guarantee:** Every scraped or retrieved fact is tagged with `source_url`, `timestamp`, `confidence_score` ($0.0-1.0$), and `verification_status` (`verified`, `inferred`, `unverified`).
- **Explainable Qualification Engine:** Deterministic rule evaluation against ICP hard constraints + LLM evaluation of unstructured business signals. Produces a score ($0-100$) and explicit human-readable bullet points (`Matches: ...`, `Fails: ...`, `Gaps: ...`).

### Module 4: Offer Matching & Personalized Message Generation
- **Offer Matcher:** Evaluates which specific client offer addresses the prospect's verified situation and evidence items.
- **Context-Aware Drafting:** Generates message draft (Subject line, Hook, Value proposition, CTA) strictly grounded in verified evidence.
- **Anti-Spam & Policy Validator:** Checks draft for prohibited phrases, spam triggers, missing evidence, unverifiable claims, and opt-out compliance.
- **Draft Versioning & Human Approval:** Multi-version storage (`draft_v1`, `draft_v2`, `human_edited`). Edits made by users are preserved and never overwritten by subsequent regenerations.

### Module 5: Controlled Dispatch & Deliverability Engine
- **Sending Infrastructure:** Multi-transport routing (KumoMTA port 2587, GoPhish port 8333, SMTP submission, or cloud relays).
- **Pre-Send Verification Gate:**
  1. Suppression check (global blacklist, unsubscribed recipients, complaint history).
  2. Syntax & MX verification.
  3. Domain reputation & circuit breaker state check.
  4. Quota and rate-limit evaluation (hourly, daily, per-sender, per-tenant).
  5. Human approval verification (if tenant is in `review_required` mode).
- **Delivery Event Processing:** Webhook & bounce logging for `queued`, `submitted`, `accepted`, `delivered`, `bounced` (hard/soft), `complaint`, `deferred`.

### Module 6: Conversation & Inbound Reply Management
- **Inbound Webhook & IMAP Sync:** Ingestion of recipient replies via IMAP or inbound SMTP webhook.
- **Thread Stitching:** Strict MIME header matching (`In-Reply-To`, `References`, `Message-ID`) linking replies directly to the original prospect, draft, and campaign.
- **Intent Classifier:** Categorizes incoming messages into:
  - `INTERESTED` (wants a call / demo / more information)
  - `INFORMATION_REQUEST` (has specific technical or pricing questions)
  - `OBJECTION` (timing, budget, not responsible)
  - `OUT_OF_OFFICE` (auto-responder with return date)
  - `UNSUBSCRIBE_REQUEST` (opt-out demand $\rightarrow$ immediate automated suppression)
  - `NOT_INTERESTED`
- **Follow-up Recommendation:** Suggests next action (schedule meeting, send pricing sheet, pause sequence, archive).

---

## 3. Autonomous Autonomy Levels

| Level | Name | Behavior |
|---|---|---|
| **0** | **Discovery & Research Only** | Discovers prospects and produces evidence cards. No messages drafted. |
| **1** | **Assisted / Review Required (Default)** | Discovers, researches, qualifies, and generates drafts. Requires explicit human click to approve and queue for sending. |
| **2** | **Co-Pilot / Conditional Auto** | Auto-sends drafts where qualification score $> 85$, evidence confidence $> 0.9$, and sender health is green. Flags others for review. |
| **3** | **Autonomous Operation** | Executes recurring scheduled discovery, qualification, and dispatch within strict pre-configured tenant daily sending caps and circuit breaker tripwires. |

Every tenant defaults to **Level 1** on initial onboarding. Escalation to Level 2 or 3 requires passing the Readiness Assessor.
