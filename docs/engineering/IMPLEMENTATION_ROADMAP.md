# Slidein Implementation Roadmap

- Status: Active canonical execution sequence
- Version: 2.0.0
- Date: 2026-10-26
- Product: `../product/PRODUCT_SPECIFICATION.md`
- Architecture: `../architecture/CANONICAL_ARCHITECTURE.md`
- Working checklist: `../../../planning/TASKS.md`

## Operating rule

Complete one vertical business loop before broadening the product. Do not create a dashboard phase, a new acquisition model, or a framework migration as a prerequisite.

Each phase requires implementation, tests, documentation, and a demonstrated acceptance path. Do not mark work complete from typechecks or screenshots alone.

## Phase 0 — Freeze, baseline, and protect the current system

### Tasks

- Create a working branch and preserve all existing uncommitted work.
- Re-run the current backend, frontend, and targeted infrastructure tests.
- Inventory routes, models, workers, integrations, and request paths against the current revision.
- Freeze new customer features in `workspace-app`, parallel `product` Acquisition OS routes, `osint_core`, `visitor_core`, and `unified`.
- Record live/production claims as unverified until tested.
- Ensure no live sending, production deployment, DNS change, or external provider mutation occurs without explicit authorization.
- Fix the current `slidein-app` lint error without redesigning the component.
- Add a CI/test baseline for the canonical applications.

### Exit criteria

- Canonical test baseline is reproducible.
- No parallel center is receiving new customer workflow features.
- Current behavior and data-migration risks are documented.
- Existing data and owner work are preserved.

## Phase 1 — Establish one canonical product boundary

### Tasks

- Make `slidein-app` and `slidein-api` the only customer request path for new work.
- Map every `product/core` adaptive behavior to a canonical capability, configuration, evidence, proposal, or execution concept.
- Stop `product` Acquisition OS records and `workspace-app` mock opportunities from feeding customer screens.
- Mark prototype/open surfaces unavailable to customer traffic.
- Introduce a compatibility inventory for duplicate routes/models with owner, replacement, test, and removal condition.
- Keep existing infrastructure behind adapters; do not rewrite sending or deliverability components merely for naming consistency.
- Update documentation and module names to canonical vocabulary.

### Exit criteria

- One canonical customer API and domain owns the first workflow.
- No customer screen reads mock acquisition data.
- No duplicate acquisition record is created by a second workflow authority.
- Every legacy path is explicitly retained, isolated, migrated, or scheduled for removal.

## Phase 2 — Unify capability, knowledge, and configuration persistence

### Tasks

- Reconcile `MODULE_REGISTRY` and `CAPABILITY_CATALOG` into one code-owned versioned registry.
- Reconcile tenant module settings and adaptive workspace tables into one persistent configuration authority.
- Bring adaptive tables into canonical SQLAlchemy models and Alembic migrations.
- Preserve existing configuration/history through a tested migration.
- Model capability states: available, configuring, awaiting approval, active, paused, error.
- Separate verified facts, unverified claims, hypotheses, and proposals.
- Require privileged verification; callers cannot self-assert `verified=true`.
- Require appropriate admin/approver permission for proposal approval/application and rollback.
- Make all adaptation review-required initially.
- Disable autonomous navigation reordering and auto-enablement from mentions/clicks.
- Add provenance, actor, timestamp, evidence references, and audit events.

### Exit criteria

- One registry and one configuration authority drive both navigation and server authorization.
- Configuration, evidence, proposals, and history survive restart and migration.
- Viewer/member roles cannot verify evidence or apply privileged changes.
- A rejected or unapproved proposal has no effect.
- Repeating an apply/rollback request cannot corrupt version history.

## Phase 3 — Make execution durable and safe

### Tasks

- Define one execution authority around canonical stage contracts and `StageRunner` semantics.
- Move the seven-stage machine definition from the interim `product/core/flow.py` guard into `slidein-api`; fold `synthesize` into conversation/feedback with migrations and tested compatibility mappings.
- Enforce canonical stage order and provenance before persisting workflow proposals; keep one machine definition rather than divergent copies.
- Decide narrowly where LangGraph remains behind that authority; remove parallel ownership of acquisition state.
- Extend the canonical tool registry/coverage planner into a bounded execution orchestrator; account for every stage tool as ready or explicitly skipped rather than running every package.
- Persist per-tool attempts, configuration/wiring/policy skips, source provenance, fallback selection, budgets, and unresolved capabilities without secrets.
- Keep ECC engineering-only; add runtime adapters individually after license/security review and hermetic tests, never by environment-variable presence alone.
- Add durable scheduling/queueing appropriate to the existing modular monolith.
- Add idempotency keys for stages, sends, webhooks, and approval/resume actions.
- Implement bounded automatic retries with backoff, jitter where useful, and terminal review/dead-letter states.
- Add cancellation, pause, timeout, stuck-run detection, and restart recovery.
- Ensure waiting LangGraph executions can be reconstructed and read/resumed after process restart.
- Enforce admin/approver permission and tenant binding on resume.
- Prevent duplicate dispatch on worker retry or replay.
- Default new instances to autopilot disabled, review required, and `dry_run`.
- Require explicit readiness and activation before live transport.
- Add per-tenant and global send stop controls.

### Exit criteria

- Restarting the API/worker does not lose or duplicate work.
- Replaying a webhook or send attempt does not create duplicate records/messages.
- Retry policy and terminal state are observable in Activity.
- Unauthorized callers cannot resume or approve executions.
- A fresh instance cannot accidentally send live email.

## Phase 4 — Complete prospect-to-conversation

### Tasks

- Reuse existing profile, discovery, research, qualification, personalization, approval, and delivery services.
- Implement one production inbound email connector behind the canonical adapter boundary.
- Verify provider authentication/signatures and retry behavior.
- Make inbound ingest idempotent per tenant/provider message ID.
- Preserve raw MIME only under an explicit secure retention policy.
- Thread using Message-ID, In-Reply-To, References, and tenant-scoped fallback rules.
- Route ambiguous threads, auto-replies, bounces, list loops, and low-confidence intent correctly.
- Apply opt-out immediately and cancel eligible pending sends/agent replies.
- Wire notification/grace-period behavior only through durable execution and explicit tenant policy.
- Remove hardcoded provider/pricing constants; read commercial rules from approved client knowledge.
- Route interested replies to a deterministic owner and verified Notion/custom booking link.
- Keep first-touch messages link-free.
- Record a meeting only after confirmed provider evidence.
- Implement the complete UI empty/error/review states using existing pages/components.

### Exit criteria

A hermetic and then explicitly authorized live acceptance test proves:

1. A client profile, offer, and ICP can be configured and versioned.
2. A prospect enters with source attribution.
3. Research persists sourced evidence.
4. Qualification and offer match explain their decision.
5. A draft is grounded and versioned.
6. An authorized human approves it.
7. Safety gates allow a controlled send or explicit dry run.
8. A real/provider-simulated reply arrives once, threads correctly, and records intent.
9. Opt-out blocks all later sends.
10. An interested reply reaches the right owner/booking destination.
11. Overview and Activity reflect the entire journey after restart.

## Phase 5 — Simplify the existing workspace without redesigning it

This phase intentionally follows working domain behavior.

### Tasks

- Consolidate navigation to Overview, Business Setup, Prospects & Research, Outreach, Conversations, Activity, Settings.
- Preserve existing stage routes as nested views, record tabs, or aliases where useful.
- Move OSINT into Research and stage contracts into a technical/settings surface.
- Remove mock metrics, decorative agent streams, and unsupported navigation.
- Use real empty, loading, disabled, pending, unavailable, and error states.
- Preserve current tokens, typography, orange accent, system components, and responsive behavior.
- Reconcile brand documentation with the implemented design rather than redesigning the app.
- Add accessibility and workflow-focused frontend tests.

### Exit criteria

- A new user can complete the first workflow without understanding internal architecture.
- Every visible item maps to real backend state or an explicit unavailable state.
- No duplicate section exists solely to make the product appear broader.
- No new design language, UI framework, or dashboard concept was introduced.

## Phase 6 — Add customer identity and centralized entitlements

### Tasks

- Add secure customer user/session handling to `slidein-app`.
- Add users, memberships, invitations, roles, revocation, and credential rotation.
- Distinguish viewer, member, approver, tenant admin, service credential, and platform operator.
- Bind every UI/API/job action to actor and tenant.
- Introduce central entitlement definitions for Self-Hosted, Managed, and Growth Partner.
- Separate product capability availability from service operating responsibility.
- Enforce entitlements server-side without scattering plan checks.
- Add explicit operator impersonation/support-access audit if such access is allowed.
- Keep dedicated client environments as the initial topology.

### Exit criteria

- Two users with different roles receive correct access in the same instance.
- One client cannot access another client's records, credentials, runs, streams, exports, or infrastructure.
- Revoked users/keys lose access.
- Tier changes alter authorized scope without changing domain data or application structure.

## Phase 7 — Prove dedicated deployment and no-lock-in operations

### Tasks

- Add versioned deployment records and release/configuration metadata.
- Implement repeatable fresh install and supported upgrade paths.
- Rehearse backup and restore on an isolated environment.
- Add health, failure, backup, and update status for operators.
- Implement machine-readable full customer export with documented schema.
- Exclude secret values and provide safe reconnection instructions.
- Implement offboarding: export confirmation, credential revocation, retention/deletion schedule, backup expiry, and verification.
- Document incident response, rollback, send stop, provider outage, and recovery.
- Resolve and record the owner licensing decision before third-party managed rollout; align README and license messaging only after that decision.

### Exit criteria

- The same tagged release deploys to two isolated instances without code changes.
- An upgrade preserves data and can be rolled back safely.
- A restore rehearsal reconstructs a working instance.
- Export can be independently inspected and reimported or migrated according to policy.
- Offboarding leaves no active credentials and produces a verifiable deletion/retention record.

## Phase 8 — Add only the next justified capability

Candidates include richer discovery connectors, read-only workflow visualization, optional CRM connectors, full calendar synchronization, content operations, or visitor capture.

Before selecting one, require:

- A real client/user need.
- A canonical record and API mapping.
- Entitlement and permission behavior.
- Integration/provider-rule review.
- Durable execution and failure semantics.
- Honest UI states using existing navigation.
- Tests and operational ownership.

Do not add LinkedIn automation, visitor identification, chat, voice, or generated micro-SaaS merely because prototypes or old sales copy exist.

## Continuous acceptance gates

Every pull request/change set must answer:

1. Which canonical user task does this improve?
2. Which existing records and components are reused?
3. Does it create any duplicate authority or parallel product surface?
4. How are tenant, actor, entitlement, and capability enforced?
5. How does state survive restart and upgrade?
6. How are retries, replay, approval, and audit handled?
7. What happens when data is empty, unauthorized, unavailable, or failed?
8. Which tests prove the behavior?
9. Which documentation changed?
10. Does this avoid unnecessary visual or dependency churn?

## Explicit non-goals

- Big-bang repository rewrite.
- New dashboard/frontend for each client or industry.
- Autonomous UI rearrangement or code deployment.
- CRM replacement or mandatory Twenty adoption.
- Refine adoption.
- Immediate Temporal migration.
- Arbitrary React Flow execution editor.
- Shared production multi-tenancy at this stage.
- Prices in platform code or this roadmap.
- Unverified production, compliance, deliverability, or capability claims.
