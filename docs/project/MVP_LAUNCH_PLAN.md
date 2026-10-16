# MVP and Launch Plan: First White-Label Pilot

Date: 2026-10-16. Derived from the baseline audit + research, not from
marketing copy. No pilot-vertical evidence exists in the repo, so the plan
names decision criteria + a validation experiment instead of inventing
market certainty.

## Pilot vertical: decision, not assumption

Candidate verticals (mortgage / fitness / finance) have no supporting
evidence in-repo (no customer notes, no LOIs, no usage data). Do not build
three dashboards. Pick ONE pilot by this scorecard:

1. A named, reachable buyer willing to co-design (highest weight).
2. Workflow fits the existing pipeline (prospect → research → qualify →
   draft → approve → send → reply) with terminology changes only.
3. Sending identity obtainable (their domain + ESP account).
4. No industry-regulated data in phase 1 (defer anything needing
   compliance review).
5. Pays or pre-pays the pilot fee.

**Validation experiment (1–2 weeks):** 5 discovery calls per vertical with
a clickable slidein-app prototype (branded shell + one workflow); advance
the vertical with ≥2 buyers agreeing to a paid 30-day pilot. If none
qualifies, sell the managed service manually before writing more code.

## MVP scope (phase 1)

**In:**

- Client-branded workspace shell (tenant name/logo/theme via new branding
  API) + the missing `page.tsx` bodies for: Overview, Discovery,
  Research, Qualification, Personalization, Outreach, Conversations,
  Activity, Profile/Settings. Server-rendered through the existing BFF.
- One industry template (pilot vertical): modules, nav, terminology,
  pipeline stages. Additive apply, versioned.
- Core workflow end-to-end: manual CSV ingest → research → rubric qualify
  → evidence-backed drafts → human approval → ESP send via tenant identity
  → keyword reply classification → activity/suppression/quarantine.
- One ESP adapter (pick SES/Postmark/Resend with the pilot) with
  bounce/complaint ingestion + suppression enforcement.
- Tenant isolation tests: two brands, module gating server-side, 404
  cross-tenant, role enforcement.
- Marketing copy fix: replace "finds prospects / agentic" with what the
  product does, or gate those claims until the capability ships.

**Out (explicitly deferred):**

- Second vertical, custom fields engine, visual workflow builder.
- Agent framework (no justified use-case yet), voice, chat widget.
- Booking (phase 2 via paid Cal.com Platform, only if pilot needs it).
- Prospect-data vendor API (manual ingest suffices; add with DPA later).
- Self-hosted mail stack for client mail (rejected).
- n8n/Windmill/Twenty embedding (rejected or deal-gated, see research).

## Implementation sequence

1. ✅ Tenant branding + module registry API + tests (this session).
2. slidein-app front-layer repair + section pages. First repair (all
   verified broken, see audit): route `operations` import source, 3
   `delete`-keyword parse errors, `metadata.ts` `./types` import,
   undefined `LayoutProps`/`cn`/`ApiRequestError` names; prove `next build`
   + a sensitive `tsc` pass. Then build section pages (Overview →
   Activity) + tenant theme provider + module-gated nav from the new
   branding/modules BFF operations. Each page: real BFF data, empty/error
   states, no mocks.
3. Template v1 for the pilot vertical + additive-apply endpoint + tests.
4. ESP adapter #1 (sandbox → pilot domain), event ingestion, suppression.
5. Onboarding runbook: create tenant → keys → branding → template →
   sending identity → test send → go-live checklist.
6. Pilot hardening: rate limits, audit coverage, backup/restore of tenant
   DB, incident runbook.
7. Marketing + pricing pages rewritten to match shipped behavior.

## Dependencies and risks

| Risk | Mitigation |
|---|---|
| No pilot buyer yet | Scorecard + experiment before phase-2 code |
| slidein-app has zero pages today | Sequence step 2 is the critical path |
| ESP deliverability for a new domain | Warmup plan, caps, suppression; dry_run default stays |
| Scheduler/daemon binding unknown | Phase-1 sends are API-triggered; cron/systemd proof before any automation claims |
| AGPL/SUL license traps | Shortlist avoids them; legal-review queue in research doc |
| workspace-app confusion (two consoles) | Document: workspace-app = operator-only; clients never log in there |

## Acceptance criteria (pilot go-live)

- Two tenants with different brands/modules render correctly; no leakage
  (data, branding, or activity) across tenants — proven by tests + manual run.
- One complete workflow runs end-to-end on the pilot tenant: ingest →
  send → reply → suppression, with approval gates enforced.
- Every send traces to tenant identity + policy + approval actor.
- Bounce/complaint → suppression within one ingestion cycle.
- Build + lint + typecheck + full pytest green on both repos' touched areas.
- Marketing claims match shipped behavior; pricing page live or removed.

## Effort ranges (assumptions, not promises)

Assumes one senior full-stack engineer, existing stack, no new infra:

| Item | Range | Assumption |
|---|---|---|
| Branding + modules API | 0.5–1 wk | Done this session incl. tests |
| slidein-app pages + theme | 2–3 wk | 9 sections, BFF exists, no new components lib |
| Template v1 + apply | 0.5–1 wk | JSON doc + endpoint + tests |
| ESP adapter + events | 1–2 wk | One vendor, sandbox available |
| Onboarding + hardening | 1 wk | Single VPS, SQLite→Postgres path known |
| Copy + pricing fix | 0.5 wk | — |
| **Total to pilot** | **~5–8 wk** | After the vertical is chosen |

## Reuse vs build

- **Reuse now**: slidein-api services/runtime/contracts, BFF client, Go
  sender knowledge, KumoMTA lab learnings, Refine later for admin.
- **Build now**: branding/modules API, pages, template, ESP adapter.
- **Buy later**: ESP usage, Cal.com Platform, one data vendor, LangSmith/
  tracing — all usage-based, all after a paying pilot.
