# ARCHITECTURAL DECISION RECORDS (ADR)

> **Authoritative Architectural Decisions for Slidein**  
> Status: Approved & Binding

---

## ADR-0001: Consolidation of `workspace-app` as the Canonical Console

- **Context:** The repository contains an operational Next.js console inside `workspace-app/` with advanced components (TanStack Table v9, TanStack Query v5, AppSidebar, Base UI, Command Menu, CopilotKit) as well as duplicate trees.
- **Decision:** Consolidate on `workspace-app` as the single operational frontend console for both internal operators and tenant users. Discard or ignore parallel forks.
- **Consequences:** Avoids duplicating frontend engineering; leverages existing high-quality design tokens, tables, filters, and persistence patterns.

---

## ADR-0002: Modular Monolith Over Premature Microservices

- **Context:** Slidein has distinct domain requirements (knowledge, discovery, research, drafting, dispatch, deliverability, conversations). Distributing these into separate microservices would introduce excessive network latency, distributed transaction complexity, and deployment overhead for a small team.
- **Decision:** Build a cohesive modular monolith with strictly isolated domain packages and clear typed contracts between modules.
- **Consequences:** Simple local development (`npm run dev`), direct database transactions where required, single Docker/VPS deployment model, easily refactored into services if scale requires.

---

## ADR-0003: Tenant Isolation Boundary

- **Context:** Multiple customer businesses will run on Slidein. Data leakage (prospects, business facts, research evidence, emails) is catastrophic.
- **Decision:** Every database table and state store must contain an explicit `tenant_id` foreign key. All backend queries, server actions, background tasks, and API route handlers must extract and validate `tenant_id` at the request boundary.
- **Consequences:** Eliminates cross-tenant data leakage. Frontends never supply unverified tenant IDs.

---

## ADR-0004: Traceable Evidence Requirement for Qualification & Outreach

- **Context:** AI generation frequently fabricates pleasantries, fake company milestones, or unverified claims.
- **Decision:** Outbound personalization is prohibited from asserting any fact about a prospect or business that does not have an associated `evidence_item` row containing a verified source URL or business knowledge citation.
- **Consequences:** Replaces generic cold email copy with authentic, defensible business introductions. Enhances deliverability and prevents reputational damage.

---

## ADR-0005: Decoupled Deliverability Engine & MTA Policy

- **Context:** Email deliverability requires specialized IP warmup, circuit breakers, rate limiting, and DKIM signing that must not be disrupted by web UI updates.
- **Decision:** Maintain `deliverability/` (Python engine on :8088) and KumoMTA (:2587) as a dedicated deliverability subsystem. The web application interacts with it via authenticated REST APIs and SMTP submission.
- **Consequences:** Ensures zero-downtime email delivery and protects live sending assets while allowing rapid frontend and business logic iteration.
