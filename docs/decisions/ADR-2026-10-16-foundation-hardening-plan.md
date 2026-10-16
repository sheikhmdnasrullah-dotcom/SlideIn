# ADR 2026-10-16 — SaaS Foundation Hardening: Canonical Backend, Tenant Integrity, and Prioritized Plan

Status: **Proposed** (pending owner ratification of Decision 1)
Scope: `slidein-api/`, `product/`, `workspace-app/`, `marketing-site/` (cross-cutting plan)
Author: architecture review (see findings for evidence)

---

## 1. Context: what actually exists

The workspace contains **three overlapping backend subsystems** with shared responsibilities and no single source of truth for the send path:

| Subsystem | Role | Maturity |
|---|---|---|
| `slidein-api/` | FastAPI workflow API: config → pipeline → outreach → conversations, contract-driven (`contracts.py`, `runtime.py`) | **Most complete; best-tested** (journey, permissions, compliance suites) |
| `product/` | "Acquisition OS" API + universal multi-tenant core (learning scopes, agents, evaluation) | Stage 1; partially tested; CI-excluded workflows |
| `workspace-app/` | Next.js 16 ops console (Supabase auth) with ~50 internal API routes, its **own** nodemailer + GoPhish send path, Temporal + Mastra agents | Deployed (PM2 on VPS); second ungated send path |

Supporting infrastructure (live, out of scope to change without approval): KumoMTA, GoPhish, reacher, Warmbly, Grafana/Prometheus on VPS `169.58.206.20`.

Tenant model today: **API-key auth, one key = one tenant = one role** (`security.py:27` roles: `viewer, service, operator, admin`). Tenant isolation is enforced by per-query `tenant_id` filters inside services, gated by `resolve_workspace()` (`security.py:195-209`); cross-tenant access returns **404** (no existence oracle). There is no RLS, no membership model, no user accounts.

### What is good and stays

- Tenant isolation pattern in slidein-api is sound and well-tested (`tests/test_permissions.py`).
- Send-path ordering in `OutreachService.send_draft` (`services/outreach.py:147-309`): ownership check → approval gate → suppression → rate limits → compliance → List-Unsubscribe → transport.
- Error envelope `{error: {code, message, details, recovery_action, retryable}}`.
- StageRunner idempotency via `run_key` + bounded attempts.
- Suppression engine with global rows and auto-suppression on bounce/complaint/unsubscribe.
- HMAC-verified deliverability webhooks.
- Marketing site's claim discipline (zero fabricated proof; BENCHMARK/TARGET labelling).

---

## 2. Decisions

### D1 — Canonical backend: `slidein-api` is the single workflow/write authority

**Decision.** All consequential writes — prospect pipeline state, campaign configuration, and **every outbound send** — flow through slidein-api. `product/` remains as an R&D sandbox for the learning-scope/agent layer, explicitly *not* a second production API. `workspace-app` becomes a UI/ops console; its direct send path (`lib/mail/smtp.ts`, `lib/gophish.ts` campaign dispatch) is deprecated behind a server-side feature check and new sends route through slidein-api.

**Why not product/.** product/ has the vision-layer abstractions (Platform Genome, learning scopes) but fewer passing tests, no enforcement of its org model on real workflows, and its e2e suite is CI-excluded. slidein-api has the working send path, contracts, and the strongest isolation tests. "Most tested code that does the job wins" beats "most ambitious schema."

**Why not microservices/rewrite.** Nothing in the findings requires it; the brief forbids it.

**Consequences.** workspace-app cold-outreach send buttons call slidein-api (or are hidden with an explanatory state) until D1's migration path is done. product/ API routes stay deployable for experiments but are documented as non-canonical.

### D2 — AuthN/AuthZ: keep API keys + 4 roles; no new role system

The current 4 roles (`viewer/service/operator/admin`) plus capability split (service keys can't do human actions and vice versa, `security.py:219-232`) covers present workflows. Extension path (documented, not built): user accounts + membership table keyed to the same `require_role` seam; `Tenant.autonomy_level` remains unused until a product need exists.

**Guardrail fix (part of D2):** `SLIDEIN_AUTH_MODE=disabled` must be impossible to set when any non-loopback transport or non-local database is configured — fail fast at startup.

### D3 — Jobs: no new queue now

StageRunner's idempotent `run_key` + bounded retries covers in-request state transitions. Temporal already exists in workspace-app for genuinely long-running work. Adding Celery/arq now is premature; revisit only when a workflow must survive a request lifecycle that Temporal can't host.

### D4 — Schema: introduce Alembic for slidein-api

`create_all` (`db.py:77-79`) is retained for dev/bootstrap; Alembic becomes the migration authority with reversible migrations. product/ either adopts the same Alembic env later or stays schema-experimental.

---

## 3. Findings (verified, with severity)

### P0 — fix before pilot

| # | Finding | Evidence | Fix |
|---|---|---|---|
| F1 | slidein-api has **no CI job**; its isolation/permission tests only run locally | `.github/workflows/ci.yml` covers Go, deliverability, kumomta-lab, product — not slidein-api | Add CI job (sqlite-backed pytest) |
| F2 | **Circuit breaker half-wired**: pre-send compliance reads a persisted `quarantined` flag, but nothing sets it from event data | `deliverability_guard.py:56-62` vs `:87-117` | Evaluate bounce/complaint rates from `DeliveryEvent` on each send; persist quarantine; expose un-quarantine admin op |
| F3 | **Second ungated send path**: workspace-app sends via nodemailer/GoPhish without the SuppressionRecord store | `workspace-app/lib/mail/smtp.ts`, `lib/gophish.ts` | Gate behind feature flag; route through slidein-api; interim: block real sends unless `SLIDEIN_API_URL` configured |
| F4 | **Unencrypted sensitive fields**: `calendar_credentials` JSON plaintext on product `User`; prospect PII unencrypted at rest | `product/db/models.py:79`, `slidein-api/models.py:282-291` | Encrypt credentials column (Fernet, key from env); document PII-at-rest posture honestly (remove "encrypted at rest" promise from vision docs or implement) |
| F5 | **Raw `dict = Body(...)` request payloads** — no boundary validation/length limits | e.g. `routes/outreach.py:82-95` | Pydantic request models for write endpoints; keep error envelope |
| F6 | `deliverability/config.json` (live Kumo password) sits in the working tree | repo root | Verify git-tracking exclusion + rotate if ever committed; confirm `check-secrets.sh` covers it |
| F7 | Marketing site: **3 blank nav pages** (Process/Insights/Pricing), the only published article is unlinked, **no analytics**, **no sitemap/robots**, deploy.yml CI references a non-existent `workspace-app` | `marketing-site/app/{process,insights,pricing}/page.tsx`, `content/insights.ts` | Remove/fix nav targets, link the article, add sitemap+robots+metadataBase, wire privacy-conscious analytics or remove claims of tracking, fix CI |

### P1 — soon after

| # | Finding | Fix |
|---|---|---|
| F8 | No migrations/rollback strategy (D4) | Alembic baseline + first revision |
| F9 | Key rotation absent; actors logged as `user:{role}` with no key identity | Key ID in env JSON, logged as actor; rotation doc |
| F10 | Suppression check loads all rows per send | Bounded/paginated check or DB-level match query |
| F11 | `abuse@global`-style synthetic rows conflate "global suppression" with "email address" | Explicit `scope` column (`global`/`tenant`) — reversible migration |
| F12 | Marketing article carries 3 uncited statistics | Cite, qualify, or remove |
| F13 | No error monitoring (Sentry) on slidein-api/workspace-app; Langfuse covers LLM only | Add Sentry (or self-hosted GlitchTip) — decision point |
| F14 | workspace-app `/insights` empty but nav-linked; BookingCalendar/Footer dead code with divergent calendar URLs | Resolve nav truth; delete or mount; single calendar URL in `content/contact.ts` |

### P2 — roadmap

- User accounts/membership (D2 extension path)
- AI evaluation suite for product/ agents + workspace-app Mastra agents (inventory exists; harness + fixtures first)
- Backup/restore drill documentation for SQLite/Postgres state
- Rate limiting at the edge (Caddy) + per-key quotas
- Billing: none exists; do not add until pilot pricing is decided

---

## 4. Implementation increments (small, reversible, locally verifiable)

1. **I1 CI + validation** — add slidein-api pytest job to `.github/workflows/ci.yml` (sqlite service-less run); Pydantic request models for the outreach/config write endpoints (F1, F5).
2. **I2 Circuit breaker** — compute bounce/complaint from `DeliveryEvent` in pre-send guard; persist quarantine with audit log; tests including retry/idempotency (F2; acceptance: no duplicate consequential actions on retry — `run_key` already covers, add regression test).
3. **I3 Send-path consolidation** — workspace-app: feature-flag real sends off unless routed via slidein-api; explanatory UI state (F3).
4. **I4 Secret hygiene** — git check + `.gitignore` audit for `deliverability/config.json`, `*.db`, CSVs; fail CI on tracked secrets (F6).
5. **I5 Encryption at rest for credentials** — Fernet-encrypted `calendar_credentials`; key via env; migration reads old plaintext lazily (F4 part 1).
6. **I6 Marketing truth pass** — nav/blanks, article links + citation fixes, sitemap/robots/metadataBase, CI repair, analytics decision (F7, F12, F14).
7. **I7 Alembic baseline** (D4/F8) after I1–I2 land.

None of I1–I7 touch live infrastructure, live sending, DNS, or production data. Per `PROJECT_POLICY.md`, anything that does needs explicit owner approval first.

---

## 5. Acceptance mapping (from the brief)

| Requirement | Where demonstrated |
|---|---|
| Two tenants cannot access each other's records/files | `slidein-api/tests/test_permissions.py` (exists, F1 makes it CI-enforced) + new workspace-app gate tests |
| Unauthorized roles blocked | `test_permissions.py` viewer/service cases + new regression tests in I2/I3 |
| Retried jobs don't duplicate actions | StageRunner `run_key` tests + I2 regression |
| Invalid inputs rejected consistently | I1 Pydantic models + error-envelope tests |
| Errors observable without leaking secrets | error envelope (no payload echo); I4 secret scan; I13 |
| Core workflows pass regression | journey suite in CI (I1) |

## 6. Unresolved / requires owner

- Ratify D1 (canonical backend) and the workspace-app send-path deprecation plan.
- Decide analytics provider for marketing site (privacy-conscious default: none or Plausible-style) before wiring events.
- Decide error-monitoring vendor (F13).
- AI evaluation suite scope/timing (which agent workflows are material *today* — product/ agents are experimental; workspace-app Mastra agents are the live AI surface).
- Calendar/voice/booking providers — engagement layer is spec-only per AGENTS.md; no work starts without approval.
