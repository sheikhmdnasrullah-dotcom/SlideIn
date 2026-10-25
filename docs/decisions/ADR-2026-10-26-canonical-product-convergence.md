# ADR: Canonical product convergence and controlled adaptation

- Status: Accepted product/architecture direction
- Date: 2026-10-26
- Owner confirmation: requested continuation using the four recommended defaults

## Context

The repository contains three overlapping product centers:

1. `slidein-app` + `slidein-api`, with the deepest persistent prospect-to-conversation workflow.
2. `workspace-app`, a mixed internal console with unrelated tools and mock acquisition views.
3. `product`, a second Acquisition OS domain plus adaptive workspace and LangGraph services.

Continuing all three would duplicate records, permissions, navigation, execution, and operational claims. Repeated dashboard redesigns would not solve that duplication.

## Decisions

### 1. Canonical product

Use `slidein-app` + `slidein-api` as the customer product. Absorb useful `product/core` capability, evidence, proposal, and rollback ideas behind the canonical domain. Treat `workspace-app` as internal/legacy tooling.

### 2. First complete release

Finish business setup through real inbound reply and owner/booking-link handoff. Defer broad content, LinkedIn, visitor-identification, chat/voice, and full calendar-synchronization expansion until that loop is reliable.

### 3. Deployment and access

Use dedicated isolated client environments initially, with the same product release and no client forks. Add customer user/team authentication before external access. Build the operator context/control plane incrementally. Do not launch shared production multi-tenancy yet.

### 4. Adaptive behavior

Adaptive means persistent knowledge, configuration, entitlements, and reviewable proposals. Initially require adaptation approval, disable autonomous navigation rearrangement, and prohibit self-modifying/self-deploying code.

### 5. Workspace stability

Use seven stable sections: Overview, Business Setup, Prospects & Research, Outreach, Conversations, Activity, Settings. Consolidate existing routes incrementally. Do not start another visual redesign.

### 6. Service model

Self-Hosted, Managed, and Growth Partner are centralized service entitlements and operating responsibilities over one codebase. No prices are specified here.

### 7. Framework restraint

Keep Next.js, FastAPI, SQLAlchemy, and the existing deployment stack. Do not adopt Refine. Defer Twenty behind a connector and React Flow behind read-only visualization. Reconcile LangGraph with canonical execution before broader use. Do not migrate to Temporal now.

## Consequences

### Positive

- One domain and customer journey.
- Fewer dashboard rewrites and less terminology drift.
- Existing tested code remains valuable.
- Clear separation between client configuration and shared code.
- Dedicated deployment matches current operational maturity.
- New capabilities can enter without changing the basic product concept.

### Costs

- Parallel models and routes must be migrated or retired deliberately.
- User/team auth, entitlements, migrations, durable execution, and managed operations remain real work.
- A dedicated environment per client requires repeatable updates, backups, monitoring, and recovery.
- Some attractive prototypes remain unavailable until they meet canonical boundaries.

## Safety and operational defaults

- New instances: review-required, autopilot disabled until explicitly activated, transport `dry_run`.
- No live sends or production changes without explicit authorization.
- No unimplemented capability displayed as active.
- No artificial export or offboarding lock-in.

## Explicitly unresolved owner/legal decision

`LICENSE` is BSL 1.1 and the README contains conflicting MIT messaging. Engineering must not silently change licensing terms. The owner must decide and record the managed-service licensing approach before third-party managed rollout, then align documentation.

## References

- `../product/PRODUCT_SPECIFICATION.md`
- `../architecture/CANONICAL_ARCHITECTURE.md`
- `../engineering/IMPLEMENTATION_ROADMAP.md`
- `../project/CURRENT_STATE.md`
