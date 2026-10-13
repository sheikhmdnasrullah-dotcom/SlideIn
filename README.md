# SlideIn — private outreach systems, installed with one command

> **Beta.** Prospecting, authenticated sending, and deliverability
> engineering on infrastructure you own. One terminal command installs the
> whole stack on a fresh VPS; the dashboard opens with a business intake
> form, and research agents work from your profile from there.

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

## First run: how it actually works

1. **Business setup (intake).** Fresh installs land on the intake form:
   business identity, offers, and ideal-customer profile (titles,
   industries, sizes, geographies, pains, disqualifiers). Saved on your
   server only (`.data/business-profile.json`, validated + atomic
   writes) — agents read it from there.
2. **Research prospects.** Prospect Research enriches each lead with
   sourced web evidence — and now judges offer-fit against your saved
   business profile, so personalization references *your* offers only
   when the evidence supports it.
3. **Work opportunities.** Qualified prospects land in Opportunities;
   lead verification (single + bulk) filters undeliverables first.
4. **Run outreach.** Missions & Outreach sends through your KumoMTA
   profiles with suppression, eligibility, and circuit-breaker gates.
5. **Stay warm.** Warmbly warms mailboxes and the deliverability CLI
   (`precheck`) keeps SPF/DKIM/DMARC green.

## The problem it solves

Sending from your own infrastructure means owning SPF/DKIM/DMARC
alignment, bounces, suppression, warmup pacing, verification — and
knowing whether a message was *accepted*, *delivered*, or *placed*.
Scaling beyond one business adds tenant isolation: every client's
knowledge stays private while the shared product improves through
governed releases. SlideIn puts transport, safety gates, verification,
and the tenant/shared boundary in one inspectable, self-hostable stack.

Who it's for: engineers and founders who want private outreach
infrastructure or a documented deliverability reference. Not for bulk
unsolicited mail — suppression and consent hygiene are enforced.

## What runs where

```
                 one VPS (per install — your IP, your reputation)
┌────────────────────────────────────────────────────────────┐
│ Caddy :80/:443 ──TLS──▶ app.<base> + apex (dashboard :3001)│
│                      ▶ console.<base> (GoPhish UI :8333)    │
│                      ▶ track.<base> (landing/pixels :8080)  │
│                      ▶ warmbly.* (warmup platform)          │
│                                                            │
│ dashboard ──localhost──▶ GoPhish :8333 ──AUTH──▶ KumoMTA    │
│   │ intake (.data)     (N sending profiles)      :2587     │
│   │                                              DKIM+shaping│
│   ├──▶ job_api :8091 ──▶ reacher :8090 (verification)      │
│   ├──▶ agent-reach CLI (research evidence)                 │
│   └──▶ product/core (tenant contexts, versioned defaults,  │
│        scoped memory, learning candidates, eval suites)    │
└────────────────────────────────────────────────────────────┘
```

Every send passes eligibility checks before dispatch; outcomes land in a
queryable event store. Docs: `docs/architecture/OVERVIEW.md`,
`docs/architecture/CORE_VS_TENANT_BOUNDARIES.md`.

## Current status (verified 2026-10-13)

| Area | Status |
|---|---|
| One-command installer v0.2.0 | ✅ Dry-run + 18/18 template checks green; blank-VPS proof pending |
| Intake-first dashboard (profile → ICP → research) | ✅ Built; type + store + lint verified, deploy pending |
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

Go (campaign/admin app) · Python (deliverability, product API,
universal core, job_api, agent-reach) · Rust (reacher engine) · Lua
(KumoMTA policy) · Next.js + TypeScript (dashboard) · Docker Compose,
Caddy, PostgreSQL, SQLite, Redis, NATS, Prometheus/Grafana.

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
go test ./...
python3 -m unittest discover -s deliverability/tests -p "test_*.py"
.venv/bin/python -m pytest product/tests/test_core_boundaries.py -q
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

MIT — see `LICENSE`. The Go backend derives from
[Gophish](https://github.com/gophish/gophish) (MIT, © Jordan Wright).
SlideIn modifications © Nasrullah Tanim. Warmbly, reacher, and
Agent-Reach retain their own permissive licenses; see `NOTICE`.

## Managed private installs — $350/mo

Don't want to operate this? Managed installs on **your own VPS**:
setup, monitoring, deliverability reviews, and warmup guidance — your
infrastructure and data stay yours. Open a GitHub issue to start.
