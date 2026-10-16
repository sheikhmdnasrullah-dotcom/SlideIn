# PROJECT POLICY — Simple Working Rules

> Owner: Nasrullah Tanim. This is the only policy file for this repo.
> Keep it short. Update it here when the project direction changes.

## 1. What this repo is

A research and tooling workspace for email deliverability:

- **Lab**: local / hermetic experiment space (KumoMTA lab, sink MX, test
  domains, `deliverability/` tooling, test scripts). Everything here is for
  building, testing, and learning. You are free to build and experiment with
  whatever is useful for the project, including new sending experiments,
  detectors, analyzers, and infrastructure changes.
- **Live**: the production assets. VPS `153.76.249.166` (Gophish + mail),
  VPS `169.58.207.75` (mailcow + KumoMTA), the domains `tanim.tech`,
  `tanim.social`, `nasrullahtanim.me`, and the lead lists.

## 2. What stays fixed

These rules exist to protect the live infrastructure and keep the project
recoverable. Everything else is up to the owner's judgment.

1. **Secrets live only in `deliverability/config.json`** (and `.env` files).
   Never write passwords, API keys, or credentials into code, docs, or git
   history.
2. **Don't break live service while experimenting.** Lab code must not send
   traffic to real recipient domains, mutate live VPS state, or change live
   DNS unless the owner explicitly asks for that change.
3. **Live sending changes need explicit owner approval in chat** (not a
   standing rule, just a check-in): any change to what goes out of the live
   domains (sender, domain, template, transport, volume) gets a heads-up first.
4. **Keep the repo buildable.** `go build` and the Python tests under
   `deliverability/tests/` should stay green.
5. **Back up before destructive ops** on the live VPS (db, mail config).
   Existing backup scripts in `kumomta-lab/scripts/` cover this.
6. **License & Clean-Room Provenance (BSL 1.1)**: Free self-hosting for single-tenant internal use; competitors strictly prohibited from reselling as a commercial cloud service. Strictly NEVER copy or derive code from GPL OpenOutreach or other third-party GPL tools.
7. **Deliverability Liability & Shared IP Isolation**: Shared VPS IPs must be protected from tenant abuse. Enforce per-tenant hourly/daily caps, Reacher pre-send verification, and rolling circuit breakers (quarantine tenant if bounce >3% or complaints >0.05% without impacting neighbor tenants).
8. **Cold-Email Legal Invariants (CAN-SPAM / GDPR / CASL)**: Every outbound message requires: (a) verified B2B lawful basis, (b) clear plain-text opt-out and RFC 8058 `List-Unsubscribe` headers with instant zero-delay suppression, and (c) tenant physical postal address in the footer. Messages lacking a physical address are blocked at the gate.

## 3. How to work here

- Read this file first, then look at [`SLIDEIN_PRODUCT_VISION.md`](file:///Users/nasrullahtanim/Downloads/01-Projects/email-master%20raw/SLIDEIN_PRODUCT_VISION.md) for the overarching product concept, business purpose, and architecture principles.
- Consult `README.md` and `product/` for architecture and tooling context.
- Old docs (`kumomta-lab/docs/`, runbooks) may describe the previous
  gate/circuit-breaker workflow. They are reference material, not binding
  rules. If code and docs disagree, ask.
- New work goes in a sensible folder; document what you built in a short
  README inside that folder.
- Prefer extending existing modules (`deliverability/core/`, `kumomta-lab/`)
  over creating parallel systems.

## 4. Status

- Previous policy: `EMAIL_SENDING_POLICY.md` (archived 2026-09-08, replaced
  by this file). It documents the earlier campaign workflow; keep it around
  as a record of how that track was run.
