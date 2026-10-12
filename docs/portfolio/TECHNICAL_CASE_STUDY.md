# Technical Case Study — SlideIn

> Evidence-based account of real work, 2026. Status claims cite
> `../project/CURRENT_STATE.md`; nothing here exceeds what the code, tests,
> and runs prove.

## Why I built it

Self-hosting email means owning deliverability: authentication, bounces,
suppression, warmup, and honest telemetry. I wanted one inspectable stack
where every send is gated, every outcome is traced, and no component claims
more than it verifies. Separately, I needed a system I could operate,
document, and defend end-to-end as an engineer.

## Problem and requirements

Decide per message: *may this send, through which transport, and what
happened afterwards?* Requirements: authenticated ESMTP submission; pre-send
content/risk gates; suppression that cannot be bypassed; circuit breaking on
bad signals; provider abstraction (local sink vs MTA vs relays); event
ingest from providers; local development that never touches the internet.

## Architecture and decisions

Modular monolith per runtime (Go admin app, Python engine, KumoMTA, Redis),
documented in ADR-0001. Alternatives rejected with reasons: single-framework
rewrite (would discard tested code), microservices (solo-operator cost),
ESP-only transport (defeats self-hosted control). Key invariants: one
approved outbound path per runtime; fail-closed checks; hermetic local
topology.

## What I personally did

Designed and executed the repository audit; fixed 8 safety findings
(auth bypass, cross-tenant reads, SNS SSRF, hardcoded seed key, two
suppression bypasses, review-server auth, webhook secret enforcement) with
46 new regression tests; repaired the production deploy script; brought the
local stack to verified operation (e2e 8/8, platform 8/8); wrote the audit,
architecture, threat-model, and operations docs. Pre-existing work I did
*not* originate: the GoPhish upstream codebase, KumoMTA itself, and the
initial scaffolding of several components — all attributed where relevant.

## Reliability and security approach

Fail-closed defaults (401/403/503 with audit events, never silent
pass-through); socket-free unit tests plus live sink-verified e2e; secret
hygiene enforced in CI; threat model with explicit residual risks. I
investigated and refuted one suspected SSRF (Go webhook client was already
dial-restricted) rather than "fixing" it blindly.

## Verification evidence

103 deliverability tests, 13 Go packages, lab suite, secret scan, `./doctor`
FULLY OPERATIONAL, e2e + platform suites green — commands and outputs in
`../development/TESTING.md`.

## Known limitations

Single-host; split SQLite stores; duplicated dashboard tree; product API
needs PostgreSQL; no human-approval queue; production path unexercised; no
managed service. Full register: `../project/TECHNICAL_DEBT.md`.

## Next research directions

Reproducible experiments (methods before numbers): queue throughput under
the Go worker poll loop; breaker trip/recovery timing; retry-backoff
behavior under synthetic 4xx/5xx; memory footprint of long warmup runs.
