# SLIDEIN SYSTEM ARCHITECTURE

> **Full System Architecture & Technical Specifications**  
> Status: Active & Authoritative Architecture

---

## 1. High-Level Architecture Diagram

```
+---------------------------------------------------------------------------------------+
|                                     FRONTEND LAYER                                    |
|  workspace-app: Next.js 16.3.1 (App Router) | React 19.2.8 | Tailwind v4 | Base UI    |
|  - AppShell & Persistent Sidebar (AppSidebar)                                          |
|  - TanStack Table v9 (Leads, Evidence, Campaigns)                                     |
|  - TanStack Query v5 (Data Fetching & Cache Prefetching)                              |
|  - Command Menu (cmdk) & CopilotKit Runtime (/api/copilot)                            |
+---------------------------------------------------------------------------------------+
                                        | (HTTPS / REST)
+---------------------------------------------------------------------------------------+
|                                    API & DOMAIN LAYER                                 |
|  Route Handlers (workspace-app/app/api) & Product API (product/api on :8000)          |
|  - Tenant Scoping & Auth Guard (requireUser / Session)                                |
|  - Business Knowledge Service (Profile, Offers, Evidence, ICP)                        |
|  - Prospecting Service (Discovery, Dedup, Normalization)                              |
|  - Research & Qualification Service (Tavily, Deep Crawl, LLM Evaluator)               |
|  - Personalization Engine (Evidence-Grounded Copywriter, Spintax, Sanitizer)          |
|  - Campaign & Dispatch Orchestrator (Approval Gate, Rate Limiter)                     |
|  - Inbound Conversation Classifier (MIME Stitching, Intent Scoring)                   |
+---------------------------------------------------------------------------------------+
                       |                                       |
                       v (Internal HTTP / DB)                  v (SMTP submission / Webhooks)
+--------------------------------------+      +-----------------------------------------+
|            PERSISTENCE LAYER         |      |        DELIVERABILITY INFRASTRUCTURE    |
|  PostgreSQL / Supabase / Appwrite    |      |  deliverability/server.py (:8088)       |
|  - Multi-Tenant Isolated Tables      |      |  - Precheck & Scoring Gate              |
|  - Row Level Security (RLS)          |      |  - Global Suppression DB (SQLite)      |
|  - State & Event Audit Logs          |      |  - KumoMTA (:2587 SMTP / :8029 Admin)   |
|  - Research Evidence Vault           |      |  - DKIM Signer (3 domains)              |
|  - Idempotent Message Logs           |      |  - Circuit Breakers & Warmup Governor   |
+--------------------------------------+      +-----------------------------------------+
```

---

## 2. Component Responsibilities & Boundaries

### 2.1 Frontend Console (`workspace-app`)
- **Technology:** Next.js 16.3.1, React 19.2.8, TypeScript, Tailwind CSS v4, `@base-ui/react`, `@tanstack/react-table`, `@tanstack/react-query`, `lucide-react`, `framer-motion`, `sonner`.
- **Core Views:**
  - `/dashboard`: High-level operational metrics (qualified leads, drafts awaiting review, delivery health, active workflows).
  - `/leads`: Rich data table with search, sorting, filtering, batch actions, and export.
  - `/lead-research`: File/source ingestion, automated research trigger, and evidence cards.
  - `/custom-email`: Personalized message inspection, inline draft editing, deliverability scoring, and launch.
  - `/knowledge`: Structured business profiles, offer cards, ICP rule editor, and readiness score.
  - `/integrations`: Sending identities, DNS status, provider connection health.

### 2.2 API & Business Logic Layer
- **Tenant Context:** All requests must extract authenticated `tenant_id` from verified session credentials. No endpoint may query or mutate data without an explicit tenant constraint.
- **Service Segregation:**
  - `KnowledgeService`: Manages business facts, offers, ICP rules, and pre-flight readiness checks.
  - `DiscoveryService`: Orchestrates source adapters, deduplicates records, and assigns prospect lifecycle states.
  - `ResearchService`: Dispatches search and web scraping, writes structured evidence rows with source attribution.
  - `DraftingService`: Feeds evidence + offer + persona into prompting pipeline, producing versioned drafts with attribution.
  - `DispatchService`: Enforces pre-send gates (suppression, validation, approval, quota) before handing off to MTA.
  - `InboundService`: Parses MIME replies, extracts thread context, classifies recipient intent, and updates CRM status.

### 2.3 Email Infrastructure & Deliverability Layer
- **KumoMTA:** High-throughput MTA handling SMTP submission on port 2587 with authenticated routing, DKIM signing across `nasrullahtanim.me`, `tanim.tech`, and `tanim.social`, domain-specific throttling (Gmail, Yahoo, Microsoft), and bounce event hooks.
- **Deliverability Service (`deliverability/server.py` on :8088):**
  - Standalone service managing `deliverability_state.db`.
  - Maintains `suppression_records` (hard bounces, complaints, opt-outs).
  - Provides `/v1/drafts/score` for anti-spam lexical scoring before dispatch.
  - Provides `/v1/inbound/webhook` for MIME ingestion.
  - Real-time circuit breaker tracking rolling bounce and complaint rates, auto-pausing sending if threshold ($> 2.5\%$ bounce or $> 0.1\%$ complaint) is breached.

---

## 3. Communication Contracts

1. **Frontend $\leftrightarrow$ Backend:** JSON REST over HTTPS. Standard error envelope:
   ```json
   {
     "error": {
       "code": "INVALID_STATE",
       "message": "Draft cannot be approved before qualification evidence is attached",
       "details": {}
     }
   }
   ```
2. **Backend $\leftrightarrow$ MTA:** SMTP submission with AUTH credentials over TLS (`port 2587`). Custom tracking headers:
   - `X-Slidein-Tenant-ID: <tenant_id>`
   - `X-Slidein-Prospect-ID: <prospect_id>`
   - `X-Slidein-Draft-ID: <draft_id>`
   - `Message-ID: <unique_id@domain>`
3. **MTA $\leftrightarrow$ Backend:** HTTP Webhook on delivery, bounce, or deferral events for automatic reconciliation.
