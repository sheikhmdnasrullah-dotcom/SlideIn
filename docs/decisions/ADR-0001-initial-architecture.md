# ADR-0001: Initial architecture — modular monolith with a pluggable MTA

- Status: Accepted
- Date: 2026-10-12

## Context

The project began as three independently useful pieces: a campaign/admin
backend (a modified GoPhish fork), a Python deliverability engine (gates,
circuit breakers, provider abstraction), and KumoMTA configuration (Lua
policies + Docker). A product layer (FastAPI) and dashboard (Next.js) were
started later. The owner is a solo developer with a limited budget who needs
the system to run locally for development and on a single VPS in production,
with a path to a multi-tenant hosted offering.

## Decision

1. **Keep a modular monolith per runtime, not microservices.** Three
   processes max in the default deployment: the Go admin app, the Python
   deliverability service, and KumoMTA (an external MTA container), with
   Redis for queues. Rationale: a solo maintainer cannot operate more; each
   piece already exists and works.
2. **KumoMTA as the only outbound MTA**, reached over authenticated ESMTP.
   All sending flows converge on one transport with per-provider shaping and
   DKIM signing in policy (`kumomta-lab/policy/*.lua`).
3. **Single approved outbound path in Python**
   (`deliverability/core/pipeline.py`) so safety checks (pre-send gate,
   placement risk, circuit breaker, suppression) cannot be bypassed by
   ad-hoc send scripts.
4. **Provider abstraction with three implementations** — local sink
   (Mailpit), KumoMTA, and standard SMTP relays (SendGrid/Resend/Mailgun/SES)
   — so development never touches the internet and production can relay
   through established providers when needed.
5. **SQLite per component for now.** Each process owns its store
   (`gophish.db`, `deliverability_state.db`, `warmup.db`); Redis carries
   queues. PostgreSQL is reserved for the product/multi-tenant layer, which
   needs transactional isolation and row-level security.
6. **Hermetic test topology.** The lab compose stack forces outbound mail to
   a sink MX on an internal network; the local stack terminates mail in
   Mailpit. Tests must never send real email by default.

## Alternatives considered

- **All-in-one rewrite in a single framework**: rejected — would discard
  working, tested code (16 Go packages, 57 Python tests) for cosmetic
  cohesion.
- **Microservices per capability (send, warmup, gate, campaigns)**:
  rejected — operational cost exceeds benefit at current scale; no independent
  scaling requirement exists.
- **Managed ESP APIs only (SendGrid/etc.) as the sole transport**:
  rejected as the *only* option because the project's core value is
  self-hosted control and warmup/deliverability engineering; kept as optional
  transports via `StandardSMTPProvider`.
- **mailcow for inbound mailboxes**: documented but not part of the core
  architecture; inbound mailbox hosting is separable and currently has no
  recoverable local configuration.

## Consequences

- Local development is one command (`./dev`) and never requires internet
  email access.
- Cross-component transactions are not possible; each layer must tolerate
  eventually-consistent state (documented in
  `docs/architecture/OVERVIEW.md`).
- Multi-tenancy is enforced only in the product layer today; the Go app
  remains single-operator until Stage 4 of `ROADMAP.md`.
- Consolidation of the three API surfaces is explicitly deferred (roadmap
  Stage 3) rather than done prematurely.
