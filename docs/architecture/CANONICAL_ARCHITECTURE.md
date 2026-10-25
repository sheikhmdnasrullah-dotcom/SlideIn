# Slidein Canonical Architecture

- Status: Active target architecture with as-built notes
- Version: 1.0.0
- Date: 2026-10-26
- Product companion: `../product/PRODUCT_SPECIFICATION.md`
- Implementation companion: `../engineering/IMPLEMENTATION_ROADMAP.md`

## 1. Architectural decision

Converge on `slidein-app/` and `slidein-api/` as the customer product.

This is a convergence and completion program, not a big-bang rewrite. Preserve the persistent prospect-to-conversation workflow, design system, stage contracts, approval/send controls, and useful infrastructure. Absorb adaptive capabilities selectively. Quarantine duplication rather than allowing it to remain an equal product center.

## 2. Repository roles

| Area | Canonical role | Required treatment |
|---|---|---|
| `slidein-app/` | Customer workspace and server-side BFF | Retain; simplify navigation incrementally; no visual rewrite |
| `slidein-api/` | Customer API, domain model, workflow contracts, approvals, activity, configuration | Canonical backend and vocabulary |
| `product/core/` | Source of adaptive workspace concepts | Selectively absorb capability/evidence/proposal ideas behind canonical persistence and permissions |
| `product/` Acquisition OS API/models | Parallel domain and execution model | Do not expand; migrate useful behavior then retire from the request path |
| `workspace-app/` | Broad internal/legacy console | Not a second customer workspace; salvage internal tools deliberately |
| `osint_core/` | Enrichment/drafting prototype | Place behind authenticated, tenant-scoped canonical connectors before use |
| `visitor_core/` | Visitor-capture prototype | Deferred; requires tenant model, consent, security, and product scope |
| `unified/` | Open prototype dashboard and event firehose | Never expose to customers; do not treat as production integration |
| Go/KumoMTA/deliverability/Reacher/Warmbly | Sending and delivery infrastructure | Retain behind explicit canonical adapters and verified boundaries |
| `marketing-site/` | Separate public marketing application | Out of scope for product consolidation |

No component is promoted solely because it exists. Promotion requires a user task, canonical data mapping, security boundary, persistence behavior, tests, and an owner for ongoing operation.

## 3. Target system contexts

```text
Public marketing site (separate)
             |
             v
Customer browser
             |
             v
slidein-app BFF ---- customer/operator identity and authorization
             |
             v
slidein-api canonical domain and workflow contracts
       |          |              |               |
       |          |              |               +--> activity, audit, export
       |          |              +--> durable execution and scheduling
       |          +--> registered connectors and secret references
       +--> instance database and migrations

Dedicated client instance boundary:
configuration + business data + workflow state + credentials + logs + backups

Slidein operator context:
deployment metadata + release + health + entitlement + support actions
(no customer-visible cross-client infrastructure)
```

The initial managed topology is one dedicated environment per client. A future control plane manages deployment metadata and operations; it does not become another acquisition domain.

## 4. Canonical domain model

Retain and extend the `slidein-api` model rather than renaming it around another Acquisition OS.

### Business and configuration

- Tenant/workspace.
- Business profile and version.
- Offer.
- ICP and targeting/exclusion configuration.
- Approved business knowledge and evidence.
- Configuration version.
- Branding and workspace configuration.

### Acquisition

- Prospect and source attribution.
- Research evidence and verification state.
- Qualification result.
- Offer match.
- Message draft and draft version.
- Sent message and delivery event.
- Suppression record.
- Conversation, reply/message, intent, and assignment.
- Team owner and booking destination.

### Execution and accountability

- Workflow definition/version and stage contract.
- Stage/workflow run and attempt.
- Approval/decision.
- Activity/audit record.
- Scheduled work, retry/dead-letter state, and idempotency key as required.

### Product and service

- Capability definition, code-owned and versioned.
- Tenant capability configuration and lifecycle state.
- Integration connection and secret reference.
- User, membership, role, and API credential.
- Service entitlement and operating responsibility.
- Deployment record, release, health, and lifecycle.
- Export/deletion/offboarding record.

`Tenant.plan_tier` alone is not an entitlement system. `Organization`, `Opportunity`, `Mission`, and parallel `product/` records must not become competing canonical records for the same workflow.

## 5. One capability and configuration authority

The canonical `slidein-api` module configuration and `product/core` capability catalog currently overlap. Replace the overlap with one code-owned registry and one persistent tenant configuration authority.

A capability definition declares:

- Stable ID, version, name, and description.
- Supported routes/components and canonical records.
- Required permissions and entitlements.
- Required integrations and configuration schema.
- Workflow templates or agent actions, if any.
- Setup/readiness requirements.
- Honest availability and health semantics.

Tenant configuration selects and configures registered capabilities. It cannot create executable code.

Capability lifecycle:

```text
registered -> available -> configuring -> awaiting_approval
           -> active <-> paused
           -> error
```

Navigation is a projection of enabled, implemented capabilities. API authorization is enforced independently; hiding a menu item is never authorization.

The newer instance-durable workspace persistence is a useful starting point, but must be reconciled with the canonical registry, migration strategy, authorization, and restart tests rather than maintained as a second permanent configuration system.

## 6. Workflow and agent architecture

### Canonical authority

`StageRunner` and the stage contracts remain the public domain authority for the first workflow. They define required inputs, produced outputs, transitions, permissions, review conditions, failure codes, and audit records.

There must be one authority for:

- Starting work.
- Transitioning prospect/draft/conversation state.
- Approval requirements.
- Retry and recovery.
- Audit and activity.
- Idempotency and duplicate prevention.

LangGraph may be retained behind that authority for a demonstrated graph-execution need. It must not independently move the same records through a second workflow API. Temporal is not an immediate migration requirement.

### Required execution properties

- Durable queued/scheduled work across restarts.
- Idempotent stage and webhook execution.
- Explicit automatic retry policy with backoff and maximum attempts.
- Dead-letter/manual-review terminal states.
- Cancellation and pause behavior.
- Approval tokens bound to tenant, actor, subject, and decision.
- Recovery of waiting executions after restart.
- No double send on retry or worker duplication.
- Tenant context on every job and event.
- Timeouts, heartbeat/lease semantics where needed, and observable stuck runs.

The in-process autopilot loop is not a durable scheduler. New instances default to disabled autopilot, manual approval, and dry-run transport until readiness and explicit activation.

### Agent responsibilities

Use the smallest useful set:

- Research connector/agent produces attributed evidence, not business decisions outside its scope.
- Qualification evaluates evidence against explicit ICP rules and records reasons.
- Personalization produces grounded draft candidates and citations.
- Conversation classifies and recommends; deterministic policy handles suppression and external action.
- Adaptation proposes configuration/knowledge changes; trusted code validates and applies approved changes.

Do not add agents for navigation, generic dashboard generation, or responsibilities already covered by deterministic services.

## 7. API and frontend architecture

### `slidein-app`

- Next.js App Router and server-side BFF remain.
- API keys and integration secrets never enter browser bundles.
- Replace single workspace API-credential behavior with real user/session and membership resolution before external customer access.
- Pages consume canonical API operations and domain status, not parallel mock models.
- Existing components, tokens, and workflow metadata are reused.

### `slidein-api`

- FastAPI remains the customer API.
- All routes bind tenant and actor; role/entitlement/capability checks are server-side.
- Service credentials are distinct from human roles.
- Webhooks authenticate, verify provider signatures where applicable, and are idempotent.
- API schemas remain explicit and versioned.
- Internal operator endpoints require a separate platform-operator permission and audited client-context selection.

### Workspace presentation

The stable seven-section information architecture is a projection of canonical records and enabled capabilities. It is not a generic arbitrary widget renderer.

Existing stage pages can be consolidated through nested record views and aliases. Do not rewrite every page merely to change navigation labels.

## 8. Identity, permissions, and entitlements

Before external customer use, add:

- User identity and secure session handling.
- Tenant membership and invitation lifecycle.
- Human roles such as viewer, member, approver, tenant admin.
- Separate service credentials for connectors/webhooks.
- Platform-operator role with audited cross-instance access.
- Credential rotation and revocation.

Authorization evaluates:

```text
actor + tenant membership + role + capability state
      + entitlement + resource ownership + action policy
```

Entitlements are centralized. They describe service/product scope and are not hardcoded throughout components.

## 9. Persistence and integrations

### Database

- SQLite remains supported for local and appropriately scoped single-instance use.
- PostgreSQL is the default recommendation for managed production.
- Introduce Alembic migrations before relying on managed upgrades.
- `create_all` is a development/bootstrap convenience, not an upgrade strategy.
- Adaptive workspace tables belong in the canonical migration/model lifecycle.

### Integration boundary

Every connector has:

- Stable adapter type and version.
- Tenant-owned connection record.
- Secret reference, never exported secret material.
- Least-privilege scopes.
- Health/check behavior and honest status.
- Idempotent sync and replay handling where relevant.
- Disconnect/revoke behavior.
- Audit history.

Initial integration priorities are real inbound email, outbound transport, enrichment, and verified booking destinations. CRMs, including Twenty, remain optional connectors.

## 10. Deployment and operations

### Initial topology

- Dedicated environment per managed client.
- Same tagged product release across clients.
- Instance-specific configuration, database, secrets, workflow state, logs, and backups.
- No per-client source forks.

### Operator control plane

Begin with reliable records and runbooks, then UI. Track:

- Client/instance and deployment model.
- Release and configuration version.
- Lifecycle and health.
- Connections and failures.
- Entitlement and operating responsibility.
- Backup/restore status.
- Update, pause, export, retire, and deletion history.

The existing deployment lifecycle dataclass is a model, not proof of provisioned operations.

### Required runbooks

- Fresh self-hosted install and supported upgrade.
- Managed provisioning and activation.
- Credential rotation.
- Backup and restore rehearsal.
- Export and verified offboarding/deletion.
- Incident response and global/tenant send stop.
- Rollback and failed-migration recovery.

## 11. Framework decisions

| Technology | Decision |
|---|---|
| Next.js | Keep |
| FastAPI | Keep |
| SQLAlchemy | Keep |
| PostgreSQL | Use for managed production; migrate deliberately |
| Docker Compose/Caddy | Keep for reproducible single-instance deployment |
| Refine | Do not adopt |
| Twenty CRM | Defer; optional connector only |
| React Flow | Later, read-only visualization of validated definitions/runs |
| LangGraph | Reconcile behind canonical execution; no broad parallel adoption |
| Temporal | Reassess only if demonstrated durable distributed execution needs justify it |

A new dependency must solve a measured gap more cheaply than extending existing code, and its operational cost must be recorded.

## 12. Design architecture

The current orange, neutral/editorial direction, typography, semantic tokens, and system primitives are preserved.

- No new visual concept or dashboard redesign phase.
- No decorative agent workforce streams or fake real-time metrics.
- Use existing surfaces, tables, badges, forms, states, and motion.
- Consolidate information architecture once against real user tasks.
- Resolve brand-document conflicts by updating documentation to the implemented system or deliberately versioning tokens; do not churn the UI.
- New capabilities inherit the same design language.

## 13. Security and compliance boundaries

- Treat external content as untrusted and prompt-injection-prone.
- Enforce suppression, approval, rate, deliverability, and legal policy in code.
- Verify webhook authenticity and replay behavior.
- Do not expose prototype OSINT/visitor/SSE surfaces without tenant authentication and authorization.
- Never log or export secret values.
- Keep client data and fixtures out of public source.
- Do not claim legal compliance or inbox placement without evidence.
- LinkedIn and visitor capabilities require provider-rule, consent, and legal review before implementation or activation.
- Do not change `LICENSE` from a coding task; managed-service licensing requires an explicit owner decision.

## 14. Migration strategy

1. Freeze new feature work in parallel product centers.
2. Establish tests and a current capability inventory.
3. Put canonical registry, persistence, authorization, and execution boundaries in place.
4. Route all customer behavior through `slidein-app` and `slidein-api`.
5. Migrate useful adaptive behavior with compatibility tests.
6. Complete real inbound and handoff.
7. Add user/team auth, entitlements, operator context, and managed operational controls.
8. Remove or archive duplicate request paths only after traffic, data, and tests have moved.

No big-bang deletion. No indefinite compatibility layer. Every retained adapter has an owner, test, and removal condition.

## 15. Documentation precedence

When documents disagree, use this order:

1. `../product/PRODUCT_CONSTITUTION.md`
2. `../product/PRODUCT_SPECIFICATION.md`
3. This architecture and accepted ADRs
4. `../engineering/IMPLEMENTATION_ROADMAP.md`
5. `../project/CURRENT_STATE.md` for observed implementation status
6. Historical audits, plans, and marketing narratives

Code is evidence of current behavior, not automatic proof of intended product direction. Documentation claims are not proof of implementation.
