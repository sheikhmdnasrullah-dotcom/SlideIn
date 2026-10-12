# SLIDEIN SHARED CONFIGURATION VERSIONING

> Status: Authoritative Specification
> Version: 1.0.0
> Implements: shared-config half of directive §1.A and §5
> Code: `product/core/shared.py`

---

## 1. What is versioned

Every reusable product default is a named, versioned `SharedArtifact`:

| Kind | Examples |
|---|---|
| `prompt` | `writing.tone.default`, personalization templates |
| `rule` | `qualification.score_weights.v1`, dedup rules |
| `threshold` | send limits, retry budgets |
| `workflow` | `workflow.stages.v1` stage definitions |
| `template` | shared message scaffolding (never tenant copy) |

Each artifact records: name, kind, monotonic version, SHA-256 content hash,
release timestamp, approver identity, and the evaluation record that
justified it. Seed versions use the evaluation ref `"seed"` and contain
only industry-neutral content.

## 2. Immutability

- Released artifacts are frozen. There is no update-in-place API; any
  change is a new version.
- Readers receive deep copies (`get_active`), so no caller can mutate the
  registry through a returned reference
  (`test_returned_shared_content_is_a_copy`).
- Attempting to write as an unauthorized role (agents included) raises
  `ImmutableReleaseError` — including for reads-that-mutate patterns, of
  which there are none by construction.

## 3. Release process

1. A validated learning candidate exists (see `PRODUCT_LEARNING_PIPELINE.md`).
2. A platform admin calls `release()` with actor identity, an evaluation
   ref, and a reason. Empty evaluation refs are refused.
3. The registry supersedes the prior version (recording `superseded_by`),
   activates the new version, and appends `superseded` + `released` audit
   entries (`test_shared_release_is_versioned_and_audited`).
4. Exactly one version per name is active at any time.

## 4. Rollback

`rollback(name, to_version, actor, reason)` reactivates a prior version.
History is append-only: the bad version remains visible and the rollback
itself is recorded with its reason
(`test_shared_rollback_reactivates_prior_version`). Rollback requires a
non-empty reason and a platform-admin (or system) role.

## 5. Tenant overrides (without forking the core)

Tenants never edit shared artifacts. Where per-tenant variation is
legitimate it lives in `TenantContext` (tone, ICP, terminology, policy)
and is passed to workflow stages as data. The runner
(`product/core/workflow.py`) executes identical stage logic for all
tenants; tenant data shapes outputs, never the code path
(`test_same_pipeline_for_materially_different_tenants`).

If a tenant need cannot be expressed as configuration, classify it before
implementing (directive §8): reusable core capability, config option,
provider-specific adapter, genuinely new domain capability — or a one-off
that stays out of the core. One-offs stay out.
