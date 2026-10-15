# Architecture Overview — SlideIn

> As-built description, verified 2026-10-16. Design rationale: `../decisions/ADR-0001-initial-architecture.md`.

SlideIn is a **modular monolith per runtime**: an agentic workflow API
(`slidein-api/`: configure → discover → research → qualify → personalize →
outreach → converse), a Go campaign/admin app, a Python deliverability
engine, KumoMTA as the outbound MTA, Redis for queues, and SQLite stores
per component. Default deployment is three processes plus containers on
one machine; production design targets a single VPS.

```
operator ──browser──▶ Go admin app :3333 (campaigns, profiles, templates, RBAC)
                         │ SQLite gophish.db
                         │ SMTP submit ──▶ KumoMTA :2587 (AUTH/TLS, DKIM) ──▶ MXes
                         ▼
deliverability/ (Python :8088) ── provider abstraction ──┬──▶ KumoMTA :2587
  gate → placement risk → circuit breaker → suppression  ├──▶ Mailpit :1025 (dev)
  review dashboards · inbound webhooks · CLI             └──▶ SMTP relays (prod opt)
                         │ SQLite deliverability_state.db + campaign_outreach.db
warmup-engine (Node + BullMQ/Redis) · product/ (FastAPI :8000 → PostgreSQL,
  early-stage) · dashboard (Next.js :3000, early-stage) · sink-mx (hermetic tests)
```

Key properties: one approved outbound path per runtime with fail-closed
safety checks; local stacks never reach the internet (Mailpit/sink
termination); no shared transactions across stores (see `COMPONENTS.md`).
Module details: `COMPONENTS.md`. Lifecycles: `DATA_FLOW.md`. Topologies:
`DEPLOYMENT_MODEL.md`.

## Four-plane view

```
CONTROL PLANE:   Workspaces · Domains · Profiles · Contacts · RBAC
DATA PLANE:      Gate · Placement risk · Personalization · Suppression
TRANSPORT:       Provider abstraction (Mailpit / KumoMTA / SMTP relays)
OBSERVABILITY:   Send events · Webhook ingest · Circuit breaker
```

## Repository map

| Component | Directory | Entrypoint |
|---|---|---|
| Agent workflow API | `slidein-api/` (FastAPI) | `python run.py` → `:8100` |
| Client workspace UI | `slidein-app/` (Next.js) | `npm run dev` → `:3200` |
| Go admin/API backend | `controllers/`, `models/`, `worker/`, `gophish.go` | `./gophish_local --config=config.local.json` → `:3333` |
| Deliverability engine | `deliverability/` (`core/`, `server.py`) | `python3 deliverability/server.py` → `:8088` |
| KumoMTA policy lab | `kumomta-lab/` (`policy/*.lua`, `compose/`) | `docker-compose.local.yml` |
| Warmup engine | `warmup-engine/` | `cd warmup-engine && npm start` |
| Product API | `product/` (FastAPI) | `:8000` (needs PostgreSQL) |
| Dashboard | `project/` (duplicate: `workspace-app/`) | `npm run dev` → `:3000` |
| Local stack | repo root | `./dev`, `./doctor`, `./stop` |

Stores: `gophish.db` (campaigns), `deliverability_state.db`
(gate/circuit/events), `campaign_outreach.db`, `warmup.db` (all SQLite);
PostgreSQL (product layer); Redis (queues/cache).
