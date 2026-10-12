# SLIDEIN TENANT MEMORY POLICY

> Status: Authoritative Specification
> Version: 1.0.0
> Implements: directive §2 (learning scopes), §4 (cross-tenant rules)
> Code: `product/core/scopes.py`, `product/core/memory.py`

---

## 1. Scopes

Every persistent learning item carries exactly one scope:

| Scope | Visibility | Contents |
|---|---|---|
| `tenant_private` | Owning tenant only (+ platform admin for ops) | Business profile, ICP, prospects, messages, outcomes, preferences |
| `platform_operational` | All authenticated roles | Error patterns, latency, cost, queue health — no customer content |
| `platform_candidate` | All authenticated roles | Proposed shared improvement awaiting review |
| `platform_validated` | All authenticated roles | Approved improvement with evaluation results |
| `platform_released` | All authenticated roles | Versioned improvement active in the product |

## 2. Allowed transitions

```
tenant_private ──▶ platform_candidate ──▶ platform_validated ──▶ platform_released
                         ▲
platform_operational ────┘
```

- Each hop requires an authorized approver (§3) and a recorded reason.
- `tenant_private` can never jump directly to validated or released.
- `platform_released` is terminal; behavior changes ship as new versions,
  and regressions are handled by rollback, not by editing history.

## 3. Who may approve what

| Edge | Approvers |
|---|---|
| `tenant_private` → `platform_candidate` | `tenant_admin` (own tenant) or `platform_admin` |
| `platform_operational` → `platform_candidate` | `platform_admin` |
| `platform_candidate` → `platform_validated` | `platform_admin` + evaluation record |
| `platform_validated` → `platform_released` | `platform_admin`, via versioned release |

**Agents approve nothing.** An AI agent may submit candidates and attach
evidence; it cannot change any item's scope, approve a review, or release a
shared change. Promotion without an authorized approver raises
`UnauthorizedPromotion`. This is enforced in `MemoryStore.promote()` and
`LearningRegistry.approve()/release()`, and asserted by
`test_agent_cannot_promote_memory` and `test_no_role_approves_for_agents`.

Promotion of tenant-private material additionally requires a policy check:
contract, consent, and applicable law must permit the reuse. Where shared
analysis is not permitted, the item stays `tenant_private` — no exceptions,
no silent upgrades.

## 4. Retrieval rules (prohibit uncontrolled cross-tenant learning)

1. Tenant-private memory is never globally searchable. `MemoryStore.search()`
   excludes `tenant_private` unless the caller explicitly requests their own
   tenant's records — and even then, another tenant's records are unreachable.
2. Agents must not retrieve another tenant's records as context. `get()`
   raises `CrossTenantAccess` on any tenant mismatch.
3. Consequences, enforced by the same mechanism rather than by instruction:
   - One tenant's rejections never enter another tenant's exclusions.
   - One tenant's ICP never becomes another tenant's default.
   - One tenant's message edits never change another tenant's messaging.
   - One tenant's conversions never redefine global qualification scores.
   - Tenant research/conversations never enter shared training without an
     explicit, authorized data-use process (a Stage 5 concern, not present).
   - Shared prompts are never modified from ordinary tenant execution.

## 5. Anonymization stance

Removing names or email addresses is **not** sufficient anonymization.
Business context, unique events, message content, and attribute combinations
can re-identify a customer. Promotion review must assess the whole item.

Prefer, in order:
1. General technical telemetry that answers the question without customer
   content at all.
2. Synthetic evaluation cases reproducing the observation.
3. Explicitly authorized excerpts, with the authorization reference recorded
   on the candidate (`authorization_ref`).

## 6. Tenant memory lifecycle

- Tenant configuration changes through authorized tenant workflows
  (`TenantConfigStore.update_*`); history accumulates as `tenant_private`
  memory records.
- Tenant deletion (ops runbook, Stage 2): purge `tenant_private` memory,
  tenant context, and prospect data. Already-promoted shared artifacts stay
  (they contain no tenant content by construction) but their origin link is
  severed.
