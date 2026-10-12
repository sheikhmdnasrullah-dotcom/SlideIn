# SlideIn — Self-Hosted Email Infrastructure & Outreach Platform

> **Beta.** An open-core platform for prospecting and personalized outreach
> on your own infrastructure: authenticated sending, deliverability
> engineering, lead verification, warmup, and a universal multi-tenant core
> with governed product learning. Live reference deployment:
> **https://www.slideinventure.com** (owner-operated, single tenant).

## The problem

Sending email from your own infrastructure means owning the unglamorous
parts: SPF/DKIM/DMARC alignment, bounce and complaint handling, suppression
lists, warmup pacing, lead verification — and knowing whether a message was
*accepted*, *delivered*, or actually *placed*. Scaling outreach beyond one
business adds a harder problem: keeping every tenant's business knowledge
private while still improving the shared product. SlideIn puts the transport,
the safety gates, the verification, and the tenant/shared boundary in one
inspectable stack.

## Who it's for

Backend engineers and solo founders who want to self-host outreach
infrastructure, learn deliverability engineering, or evaluate a documented
reference implementation. Not for bulk unsolicited mail: suppression and
consent hygiene are enforced, not optional.

## How it works

```
                     one VPS (reference deployment)
┌──────────────────────────────────────────────────────────────┐
│ Caddy :80/:443 ──TLS──▶ www/app (dashboard :3001)            │
│                      ▶ track (GoPhish landing :8080)         │
│                      ▶ warmbly.* (warmup platform)           │
│                                                              │
│ dashboard ──localhost──▶ GoPhish :8333 ──SMTP AUTH──▶ KumoMTA │
│   │                      (3 sending profiles)      :2587     │
│   │                                                        DKIM + shaping
│   ├──▶ job_api :8091 ──▶ reacher :8090 (lead verification)   │
│   ├──▶ agent-reach CLI (research evidence: pages, GitHub)    │
│   └──▶ product/core (tenant contexts, versioned defaults,    │
│        scoped memory, learning candidates, eval suites)      │
└──────────────────────────────────────────────────────────────┘
```

Every send passes eligibility checks (suppression, circuit breaker,
authentication) before dispatch, and every outcome lands in a queryable
event store. Every tenant's business knowledge stays tenant-private; shared
behavior changes only through versioned, evaluated releases. Docs:
`docs/architecture/OVERVIEW.md`,
`docs/architecture/CORE_VS_TENANT_BOUNDARIES.md`.

## Current status (verified 2026-10-12)

| Area | Status |
|---|---|
| Live VPS (single host, 18 containers + systemd + pm2) | ✅ Healthy |
| Public HTTPS: dashboard, tracking, warmup UI/API | ✅ 200s, LE certs |
| Mail auth (SPF/DKIM/DMARC, 3 domains) + precheck | ✅ Green |
| SMTP AUTH over STARTTLS; GoPhish 3/3 profiles via KumoMTA | ✅ Verified, zero-send probes |
| Lead verification (single + bulk CSV + SSE + download) | ✅ Verified live |
| Universal core Stage 1 (isolation, versioning, scopes) | ✅ 22 boundary tests green |
| Local stack (`./dev` + `./doctor`), e2e 8/8, platform 8/8 | ✅ Green |
| Go suite (13 pkgs), deliverability suite (103 tests) | ✅ Green |
| Warmup platform (self-hosted Warmbly, SMTP via KumoMTA) | ⚠️ Stack healthy; mailbox connect pending |
| Receiving/IMAP for our domains (mailcow era ended) | ❌ Not hosted; replies go nowhere |
| Multi-customer SaaS, billing, human-approval queue | ❌ Planned, not implemented |

Full matrix: `docs/project/CURRENT_STATE.md`. Debt register:
`docs/project/TECHNICAL_DEBT.md`.

## Tech stack

Go (campaign/admin app, Warmbly platform) · Python (deliverability engine,
FastAPI product layer, universal core, job_api, agent-reach) · Rust
(reacher verification engine) · Lua (KumoMTA policy) · Node.js
(warmup) · Next.js + TypeScript (dashboard) · Docker Compose, Caddy,
PostgreSQL, SQLite, Redis, NATS, Prometheus/Grafana.

## Quick start (tested)

Prerequisites: Go 1.24+, Python 3.12+, Node.js 20+, Docker Desktop.

```bash
git clone https://github.com/sheikhmdnasrullah-dotcom/SlideIn.git && cd SlideIn
./dev            # boots everything; ends with ./doctor (exit 0 = healthy)
./doctor         # re-check anytime
python3 test_e2e_local_flow.py   # 8/8: gate → KumoMTA → Mailpit → trace
./stop           # clean shutdown
```

Open: API `http://127.0.0.1:8088/?api_key=<key>`, Mailpit
`http://127.0.0.1:8025`, Go admin `http://127.0.0.1:3333`.
Details: `docs/development/LOCAL_SETUP.md`.

Production (one VPS, port 25 open): `kumomta-lab/scripts/deploy-production.sh`
(full script, idempotent), DNS via `docs/deployment/DNS_RECORDS.md`,
verify with `precheck.py`. The script has completed live runs; see
`docs/deployment/PRODUCTION_READINESS.md` for the honest remaining items.

## Configuration

Copy `.env.example` to `.env` (gitignored) and fill placeholders:

```bash
KUMO_AUTH_PASS=        # KumoMTA submission password (env-provided, rotated)
WEBHOOK_SECRET=        # required for provider webhook routes
SLIDEIN_API_KEY=       # workspace key (or: python3 deliverability/cli.py show-key)
```

Per-service JSON configs (`config.json`, `warmup-engine/accounts.json`,
…) are gitignored; examples live beside each service. Never commit real
values — CI enforces this (`scripts/check-secrets.sh`).

## Minimal example

```bash
KEY=$(python3 deliverability/cli.py show-key)
curl -H "X-API-Key: $KEY" http://127.0.0.1:8088/v1/status
curl -H "X-API-Key: $KEY" -X POST http://127.0.0.1:8088/v1/drafts/score \
  -H 'Content-Type: application/json' \
  -d '{"subject":"Intro","body_text":"Hello world"}'
```

API reference: `docs/api/API_OVERVIEW.md`.

## Testing & development

```bash
go test ./...
python3 -m unittest discover -s deliverability/tests -p "test_*.py"
.venv/bin/python -m pytest kumomta-lab/tests -q
.venv/bin/python -m pytest product/tests/test_core_boundaries.py -q  # 22 boundary tests, DB-free
bash scripts/check-secrets.sh
```

Matrix, CI mapping, and last-verified results: `docs/development/TESTING.md`.
(Product API tests need PostgreSQL; CI provides it.)

## Self-hosting

Designed for one host: `./dev` topology plus production KumoMTA policy,
public DNS, and Caddy TLS. Guide: `docs/deployment/SELF_HOSTING.md`.
Production readiness checklist: `docs/deployment/PRODUCTION_READINESS.md`.
DNS record reference: `docs/deployment/DNS_RECORDS.md`.

## Security & privacy

- Workspace API keys (constant-time compare, rotation CLI), workspace-scoped
  access, HMAC webhooks with fail-closed secrets, SSRF allowlists.
- Suppression + circuit breaker enforced at every live send site.
- Tenant isolation enforced in code: cross-tenant reads raise, global search
  excludes tenant-private memory, agents cannot approve promotions, shared
  changes are versioned + evaluated + rollback-able
  (`docs/architecture/CORE_VS_TENANT_BOUNDARIES.md`).
- Threat model: `docs/security/THREAT_MODEL.md`. Report vulnerabilities
  privately per `SECURITY.md` — never in a public issue.

## Limitations

Single-host design; SQLite stores without cross-transactions; our domains
have no receiving/IMAP mailboxes yet; Warmbly mailbox connection is a manual
UI step; product API needs PostgreSQL; no human-approval queue yet; the live
deployment is single-tenant (owner-operated), not multi-customer SaaS. Debt
register: `docs/project/TECHNICAL_DEBT.md`.

## Roadmap

Staged plan with honest status labels: `ROADMAP.md`. Audit trail:
`docs/project/PROJECT_AUDIT.md`. Decisions: `docs/decisions/`.

## Contributing

Small, tested, documented PRs welcome. Read `CONTRIBUTING.md` and the
[Contributor Covenant](CODE_OF_CONDUCT.md) first. Keep every suite green.

## License

MIT — see `LICENSE`. The Go backend derives from
[Gophish](https://github.com/gophish/gophish) (MIT, © Jordan Wright);
original copyright and permission notices are preserved. SlideIn
modifications © Nasrullah Tanim. Warmbly (`warmbly/` overlay config only —
upstream images), reacher (`reacherhq/backend` image), and Agent-Reach
(upstream repo) retain their own licenses; see `NOTICE`.

## Managed SaaS

No multi-customer hosted offering exists today. The live sites are the
owner's own single-tenant deployment, not a product. The intent — open-core,
paid hosting for convenience, self-hosting forever first-class — is
documented in `docs/deployment/MANAGED_SERVICE_PLAN.md`. Nothing there is a
product, price, or commitment.
