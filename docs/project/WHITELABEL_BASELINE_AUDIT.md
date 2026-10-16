# Slidein White-Label Baseline Audit

Date: 2026-10-16. Evidence from direct file inspection + test runs in this
workspace (parent `SlideinVenture/`, repos `saas/` and `marketing-site/`).
Nothing below is inferred from UI text or marketing copy alone: every
"working" claim names the implementing module.

## System map (verified)

| Surface | Path | Stack | Deploys to |
|---|---|---|---|
| Marketing site | `marketing-site/` (own git repo) | Next.js 15 | Vercel, `www.slideinventure.com` |
| Client-workspace BFF + shell | `saas/slidein-app/` | Next.js 16, React 19, Tailwind 4 | VPS (`app.slideinventure.com`) |
| Workflow API | `saas/slidein-api/` | FastAPI, SQLAlchemy async, SQLite/Postgres | VPS `:8100` |
| Operator console | `saas/workspace-app/` | Next.js (Supabase auth, Gophish client) | VPS (operator only) |
| Legacy sender | `saas/` root (Go files, `worker/`, `mailer/`, `imap/`, `webhook/`) | Go 1.13 Gophish fork, gorilla/mux, gorm | VPS |
| Mail transport lab | `saas/kumomta-lab/`, `saas/deliverability/`, `saas/warmup-engine/` | KumoMTA configs, Python scripts | VPS / local |

`saas/` git: branch `main`, 1 commit ahead of origin (`b6727ae app`), 1
untracked file (`docs/decisions/ADR-2026-10-16-foundation-hardening-plan.md`).
`marketing-site/` git: clean at `cc2a06b small`.

## 1. Working and verified

- **slidein-api test suite: 68 passed** (`saas/slidein-api/.venv/bin/pytest`,
  this session). Covers contracts, journey, permissions, engagement,
  compliance/deliverability.
- **Tenant-scoped auth** (`slidein_api/security.py`): per-workspace Bearer
  keys, roles `viewer/service/operator/admin`, constant-time verify, 404
  anti-oracle on cross-tenant access (`resolve_workspace`).
- **Tenant data model** (`slidein_api/models.py`): `tenants` (name, slug,
  plan_tier, autonomy_level, settings JSON), versioned `business_profiles`,
  `offers`, `icp_definitions`, `config_versions`; pipeline tables
  (`prospects`, `evidence_items`, `qualification_results`, `offer_matches`);
  outreach tables (`message_drafts`, `draft_versions`, `sent_messages`,
  `delivery_events`, `suppression_records`); `conversations`,
  `inbound_replies`; `stage_runs`, `activity_logs`.
- **Pipeline services**: manual ingest w/ source attribution + dedupe
  (`services/discovery.py`), HTTP research w/ verified/inferred/unverified
  labels (`services/research.py`), fixed-weight rubric qualification
  (`services/qualification.py`), deterministic evidence-backed draft assembly,
  no LLM (`services/personalization.py`), approval + suppression + policy
  gates (`services/outreach.py`), keyword reply intents
  (`services/conversations.py`), activity/suppression/bounce-quarantine
  (`services/activity.py`, `suppression.py`, `deliverability_guard.py`).
- **Transports** (`services/transport.py`): `dry_run` default (records
  lifecycle, sends nothing) + `SMTPTransport` for real dispatch through the
  tenant's identity.
- **Stage runtime** (`runtime.py`, `contracts.py`, `lifecycle.py`):
  contract-gated stage execution with permission checks, failure/needs-review
  recording, activity trail.
- **slidein-app BFF + shell**: typed API client + 1:1 operation map
  (`lib/api/`), workflow metadata derived from API contracts
  (`lib/workflow/metadata.ts`), workspace sidebar shell
  (`app/(workspace)/layout.tsx`), ~20 API route proxies.
- **Go legacy sender**: campaign poller + SMTP mailer with backoff
  (`worker/`, `mailer/`), per-user IMAP poll (`imap/`), signed webhooks
  (`webhook/`), bcrypt sessions + API keys + RBAC (`auth/`, `models/rbac.go`).
- **Marketing site builds/renders**: Next.js 15, hero + product-narrative
  pages; pricing route intentionally blank.

## 2. Partially implemented

- **slidein-app pages**: built 2026-10-16 — all 9 sections
  (overview/profile/discovery/research/qualification/personalization/
  outreach/conversations/activity) plus prospect, draft, conversation, and
  contracts routes render real BFF data with empty/error/module-disabled
  states; workflow mutations run through server actions. Not yet
  browser-verified (sandbox blocks ports; needs an unsandboxed run).
- **slidein-app front layer: repaired 2026-10-16** (was: not building).
  Fixed: `operations` import source in all 35 `app/api/**/route.ts` files,
  3 `async function delete` parse errors, `search`/`from(search)` query
  handling in 8 routes, `metadata.ts` `./types` import, undefined
  `LayoutProps`/`cn`/`ApiRequestError` names, Button `render` prop type,
  removed Next-16-invalid `eslint` key from `next.config.ts`. `tsc` is a
  reliable gate again (parse errors had suppressed all semantic
  diagnostics — demonstrated by probe, sensitivity re-verified after the
  fix). `next build --webpack` passes; Turbopack build is unproven in the
  sandbox (process-spawn restriction, not a code defect). Remaining
  pre-existing gaps: `npm run lint` is broken (`next lint` removed in
  Next 16, no eslint config); the 35 BFF `/api/*` proxies compile but are
  currently uncalled (pages use server components + server actions).
- **`SMTPTransport`**: real-send path exists but live-sending policy gates it;
  no evidence of a production send through it in this workspace.
- **Notifications/booking/scheduler** (`services/notifications.py`,
  `booking.py`, `scheduler.py`): service modules exist; scheduler/daemon
  binding to cron/systemd unverified.
- **Deliverability tooling** (`saas/deliverability/`, `warmup-engine/`,
  `reacher/`, `kumomta-lab/`, `warmbly/`, `sink-mx/`): scripts/configs
  present; linkage to the live send path unproven.
- **Monitoring**: `/health` + `models.Ping` readiness only; no APM/tracing.
- **Go tenant model**: global admin/user roles only — no teams/tenants, so the
  Go app cannot serve clients directly in multi-tenant mode.
- **Marketing pricing page**: route renders blank; metadata still claims
  "$1,999 a month" managed service (stale).

## 3. UI-only or mocked

- **workspace-app (~40 pages under `app/(app)/`)**: operator console using
  Supabase auth + direct Gophish client (`lib/gophish.ts`); **zero
  references to slidein-api** — it is a separate operator tool, not a client
  workspace, and its panels (dashboard, cold-outreach, lead-research, etc.)
  do not exercise the tenant API.
- **Marketing hero claim "finds prospects"**: Discovery is manual ingest;
  no autonomous sourcing exists. "Captures leads": no lead-capture
  endpoint in slidein-api. "Agentic system": personalization is
  deterministic templates; reply classification is keyword intents; no LLM
  agent runtime exists in the pipeline.

## 4. Missing

- Tenant branding (business name/logo/colors/domain) — `Tenant.settings`
  JSON can hold anything but has no branding schema, validation, or API.
- Module registry / per-tenant enabled modules + navigation config.
- Industry/workspace templates; custom fields; pipeline-stage config.
- Tasks, contacts/people, file upload, knowledge/documents in the new stack.
- Booking pages, chat, voice — no implementation.
- Domain/subdomain routing + verification; tenant-aware email templates.
- Scheduler binding for background outreach/warmup daemons.
- Evaluation suite + tracing for AI workflows (no AI workflows yet).

## 5. Unknown / requires investigation

- Whether `background_outreach_daemon`/warmup run on the VPS (cron/systemd).
- Whether `saas/deliverability/` legacy scripts verify SPF/DKIM/DMARC.
- Whether `product/agents/real_agents.py` provides autonomous prospecting
  (file listed, body unopened — low priority, outside new stack).
- Deployed-site parity: does `www.slideinventure.com` match this revision?
- `slidein-app` missing pages: intentional (not yet built) vs deleted.

## Constraints that shape the plan

1. The credible core is **slidein-api + slidein-app BFF**; workspace-app is
   an operator console, not the client product.
2. White-label must be built on the `tenants` row + API, not on the Go app.
3. Marketing overclaims autonomy ("finds", "agentic") — fix copy or build
   the capability before selling it.
4. No scheduler, tracing, or APM — MVP must stay small enough to operate
   without them.
