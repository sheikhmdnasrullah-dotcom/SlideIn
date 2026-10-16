# Current State — SlideIn

> Living snapshot, last updated 2026-10-16. Source of
> truth for "what works". Detail and evidence: `PROJECT_AUDIT.md` (point-in-time,
> pre-launch). Debt register: `TECHNICAL_DEBT.md`.

SlideIn is a self-hosted outreach platform in **beta**, live on a single VPS
as an owner-operated reference deployment. The SaaS surface now includes the
agent workflow API (`api.slideinventure.com`) and the client workspace UI
(`workspace.slideinventure.com`), alongside the dashboard
(`app`/apex), campaign console, tracking, and warmup hosts (all HTTPS; `www`
is the Vercel marketing site, not served by the VPS). The stack: a modified
GoPhish campaign/admin backend (Go), a Python deliverability engine (gate,
circuit breaker, placement risk, provider abstraction), KumoMTA with a
production Lua policy, a Next.js dashboard wired to local backends, a
reacher-backed lead verification service, a self-hosted Warmbly warmup
platform, Agent-Reach research tooling, a universal multi-tenant core
(`product/core/`) with enforced tenant/shared boundaries, and the new
slidein-api (FastAPI) + slidein-app (Next.js) workflow layer. No
multi-customer SaaS, billing, or human-approval queue exists; the live
deployment is single-tenant.

## Capability matrix

| # | Capability | Status | Evidence |
|---|---|---|---|
| 1 | Go campaign/admin app | Implemented and verified | systemd; 13 Go pkgs ok; admin API live |
| 2 | Deliverability pipeline + safety core | Implemented and verified | 103 Python tests OK; live e2e 8/8 |
| 3 | KumoMTA production policy | Implemented and verified | kumod 2026.09.29; STARTTLS+AUTH verified; v4-only egress (sysctl pin); EHLO mail.nasrullahtanim.me; live delivery to Zoho confirmed |
| 4 | Local dev stack | Implemented and verified | `./dev` + `./doctor` FULLY OPERATIONAL 2026-10-12 |
| 5 | End-to-end local send | Implemented and verified | e2e 8/8 + platform 8/8; DKIM verified at sink |
| 6 | Production VPS deployment | Implemented and verified | 18 containers healthy; deploy script completed live runs; idempotent reruns |
| 7 | Public HTTPS (app/apex/console/track/warmbly×3) + Caddy | Implemented and verified | 200s live; LE certs auto-issued; www is Vercel (CNAME, never VPS) |
| 8 | Mail auth DNS (SPF/DKIM/DMARC ×3) | Implemented and verified | precheck green; Cloudflare API push 2026-10-12 |
| 9 | GoPhish sending profiles (9/9) | Implemented and verified | via KumoMTA relay; 3× nasrullahtanim.me + 6× tanim.social/tanim.tech; dashboard reads live profiles (sanitized) |
| 10 | Dashboard ↔ backend wiring | Implemented and verified | no-login open mode; live profile/verification/job proofs |
| 11 | Lead verification (single + bulk) | Implemented and verified | job lifecycle: upload → SSE → download, real verdicts |
| 12 | Warmup platform (Warmbly self-host) | Implemented, partially verified | 11/11 healthy; SMTP relay proven; mailbox connect is a manual UI step |
| 13 | Research evidence (Agent-Reach) | Implemented and verified | jina page-read live in lead research; gh/bili/yt need logins |
| 14 | Universal core Stage 1 | Implemented and verified | `product/core/` + 22 boundary tests green, DB-free |
| 15 | Suppression on live paths | Implemented and verified | worker + submit gated (8 tests) + live platform pass |
| 16 | HTTP auth/tenancy (deliverability) | Implemented and verified | 401/404 enforcement, 28 tests + live pass |
| 17 | Monitoring (Prom/Grafana/AM/Loki) | Implemented, partially verified | all Up; alert routes untested; no notifier wired |
| 18 | Warmup engine (BullMQ, legacy) | Implemented but unverified | installed; superseded by Warmbly for warmup |
| 19 | Transactional CLI (`cli.py tx-*`) | Implemented but unverified | no live sends run |
| 20 | Product API (FastAPI, tenant model) | Partially implemented | needs PostgreSQL; no alembic; roles unenforced |
| 21 | AI agents (research/personalization) | Partially implemented | Tavily + agent-reach evidence live; mock default elsewhere |
| 22 | Human-approval enforcement | Planned but not implemented | `Message.ai_approved` unset-at-send; no queue |
| 23 | Receiving/IMAP mailboxes | Not implemented | mailcow era ended; replies go nowhere; MX points at dead host |
| 24 | Billing / entitlements | Planned but not implemented | — |
| 25 | Managed multi-tenant SaaS | Planned but not implemented | intent only (`managed-service-plan.md`); core Stage 1 is the foundation |
| 26 | Backups rehearsed | Not implemented | `backup.sh/restore.sh` present, never rehearsed |
| 27 | Campaign console (public GoPhish UI) | Implemented and verified | `console.slideinventure.com/login` 200; loopback binds; CSRF origin fix (bare-host match); dry-run group+template created, zero sends |
| 28 | Bulk-compliance + reputation hygiene | Partially implemented | List-Unsubscribe on 9/9 profiles; IP clean on Spamhaus/SpamCop/SORBS; PTR mail.nasrullahtanim.me forward-confirmed; dmarc@ mailboxes missing (Zoho TODO); Postmaster/SNDS unregistered |
| 29 | Intake-first onboarding (profile → ICP → research) | Implemented and verified | `/intake` form + file store + API live; gate flips verified both ways; research prompts consume business context |
| 30 | Agent workflow API (slidein-api, FastAPI) | **Live** | `api.slideinventure.com/health` → 200; `:8100` via systemd; SQLite default DB; API-key auth (`ten_local`); `/v1/contracts` returns stage contracts |
| 31 | Client workspace UI (slidein-app, Next.js) | **Live** | `workspace.slideinventure.com/` → 307→/overview; `:3201` via PM2; connects to slidein-api server-side via localhost:8100; full workflow sidebar + overview page rendering |
| 32 | Prospect engagement: inbound reply path to backend | Partially implemented | Backend `POST /webhooks/inbound`, threading, intent, opt-out suppression exist (`slidein-api`); **no production inbound mail path** (see #23) |
| 33 | Engagement: grounded reply agent with approval | Planned but not implemented | Spec only: `docs/product/PROSPECT_ENGAGEMENT.md` |
| 34 | Engagement: chat agent via secure link | Planned but not implemented | Spec only; M2 |
| 35 | Engagement: meeting booking (provider, webhooks, records) | Planned but not implemented | No provider selected (OQ-004) |
| 36 | Engagement: voice (inbound/callback only) | Planned but not implemented | Research + legal review required; outbound calling blocked |

## Data on the live VPS (private, never in git)

GoPhish DB (`/root/gophish/gophish.db`), KumoMTA spool + DKIM private keys,
job_api SQLite, Warmbly Postgres, slidein-api SQLite (`/opt/slidein-api/data/`),
slidein-app env (`/opt/slidein-app/.env.local` with API key), app env
(Appwrite/Supabase keys), Caddy certs, systemd/pm2 state. Secrets live in
root-only files and environment, never in the repo.
