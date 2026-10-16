# Integration Research: Candidate Matrix + Shortlist

Evidence date: 2026-10-16. Sources: official repos, license files, official
docs/pricing as reached via web search this session. Anything marked
**legal-review** needs a qualified lawyer before hosted paid use — license
notes below are engineering flags, not legal conclusions.

## Comparison matrix

| Product / category | Repo + docs | License + commercial restriction | Relevant function | API quality | White-label? | Tenant isolation | Fits Next.js + FastAPI SaaS? | Behind own UI? | Hosting burden | Effort | Costs | Security/privacy | Lock-in | Verdict | Reason + evidence |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Refine (admin framework) | [refinedev/refine](https://github.com/refinedev/refine), [docs](https://refine.dev/docs) | MIT core (verify LICENSE file at pin time). Commercial cloud/EE extras optional | Tables, filters, CRUD, auth providers, data providers | Good (REST/GraphQL providers) | Yes — headless UI, own components | App-level (we build it) | Yes, React lib | Yes | None (library) | Small | Free core | Low — own code | Low | **Adopt for operator/internal UI only** | MIT library, no separate product UI. But it generates admin-style CRUD, not a polished client product — use for platform-admin, not the client workspace. |
| react-admin (admin framework) | [marmelab/react-admin](https://github.com/marmelab/react-admin), [docs](https://marmelab.com/react-admin) | MIT core, free even commercially; Enterprise Edition commercial (marmelab) | Same class as Refine, Material-UI opinionated | Good (data providers) | Partial — Material look is distinctive | App-level | Yes | Yes | None (library) | Small | Free core / EE paid | Low | Low | **Revisit** | MIT like Refine but less flexible theming; pick one (Refine) if an admin lib is needed at all. |
| Twenty (CRM) | [twentyhq/twenty](https://github.com/twentyhq/twenty), [docs](https://twenty.com/developers) | **AGPL-3.0 core** + commercial EE files; self-host free, Pro $9/user/mo, Org $19, Enterprise from $50k/yr | Custom objects/fields, pipelines, activities, views, GraphQL API | Good (GraphQL, metadata-driven) | **No for proprietary hosting** — AGPL network use obligates source availability to users | Single-tenant-oriented; multi-tenancy is DIY | Separate NestJS/Next.js app — heavy | Its UI is the product | High (second stack to run) | Large | Ops + likely Enterprise for our use | High — second data store with PII | High | **Reject for embedded use; legal-review if headless** | AGPL + separate branded app = unacceptable UX + license risk for paid white-label. Our `prospects/evidence/conversations/activity` core already covers MVP CRM needs. |
| n8n (automation) | [n8n-io/n8n](https://github.com/n8n-io/n8n), [docs](https://docs.n8n.io) | **Sustainable Use License 1.0** (fair-code, not OSI open source). Free for internal business use; hosting client workflows for a fee, embedding, white-label, or dynamic customer credentials **require Enterprise/Embed license** | 400+ integrations, visual flows, executions API | Good | Only with paid Embed license | Workspaces/EE features gated | Sidecar via API/webhook | Results yes; editor no | Medium (self-host) | Medium | Self-host free-internal / Enterprise+Embed custom pricing | Medium — credentials store holds client secrets | High | **Reject free tier for client workflows; revisit paid Embed** | Our exact use (operate client workflows, paid product) is the prohibited zone without a commercial deal. |
| Windmill (automation) | [windmill-labs/windmill](https://github.com/windmill-labs/windmill), [docs](https://www.windmill.dev/docs) | **AGPL-3.0 CE**; internal-org or as-is API use needs no commercial license; embedding/offering as a service needs one | Code-first flows (Python/TS), schedules, approvals, secrets | Good | Only with commercial license | Workspaces; EE adds SSO/audit depth | Sidecar via API | Results yes; editor no | Medium | Medium | CE free-internal / EE paid | Medium | Medium | **Prototype as private internal orchestrator only** | Clearer than n8n for internal use, but client-facing or embedded use still needs a deal. MVP does not need it — FastAPI service + queue suffices. |
| Temporal (durable workflows) | [temporalio/temporal](https://github.com/temporalio/temporal), [docs](https://docs.temporal.io) | MIT (server + SDKs); Temporal Cloud paid SaaS optional | Durable execution, retries, timers, signals, versioning | Excellent (Python/TS SDKs) | Yes — headless infra, never user-visible | Namespaces + task queues (verify secret/log posture in docs deep-dive) | Yes, sidecar service | Yes | Medium (own cluster or Cloud) | Medium | Self-host ops / Cloud usage | Low-Medium | Medium | **Prototype when scheduling/durability outgrows a queue** | Only truly permissive durable engine on the list. Defer until MVP proves the need; start with APScheduler/RQ in slidein-api. |
| Inngest / Trigger.dev (dev-centric jobs) | [inngest/inngest](https://github.com/inngest/inngest), [triggerdotdev/trigger.dev](https://github.com/triggerdotdev/trigger.dev) | Source-available + commercial SaaS; self-host options limited; **verify current pricing + EE-gated isolation/SSO/audit** | Event-driven background jobs, retries, cron, step functions | Excellent | Yes (headless) | Project/env-level; per-tenant is DIY | Yes | Yes | Low (SaaS) | Small | Usage-based SaaS | Medium — tenant data flows through vendor | Medium | **Prototype (one of them) for MVP jobs if queue DIY feels heavy** | Fastest path to reliable retries/schedules; confirm DPA + tenant-story before client data flows. |
| LangGraph (agent orchestration) | [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph), [docs](https://langchain-ai.github.io/langgraph) | **MIT**, actively maintained | Stateful graphs, checkpointing, interrupts/approvals, multi-model, structured output | Good (Python first, JS port) | Yes (library) | App-level (we scope checkpointer by tenant) | Yes (Python side, matches slidein-api) | Yes | Low (library; LangSmith tracing optional SaaS) | Small-Medium | Free core; LangSmith Plus ~$39/seat/mo + usage units | Low core; tracing vendor sees prompts if enabled | Low | **Adopt as the single agent framework — when agents are justified** | MIT + Python + checkpoint/approval primitives fit slidein-api. But: MVP needs zero agents (deterministic services suffice). Adopt on first real agent use-case (reply classification/drafting), not before. |
| OpenAI Agents SDK | [openai/openai-agents-python](https://github.com/openai/openai-agents-python) | MIT | Lightweight tool-calling agents, handoffs | Good | Yes | App-level | Yes | Yes | Low | Small | API usage | Medium — prompts to OpenAI | Medium (model) | **Revisit** | Fine SDK but single-vendor gravity + fewer state/approval primitives than LangGraph for our pipeline. |
| CrewAI / LlamaIndex Workflows | [crewaiinc/crewAI](https://github.com/crewaiinc/crewAI), [run-llama/llama_index](https://github.com/run-llama/llama_index) | MIT | Multi-agent roles (CrewAI); workflow layer over retrieval (LlamaIndex) | OK | Yes | App-level | Yes | Yes | Low | Small-Medium | API usage | Medium | Low | **Reject for now** | Role-playing crews solve a problem we do not have; LlamaIndex matters only when document-RAG becomes a requirement. One framework max. |
| Prospect data APIs (Apollo, PDL, etc.) | Vendor docs/ToS (Apollo.io, People Data Labs, Clearbit successors) | Commercial ToS; **cache-days + redistribution + AI-training wording must be fetched per vendor — ToS pages truncated this session** | Discovery, enrichment, verification | Varies | Yes (headless) | N/A (we store results per tenant) | Yes via adapter | Yes | None | Small per vendor | Per-record/credit pricing | High — PII provenance, consent, suppression, deletion | Medium | **Prototype one vendor behind the Discovery adapter** | Manual CSV ingest works for MVP; add one paid API only with a paying pilot + DPA + verified storage rights. Never scrape. |
| Sending: client-owned + ESP (SES/Postmark/Resend) | Vendor docs | Commercial SaaS | Deliverability, bounces/complaints webhooks, suppression | Excellent | Yes (headless) | Per-client accounts/domains | Yes | Yes | Low | Small-Medium | Usage-based | Medium — vendor handles mail; we enforce suppression | Low (adapter) | **Adopt pattern: client-owned sending identity + reputable ESP** | Safer and faster than a shared self-hosted mail stack for a paid multi-client product. Keep KumoMTA lab for learning, not for client mail. |
| Sending: listmonk/Postal/KumoMTA/Mailcow (self-host) | Various (verify each LICENSE at pin time) | Mostly permissive/AGPL-mixed — verify per tool | Campaigns, MTA, warmup | Varies | Partial | DIY, risky shared-IP | Sidecar | Partial | **High** (IP reputation is a full-time job) | Large | Ops + IPs | High — shared reputation across clients | Medium | **Reject for client mail at launch** | Newsletter tools ≠ multi-client sales outreach. One bad client burns every client's deliverability. |
| Cal.com (scheduling) | [calcom/cal.com](https://github.com/calcom/cal.com), [platform docs](https://cal.com/platform) | **AGPLv3 "Singleplayer APIs"** open; **"Multiplayer APIs" commercial**; white-label = paid Platform product | Availability, booking, reschedule, reminders, embeds | Good | Only via paid Platform | Platform handles per-client | Yes via API/embed | Yes (Platform) | Low (SaaS) / High (self-host AGPL) | Small-Medium | Platform usage pricing (verify live rate) | Medium — booking data via vendor | Medium | **Prototype via paid Cal.com Platform for first pilot needing booking** | AGPL self-host is the wrong vehicle for white-label booking; pay for Platform or defer booking to phase 2. |
| Voice (Vapi/Retell/etc.) | Vendor docs | Commercial SaaS; EU-hosting gaps reported — verify | AI voice calls | Good | Partial (vendor app surface) | Vendor | Via API | Partial | Low | Medium | Usage-based | High — recording, consent, PII | High | **Defer — separately scoped, risk-reviewed phase** | Not MVP. Consent/recording/compliance review required first. |

## Shortlist (do now / do next)

1. **Adopt now (no new dependency): deterministic slidein-api services** —
   discovery/research/qualification/personalization/outreach already cover
   the MVP workflow. No framework needed.
2. **Adopt pattern: client-owned sending identity + ESP adapter**
   (SES/Postmark/Resend — pick one with the first pilot).
3. **Adopt for platform-admin only: Refine (MIT)** if hand-rolled admin
   pages become expensive. Never the client UI.
4. **Prototype next: LangGraph (MIT)** for the first justified agent step
   (reply classification / draft assist), behind the existing approval gates.
5. **Prototype next: Temporal (MIT)** or Inngest/Trigger.dev when durable
   scheduling outgrows in-API jobs.
6. **Prototype with paying pilot: one prospect-data vendor + Cal.com
   Platform (paid)** — only with signed DPA/terms and verified storage rights.

## Rejected (with reason)

- **Twenty embedded/white-labeled**: AGPL + separate branded app; our own
  prospect/conversation/activity core suffices.
- **n8n free self-host for client workflows**: SUL prohibits exactly our use
  (paid managed client automation) without Enterprise/Embed.
- **Shared self-hosted mail stack for client mail**: reputation blast radius.
- **Multiple agent frameworks / CrewAI now**: no justified use-case.
- **Scrapers / free datasets**: provenance, ToS, and privacy risk.
- **Voice in MVP**: consent + compliance scope, not silently included.

## Legal-review queue (do not proceed without counsel)

- Any AGPL component (Twenty, Windmill CE, Cal.com CE) near the paid product.
- n8n SUL interpretation for "operate client workflows via own UI".
- Prospect-vendor ToS: storage, caching, redistribution, AI-use rights.
- Industry-specific obligations (mortgage/finance/fitness data handling).
