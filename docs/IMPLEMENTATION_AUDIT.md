# Implementation Audit — Adaptive Agentic Workspace

Date: 2026-10-26. Baseline commit: `84bad03` (checkpoint). Auditor: principal-agent session.

## 1. What exists and works (verified)

| Area | State |
|---|---|
| `saas/product/` | Documented agentic core: ARCHITECTURE, CORE_ABSTRACTIONS, AGENTS_DESIGN, DATA_MODEL, API_SPEC, UX_PATTERNS. Implemented: `core/` (tenant context store with hard isolation, universal FSM workflow runner, learning-candidate governance registry, memory, evaluation, scopes/roles, field encryption), `agents/` (9 agent classes incl. LLM-backed real_agents), `api/`, `services/`, `db/` (SQLAlchemy models), `workers/`. |
| Tenant isolation | `TenantConfigStore` enforces caller-tenant checks; boundary tests exist (`test_core_boundaries.py`). |
| Tests (baseline) | 38 passed / 5 failed / 33 errors — ALL failures pre-existing in `test_workflows.py` (opportunity/pipeline fixtures), unrelated to this work. Missing dep `cryptography` installed to unblock collection. |
| `saas/osint_core/`, `saas/visitor_core/`, `saas/unified/` | Real, live-verified enrichment + visitor-capture engines (separate session). Unified server + worker at `unified/`. |
| `slidein-app/` | Existing Next.js client dashboard — currently **tenant-branded for one client ("Finaya Home Loans")** in the latest commit. This is the anti-pattern the mission targets: branding is per-tenant config, not per-tenant code. |
| `slidein-api/` | Flask-blueprints backend (own venv), routes for workspace/branding. |
| Marketing site | Next 16 marketing site (Vercel); `@xyflow/react` (React Flow 12) **already a dependency**. |

## 2. Decisions (see docs/ADR/)

- **Refine**: NOT adopted. slidein-app's existing Next.js App Router + component system is superior and in production; Refine's data-provider/router abstractions would force a parallel routing/auth model. Existing abstractions kept. (ADR-0001)
- **React Flow**: already installed (v12, MIT core). MVP uses it read-only for workflow inspection in a later slice; editor comes after execution parity. (ADR-0003)
- **Twenty CRM**: repo is AGPLv3-dominant with MIT packages — commercial-SaaS embedding risk. Decision: build the internal CRM model as source of truth + a connector interface; Twenty adapter deferred behind the interface. Slidein stays fully functional disconnected. (ADR-0002)
- **LangGraph**: Python (existing backend language; no second language introduced). SQLite checkpointer now, Postgres swap via `langgraph-checkpoint-postgres` later.

## 3. What was implemented (this pass)

1. `product/core/capabilities.py` — typed, code-defined capability registry (11 modules) with permission/integration gating and config-schema validation. Tenants select/configure; they cannot create modules or code.
2. `product/core/workspace.py` — versioned tenant-scoped `WorkspaceConfig`, validation (refs resolve, widget/component support, role visibility), proposal flow with risk policy (low-risk auto-apply opt-in; consequential requires tenant-admin approval), full history + rollback.
3. `product/core/adaptation.py` — evidence store (provenance, confidence, verified/hypothesis), workflow proposals with evidence thresholds (≥2 verified repeats or 1 explicit instruction), workspace-change proposals (presentation-only, validated via registry), all tenant-isolated.
4. `product/services/agentic_workflow.py` — LangGraph service: planning → research → qualification → evaluation → runtime-interrupt approval → finalize; AsyncSqliteSaver checkpoints (resume across process restart), typed handoff (qualification consumes research output), deterministic fallbacks, FAILED/REJECTED terminal states, thread-id tenant scoping.
5. Tests: `test_workspace_adaptation.py` (8) + `test_agentic_workflow.py` (4) — all pass.

## 4. Missing / next slices (priority order)

1. Wire workspace config → slidein-app rendering (module renderer against the saved config; remove the per-tenant branded code path, make branding a config record).
2. LangGraph service → HTTP API + execution-status events to the existing dashboard (reuse unified/ SSE infra).
3. React Flow read-only workflow inspection view (definitions already persist; editor after parity).
4. Postgres persistence for workspace store + checkpointer (in-memory/SQLite now, per existing core style).
5. Twenty connector implementation behind the CRM interface (blocked on licensing decision; alternative: HubSpot/Pipedrive MIT-friendly adapter).
6. Fix pre-existing `test_workflows.py` fixture errors (33 errors, 5 failures — predate this work).

## 5. Risks

- slidein-app branding commit hardcodes one client — must be migrated to tenant-config before onboarding a second tenant.
- Learning governance (`learning.py`) and the new adaptation engine are sibling pipelines; consolidate evidence semantics in a future pass.
