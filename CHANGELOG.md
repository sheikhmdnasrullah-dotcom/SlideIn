# Changelog

All notable changes to this project are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Live production deployment on a single VPS (Ubuntu, Docker, Caddy):
  KumoMTA, GoPhish (systemd), Prometheus/Grafana/Alertmanager/Loki/Redis,
  Next.js dashboard, reacher verification backend, self-hosted Warmbly
  (11 services), Agent-Reach research tooling.
- Public HTTPS for 6 hosts (dashboard, tracking, warmup UI/API/pixels)
  with auto-issued Let's Encrypt certificates.
- Cloudflare DNS automation values for 3 mail domains (SPF/DKIM/DMARC)
  plus 7 site records; `docs/deployment/DNS_RECORDS.md`.
- Universal core Stage 1 (`product/core/`): tenant contexts, scoped
  memory, versioned shared defaults, learning-candidate registry,
  cross-business eval suites, industry-neutral workflow runner.
- 22 DB-free architecture boundary tests
  (`product/tests/test_core_boundaries.py`).
- Boundary docs: core-vs-tenant, memory policy, learning pipeline,
  config versioning, cross-business evaluation.
- Lead verification service (`reacher/`): FastAPI job API (single,
  bulk CSV, SSE, download) over `reacherhq/backend`, secret-gated.
- Warmbly production overlay (`warmbly/`): loopback-bound compose,
  KumoMTA relay networking, Caddy routes, owner bootstrap.
- Dashboard open mode (`DISABLE_AUTH`, reversible) with anonymous
  script-execution lock and SMTP-credential response sanitization.
- Agent-Reach company page-read wired into lead research as a
  best-effort snippet source alongside Tavily.
- Publication preparation: credential scrub, hardened `.gitignore`,
  secret-hygiene gate (`scripts/check-secrets.sh`) in CI.
- Canonical docs layout (`docs/project|architecture|development|deployment|
  security|api|decisions|portfolio/`), new README, `ROADMAP.md`, threat
  model, API overview, portfolio case study.
- Community files: `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`,
  `SUPPORT.md`, issue/PR templates, Dependabot.
- Server auth hardening: 401 fail-closed + constant-time compare,
  workspace-scoped conversations, per-DB random seed keys, `show-key` /
  `rotate-key` CLI, `/v1/workspaces` key redaction.
- Webhook hardening: SNS SSRF allowlist, required `WEBHOOK_SECRET`
  (503 fail-closed), SNS TopicArn allowlist, unspam URL validation.
- Send-path eligibility: `campaign_worker.process_lead()` (duplicate +
  breaker + suppression), `/v1/leads/submit` checks (403/503).
- Review-server auth: shared `core/dev_auth.py` key check + loopback bind.
- 46 new deliverability regression tests (103 total, socket-free).

### Changed

- Deploy scripts read `VPS_PASS` / `KUMO_AUTH_PASS` / `KUMO_ADMIN_PASS`
  from the environment; `deploy-production.sh` paths fixed and statically
  verified.
- Local default SMTP password unified as `local-dev-password` (local stack
  only; production credentials are environment-provided and rotated).
- `LICENSE`: retained MIT (GoPhish fork attribution preserved) with
  SlideIn modification copyright added.

### Verified

- `./dev` + `./doctor`: FULLY OPERATIONAL; e2e 8/8; platform suite 8/8
  (2026-10-12, local stack, Mailpit sink).

## [0.1.0] — 2026-10-12

Initial public alpha (tag `v0.1.0`). Contents and verification status:
`docs/project/CURRENT_STATE.md`, `docs/project/PROJECT_AUDIT.md` §10.
Known limitations: `docs/project/TECHNICAL_DEBT.md`. No upgrade path yet —
fresh clones only; no production deployment exists.
