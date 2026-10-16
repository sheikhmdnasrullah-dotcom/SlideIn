# ADR: Deployment Factory — Keep the Engine, Add Provisioning

Date: 2026-10-16. Decider: founder. Status: accepted, implemented (M1).

## Decision

**A + E now, F from template next.** Keep the current `slidein-api`
orchestration (8-stage contracts + `StageRunner` + approval gates) and add
configuration/provisioning around it (`slidein_api/factory/`). Run clients
as isolated tenants of the managed API where tenancy is already enforced
(E); produce repeatable dedicated installs from the existing `install.sh`
single-host template when isolation demands it (F). No new platform.

## Evidence (current code, inspected)

- Orchestration exists and is tested: `contracts.py` (8 stages),
  `runtime.py` (`StageRunner`), `models.py` (`stage_runs` audit trail),
  107 pytest green before this change.
- Hard constraints are already deterministic code, not prompts: approval
  gates + quarantine + suppression (`api/routes/outreach.py`,
  `services/outreach.py`, `services/suppression.py`), legal footer/basis
  defaults (`DEFAULT_POLICY`), dry-run default transport.
- Tenancy is enforced at the API boundary: one-key-one-workspace,
  cross-tenant 404, role gates (`security.py`); tenant settings carry
  sending policy (`Tenant.settings`).
- What was genuinely missing (now added): versioned deployment config,
  owner/booking mappings, CRM field maps, connection registry, onboarding
  validation, activation gate, safe test, rollback. None of that needed a
  new runtime — it needed tables, schemas, and routes.

## Alternatives rejected

- **B1 n8n** — Rejected: license + fit. Sustainable Use License 1.0
  (verified 2026-10-16, `n8n-io/n8n` `LICENSE.md` on master) limits use to
  internal business or non-commercial purposes; serving it as a commercial
  managed service needs an enterprise license. Repos/docs:
  [n8n-io/n8n](https://github.com/n8n-io/n8n),
  [docs](https://docs.n8n.io).
  Migrating the 8-stage contract system into flows would also discard the
  tested audit trail for no current gain.
- **B2 Windmill** — Rejected: license. Source is AGPLv3 by default and the
  Community Edition binaries forbid sell/resell/serve-as-managed-service
  without agreement (verified 2026-10-16, `windmill-labs/windmill`
  `LICENSE`). AGPL network-use terms would also encumber our service.
  Repos/docs: [windmill-labs/windmill](https://github.com/windmill-labs/windmill),
  [docs](https://www.windmill.dev/docs).
- **C Temporal** — Deferred, not rejected. Server MIT (verified
  2026-10-16, `temporalio/temporal` LICENSE). Correct later answer for
  durable converse/follow-up timers and approval-resume across restarts;
  the repo already vendors the worker pattern (`workspace-app/`). Not
  needed for the approval-gated MVP: current runs are synchronous with
  `needs_review` holds and manual retry, which is the safe behavior today.
  Adopt when automated follow-up timing becomes a real requirement.
  Repos/docs: [temporalio/temporal](https://github.com/temporalio/temporal),
  [sdk-python](https://github.com/temporalio/sdk-python),
  [docs](https://docs.temporal.io).
- **D Agent frameworks (OpenAI Agents SDK, LangGraph)** — Deferred. Both
  MIT (verified 2026-10-16: `openai/openai-agents-python` LICENSE,
  `langchain-ai/langgraph` LICENSE). Nothing in the current workflow
  needs autonomous agents: drafting is evidence-grounded deterministic
  composition, and unbounded tool use would violate the bounded-autonomy
  rule. Revisit for reply classification behind explicit tools/policies.
  Repos/docs: [openai-agents-python](https://github.com/openai/openai-agents-python)
  ([docs](https://openai.github.io/openai-agents-python/)),
  [langgraph](https://github.com/langchain-ai/langgraph)
  ([docs](https://langchain-ai.github.io/langgraph/)).

## Consequences

- Least migration: zero changes to workflow behavior; factory is additive
  tables + services + routes with its own tests.
- Least ops: no new stateful system to run per client (Temporal/n8n would
  each add one); per-client cost stays a small host or a tenant row.
- Tradeoff accepted: no cross-restart durable timers yet; long automated
  follow-ups wait for Temporal (C) with a clean seam (`stage_runs` already
  records everything a resume would need).
- License watch: our own BSL 1.1 still needs the managed-service decision
  (see `WORKFLOW_PLATFORM_REFRAME.md` §9) before paid clients.
