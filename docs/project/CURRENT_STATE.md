# Current State — Slidein

- Living implementation snapshot
- Last locally verified: 2026-10-26
- Repository revision inspected: `9e87b46`, plus the uncommitted one-shot setup slice described in the 2026-10-26 setup section below
- Scope: local source and tests; live VPS and external providers were not contacted
- Product direction: `../product/PRODUCT_SPECIFICATION.md`
- Target architecture: `../architecture/CANONICAL_ARCHITECTURE.md`

This file describes observed implementation, not aspirations. Older live-deployment claims remain historical until directly reverified.

## 1. Current architectural reality

The product interface is one page shell — `slidein-app/` — with a single
`ModeSwitcher` toggling Console (controller) and Dashboard (viewer). The
parallel dashboards that previously competed with it (`unified/`, and the
Acquisition OS under `project/`) were quarantined to `saas/.quarantine/` so
they are no longer in the runtime path; the unified shell is the only
customer Console/Dashboard. Boot state, see §6.

| Area | Observed state | Canonical disposition |
|---|---|---|
| `slidein-app/` | Next.js customer workspace: one page shell with ModeSwitcher toggling Console (seven-step workflow + tool/connector surface) and Dashboard (live adaptive viewer). Auth-disabled local dev renders immediately. | Canonical customer frontend |
| `slidein-api/` | FastAPI workflow API. New `/v1/tenants/{id}/dashboard/sections` + `/proposals` + `/behavior` routes back a Redis-persisted adaptive Dashboard layout (validated module registry only; proposals require explicit approval). | Canonical backend/domain |
| `workspace-app/` | Broad internal/legacy console (mock opportunities, hardcoded content). No longer booted by `dev`. | Internal/legacy; not customer workspace |
| `project/` | Parallel Acquisition OS with a separate command-center dashboard. Quarantined to `.quarantine/`; never booted; not a product. | Do not expand; absorb useful core concepts only |
| `osint_core/`, `visitor_core/`, `unified/` | Useful enrichment/visitor prototypes with unauthenticated, non-tenant-scoped surfaces; never exposed to customers. Quarantined. | Not customer-safe; adapt only after isolation and scope review |
| Mail/deliverability stack | Go/KumoMTA/Lua/Python/Rust/Redis/Celery/Caddy/Docker and monitoring components | Retain behind verified canonical adapters |

## 2. Implemented canonical workflow

The existing `slidein-api` stage sequence is:

```text
configure -> discover -> research -> qualify -> personalize
          -> outreach -> converse -> synthesize
```

Commit `eacec26` also introduced `docs/UNIVERSAL_FLOW.md` and `product/core/flow.py`, which define the accepted seven-stage product invariant:

```text
configure -> discover -> research -> qualify -> personalize -> outreach -> converse
          -> activity -> overview -> approved configuration refinement
```

These currently differ. Convergence must fold useful synthesis/learning behavior into `converse` and the activity/overview feedback loop, move the machine flow definition into the canonical API, and retain only tested compatibility mappings during migration. The `product/core` guard must not become a second permanent workflow authority.

Verified code provides:

- Versioned business profiles, offers, ICPs, and configuration.
- Source-attributed prospect records.
- Research evidence with verification states.
- Explainable qualification and offer-match records.
- Versioned message drafts and approval states.
- Sending policy, suppression, delivery events, deliverability and quarantine controls.
- Inbound webhook threading, intent classification, and opt-out behavior.
- Stage runs, explicit caller-driven attempts, failure/recovery metadata, and activity history.
- Backend-driven overview with pipeline, attention, next actions, stage health, sources, and autopilot status.

The overview is operational API-backed UI. The `workspace-app` acquisition command center is not equivalent and must not be treated as operational truth.

## 3. Adaptive workspace state

The adaptive layer currently includes:

- A code-defined capability catalog.
- Versioned workspace configuration and rollback.
- Evidence and adaptation proposals.
- LangGraph research/qualification/approval execution with SQLite checkpoints.
- Configuration-driven navigation ordering in `slidein-app`.
- Instance-database write-through persistence for workspace config versions, evidence, and proposals, added in `a808b23`.
- A seven-stage flow/provenance guard in `product/core/flow.py`, with adaptation-time rejection of unknown stages and four focused tests, added in `eacec26`; ordering is not yet fully enforced by `assert_flow_aligned()`, and the canonical API still has its own stage enum.

Remaining concerns:

- Canonical `MODULE_REGISTRY` and `CAPABILITY_CATALOG` still overlap.
- Adaptive models/persistence must be brought into the canonical model and migration lifecycle.
- Viewers are mapped to tenant members for adaptive routes; evidence submission accepts caller-supplied `verified=true`.
- Proposal approval/application and execution resume require a complete authorization review.
- Agent execution lookup/resume still relies on an initialized in-memory executor; restart behavior must be tested and repaired.
- Text-mention-driven navigation reordering is not accepted product behavior.
- Two workflow authorities must not independently own the same acquisition records.

## 4. Authentication and isolation

Implemented in the canonical API:

- Workspace-bound bearer API keys.
- Viewer/service/operator/admin roles.
- Cross-workspace 404 behavior.
- Server-side API key use by `slidein-app`.

Not yet a complete external-customer identity model:

- No canonical customer user-session and team-membership flow.
- `slidein-app` is configured around a server-side workspace ID/key.
- No central three-tier entitlement enforcement.
- No complete audited operator control plane across dedicated instances.

Dedicated client environments remain the initial managed deployment model. Shared production multi-tenancy is not approved.

## 5. Execution and automation

- `StageRunner` provides contracts, run/activity records, and explicit retry attempts.
- A `WorkJob` database ledger, lease/recovery service, and Celery/Redis worker path now exist alongside inline execution. `docker-compose.workers.yml` provides the API/worker/single-scheduler/PostgreSQL/Redis slice with dry-run transport. Hermetic tests cover lease recovery, retry/backoff, dead-letter, cancellation, tenant isolation, setup-triggered research, duplicate delivery, and no-double-send replay; live broker, container restart, and VPS behavior still require acceptance verification.
- New autopilot state defaults to disabled, review-required, and send-disabled; transport defaults to `dry_run`.
- Research uses the canonical orchestrator by default. `ToolExecution` and `ToolAttempt` persist every registry row, sequential adapter outcome, fallback, unresolved capability, and replay result.
- LangGraph checkpoints exist, but HTTP restart/resume behavior requires verification and authorization hardening.

## 6. Inbound, engagement, and booking

- Canonical inbound webhook, threading, intent, and suppression exist.
- A confirmed production mailbox/IMAP/provider ingress feeding that webhook is still missing.
- Grace-period and notification helpers exist, but canonical inbound execution is not wired into a complete durable engagement loop.
- Team-owner and verified booking-destination resolution exists.
- `services/booking.py` still contains Notion and `$350` platform constants; client commercial policy must come from versioned client configuration.
- Notion primary booking plus custom booking links is already an owner-resolved provider decision; do not reopen it without new requirements.
- Full booking webhooks, availability synchronization, meeting lifecycle, and no-show recovery are not a complete canonical journey.

## 7. Persistence, operations, and service tiers

- SQLite is the canonical local default; PostgreSQL URL configuration is supported.
- No Alembic migrations were found; initialization uses `create_all`.
- Instance-durable adaptive tables were added, but still need migration lifecycle treatment.
- Deployment lifecycle transitions exist as a dataclass model, not a deployed fleet control plane.
- Backup scripts/docs exist; restore rehearsal is not verified in this investigation.
- No coherent customer export/deletion/offboarding workflow was found.
- `Tenant.plan_tier` is stored/serialized but does not enforce the three service levels.
- Self-hosted installation assets exist; reproducible upgrade/recovery proof remains incomplete.

## 8. Security and exposed prototypes

- OSINT enrichment, result, approval, and dossier routes lack tenant authentication and use email/job-based Redis keys.
- Visitor APIs lack tenant authentication; visitor rows have no tenant ID.
- `unified/` mounts these routers and exposes a dashboard and merged SSE firehose without a production tenant boundary.
- External research and connected content require prompt-injection handling.
- Production use must never run with authentication disabled or rely on hidden navigation as authorization.

## 9. Design and documentation

- `slidein-app` has a coherent orange/neutral editorial design system and reusable primitives.
- Current implementation uses Inter Tight and copied hex/semantic tokens, including pure white.
- `docs/design/UPDATED_BRAND_KIT.md` conflicts with that implementation by requiring Fraunces, OKLCH, and no pure white.
- The accepted direction is to preserve the current implementation and stop visual churn; documentation must be reconciled without another redesign.
- `LICENSE` is BSL 1.1 and restricts third-party hosted/managed offerings without commercial permission; README displays an MIT badge. Owner/licensing decision remains unresolved.
- Older planning and status documents contain conflicting tiers, pricing, content scope, dashboard names, and implementation claims. Canonical documentation precedence is defined in `../architecture/CANONICAL_ARCHITECTURE.md`.

## 10. Verification performed on 2026-10-26

| Check | Observed result |
|---|---|
| `slidein-api` pytest | 313 passed, 0 failed, 0 skipped; includes orchestration, durable jobs with lease heartbeats, setup/identity, billing, inbound mail, and full API acceptance journey |
| `product/tests/test_flow.py` | 4 passed; verifies stage identifiers, aliases, unknown-stage rejection, and adaptation integration |
| `slidein-app` TypeScript | Passed |
| `slidein-app` lint | Passed (the `no-assign-module-variable` error in `components/workspace/sidebar.tsx` was renamed away) |
| `slidein-app` production build | Passed; `/setup` present in the route list |
| `/setup` browser run (headless Chrome, live API) | generate → answer → controlled test → activation; both intake endpoints called; activation correctly refused with `Deployment is not ready to activate` |
| Full local `product` pytest | 50 passed, 5 failed, 33 errors; local PostgreSQL unavailable and async workflow tests not runnable |
| `workspace-app` targeted project tests | 13 passed, 2 failed from `server-only` imported in test runtime |
| Marketing lint | Failed across included skill/worktree scripts and application files |
| Production frontend build | Not run in this investigation |
| Live VPS/providers | Not verified |

CI explicitly ignores `product/tests/test_workflows.py`; the parallel product suite must not be described as fully green.

## 11. Immediate priority order

1. Preserve the canonical workflow and stop new parallel product surfaces.
2. Fix adaptive authorization, executor restart behavior, and registry/persistence duplication.
3. Establish migrations, durable execution/idempotency, and safe autopilot defaults.
4. Complete real inbound reply ingestion and owner/booking-link handoff.
5. Add customer identity, entitlements, export/offboarding, and managed operational proof.
6. Consolidate navigation only against real backend capabilities.
7. Expand to additional channels only after the first complete loop passes acceptance.

See `../engineering/IMPLEMENTATION_ROADMAP.md` for tasks and exit criteria.

## 2026-10-26 — Canonical Convergence (branch `canonical-convergence`)

Phase 0–2 slice, per ADR-2026-10-26-canonical-product-convergence:
- `slidein_api/canonical.py`: ONE authority for (a) the seven stable
  workspace sections and the total capability->section projection, (b) the
  machine flow surface with the deliberate `synthesize -> converse`
  compatibility mapping (§9.1 — legacy eighth stage validates, history safe).
- `GET /v1/workspace/config` now returns the 7-section navigation projection.
- §3.4 enforced at the API: adaptations REQUIRE approval — the auto-apply
  bypass was removed (all risk tiers fail closed at apply).
- Setup intake generates through the canonical flow authority.
- Prototypes (osint_core/visitor_core/unified) remain isolated, not
  customer-exposed. Owner's uncommitted slidein-app changes preserved.
- Tests: 188 passed (5 new convergence tests incl. fail-closed adaptation
  apply, synthesize reconciliation, section totality).

## 2026-10-26 — One-shot client setup slice

The ~30-minute onboarding flow ("Set up a client": provide context → generate →
review exceptions → connect tools → test → activate) is implemented as a
vertical slice. Per-client instances only — no centralized control room, no
per-client forks, no long wizard.

- **Screen:** `/setup` in `slidein-app` (`components/workspace/setup/`),
  five stages + active, sidebar entry "Client Setup", server actions for
  generate / answers / probe / controlled test / activate.
- **Engine:** `slidein_api/setup/` (sources → extract → questions → blueprint
  → service), deterministic first because no LLM key is configured. State
  lives in `Tenant.settings["setup"]` plus normal tenant records.
- **Two entry points, one screen:** `POST /v1/setup/client` remains the intake
  of record (profile + universal-flow first workflow + readiness);
  `GET/POST /v1/tenants/{id}/setup(/generate|/answers)` serve the per-stage
  state the screen renders. The UI action calls both so neither store is left
  behind. See `slidein_api/setup/README.md`.
- **Honesty enforced by tests:** unsupported asks (e.g. SMS) become proposed
  enhancements, unsafe/local website sources are refused and shown, profile
  provenance is confirmed-vs-assumed, and `active` is only returned when
  activation actually passes. Blocking questions (postal address, sender,
  lawful basis, approver) keep sending policy unwritten until answered.
- **Observed gaps, not hidden:** activation is still refused with
  `Deployment is not ready to activate` until CRM field maps and the readiness
  gate pass; transport is `dry_run`, so a controlled test sends nothing.

## 2026-10-26 — Deep-read reconciliation (all canonical docs read in full)

Conflicts found and resolved against the canonical texts:
1. ARCHITECTURE §6 (two flow definitions drift): the machine flow definition
   MOVED into `slidein_api/canonical.py` (STAGE_IDS + aliases + FlowViolation
   owned there). `product/core/flow.py` remains an interim guard, tied by
   `test_no_dual_flow_drift` (byte-equality).
   REMOVAL CONDITION: when product/ acquisition path is retired from the
   request path (TASKS 1), delete product/core/flow.py and the equality test.
2. SPEC §7.1 (caller self-verification): POST /workspace/evidence now only
   honors `verified=true` from admin/platform roles; member/agent callers
   persist unverified. Covered by test_caller_cannot_self_verify.
3. ARCHITECTURE §5 (second permanent config system): adaptive workspace
   tables remain as the instance-durable persistence of tenant capability
   configuration; the REGISTRY merge with the canonical slidein-api module
   registry (TASKS 2) is the next controlled step — target: one code-owned
   registry in slidein_api, adaptive catalog deleted after callers migrate.
   Owner: convergence program. Test: registry parity + lifecycle test.
Noted, not yet done: Alembic (create_all still bootstrap), production-proven
durable scheduling, production inbound connector, user/team sessions. No live
sending performed.

## 2026-10-26 — Research tool orchestration and recipient verification

- The research route and autopilot default to `orchestrated`. The orchestrator
  resolves the full registry coverage plan, executes only eligible adapters
  sequentially, applies attempt/time budgets and deterministic fallback, and
  persists `ToolExecution` plus ordered `ToolAttempt` records. Replay uses a
  tenant-scoped execution key and does not duplicate evidence.
- Authenticated execution reads are available at
  `GET /v1/tenants/{id}/tools/executions` and
  `GET /v1/tenants/{id}/tools/executions/{execution_id}`.
- The registry now includes Warmbly, Node mailbox warmup, deliverability and
  optimization warmup, the legacy outreach daemon, deterministic drafting,
  SMTP/KumoMTA, and inbound/conversation capabilities. Registration is not an
  active-health claim. No separate Warmly installation was found.
- Reacher has a canonical HTTP adapter and is recorded in draft/send
  preflight. Live SMTP/KumoMTA requires a `safe` recipient verdict; dry-run
  records unconfigured/unavailable/unknown verdicts without sending.
- New autopilot defaults are disabled, review-required, send-disabled, and
  dry-run. Existing explicit tenant switches are preserved.
- Warmbly and the three legacy warmup/daemon paths remain unwired to canonical
  execution. External provider health, live DNS/SMTP, and production mailbox
  ingestion were not exercised.
