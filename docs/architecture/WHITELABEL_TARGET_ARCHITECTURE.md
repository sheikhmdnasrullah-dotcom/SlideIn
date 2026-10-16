# Target Architecture: Configurable White-Label Multi-Tenant Platform

Date: 2026-10-16. Builds on `WHITELABEL_BASELINE_AUDIT.md` and
`INTEGRATION_RESEARCH.md`. Reuses existing structures; every new concept
names the smallest viable version.

## Principle: one product, tenant-scoped configuration

No per-industry forks. Shared core + `tenants` row configuration +
versioned industry templates + paid custom work at the boundary.

```
                    ┌─────────────────────────────────┐
                    │  slidein-app (client workspace)  │
                    │  tenant theme · nav · modules    │
                    └───────────────┬─────────────────┘
                                    │ BFF (tenant key)
                    ┌───────────────▼─────────────────┐
                    │  slidein-api (FastAPI :8100)     │
                    │  tenants · profiles · pipeline   │
                    │  outreach gates · conversations  │
                    │  branding · modules · templates  │  ◄── NEW (this plan)
                    └───┬─────────┬─────────┬─────────┘
                        │         │         │
              ┌─────────▼──┐ ┌────▼────┐ ┌──▼──────────┐
              │ ESP adapter │ │ Jobs    │ │ Go sender   │
              │ (SES/etc,   │ │ (in-API │ │ sidecar     │
              │ per-client  │ │ →Temporal│ │ (tenant     │
              │ identity)   │ │ later)  │ │ wrapper)    │
              └─────────────┘ └─────────┘ └─────────────┘
```

workspace-app stays the **operator console** (Supabase + Gophish). It is
never the client product. Platform-admin screens for tenants/branding live
in slidein-api + a small admin UI (Refine if hand-rolled gets expensive).

## 1. Shared platform core (exists — keep generic)

Existing tables stay the core primitives: `tenants`, `business_profiles`,
`offers`, `icp_definitions`, `prospects`, `evidence_items`,
`qualification_results`, `offer_matches`, `message_drafts`,
`draft_versions`, `sent_messages`, `delivery_events`,
`suppression_records`, `conversations`, `inbound_replies`, `stage_runs`,
`activity_logs`, `config_versions`.

Rules: permissions, billing hooks, opt-outs, suppression, sending limits,
scheduling constraints are **ordinary code** in services + `runtime.py`
contracts. Agents never enforce hard rules.

## 2. Tenant configuration and branding (extend `tenants.settings`)

Smallest viable version — validated sections inside the existing
`Tenant.settings` JSON (no new tables until proven):

- `branding`: `{ business_name, logo_url (https, allowlisted host),
  colors: { primary, surface, ink } (hex-validated), favicon_url?,
  email_from_name?, custom_domain? (verified only) }`
- `modules`: `{ enabled: ["discovery", "outreach", ...], nav_order: [...] }`
- `terminology`: `{ prospect: "borrower", ... }` (per-tenant labels)
- `template`: `{ id: "mortgage-v1", version: 3, applied_at }`
- `sending`: `{ transport: "esp:<name>", from_domain (verified),
  daily_cap, per_prospect_cap }` — merged with existing sending policy.
- `ai`: `{ enabled_use_cases: [], require_approval: true, model_policy }`

Requirements: tenant-scoped reads/writes through existing auth
(`resolve_workspace` + `require_role`), server-side validation, activity
log on every change, fallback theme when incomplete, preview mode for
admins (render with candidate branding without persisting).

## 3. Industry / workspace templates (new, small)

New concept, minimal shape — a versioned JSON document (stored in DB or
repo-pinned file in phase 1):

```
template { id, version, label, modules[], nav[], terminology{},
           pipeline_stages[], custom_fields[], forms[], task_types[],
           workflow_recipes[], dashboard_widgets[], ai_use_cases[],
           required_integrations[], role_defaults{} }
```

- Applying a template = additive merge, never destructive; existing tenant
  data/config wins on conflict; every apply writes a `config_version` row.
- Phase 1: one template only (the pilot vertical). Template engine earns
  generality after two real tenants.

## 4. Module system

Static registry in code (phase 1), e.g. `MODULES = { discovery, research,
qualification, personalization, outreach, inbox, tasks, calendar,
assistant, knowledge, reports, integrations, settings }`, each with:
`id, label, required_role, required_integrations[], api_prefixes[]`.

- UI reads `modules.enabled` for nav; **API enforces per-module access
  server-side** (a `require_module` guard alongside `require_role`).
  Hidden nav is not authorization.
- Module → build/integrate/defer decision per module (see MVP plan);
  phase-1 modules are the existing services only.

## 5. External integration adapters

One adapter interface per capability, provider logic isolated:

- `SendingAdapter`: `dry_run` (exists) → `smtp` (exists) → `esp:<name>`
  (new; one ESP first). Tenant sending identity always per-client.
- `DiscoveryAdapter`: `manual_csv` (exists) → `vendor:<name>` (new, one
  vendor, paying pilot only).
- `SchedulingAdapter`: `none` → `calcom_platform` (new, paid, phase 2).
- `DataSyncAdapter` (future): CRM export/webhooks.

Each adapter: pinned version, config/upgrade/monitor/remove runbook,
sandbox testing, no secrets in code/prompts/logs, tenant auth enforced
before any provider call.

## 6. AI / workflow architecture

- **Deterministic first**: pipeline stages stay plain services. No agent
  framework until a step needs flexible interpretation.
- **First agent framework (when justified): LangGraph (MIT)** in
  slidein-api (Python-native): tenant-scoped checkpointer, interrupts for
  the existing approval gates, structured-output validation, Langfuse or
  LangSmith tracing (confirm data terms), per-workflow eval suite.
- **Jobs**: in-API scheduler now (APScheduler/RQ class); Temporal (MIT)
  or Inngest/Trigger.dev when durability/scale demands.
- **Windmill/n8n**: not in the product path. Windmill only as a private
  internal orchestrator if ever; n8n only with a paid Embed deal.
- Every AI workflow documents: trigger, tenant/user context, input
  provenance, deterministic validation, tools + permissions, structured
  output, side effects, approvals, retry/idempotency, failure + escalation,
  logs/traces/evals/latency/cost. Untrusted inputs (files, pages, emails)
  are prompt-injection surfaces — validate + sandbox.

## 7. Data and authorization boundaries

| Layer | Rule |
|---|---|
| Core platform | Generic primitives, tenant_id on every row, 404 anti-oracle |
| Tenant config | Validated JSON on `tenants`, admin/operator writes, activity-logged |
| Industry template | Versioned recipe, additive apply, never overwrites tenant data |
| Custom/paid work | Separate adapter or template fork, never core branches |
| Client UI | Renders tenant config; no Slidein branding on client surfaces |
| Platform admin | Separate surface + credentials; clients never see other tenants, logs, provider keys, or agent tools |

## 8. White-label rendering checklist (slidein-app)

Tenant name/logo/theme on: login, onboarding, workspace shell, nav,
page titles, favicon, emails (from identity + template), booking/public
pages, error pages, generated docs, public links. Metadata audit each
release. Third-party surfaces that cannot be de-branded must be disclosed,
never disguised.
