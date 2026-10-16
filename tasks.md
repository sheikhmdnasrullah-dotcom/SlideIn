# SlideIn — Master Task Roadmap & Execution Backlog

> **Authority note (2026-10-16):** This root file is a high-level summary created before the engagement capability was documented.
> Where it differs from `docs/` (canonical layout, ADR-0002), **`docs/` prevails**. Figures marked as targets here (placement %, latency, price/cost,
> thresholds) are **proposals, not confirmed requirements**. Prospect Engagement (reply → chat/voice → meeting booking):
> `docs/product/PROSPECT_ENGAGEMENT.md`.


> **Version:** 1.0.0  
> **Status:** Active Execution Plan  
> **Execution Strategy:** Iterative, test-driven phases with zero downtime on live VPS  

---

## Phase 1: Design System Alignment & Token Synchronization

**Objective:** Ensure `workspace-app` 100% replicates the SlideIn Venture design system (`sv to tanim.social`) with identical OKLCH tokens, wordmark, and blueprint aesthetics.

- [x] **Task 1.1: Audit & Align OKLCH Tokens**
  - Verify `workspace-app/app/styles/tokens.css` matches exact values from SlideIn Venture.
  - Confirm hue `42.28` for all brand orange variants (`brand`, `brand-hi`, `signal`, `signal-deep`, `signal-deeper`, `ember`).
  - Confirm paper ramp (`paper-25` to `paper-200`) and ink ramp (`slate-500` to `ink-deep`).
- [x] **Task 1.2: Implement Live Text Wordmark in Console**
  - Add `.wordmark`, `.wordmark-name`, `.wordmark-qualifier` to `workspace-app/app/styles/type.css`.
  - Create `workspace-app/components/brand/logo.tsx` with `<LogoWordmark />`.
  - Replace generic "OS" placeholder in `workspace-app/components/dashboard/app-sidebar.tsx`.
- [x] **Task 1.3: Port System Blueprint Primitives**
  - Add `CornerBrackets` and `Ticks` to `workspace-app/components/system/`.
  - Ensure `MonoLabel` and `SectionRule` adhere to the semantic contract (`--muted`, `--rule`).
  - Audit all dashboard views to eliminate raw hex values, raw px sizes, and ad-hoc `dark:` classes.

---

## Phase 2: Multi-Tenant Architecture & Context Isolation

**Objective:** Implement strict 3-tier memory and row-level tenant isolation in `slidein-api` to prevent cross-tenant data contamination.

- [ ] **Task 2.1: Tenant Database Schema & RLS**
  - Add `tenant_id` column to all tables (leads, dossiers, sequences, campaigns, events).
  - Create SQLAlchemy async middleware enforcing automatic `tenant_id` filtering on all session queries.
  - Write multi-tenant boundary test suite (`test_tenant_isolation.py`) ensuring `403 Forbidden` across boundaries.
- [ ] **Task 2.2: Tenant-Scoped Vector Vault**
  - Implement partitioned namespace logic for vector similarity search (`tenant_{tenant_id}`).
  - Ensure client ICP definitions and private lead dossiers are isolated to their specific namespace.
- [ ] **Task 2.3: Platform Heuristic Aggregator (The Genome)**
  - Build differential privacy extraction pipeline to collect anonymized send-time histograms and subject line length metrics.
  - Enforce strict redaction of PII, company names, and raw email text before heuristics enter Tier 3 memory.

---

## Phase 3: Agentic Discovery & Intelligence Pipeline

**Objective:** Deliver an automated research engine that discovers prospects and compiles rich business dossiers.

- [ ] **Task 3.1: ICP Query Execution Engine**
  - Wire search operators and scraping workers to discover target company domains matching client criteria.
  - Implement contact extraction with role and seniority filters.
- [ ] **Task 3.2: Company Intelligence & Dossier Generator**
  - Build scraping worker to extract company about pages, recent news, and product documentation.
  - Implement LLM synthesis worker to extract core pain points and link them to the tenant's offering.
  - Enforce source citation tracking: every dossier fact must link to a valid source URL.
- [ ] **Task 3.3: Pre-Send Reacher Verification Integration**
  - Connect `slidein-api/services/verification.py` to Reacher engine on `127.0.0.1:8090`.
  - Mark leads as `safe`, `risky`, or `invalid`. Block invalid addresses from entering outbound queues.

---

## 4. Phase 4: Production Deliverability & Transport Binding

**Objective:** Connect the SaaS dispatch pipeline directly to the production KumoMTA mail transport.

- [ ] **Task 4.1: Authenticated SMTP Queue Worker**
  - Connect dispatch worker to KumoMTA on `127.0.0.1:2587` with SASL authentication.
  - Configure automatic DKIM signature validation for outbound messages.
- [ ] **Task 4.2: Circuit Breaker Monitoring Worker**
  - Monitor live delivery receipts and calculate rolling bounce rate over 100-email windows.
  - Implement automatic pause trigger if bounce rate $> 3\%$ or spam complaint $> 0.05\%$.
- [ ] **Task 4.3: 1:1 Plain-Text Email Formatter**
  - Implement peer-to-peer copy sanitizer that removes commercial tracking tags and forces clean plain-text delivery.

---

## 5. Phase 5: Radar & Live Telemetry Stream

**Objective:** Enable real-time reply classification, sentiment tracking, and live dashboard event streaming.

- [ ] **Task 5.1: Inbound Webhook Listener & Classifier**
  - Ingest inbound email events from KumoMTA.
  - Run sentiment analysis worker to classify replies (`Meeting Requested`, `Information Request`, `Not Interested`).
- [ ] **Task 5.2: SSE Telemetry Endpoint**
  - Create `/api/v1/telemetry/stream` in `slidein-api` emitting real-time dispatch, open, and reply events.
  - Connect dashboard UI (`workspace-app`) to SSE stream for live table updates without page reloads.

---

## 6. Phase 6: Client Command Hub & Custom Branded Views

**Objective:** Deliver customized client dashboard views reflecting individual client preferences.

- [ ] **Task 6.1: Tenant Onboarding & Profile Customization**
  - Build client settings panel allowing tenant to define ICP parameters, brand name, and sending preferences.
- [ ] **Task 6.2: Custom Client Command Views**
  - Create executive client view displaying high-level acquisition progress, booked calls, and lead dossiers.
  - Provide operator view for adjusting sequence angles and sending volumes.
- [ ] **Task 6.3: Production Build & Deployment**
  - Build production Next.js bundle (`workspace-app`) and deploy to `/var/www/workspace-app` via pm2.
  - Verify live telemetry and SSL certificates across all domains.

---

## Prospect Engagement Tasks (T-001…T-041)

Authoritative task table, dependencies, acceptance and verification: `docs/engineering/IMPLEMENTATION_ROADMAP.md` → "Phase 10 Expansion".
**Milestone 1 (M1: Reply-to-Meeting Loop) is APPROVED BY OWNER (2026-10-16)**:
- [ ] **Dual Inbound Path (T-001)**: KumoMTA dashboard webmail viewer OR Google Workspace / Microsoft 365 IMAP/OAuth sync.
- [ ] **24-Hour Business Grace Period Scheduler (T-013)**: 24 business hours (US business days only) for human rep before agent auto-replies with human-indistinguishable grounded copy.
- [ ] **Notion Booking Calendar Adapter (T-016)**: Notion Calendar primary provider with fallback sync for existing dedicated links.
- [ ] **Strict Link Policy (T-017)**: Strictly ZERO links in cold first touches; booking links only sent when prospect explicitly expresses interest.
- [ ] **Non-Negotiable Monthly Pricing (T-009)**: Agent knowledge strictly enforces fixed monthly fee ($350/mo) with zero discount or negotiation capability.
- [ ] **24/7 VPS Alert Dispatcher (T-023)**: Real-time notification worker for Telegram Bot, Discord Webhook, and Slack Webhook.
