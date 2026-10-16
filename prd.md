# SlideIn — Product Requirements Document (PRD)

> **Authority note (2026-10-16):** This root file is a high-level summary created before the engagement capability was documented.
> Where it differs from `docs/` (canonical layout, ADR-0002), **`docs/` prevails**. Figures marked as targets here (placement %, latency, price/cost,
> thresholds) are **proposals, not confirmed requirements**. Prospect Engagement (reply → chat/voice → meeting booking):
> `docs/product/PROSPECT_ENGAGEMENT.md`.


> **Version:** 1.0.0  
> **Status:** Draft summary (not an approved baseline)  
> **North Star:** *"Find the right people. Understand their business. Reach out personally. Start more conversations."*  
> **Owner:** Nasrullah Tanim  

---

## 1. Executive Summary & Vision

SlideIn is an agentic, end-to-end outbound acquisition operating system. It merges six previously fragmented software categories into a single, cohesive engine:
1. **Prospect Discovery** (ICP search, domain scraping, contact extraction)
2. **Deep Business Intelligence** (company dossier generation, recent news, pain point synthesis)
3. **Hyper-Personalized Outreach** (1:1 peer-tone copy, sequence automation)
4. **Autonomous Email Deliverability Infrastructure** (KumoMTA, GoPhish, Warmbly, Reacher)
5. **Radar & Conversation Inbox** (real-time sentiment tracking, reply classification, meeting extraction)
6. **Client Command Hub** (customized, tenant-isolated executive dashboards)

Existing market tools (Apollo, Clay, Instantly, Smartlead, GlockApps) force operators to stitch together fragile CSV exports, third-party APIs, and disconnected MTA services. SlideIn eliminates this friction by operating as a unified system where discovery directly feeds intelligence, intelligence crafts personalized copy, and dedicated MTA infrastructure guarantees primary inbox placement.

---

## 2. Core User Personas & Commercial Model

### 2.1 Personas
- **The Agency Client / SaaS Subscriber ($350/mo Tier):**
  - Needs a high-leverage outbound engine running autonomously on dedicated infrastructure.
  - Requires clean, client-facing command views tailored to their business niche (e.g. B2B SaaS, Real Estate, Agency Services, Technical Consulting).
  - Demands strict confidentiality: their prospect lists, proprietary pitches, and client data must never leak to other tenants.
- **The Growth Operator / Campaign Manager:**
  - Configures ICP parameters, sets daily send caps, reviews AI-generated dossiers, and refines messaging angles.
  - Monitors deliverability health (SPF/DKIM/DMARC status, bounce rates, spam flags).
- **The System Administrator:**
  - Manages the underlying VPS infrastructure (`169.58.206.20`), KumoMTA mail routing, Warmbly warmup clusters, and Reacher validation engines.

### 2.2 Commercial Tiering & Multi-Tenant Mandate
- **Subscription Baseline:** $350/month per tenant.
- **Infrastructure Cost Target:** ~$150/month per tenant (VPS compute, dedicated IP warmup, mail routing, LLM tokens).
- **Multi-Tenant Invariant:** Every customer has an isolated workspace, isolated semantic vector store, and distinct outbound identity. Under no circumstance may one tenant's proprietary positioning, prospect list, or customer responses bleed into another tenant's workspace.

---

## 3. Product Architecture & Core Pipeline

SlideIn operates as a continuous acquisition pipeline:

$$\text{DISCOVER} \longrightarrow \text{ENRICH} \longrightarrow \text{VERIFY} \longrightarrow \text{PERSONALIZE} \longrightarrow \text{DISPATCH} \longrightarrow \text{RADAR} \longrightarrow \text{LEARN}$$

```
+---------------------------------------------------------------------------------+
|                                SLIDEIN ENGINE                                   |
+---------------------------------------------------------------------------------+
| [1. DISCOVERY]    Find ideal targets matching tenant ICP (Domain/Role/Region)   |
|         v                                                                       |
| [2. INTELLIGENCE] Build prospect dossier: company pain points, news, tech stack |
|         v                                                                       |
| [3. VERIFICATION] Reacher engine (:8090) validates MX, mailbox, disposable      |
|         v                                                                       |
| [4. PERSONALIZER] 1:1 peer copy generation (plain-text, zero commercial spam)   |
|         v                                                                       |
| [5. DISPATCH]     KumoMTA (:2587) + DKIM sign + IP rate limits + circuit break  |
|         v                                                                       |
| [6. RADAR & INBOX]Live reply webhook -> sentiment analysis -> meeting booking   |
|         v                                                                       |
| [7. HEURISTICS]   Platform learning: optimize send times & lengths (No PII)    |
+---------------------------------------------------------------------------------+
```

---

## 4. Functional Requirements by Module

### 4.1 Module 1: Prospect Discovery Engine
- **ICP Query Builder:** Tenants define target industries, employee counts, geographic boundaries, job titles, and technology usage.
- **Multi-Source Scraping:** Discovers target domains, leadership contacts, and business profiles.
- **De-duplication:** Automatically checks new leads against existing contacts, global suppression lists, and past campaign runs.

### 4.2 Module 2: Intelligence & Enrichment Dossier
- **Company Synthesis:** Gathers company mission, recent press releases, product updates, and key executives.
- **Pain Point & Value Mapping:** Connects the prospect's real business situation directly with the tenant's offering.
- **Evidence Citations:** Every assertion in the dossier links to a verified source URL.

### 4.3 Module 3: Verification & Deliverability Shield
- **Reacher Validation:** Direct SMTP handshake verification before any message enters the send queue.
- **State Filtering:** Automatically isolates `safe`, `risky` (catch-all), and `invalid` addresses.
- **Mail Authentication Assurance:** Verifies SPF, DKIM, and DMARC alignment across all sending domains (`nasrullahtanim.me`, `tanim.social`, `tanim.tech`).
- **Autonomous Circuit Breaker:**
  - Auto-pauses outbound dispatch if bounce rate exceeds **3.0%** over any 100-email rolling window.
  - Auto-pauses outbound dispatch if spam complaint rate exceeds **0.05%**.
  - Sends immediate high-priority alerts to the Command Hub.

### 4.4 Module 4: Sequence & Personalization Studio
- **1:1 Peer-to-Peer Tone:** Drafts emails that read as genuine human-to-human correspondence.
- **Primary Inbox Design:**
  - Plain-text format by default.
  - No bloated HTML wrappers, commercial tracking pixels, or high-risk marketing words.
  - Clean links only when contextually relevant.
- **Angle Variations:** Generates distinct strategic angles (e.g. pain-point trigger, observation-based, mutual connection, case study reference).

### 4.5 Module 5: Radar & Live Telemetry
- **Unified Conversation Stream:** Centralizes inbound replies across all mailboxes.
- **Sentiment & Intent Classification:** AI categorizes responses into `Interested / Meeting Request`, `Objection / Info Request`, `Not Interested`, or `Out of Office`.
- **Real-Time Notification:** Immediate alerts for high-intent responses.

### 4.6 Module 6: SaaS Command Hub (`workspace-app`)
- **Executive Overview:** Real-time metrics on prospects discovered, dossiers generated, emails dispatched, open/reply rates, and booked calls.
- **Brand System Parity:** 100% aligned with the SlideIn Venture design system (warm paper tones, OKLCH color spaces, blueprint aesthetics, zero generic SaaS tropes).
- **Client Preference Customization:** Dashboards display tenant-specific metrics, customized ICP profiles, and personalized campaign levers.

---

## 5. Non-Functional Requirements

### 5.1 Deliverability & Infrastructure
- **Placement Target:** >90% Primary Inbox placement on major providers (Google Workspace, Microsoft 365).
- **Transport Reliability:** 99.9% uptime on MTA engine (`169.58.206.20`).
- **Rate Limiting:** Provider-specific pacing strictly enforced in KumoMTA policy.

### 5.2 Performance & Responsiveness
- **API Latency:** p95 latency < 300ms for all standard dashboard queries.
- **Real-Time Updates:** SSE (Server-Sent Events) dispatch latency < 500ms from MTA event to dashboard update.
- **Frontend Load:** Initial dashboard paint < 1.2s.

### 5.3 Privacy & Data Governance
- **Strict Row-Level Isolation:** Every database entity strictly bound to `tenant_id`.
- **Zero Cross-Tenant Leakage:** An LLM working for Tenant A can never access Tenant B's dossiers, emails, or strategy preferences.
- **Compliance:** Full compliance with CAN-SPAM, GDPR, and CASL regulations.

---

## 6. Success Metrics & KPIs

| Metric | Target | Verification Method |
|---|---|---|
| Primary Inbox Placement | $\ge 90\%$ | Seed testing & real-inbox placement probes |
| Hard Bounce Rate | $< 2\%$ | Reacher pre-send verification + KumoMTA bounce logs |
| Positive Reply Rate | $> 8\%$ | Inbound Radar intent classifier |
| Dashboard Responsiveness | $< 1.2\text{s}$ | Playwright performance tests & Web Vitals |
| Tenant Isolation Breach | **0 incidents** | Automated boundary & multi-tenant regression test suite |

---

## 7. Prospect Engagement, Conversational Agents & Meeting Booking (PROPOSED)

Extended workflow: discovery → outreach → engagement → AI-assisted conversation → qualification → meeting booking → client handoff.
Requirements `ENG-REQ-*`, flows `FL-*`, MVP candidate M1 (Reply-to-Meeting Loop), sources and status labels:
`docs/product/PROSPECT_ENGAGEMENT.md`. Not approved scope; open questions in `docs/project/OPEN_QUESTIONS.md`.
