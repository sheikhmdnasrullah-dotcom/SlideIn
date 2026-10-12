# Deployment Model — SlideIn

## Local development (verified 2026-10-12)

`./dev` → Docker (Mailpit, Redis, KumoMTA) + Go :3333 + Python :8088 +
Next.js :3000. `./doctor` health-gates; `./stop` tears down. All ports
loopback-bound. Hermetic alternative: `kumomta-lab` lab stack with sink MX
on an internal network. See `../development/LOCAL_SETUP.md`.

## Self-hosting (designed, unexercised end-to-end)

Same compose topology on one host, production KumoMTA policy, public DNS
(SPF/DKIM/DMARC), Let's Encrypt TLS. See `../deployment/SELF_HOSTING.md`.

## Production VPS (designed, blocked)

`kumomta-lab/scripts/deploy-production.sh` (9 phases: precheck → KumoMTA →
GoPhish → profiles → warmup → monitoring → pipeline → verify) plus
`setup-dns.sh`, `precheck.py`, `configure-gophish-profiles.py`. Script paths
fixed and statically verified 2026-10-12; no live run (previous VPS
destroyed; mailcow unrecoverable). Requirements: Ubuntu 22.04/24.04, clean
IPv4, unblocked outbound port 25, PTR record. See
`../deployment/PRODUCTION_READINESS.md`.

## Managed service (intent only)

No hosted offering exists. Boundary rules:
`../deployment/managed-service-plan.md`.
