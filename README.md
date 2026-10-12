# SlideIn — Self-Hosted Email Infrastructure & Deliverability Platform

> **Alpha.** A modular, test-covered toolkit for sending email through your
> own infrastructure with honest deliverability engineering: authenticated
> transport, pre-send gates, suppression hygiene, and verifiable telemetry.
> No hosted service exists yet; everything here runs on your machine.

## The problem

Sending email from your own infrastructure means owning the unglamorous
parts: SPF/DKIM/DMARC alignment, bounce and complaint handling, suppression
lists, warmup pacing, and knowing whether a message was *accepted*, *delivered*,
or actually *placed*. SlideIn puts those parts — MTA policy, safety gates,
provider abstraction, and audit trails — in one inspectable stack.

## Who it's for

Backend engineers and solo founders who want to self-host email
infrastructure, learn deliverability engineering, or evaluate a documented
reference implementation. Not for bulk unsolicited mail: suppression and
consent hygiene are enforced, not optional.

## How it works

```
operator ──▶ Go admin app :3333 ──SMTP AUTH──▶ KumoMTA :2587 ──▶ MXes
                    │                              ▲ DKIM + shaping
Python API :8088 ───┘                              │
  gate → risk → breaker → suppression → provider ──┘
  (local: everything terminates in Mailpit :1025 — no internet egress)
```

Every send passes eligibility checks (suppression, circuit breaker,
authentication) before dispatch, and every outcome lands in a queryable
event store. Docs: `docs/architecture/OVERVIEW.md`.

## Current status (verified 2026-10-12)

| Area | Status |
|---|---|
| Local stack (`./dev` + `./doctor`) | ✅ Fully operational |
| End-to-end send (KumoMTA → Mailpit, DKIM verified) | ✅ 8/8 green |
| Platform suite (API auth, inbound AI, thread stitching) | ✅ 8/8 green |
| Go suite (13 pkgs), deliverability suite (103 tests) | ✅ Green |
| Production deploy scripts | ⚠️ Statically verified; no live VPS run |
| Product API, Next.js dashboard, AI research | ⚠️ Partial / early-stage |
| Managed SaaS, billing, human-approval queue | ❌ Planned, not implemented |

Full matrix: `docs/project/CURRENT_STATE.md`.

## Tech stack

Go (campaign/admin app) · Python stdlib-only (deliverability engine) · Lua
(KumoMTA policy) · Node.js + BullMQ (warmup) · FastAPI + PostgreSQL
(product layer) · Next.js + TypeScript (dashboard) · Docker Compose, SQLite,
Redis, Mailpit.

## Quick start (tested)

Prerequisites: Go 1.24+, Python 3.12+, Node.js 20+, Docker Desktop.

```bash
git clone <repo-url> && cd slidein
./dev            # boots everything; ends with ./doctor (exit 0 = healthy)
./doctor         # re-check anytime
python3 test_e2e_local_flow.py   # 8/8: gate → KumoMTA → Mailpit → trace
./stop           # clean shutdown
```

Open: API `http://127.0.0.1:8088/?api_key=<key>`, Mailpit
`http://127.0.0.1:8025`, Go admin `http://127.0.0.1:3333`.
Details: `docs/development/LOCAL_SETUP.md`.

## Configuration

Copy `.env.example` to `.env` (gitignored) and fill placeholders:

```bash
KUMO_AUTH_PASS=        # KumoMTA submission password (local default: local-dev-password)
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
bash scripts/check-secrets.sh
```

Matrix, CI mapping, and last-verified results: `docs/development/TESTING.md`.

## Self-hosting

Designed for one host: `./dev` topology plus production KumoMTA policy,
public DNS, and TLS. Guide: `docs/deployment/SELF_HOSTING.md`. Production
readiness checklist (open items flagged): `docs/deployment/PRODUCTION_READINESS.md`.

## Security & privacy

- Workspace API keys (constant-time compare, rotation CLI), workspace-scoped
  access, HMAC webhooks with fail-closed secrets, SSRF allowlists.
- Suppression + circuit breaker enforced at every live send site.
- Threat model: `docs/security/THREAT_MODEL.md`. Report vulnerabilities
  privately per `SECURITY.md` — never in a public issue.

## Limitations

Single-host design; no distributed queue; three SQLite stores without
cross-transactions; dashboard tree duplicated pending canonical choice;
product API needs PostgreSQL; no human-approval queue yet; production path
unexercised. Debt register: `docs/project/TECHNICAL_DEBT.md`.

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
modifications © Nasrullah Tanim.

## Managed SaaS

No hosted offering exists today. The intent — open-core, paid hosting for
convenience, self-hosting forever first-class — is documented in
`docs/deployment/MANAGED_SERVICE_PLAN.md`. Nothing there is a product, price,
or commitment.
