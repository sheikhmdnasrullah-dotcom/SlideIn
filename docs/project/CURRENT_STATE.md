# Current State — Slidein

- Living implementation snapshot
- Last locally verified: 2026-10-26
- Repository revision inspected: `a808b23`
- Scope: local source and tests; live VPS and external providers were not contacted
- Product direction: `../product/PRODUCT_SPECIFICATION.md`
- Target architecture: `../architecture/CANONICAL_ARCHITECTURE.md`

This file describes observed implementation, not aspirations. Older live-deployment claims remain historical until directly reverified.

## 1. Current architectural reality

Slidein currently has multiple product centers, not one fully converged workspace.

| Area | Observed state | Canonical disposition |
|---|---|---|
| `slidein-app/` | Real Next.js customer workspace with server-side BFF, workflow navigation, backend-driven overview, prospect/draft/conversation pages | Canonical customer frontend |
| `slidein-api/` | FastAPI workflow API with persistent acquisition records, stage contracts, approvals, sending policy, conversations, activity, and autopilot | Canonical backend/domain |
| `workspace-app/` | Broad Next.js internal console with many tool surfaces; acquisition command center consumes mock opportunities and hardcoded operational content | Internal/legacy; not customer workspace |
| `product/` | Parallel Acquisition OS models/API plus adaptive core; main API mounts opportunities, command-center, and health routers | Do not expand as another product; absorb useful core concepts |
| `osint_core/`, `visitor_core/`, `unified/` | Useful enrichment/visitor prototypes with unauthenticated, non-tenant-scoped surfaces | Not customer-safe; adapt only after isolation and scope review |
| Mail/deliverability stack | Go/KumoMTA/Lua/Python/Rust/Redis/Celery/Caddy/Docker and monitoring components | Retain behind verified canonical adapters |

## 2. Implemented canonical workflow

The canonical stage sequence is:

```text
configure -> discover -> research -> qualify -> personalize
          -> outreach -> converse -> synthesize
```

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
- It does not provide durable scheduling, automatic retry/backoff, exactly-once behavior, or distributed execution.
- Autopilot is an in-process loop, not a durable worker system.
- Autopilot state currently defaults to enabled, auto-approve, and send-enabled; transport defaults to `dry_run`.
- The accepted target default for new instances is autopilot disabled until activation, review required, and dry-run transport.
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
| `slidein-api` pytest | 179 passed; one `TestRunService` collection warning |
| `slidein-app` TypeScript | Passed |
| `slidein-app` lint | Failed: one `no-assign-module-variable` error in `components/workspace/sidebar.tsx` |
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
