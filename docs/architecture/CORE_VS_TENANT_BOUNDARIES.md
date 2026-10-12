# SLIDEIN CORE VS TENANT BOUNDARIES

> Status: Authoritative Specification
> Version: 1.0.0
> Implements: directive §1 (three architectural boundaries), Stage 1

---

## 1. The invariant

Slidein is a **universal prospecting and outreach platform** that serves many
businesses. It must improve at operating that platform over time. It must not
become, in behavior or defaults, the business of whichever customer it has
served most recently.

This document establishes three permanent boundaries. They are enforced in
code (`product/core/`), in the database schema, in agent permissions, and in
tests (`product/tests/test_core_boundaries.py`) — not by convention alone.

## 2. The three boundaries

### A. Shared Product Core

Reusable capabilities, identical for every tenant:

- Canonical domain models (`product/db/models.py`, `product/core/`).
- Workflow orchestration: the fixed pipeline Discover → Research → Qualify →
  Match Offer → Personalize → Validate → Execute → Measure
  (`product/core/workflow.py`, `STAGES`).
- Research, qualification, personalization, and validation interfaces.
- Provider adapters, suppression and authorization enforcement.
- Scheduling, retries, idempotency, observability.
- API contracts and shared UI components.
- **Versioned** reusable prompts, rules, thresholds, and workflow definitions
  (`product/core/shared.py` — `SharedDefaultsRegistry`).

The shared core must never contain a specific customer's business profile,
ICP, prospect records, message history, sales preferences, or unvalidated
business assumptions as global defaults. Shared content changes only through
a versioned release with an evaluation record and a platform-admin approver.

### B. Tenant-Owned Business Context

Everything that makes one business different from another, isolated per
tenant (`product/core/tenant.py` — `TenantContext`, `TenantConfigStore`):

- Business identity, offers and services, ICPs, exclusions.
- Approved claims and evidence, terminology, messaging preferences.
- Prospect/account records, research history, qualification results.
- Campaigns, conversations, feedback, operating policies, outcomes.

Rules:

- Tenant context flows **through** the shared workflow as data. It never
  rewrites shared code, shared prompts, shared rules, or another tenant.
- Readers/writers: the owning tenant's roles (`tenant_admin`,
  `tenant_member`), the tenant-scoped agent runs executing for that tenant,
  and `platform_admin` for ops tooling only — never as agent context for
  another tenant.
- Cross-tenant access raises `CrossTenantAccess` at every layer: the
  `TenantConfigStore`, the `MemoryStore`, and (in production) the
  repository layer (`org_id` scoping, see §5) plus PostgreSQL RLS.

### C. Product Learning and Governance

The controlled process that turns operational evidence into shared
improvements (`product/core/learning.py`, `product/core/memory.py`,
`product/core/evaluation.py`). Full pipeline:
`PRODUCT_LEARNING_PIPELINE.md`.

It is separate from tenant workflow execution. Ordinary runs may **submit**
candidates; they can never approve, validate, or release them.

## 3. Component access matrix

| Component | tenant_private (own) | tenant_private (other) | platform_* scopes | Shared releases |
|---|---|---|---|---|
| Tenant agent run | read/write own tenant | **denied** | read | **denied** |
| `tenant_member` / `tenant_admin` | read; admin writes config | **denied** | read | **denied** |
| `platform_admin` | read (ops only) | read (ops only) | read | release/rollback |
| `system` (migrations, seeds, CI) | read/write | read/write | read/write | seed + release |

Promotion edges (`product/core/scopes.py`):

- `tenant_private` → `platform_candidate`: tenant_admin or platform_admin.
- `platform_operational` → `platform_candidate`: platform_admin.
- `platform_candidate` → `platform_validated`: platform_admin + evaluation record.
- `platform_validated` → `platform_released`: platform_admin, via versioned release.
- Agents approve **nothing**: `Role.AGENT` authorizes zero edges
  (asserted by `test_no_role_approves_for_agents`).

## 4. Data flow

```
Tenant workflow execution
  TenantContext ──data──▶ UniversalWorkflow stages ──▶ outcomes
        │                         │
        │                         ▼ (submit only)
        │                   LearningCandidate (platform_candidate, pending)
        │                         │
        ▼                         ▼ (governed pipeline: evaluate → approve → release)
TenantConfigStore        SharedDefaultsRegistry (new immutable version)
  (tenant_private)         (platform_released)
```

No arrow runs from tenant execution to shared behavior except through the
governed pipeline. That is the whole architecture.

## 5. Database mapping (production)

Stage 1 ships the in-memory core with identical semantics; the production
SQLAlchemy mapping follows the existing `TenantMixin` pattern:

- `tenant_contexts` — one row per tenant (`tenant_id` PK): identity, offers,
  ICPs, exclusions, terminology, messaging prefs, policy (JSON columns).
- `memory_records` — `id, scope, tenant_id NULLABLE, category, content,
  created_by_role, created_at`. Partial index on
  `(tenant_id) WHERE scope = 'tenant_private'`.
- `promotion_records` — append-only audit of every scope change.
- `learning_candidates` + `review_records` — registry + audit trail.
- `shared_artifacts` — `(name, version)` PK, content hash, released_by,
  evaluation_ref; `release_records` append-only.
- `eval_suites`, `eval_cases` (with `provenance`, `authorization_ref`),
  `eval_reports`.

Enforcement layers (in addition to the existing three in
`SECURITY_AND_TENANCY.md`):

1. **Core library**: every read/write/promotion checks scope + role + tenant
   match and raises on violation.
2. **Repository layer**: `WHERE tenant_id = :tenant_id` on tenant tables
   (existing `BaseRepository` convention); shared tables readable by all,
   writable only through release functions.
3. **PostgreSQL RLS**: tenant tables get
   `USING (tenant_id = current_setting('app.current_tenant_id', true))`;
   shared tables get read-for-all / admin-write policies.

## 6. What is explicitly out of Stage 1

Per directive §10: operational telemetry pipelines (Stage 2), the
full review UI and scheduled evaluation runs (Stages 3–4), and any
aggregate analysis or model adaptation (Stage 5). The registry,
state machine, and suite runner in `product/core/` are the
foundations those stages build on; their interfaces are stable.
