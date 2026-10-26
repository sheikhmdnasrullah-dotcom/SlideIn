# SlideIn

> **An agentic system that finds prospects, captures leads, and reaches out to them.**

[![License: BSL 1.1](https://img.shields.io/badge/License-Business%20Source%201.1-000000?logo=bookseller)](LICENSE)
[![Go](https://img.shields.io/badge/Go-1.21%2B-00ADD8?logo=go&logoColor=white)](https://go.dev)
[![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)](https://python.org)
[![Next.js](https://img.shields.io/badge/Next.js-16-black?logo=next.js&logoColor=white)](https://nextjs.org)
[![KumoMTA](https://img.shields.io/badge/KumoMTA-Apache--2.0-orange)](https://github.com/KumoCorp/kumomta)

One self-hosted stack for the entire outbound motion: prospect research,
lead qualification, personalized outreach, campaign management, and the
deliverability infrastructure to land it — on a VPS and sender domains you
own. **Beta.**

## The loop

Everything in the repo serves one pipeline with three jobs:

1. **Find prospects.** Research agents enrich each lead with sourced web
   evidence, then judge offer-fit against your saved business profile — so
   personalization references *your* offers only when the evidence
   supports it.
2. **Capture leads.** Qualified prospects land in Opportunities. Lead
   verification (single + bulk) filters undeliverable addresses before a
   single send, and every qualification decision is recorded with
   provenance.
3. **Reach out.** Missions & Outreach dispatches through your KumoMTA
   sending profiles with suppression, eligibility, and circuit-breaker
   gates. Warmbly keeps mailbox reputation warm; inbound replies are
   stitched, classified by intent, and routed back into the loop.

## Install on your VPS

Prerequisites: Ubuntu 22.04/24.04 x86_64 VPS (4GB+ RAM) with **outbound
port 25 open**, one base domain for the software, one or more sender
domains, and DNS control. As root:

```bash
curl -fsSL https://raw.githubusercontent.com/sheikhmdnasrullah-dotcom/SlideIn/main/install.sh \
  | bash -s -- --base-domain client.com \
             --mail-domains send1.com,send2.com \
             --admin-email you@client.com
```

The installer (idempotent, dry-run with `--dry-run`) provisions Docker,
Caddy + HTTPS, KumoMTA (per-domain DKIM), GoPhish (built + configured,
`senders × domains` profiles), the Next.js dashboard, lead verification,
Warmbly warmup, monitoring, and the deliverability CLI — then prints your
exact DNS table and next steps. Full guide: `INSTALL.md`.

**Instant local preview** (before DNS propagates):

```bash
ssh -L 3001:localhost:3001 root@<your-vps-ip>
# open http://localhost:3001 — the dashboard, live from your VPS
```

After DNS: `https://app.<base>/` (dashboard),
`https://console.<base>/login` (campaign console),
`https://track.<base>/` (landing/pixels).

## Architecture

### One VPS, six planes

Every install is a single-tenant stack on one VPS — your IP, your
reputation, your data. Nothing phones home.

```
┌──────────────────────────── ONE VPS PER INSTALL ────────────────────────────┐
│                                                                              │
│  AGENT LAYER         configure → discover → research → qualify →             │
│  slidein-api :8100   personalize → outreach → converse                       │
│  (FastAPI · explicit stage contracts · stage_runs + activity audit)          │
│                                                                              │
│  CONTROL PLANE       workspaces · domains · profiles · campaigns · RBAC      │
│  Go app :3333 / GoPhish :8333            (SQLite gophish.db)                 │
│                                                                              │
│  DELIVERABILITY      gate → placement risk → circuit breaker → suppression   │
│  engine :8088        ├─▶ KumoMTA :2587 (AUTH/TLS · DKIM) ──▶ recipient MX    │
│                      └─▶ Mailpit :1025 (dev only — local stacks never        │
│                          reach the internet)                                 │
│                                                                              │
│  WARMTH &            warmup-engine (BullMQ/Redis) · reacher :8090/:8091      │
│  VERIFICATION        (email verification, single + bulk)                     │
│                                                                              │
│  FRONTENDS           dashboard :3001 · slidein-app :3200 · GoPhish console   │
│  Caddy :443 (TLS) ─▶ app · console · track · warmbly.<base>                  │
│                                                                              │
│  OBSERVABILITY       Prometheus · Grafana · queryable send-event store ·     │
│                      inbound webhooks                                        │
└──────────────────────────────────────────────────────────────────────────────┘
```

Design properties: one approved outbound path per runtime with
fail-closed safety checks; no shared transactions across stores
(`docs/architecture/COMPONENTS.md`); tenant-private knowledge stays
private while shared defaults are versioned, evaluated, and rollback-able
(`docs/architecture/CORE_VS_TENANT_BOUNDARIES.md`).

### The agent workflow

```
configure ──▶ discover ──▶ research ──▶ qualify ──▶ personalize ──▶ outreach ──▶ converse
   │             │            │            │             │             │            │
 profile      prospects    evidence    qualification   drafts      sent mails   replies
 offers       provenance  provenance   offer match   (versioned)   + policy   + intent
 icps                                                                             │
                                                        overview ◀── activity ◀──┘
```

Every arrow is a declared contract (`docs/architecture/CONTRACTS.md`):
required inputs, produced outputs, permitted status transitions, failure
codes with retry behaviour, and the recovery action to surface. Nothing
advances implicitly — `StageRunner` validates each call and records a
`stage_runs` row before and after.

### Repository map

| Component | Directory | Entrypoint |
|---|---|---|
| Agent workflow API | `slidein-api/` | `python run.py` → `:8100` (`/docs`) |
| Client workspace UI | `slidein-app/` (Next.js 16, App Router) | `npm run dev` → `:3200` |
| Dashboard | `workspace-app/` | `npm run dev` → `:3001` |
| Go campaign/admin app | `controllers/`, `models/`, `worker/`, `gophish.go` | `./gophish_local --config=config.local.json` → `:3333` |
| Campaign console (GoPhish) | `gophish-config-production.json` + `kumomta-lab/` | `:8333` (loopback) |
| Deliverability engine | `deliverability/` (`core/`, `server.py`) | `python3 deliverability/server.py` → `:8088` |
| Universal multi-tenant core | `product/` (FastAPI) | `:8000` (needs PostgreSQL) |
| KumoMTA policy lab | `kumomta-lab/` (`policy/*.lua`, `compose/`) | `docker-compose.local.yml` |
| Warmup engine | `warmup-engine/` | `npm start` |
| Lead verification | `reacher/` (Rust engine + job_api) | `:8090` / `:8091` |
| Warmup platform overlay | `warmbly/` | `docker-compose.yml` |
| Local stack | repo root | `./dev`, `./doctor`, `./stop` |

Stores: `gophish.db` (campaigns), `deliverability_state.db`
(gate/circuit/events), `campaign_outreach.db`, `warmup.db` (all SQLite);
PostgreSQL (product + agent layer); Redis (queues/cache).

Full docs: `docs/architecture/OVERVIEW.md` (as-built),
`docs/architecture/SYSTEM_ARCHITECTURE.md` (authoritative spec),
`docs/architecture/CONTRACTS.md` (stage contracts).

## Current status (verified 2026-10-13)

| Area | Status |
|---|---|
| One-command installer v0.2.0 | ✅ Dry-run + 18/18 template checks green; blank-VPS proof pending |
| Intake-first dashboard (profile → ICP → research) | ✅ Built; type + store + lint verified, deploy pending |
| Agent workflow API (slidein-api) + client workspace (slidein-app) | ✅ Built; contracts + stage runs + activity audit |
| Live reference VPS (18 containers + systemd + pm2) | ✅ Healthy |
| Public HTTPS: dashboard, console, tracking, warmup | ✅ 200s, LE certs |
| Mail auth (SPF/DKIM/DMARC) + precheck | ✅ Green |
| SMTP AUTH/STARTTLS; GoPhish 9/9 profiles via KumoMTA | ✅ Verified live sends |
| Lead verification (single + bulk + SSE + download) | ✅ Verified live |
| Universal core Stage 1 | ✅ 22 boundary tests green |
| Go suite, deliverability suite (103), e2e 8/8 | ✅ Green |
| Warmup platform (Warmbly via KumoMTA) | ⚠️ Healthy; mailbox connect is a manual UI step |
| Receiving/IMAP for our domains | ❌ Not hosted |
| Multi-customer SaaS, billing, human-approval queue | ❌ Planned, not implemented |

Full matrix: `docs/project/CURRENT_STATE.md`. Debt:
`docs/project/TECHNICAL_DEBT.md`.

## Tech stack

Go (campaign/admin app) · Python 3.12+ (deliverability, product API,
universal core, slidein-api agent workflow, job_api) · Rust (reacher
engine) · Lua (KumoMTA policy) · Next.js 16 + TypeScript (dashboard,
client workspace) · Docker Compose, Caddy, PostgreSQL, SQLite, Redis,
NATS, Prometheus/Grafana.

## Local development

```bash
git clone https://github.com/sheikhmdnasrullah-dotcom/SlideIn.git && cd SlideIn
./dev            # boots everything; ends with ./doctor (exit 0 = healthy)
./doctor         # re-check anytime
./stop           # clean shutdown
```

Details: `docs/development/LOCAL_SETUP.md`. Develop locally; send from
the VPS (residential IPs are blocklisted).

## Configuration

Service secrets are generated by the installer into root-only files and
never enter git — CI enforces this (`scripts/check-secrets.sh`). Local
dev copies `.env.example` to `.env` and fills placeholders.

## Testing

```bash
# Go (campaign/admin app + core libraries)
gofmt -l . && go vet ./... && go test ./...

# Python — deliverability engine + lab
.venv/bin/python -m pytest deliverability/tests/ -q
.venv/bin/python -m pytest kumomta-lab/tests -q

# Python — universal core boundary tests (DB-free, fast)
.venv/bin/python -m pytest product/tests/test_core_boundaries.py -q

# Secret hygiene — never commit credentials
bash scripts/check-secrets.sh
```

Matrix and last-verified results: `docs/development/TESTING.md`.

## Security & privacy

- Workspace API keys (constant-time compare, rotation CLI),
  workspace-scoped access, HMAC webhooks, SSRF allowlists.
- Suppression + circuit breaker at every live send site.
- Tenant isolation in code: cross-tenant reads raise, global search
  excludes tenant-private memory, shared changes are versioned +
  evaluated + rollback-able.
- Dashboard ships **open** (no login) for first-run simplicity — put
  Caddy `basic_auth` in front before inviting users.
- Threat model: `docs/security/THREAT_MODEL.md`. Report vulnerabilities
  privately per `SECURITY.md`.

## Limitations

Single host per install; SQLite/file stores; no receiving/IMAP; Warmbly
mailbox connect is manual; installer greenfield proof pending; no
human-approval queue yet. Debt register:
`docs/project/TECHNICAL_DEBT.md`.

## Roadmap & contributing

Staged plan: `ROADMAP.md`. Audit trail:
`docs/project/PROJECT_AUDIT.md`. Decisions: `docs/decisions/`.
Small, tested, documented PRs welcome — read `CONTRIBUTING.md` and the
[Contributor Covenant](CODE_OF_CONDUCT.md) first.

## License

SlideIn is licensed under the **Business Source License 1.1**
(see `LICENSE`). Commercial use is permitted for self-hosting on your own
infrastructure under the Additional Use Grant; reselling or operating it
as a hosted service for third parties requires a separate commercial
license from the author (open a GitHub issue).

The Go backend derives from [Gophish](https://github.com/gophish/gophish)
(MIT, © Jordan Wright). Warmbly, reacher, and Agent-Reach retain their
own permissive licenses; see `NOTICE`. A clean-room provenance declaration
is included in `LICENSE`.

## Prospect engagement (planned capability)

The product vision extends past outreach: reply → AI-assisted conversation → direct meeting booking.
Specification: `docs/product/PROSPECT_ENGAGEMENT.md`; architecture: `docs/architecture/ENGAGEMENT_ARCHITECTURE.md`;
tasks: `docs/engineering/IMPLEMENTATION_ROADMAP.md` (Phase 10 expansion); open questions: `docs/project/OPEN_QUESTIONS.md`.
Not built yet; status in `docs/project/CURRENT_STATE.md`.

## About

The internet's most powerful client acquisition secrets, unified into one actionable framework.

[www.slideinventure.com](https://www.slideinventure.com)

### Topics

agentic · campaign-management · docker · email-deliverability · email-verification · go · kumo-mta · lead-generation · multi-tenant · nextjs · outreach · prospecting · python · sales-automation · self-hosted · smtp
