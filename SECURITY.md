# Security Policy

## Reporting a vulnerability

Please **do not** open a public issue for security vulnerabilities.

Report privately via one of:

- GitHub's **private vulnerability reporting** on this repository
  (Security tab → Report a vulnerability), or
- A private message to the maintainer's GitHub profile
  ([sheikhmdnasrullah-dotcom](https://github.com/sheikhmdnasrullah-dotcom)).

Include: affected component/file path, reproduction steps, impact, and any
suggested fix. You will receive an acknowledgement when the maintainer is
available; this is a solo-maintained alpha project, so response times vary.

## Supported versions

Only the latest `main` branch receives fixes. There are no released version
branches yet.

## Credential hygiene (project policy)

- All real credentials live in gitignored files (`*.config.json`, `.env`) —
  never in code, docs, or git history (`PROJECT_POLICY.md` §2.1).
- CI enforces this with `scripts/check-secrets.sh` plus secret scanning.
- The local development password is the public placeholder
  `local-dev-password`. It is intentionally non-secret and only meaningful on
  `127.0.0.1`.
- Production credentials are supplied per-deployment via environment
  variables (`VPS_PASS`, `KUMO_AUTH_PASS`, `KUMO_ADMIN_PASS`).

## Scope notes

This software sends email. Reports about *sending behavior* (for example how
to improve authentication or suppression handling) are welcome. Requests or
pull requests for spam-filter evasion, header forgery, or guaranteed inbox
placement will be declined — see `CONTRIBUTING.md`.
