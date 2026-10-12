# Threat Model — SlideIn

> Scope: the self-hosted deployment (single VPS + local dev). Assumes the
> host OS and Docker daemon are trusted; the network is not.

## Assets

Recipient/lead data, workspace API keys, SMTP/DKIM credentials, mail
content, delivery telemetry, sender reputation (IP/domain).

## Attackers & vectors

| Vector | Control (implemented) | Residual |
|---|---|---|
| Unauthenticated API access | Workspace keys, 401 fail-closed, constant-time compare | Key theft via leaked logs/URLs — mitigate by rotation; keys never logged |
| Cross-tenant access | Workspace scoping on reads/writes, 404 anti-oracle | Go app is single-operator; product roles unenforced |
| Webhook event injection | HMAC required (503 fail-closed); SNS TopicArn allowlist | Full SNS signature verification needs non-stdlib crypto (planned) |
| SSRF via fetched URLs | SNS SubscribeURL allowlist + https-only + no-redirect; unspam host allowlist; Go `RestrictedDialer` on webhook client | None known on reviewed paths |
| Sends to opted-out recipients | Suppression enforced at every live send site; breaker halts on signal | Human-approval queue still missing |
| Open relay abuse | KumoMTA AUTH-required on all submission listeners | Admin API exposure depends on host firewall (see `PRODUCTION_READINESS.md`) |
| Secret leakage into git | `.gitignore` + `check-secrets.sh` in CI + publication checklist | Old `main` history + `refs/agents/*` stay local-only; fresh public history required |
| Dependency compromise | Pinned Go modules; Python deliverability stdlib-only; Dependabot (Go + Python + npm) | No lockfile audit cadence documented yet |

## Out of scope (documented, not solved)

Prompt injection via untrusted content into LLM prompts (see
`TECHNICAL_DEBT.md`); physical host security; provider-side Gmail/Outlook
filtering behavior (never bypassed by design).
