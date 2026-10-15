# AGENTS.md

## Core Product Vision & North Star (SLIDEIN)
**The foundational product context for this entire project is defined in [`SLIDEIN_PRODUCT_VISION.md`](file:///Users/nasrullahtanim/Downloads/01-Projects/email-master%20raw/SLIDEIN_PRODUCT_VISION.md).**
> **"Find the right people. Understand their business. Reach out personally. Start more conversations."**
> Slidein combines prospect research, lead qualification, personalized email outreach, campaign management, automation, and email deliverability infrastructure into one connected system.
> Every engineering, architecture, and UI decision must anchor back to this workflow and product vision. If work begins to derail or lose focus, re-align immediately with [`SLIDEIN_PRODUCT_VISION.md`](file:///Users/nasrullahtanim/Downloads/01-Projects/email-master%20raw/SLIDEIN_PRODUCT_VISION.md).

This workspace is owned by Nasrullah Tanim.

**The working operational policy file is `PROJECT_POLICY.md` (repo root). Read it
first.** It protects the live infrastructure, while all product design aligns with SlideIn's vision.

Background context on the project lives in `CLAUDE.md`, `README.md`, and `product/`.
Old campaign-era rules (gates, circuit breaker, copy rules, runbook) are
archived under `archived_rules/` for reference; they are not binding.

## Production Deployment

### Infrastructure (live 2026-10-13)
- VPS: `169.58.206.20` — Ubuntu, Docker, Caddy; 18 containers + systemd + pm2
  (KumoMTA, GoPhish, monitoring, reacher, Warmbly ×11, dashboard)
- SSH: `ssh -i ~/.ssh/slidein_vps root@169.58.206.20`
- Public HTTPS (Caddy, LE certs): `app`/apex dashboard, `console` GoPhish
  campaign UI, `track` landing/pixels, `warmbly.*` warmup UI/API/pixels.
  `www` is the Vercel marketing site (CNAME, never served by the VPS).
- Loopback-only: KumoMTA :2587/:8029, GoPhish :8333, Grafana :3000,
  Prometheus :9090, reacher :8090, job_api :8091, app :3001
- 3 sender profiles: hello@, talk@, connect@ at nasrullahtanim.me
- Mail auth: SPF/DKIM/DMARC live for nasrullahtanim.me, tanim.social,
  tanim.tech. PTR mail.nasrullahtanim.me forward-confirmed. No
  receiving/IMAP mailboxes (mailcow era ended).

### Deployment Flow
1. Run `kumomta-lab/scripts/deploy-production.sh root@169.58.206.20` with
   `VPS_PASS`, `KUMO_AUTH_PASS` (and optionally `KUMO_ADMIN_PASS`) set in
   the environment — values live in `~/.slidein-vps-credentials` /
   `deliverability/config.json`, never in docs. Idempotent; safe to rerun.
2. DNS: values in `docs/deployment/DNS_RECORDS.md` (pushed via Cloudflare
   API 2026-10-12; token at `/tmp/.cf-token` when needed again)
3. Verify: `cd /opt/deliverability && python3 cli.py precheck`
4. GoPhish profiles: deployed script configures 3/3 via authenticated API
5. Dashboard: rsync `workspace-app/` (excl. node_modules/.next/.git) →
   `/var/www/workspace-app`, `npm ci && npm run build`, `pm2 start`
6. Verification backend: `reacher/` (engine :8090 + job_api :8091)
7. Warmbly: `warmbly/docker-compose.yml` + `.env` via `gen-warmbly-env.sh`

### Key Files
- `kumomta-lab/policy/production_init.lua` - KumoMTA production policy (DKIM, routing, rate limits)
- `kumomta-lab/compose/docker-compose.production.yml` - Production Docker compose
- `kumomta-lab/scripts/deploy-production.sh` - Full deployment script (live-verified)
- `kumomta-lab/scripts/gophish.service` - GoPhish systemd unit
- `deliverability/GOPHISH_KUMOMTA_COORDINATION_PRODUCTION.md` - Full coordination guide
- `deliverability/SETUP_GUIDE_PRODUCTION.md` - Setup guide
- `deliverability/config.json` - Deliverability configuration (kumo user: outbound)
- `gophish-config-production.json` - GoPhish configuration with 3 profiles
- `warmup-engine/config.json` - Warmup engine configuration
- `reacher/` - lead verification backend (FastAPI job API + reacher engine compose)
- `warmbly/` - warmup platform overlay (compose, env template, Caddy hosts)
- `product/core/` - universal multi-tenant core (Stage 1) + boundary tests
- `docs/deployment/DNS_RECORDS.md` - all live DNS values (public by design)

### Credentials (VPS:169.58.206.20)
- KumoMTA: user `outbound`, password from local `deliverability/config.json`
  (`kumo.password`, env `KUMO_AUTH_PASS`), port 2587
- GoPhish: uses KumoMTA on port 2587; API key at `/root/gophish/api_key.txt`
- VPS root password: local secret store only (env `VPS_PASS`)

### Security Rules
- All SMTP requires AUTH
- DKIM signs every message for all 3 domains
- Rate limits enforced per provider
- No header forgery or spoofing
- Warmup engine governs volume ramping
- Circuit breaker auto-pauses on high bounce/complaint rates

