# Client setup (`slidein_api.setup`)

The one-shot onboarding flow behind the **Client Setup** screen:

```text
provide context -> generate setup -> review exceptions
                -> connect tools -> test -> activate
```

One engine, no per-client forks: everything here writes the *tenant's own*
workspace. The screen never reports a stage the backend has not proven, and
nothing here invents a business fact.

## Two entry points, one screen

| Endpoint | Purpose |
|---|---|
| `POST /v1/setup/client` | **Intake of record** (see `setup_service.py`): a transcript/notes in, business profile + universal-flow first workflow + readiness out. |
| `GET  /v1/tenants/{tenant_id}/setup` | Rich status the screen renders: stage map, checklist, open questions, validation stages, connections, activation. |
| `POST /v1/tenants/{tenant_id}/setup/generate` | Deterministic extraction → blueprint → profile/offer/ICP saved → status. |
| `POST /v1/tenants/{tenant_id}/setup/answers` | Record decisions (address, sender, lawful basis, approver, …), then regenerate from the same sources. |

`POST /setup/client` is the intake of record for a client's context; the
tenant-scoped endpoints keep the per-stage state the screen renders. The UI
action calls both so neither store is left behind.

## Modules

| File | Job |
|---|---|
| `sources.py` | Normalise operator input. Never invents text; refuses local/private website targets, binary formats, and oversized intake (per-source and total caps). A refused source is **shown with its error**, not dropped. |
| `extract.py` | Deterministic profile extraction with provenance: `confirmed` (a source said it), `assumed` (read out of prose), `unknown`. Conflicts are recorded, never silently resolved. |
| `questions.py` | The short list of decisions only a human can make (address, sender, lawful basis, approver, ICP, …) and which of them still block. |
| `blueprint.py` | Proposed modules (only capabilities this build implements), terminology, required integrations, approval policy, deployment config. Unsupported asks become `proposed_core_enhancement`, never fake features. |
| `service.py` | Orchestration + status: `generate` / `answer` / `status`, stage derivation, blockers. |

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

Everything lives under `Tenant.settings["setup"]` (sources, answers, draft,
questions, blueprint summary, version) plus the normal tenant records
(profile, offers, ICPs, deployment config, connections, suppression). It
survives restarts; regeneration from the same sources is idempotent.

## Tests

`tests/test_setup_rich_flow.py` covers generate → answer → status, provenance,
unsupported-capability reporting, unsafe-source refusal, role and tenant
guards, and idempotent regeneration. The intake endpoint is covered by
`tests/test_setup_flow.py`.

Docs: `docs/project/CURRENT_STATE.md`, `docs/ADR/0001-refine-not-adopted.md`.
