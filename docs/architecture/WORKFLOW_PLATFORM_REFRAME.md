# Slidein: Workflow Deployment Platform — Architecture Report

> **2026-10-26 supersession notice:** This is a useful historical audit, not the active architecture. Canonical convergence decisions are now in `../decisions/ADR-2026-10-26-canonical-product-convergence.md`, `CANONICAL_ARCHITECTURE.md`, and `../product/PRODUCT_SPECIFICATION.md`. Booking provider and first-workflow questions described as pending here have since been resolved; current implementation gaps are tracked in `../project/CURRENT_STATE.md`.

Date: 2026-10-16. Status: historical audit; superseded as active guidance.
Companion code: `slidein-api/slidein_api/blueprints/`, `integrations/`, `deployments/`
(new files only; no migrations, no edits to in-progress work).

> DECISIONS REQUIRED BEFORE FIRST CLIENT DEPLOY (see §9–10):
> 1. Amend `saas/LICENSE` (BSL 1.1 currently prohibits managed service to third
>    parties; you are the licensor, so this is your call to make).
> 2. Select a booking provider (blocks meeting-booking stage).
> 3. Confirm the first client workflow is prospect-to-conversation (§2).

## 1. Current-state audit (verified on disk this session)

Git: parent dir is not a repo. `saas/` @ `main 53ce000` with 7 dirty files
(preserved, untouched): `docs/legal/COMPLIANCE_AND_RISK_REGISTER.md`,
`docs/project/CURRENT_STATE.md`, `slidein-api/.../routes/outreach.py`,
`slidein-api/.../models.py`, `slidein-api/.../deliverability_guard.py`,
`slidein-api/.../services/outreach.py`,
`slidein-api/tests/test_compliance_and_deliverability.py`.
`marketing-site/` @ `main c306219`, clean.

| Area | Path | Verdict |
|---|---|---|
| Workflow API (real engine) | `saas/slidein-api/` | Implemented. 8 stages in `slidein_api/contracts.py`; tenant-scoped API-key auth, one-key-one-workspace, cross-tenant 404 (`security.py`); SQLite default, Postgres-ready (`db.py`); canonical models (`models.py`, 736 lines); draft approve/revoke/send + policy gate + quarantine (`api/routes/outreach.py`); dry_run-default + SMTP transports (`services/transport.py`); profile/offers/ICPs/readiness/config-versions/branding/modules (`api/routes/config.py`); overview/activity/runs/health (`api/routes/overview.py`); contracts catalog (`api/routes/system.py`). **107 pytest green, verified this session.** |
| Client workspace UI | `saas/slidein-app/` | Implemented. Server-side BFF, API key never in browser (`lib/api/client.ts`, `operations.ts`, `actions.ts`); 13 pages incl. decision-focused overview, draft approval (`outreach/[draftId]`), conversations, discovery→personalization. This is the real client surface. |
| SaaS console | `saas/workspace-app/app/(app)/` | Mixed. ~30 routes; `dashboard/` renders `AcquisitionCommandCenter` fed by `MOCK_OPPORTUNITIES` — **mock**. `/intake` live per CURRENT_STATE. Temporal worker (`server/temporal-worker.ts`) + `mastra-server/` + `temporal/` exist but only a browse-task uses them. |
| Agents / product core | `saas/product/` | Partial. `agents/real_agents.py` has structured-mock fallbacks; `services/acquisition_engine.py` FSM exists (depth uninspected); product API roles unenforced per CURRENT_STATE. |
| Deliverability | `saas/deliverability/webhook_server.py` | Implemented, partially verified. SES/SendGrid/Postmark/Mailgun handlers + signature check present; full bodies not re-read here. |
| Marketing site | `marketing-site/app/` | Home renders `Hero` only; other sections unmounted-but-retained. Routes exist: contact, insights(+slug), portfolio, pricing, process, ai-pipeline-emas. Page bodies (except home) unconfirmed. |
| Deploy tooling | `saas/install.sh`, `docker-compose.local.yml`, `workspace-app/ecosystem.config.cjs` | Implemented. Single-host installer (v0.2.0, idempotent), local mailpit/redis compose, PM2 config. `ansible-playbook/site.yml` role unclear (uninspected). |
| Docs vs reality | `saas/docs/` | CURRENT_STATE capability matrix (#1–#37) matches spot checks. Live-VPS claims (`169.58.206.20`, api/workspace hosts) **not reachable from here — unverified**. |

Not implemented (confirmed): billing/entitlements, IMAP inbound (replies go
nowhere), rehearsed backup/restore, monitoring alert routes, booking provider.
Hardcoded business logic: `services/booking.py` pins Notion provider + $350/mo
fixed price — must become per-client config, not platform code.

## 2. Product reframing (plain language)

Slidein is a **workflow deployment platform**: we configure an AI workflow
for a client's business, connect it to tools they already use, give them
approval controls, and operate it reliably. We sell **one deployable
workflow at a time**, not dashboards. The reusable unit is
client discovery → workflow definition → configuration → validation →
deployment → operation. No new dashboard widgets; no per-client app forks;
industry logic lives in configuration and versioned workflow modules.

First workflow: **prospect-to-conversation** (discover → research →
qualify → personalize → approve → send → converse). It is the only
workflow the code can deliver today, end to end, tested.

## 3. Recommended deployment model: B now, A later, C on demand

Default: **Model B — Slidein-managed dedicated environment** (one
single-host install per client, reusing the proven `install.sh` +
Caddy + systemd/PM2 pattern, SQLite or small Postgres, per-client
secrets, backup, domain).

Why not shared (A) today: the stack is single-tenant-shaped — SQLite
default, no Alembic migrations, unenforced roles in the product API, no
billing/entitlements, no per-tenant caps or proven per-tenant quarantine
scoping. Sharing tenants now would be unsafe, and a dedicated VPS is not
automatically more secure — it only isolates blast radius while adding
per-host upgrade, backup, monitoring, and access duties (checklist in §10).

Trade-off summary: B gives real isolation, simple per-client cancel
(archive host + data export + key revocation), and fast onboarding from a
known-good image, at the cost of N hosts to patch/monitor/back up.
Use C (client-owned) only when a client mandates data residency or
prefers self-hosting — note the current BSL grant already fits C best.
Move to A only after: Postgres + migrations, enforced tenancy everywhere,
per-tenant caps + quarantine, billing/entitlements, and tenant-scoped
observability all exist and are tested.

## 4. Core domain model (keep slidein-api names)

Existing (do not duplicate): `workspace` (= tenant = one client
deployment), `business_profile`, `offer`, `icp`, `prospect`,
`evidence_item`, `qualification`, `message_draft` (+versions, approval
states), `sent_message`, `delivery_event`, `suppression_record`,
`conversation`, `stage_run`, `activity_log`, `config_version`.
Terminology for humans: client, workflow, deployment, connection, run,
approval, inbox. Retire `product/` "opportunity" wording for v1.

New (foundation implements the code side without DB changes):
`WorkflowBlueprint` (versioned definition: stages, I/O contracts,
required/optional/integration-dependent config, approval gates,
retry/timeout, monitoring needs), `Deployment` (installed instance:
client, blueprint version, validated config, connection refs,
environment, status, history), `IntegrationConnection`
(adapter + secret reference + health). See `blueprints/`,
`deployments/`, `integrations/` in `slidein-api`.

## 5. Client onboarding flow (minimum to deploy workflow v1)

Core (always): business profile, offer(s), ICP(s), sending identity +
physical address + lawful basis (legal gate already enforced),
approval policy (who approves, SLA), volume/latency/budget, success
metric. Workflow-specific: prospect sources, qualification criteria +
exclusions, voice/examples, never-violate rules, booking URL,
failure/escalation path. Integration-dependent: SMTP credentials,
enrichment keys, calendar/CRM access — each with least-privilege scopes
documented. Unknown/unsupported (e.g. voice outbound, IMAP-dependent
auto-reply): recorded explicitly, never silently accepted.
Nothing deploys unless readiness passes: the existing
`GET /readiness` gate is extended by blueprint validation
(`blueprints.validate_deployment_config`), never bypassed.

## 6. Client interface strategy (first workflow only)

Derived from actual inputs/outputs/approvals — all already exist in
`slidein-app`: (1) **approval inbox** (`outreach`, `outreach/[draftId]`)
— the core client control; (2) **status page** (`overview`: what needs a
decision); (3) **results tables** (discovery, conversations, activity);
(4) **configuration forms** (profile/offers/ICPs). No new surfaces for
v1. Later, meet clients where they work: replies stay in their mailbox,
meetings in their calendar, summaries via email — CRM/calendar as primary
surface where it fits. Never render a generic dashboard because the user
"is a tenant".

## 7. Internal control-plane strategy (founder ops)

Answer, per deployment: client, workflow + version, environment + model
(B/A/C), connection health (connected/expired/failing), system health,
failed runs + required intervention, operating cost, lifecycle state,
next action (mine vs client's). Sources already exist:
`overview` (attention/runs/failed), `runs` + `activity` trails,
`/health` + `/contracts`, deliverability/quarantine endpoints; the new
`deployments/lifecycle.py` adds explicit states and transitions
(planned → awaiting_client → ready → deploying → active ⇄
degraded/paused/updating → retiring → archived — use only states with
real behavior behind them). Hard rule: one client's credentials, data,
logs, and config are never visible to another; deployment records show
which isolation model actually applies. Screens come later; entities,
lifecycle, and permissions first.

## 8. Tool research (adopt nothing for MVP)

Verified from primary sources this session: Temporal server MIT
(`temporalio/temporal` LICENSE, fetched 2026-10-16); Cal.com root MIT
(`calcom/cal.com` LICENSE, fetched 2026-10-16 — `ee/` commercial terms
must be checked before using paid features). Temporal's Python SDK +
server are the later answer for durable converse/follow-up timers and
approval-resume; the repo already vendors the worker pattern. Cal.com is
the leading booking-provider candidate (UI + API + webhooks) pending the
§9 decision. Agent-reported but not independently corroborated here —
re-verify from primary sources before any adoption: Mastra, Langfuse,
Infisical, CopilotKit, Gmail API client licenses and tenant-isolation
claims. Everything else the MVP needs (adapters, readiness, dry-run
transport, StageRunner retries, approval gates) is cheaper and safer as
the small internal abstractions now in `slidein-api`.

## 9. Security and operational risks

1. **License blocks the business model.** `saas/LICENSE` (BSL 1.1)
   prohibits offering the work as hosted/managed service to third
   parties. You are the licensor — amend it (e.g. add a managed-service
   exception for Slidein-operated deployments) before onboarding a
   paying client. Without this, every deployment model except pure
   client self-hosting needs a legal decision first.
2. **Tenancy is API-key-shaped, not SaaS-shaped.** `slidein-api`
   scoping is sound (server-side context, cross-tenant 404, role
   gates); but `SLIDEIN_AUTH_MODE=disabled` must never reach
   production, product-API roles are unenforced, and per-tenant
   breaker/quarantine scoping needs code-level confirmation before any
   shared tenancy. Background jobs must carry tenant context explicitly.
3. **Deterministic enforcement stays in code.** Suppression, sending
   limits, approval gates, quarantine, legal footer/basis checks are
   application-level today — keep them there; never delegate to prompts.
   Treat connected documents/mail/sites as untrusted input (injection).
4. **Secrets discipline.** Env/root-only files today; never in code,
   bundles, logs, or config exports. Client offboarding = revoke keys,
   export data, verify deletion, archive host (runbook in §10).
5. **Unverified ops claims.** Live-VPS health, backup/restore,
   monitoring alert routes, ESP webhook bodies, Go mail-queue scoping,
   and any "BookingAgent fabricates link"-class agent behavior need
   direct verification before being trusted in production.

## 10. MVP milestones (prove the 10 capabilities, in order)

M1 Foundation (done): blueprint registry + prospect-to-conversation v1
definition + config validator; adapter interfaces + dry-run;
deployment lifecycle states/transitions; tests green; this report.
Accept: `pytest` green incl. new `test_blueprints_and_deployments.py`.
M2 License + booking decisions recorded; `booking.py` hardcoded
price/provider moved to per-client config (tests updated).
Accept: no price/provider literals in platform code; decision doc merged.
M3 Onboarding path: profile/offer/ICP + sending-identity forms drive
`readiness` + blueprint validation; unsupported requirements blocked
with reasons. Accept: incomplete config cannot reach `ready`.
M4 Connections: SMTP + enrichment + calendar connected via adapters
with secret refs + health checks. Accept: connect/fail/disconnect shown
per deployment; secrets never in logs/exports.
M5 Deploy: second workspace from the same blueprint without code
changes (B-model host or local second instance). Accept: two tenants,
isolated data, cross-tenant 404 probed.
M6 Operate: run pipeline, approve dispatch in client inbox, observe
runs/activity, pause/update/retire one deployment. Accept: full
lifecycle exercised on the second tenant, then archived with data
export + key revocation.
Per-host ops checklist (B model): image version pinned, automatic
security updates, Caddy/TLS, systemd+PM2 supervision, health checks,
daily backup + quarterly restore rehearsal, log retention policy,
break-glass access without client root/SSH by default.
