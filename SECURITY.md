# Security Policy

## Reporting a vulnerability

Please **do not** open a public issue for security vulnerabilities.

Report privately via one of:

- GitHub's **private vulnerability reporting** on this repository
  (Security tab → Report a vulnerability), or
- A private message to the maintainer on GitHub
  ([sheikhmdnasrullah-dotcom](https://github.com/sheikhmdnasrullah-dotcom)).

Include: affected component/file path, reproduction steps, impact, and any
suggested fix. You will receive an acknowledgement when the maintainer is
available; this is a solo-maintained alpha project, so response times vary.

## Supported versions

Only the latest `main` branch receives fixes. There are no released version
branches yet.

## Credential hygiene (project policy)

- All real credentials live in gitignored files (`*.config.json`, `.env`,
  `.secrets.env`) — never in code, docs, or git history
  (`PROJECT_POLICY.md` §2.1).
- CI enforces this with `scripts/check-secrets.sh` plus GitHub secret
  scanning. `.gitignore` excludes `*.db`, `.env`, `*.key`, `*.pem`, and
  `*.config.json`.
- The local development SMTP password is the public placeholder
  `local-dev-password`. It is intentionally non-secret and only meaningful on
  `127.0.0.1`.
- Production credentials are supplied per-deployment via environment
  variables (`VPS_PASS`, `KUMO_AUTH_PASS`, `KUMO_ADMIN_PASS`) and never
  committed.

## Architecture-level protections

- **Tenant isolation:** every query is scoped by `tenant_id`;
  cross-tenant reads raise a `403`. Tenant-private memory is partitioned
  (`docs/architecture/CORE_VS_TENANT_BOUNDARIES.md`).
- **Fail-closed delivery:** the deliverability gate
  (suppression + circuit breaker + pre-send verification) blocks dispatch
  on high bounce/complaint rates or failed MX verification
  (`deliverability/core/`).
- **Authenticated SMTP:** all outbound submission requires SASL AUTH through
  KumoMTA on loopback `:2587`; port 25 is never exposed to the public
  internet.
- **Webhook hardening:** inbound webhooks require a valid HMAC signature
  (`WEBHOOK_SECRET`); unsigned or allowlist-violating requests are rejected
  (`503`).
- **Edge isolation:** public HTTPS is served by Caddy; internal services
  (KumoMTA admin `:8029`, GoPhish `:8333`, verification `:8090/:8091`,
  Grafana `:3000`) are bound to loopback only.
- **No home-calling:** a SlideIn install never phones home. All data stays
  on your VPS.

## Scope notes

This software sends email. Reports about *sending behavior* (for example how
to improve authentication or suppression handling) are welcome. Requests or
pull requests for spam-filter evasion, header forgery, or guaranteed inbox
placement will be declined — see `CONTRIBUTING.md`.
