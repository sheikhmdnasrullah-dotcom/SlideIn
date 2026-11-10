# Client setup (`slidein_api.setup`)

The one-shot onboarding flow behind the **Client Setup** screen:

```text
provide context -> generate setup -> review exceptions
                -> connect tools -> test -> activate
```

One engine, no per-client forks: everything here writes the *tenant's own*
workspace. The screen never reports a stage the backend has not proven, and
nothing here invents a business fact.

## Intake endpoints

| Endpoint | Purpose |
|---|---|
| `POST /v1/tenants/{tenant_id}/setup/intake` | Current UI path: persist one free-form intake and return a queued setup run. Accepts pasted notes, supported text/transcript files, and public website URLs. |
| `GET /v1/tenants/{tenant_id}/setup/runs/{run_id}` | Tenant-bound queued/running/complete/failed run state plus current setup status. |
| `GET /v1/tenants/{tenant_id}/setup` | Rich status the screen renders: stage map, checklist, open questions, extraction mode, validation, connections, activation. |
| `POST /v1/tenants/{tenant_id}/setup/generate` | Synchronous compatibility path: extraction → blueprint → profile/offer/ICP saved → status. |
| `POST /v1/tenants/{tenant_id}/setup/answers` | Record decisions (address, sender, lawful basis, approver, …), then regenerate from the same sources. |
| `POST /v1/setup/client` | Legacy deterministic intake for the universal-flow first workflow and readiness state. |

The UI uses the single tenant-scoped intake, not the old dual-call sequence.
Each intake commits a `WorkJob` before dispatch. Local `inline` mode retains
FastAPI background execution; `celery` mode uses durable workers and one Beat
scheduler. Setup completion enqueues the canonical autopilot automatically.
Research is enabled only when a profile, offer, and ICP exist; auto-approval
and sending stay unchanged and new installations keep them disabled.

## Modules

| File | Job |
|---|---|
| `sources.py` | Normalise operator input. Never invents text; refuses local/private website targets, binary formats, and oversized intake (per-source and total caps). A refused source is **shown with its error**, not dropped. |
| `extract.py` | Deterministic profile extraction with provenance: `confirmed` (a source said it), `assumed` (read out of prose), `unknown`. Conflicts are recorded, never silently resolved. |
| `llm.py` | Optional OpenAI-compatible extraction. A model-produced field replaces the deterministic draft only when its source ID and exact supporting quote validate. Provider failure is explicit, never mock success. |
| `questions.py` | The short list of decisions only a human can make (address, sender, lawful basis, approver, ICP, …) and which of them still block. |
| `blueprint.py` | Proposed modules (only capabilities this build implements), terminology, required integrations, approval policy, deployment config. Unsupported asks become `proposed_core_enhancement`, never fake features. |
| `service.py` | Intake runs, generation, answers, status, stage derivation, blockers, and failure-atomic setup writes. |

Set `SLIDEIN_LLM_BASE_URL`, `SLIDEIN_LLM_API_KEY`, and `SLIDEIN_LLM_MODEL`
together to enable LLM extraction. `OPENAI_API_KEY`, optional
`OPENAI_BASE_URL`, and `OPENAI_MODEL` are also recognized. With no provider
configured, extraction remains explicitly deterministic. Partial
configuration fails with `llm_configuration`.

## Invariants

- **No invented facts.** Only source-backed values become profile fields;
  everything else stays a question with its prompt and help text.
- **No silent consequential rules.** Physical postal address, sender, lawful
  basis, and approver are blocking questions; sending policy is written only
  when they are answered.
- **Only real modules.** `blueprint.modules.enabled` is a subset of
  `services.modules.MODULE_IDS`. Unimplemented needs are surfaced as
  proposed enhancements with an honest reason.
- **Never "active" before it is.** `state` is the stage the operator is
  working on; `active` is returned only when the activation service says the
  deployment is live.
- **Secrets stay server-side.** Nothing in a prompt, log, or client-visible
  config carries a credential.

## State

Everything lives under `Tenant.settings["setup"]` (latest run, sources,
answers, draft/provenance, extraction metadata, questions, blueprint summary,
version) plus the normal tenant records (profile, offers, ICPs, deployment
config, connections, suppression). Completed state survives restarts;
regeneration from the same sources is idempotent. In Celery mode the job
ledger survives restarts, duplicate deliveries are claim-protected, and an
expired worker lease is requeued or dead-lettered after its final attempt.
Inline mode remains the non-durable local compatibility path.

## Tests

`tests/test_setup_rich_flow.py` covers generate → answer → status, provenance,
unsupported-capability reporting, unsafe-source refusal, role and tenant
guards, and idempotent regeneration. `tests/test_setup_flow.py` covers the
legacy intake. `tests/test_setup_llm_intake.py` covers background runs,
source-quote grounding, profile/offer/ICP creation, provider failure, partial
configuration, secret-safe errors, and tenant isolation without provider IO.

Docs: `docs/project/CURRENT_STATE.md`, `docs/ADR/0001-refine-not-adopted.md`.
