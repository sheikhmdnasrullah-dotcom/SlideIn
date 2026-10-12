# MASTER EXECUTION PROMPT — KumoMTA COMPLIANT DELIVERABILITY LAB

> Reframed from the original "spam evasion / 100% inbox" brief. This version is
> built around **legitimate, measurable deliverability** — authentication,
> reputation, consent, and observability — and explicitly rejects filter evasion.
> Read `EMAIL_SENDING_POLICY.md` (repo root) before any sending code.

## 0. NON-NEGOTIABLE PRINCIPLES

1. **No evasion.** We do not build technology to defeat or bypass spam filters.
   Deliverability is earned through authentication, reputation, and compliant
   content — not through obfuscation. Any task that asks to "evade," "trick,"
   or "guarantee inbox" is out of scope and must be flagged, not implemented.
2. **No guaranteed inbox.** "100% inbox placement" is not a real target and is
   not claimed. We measure and improve *rates*; we report failures honestly.
3. **Consent & law first.** Cold/outreach traffic is only sent where legally
   permitted (CAN-SPAM / GDPR / CASL), with working unsubscribe, accurate
   headers, and honoring of complaints and suppression. Transactional mail
   (OTP, resets, security) is separate and privileged.
4. **Isolation.** Cold traffic never contaminates the transactional stream:
   separate domains, keys, queues, IPs, and shaping.
5. **Measure everything; hide nothing.** If a message is rejected, deferred, or
   lands in Spam, we record why. We never fabricate deliverability numbers.

## 1. PRIMARY OBJECTIVE

Build a self-hosted, reproducible email-delivery control plane on KumoMTA that:

- Sends **transactional** mail with maximal reliability and priority.
- Runs **controlled, consent-based outreach experiments** in a hermetic lab
  (no real Internet egress) before any production send.
- Produces transparent, measurement-driven deliverability scores.
- Survives failure, load, and provider throttling without retry storms.

## 2. SCORING (transparent, measured)

For each provider + experiment, record and score:

- SMTP acceptance / rejection / deferral
- connection / TLS / DNS failures
- queue delay, retry count, final status
- auth results (SPF/DKIM/DMARC alignment)
- observed placement (Inbox / Spam / Promotions) via *owned* seed inboxes only
- bounce rate, complaint rate, temporary/permanent failure rate

DELIVERABILITY SCORE (per provider, rolling 7d):
- 100–90 strong · 89–75 degraded · 74–50 poor · <50 critical
Derived from: `(inbox_rate * 0.5) + (auth_pass_rate * 0.2) + (1 - bounce_rate) * 0.15 + (1 - complaint_rate) * 0.15`.
Formula and inputs are committed to the repo; no opaque magic.

## 3. ARCHITECTURE (control plane, not just an MTA)

```
APPS / MAILCOW
   -> EMAIL API (auth required)
   -> POLICY ENGINE (suppression, priority, compliance gate)
   -> PRIORITY QUEUE (P0 security … P3 outreach)
   -> KUMOMTA (DKIM, queue, retry, shaping)
   -> GLOBAL RATE GOVERNOR (hard ceiling, survives crashes)
   -> ISP-SPECIFIC SHAPING
   -> RECIPIENT MX (live, production only)
   -> DELIVERY EVENTS
   -> REPUTATION + ANALYTICS ENGINE
   -> POLICY OPTIMIZER (logged, bounded changes)
   -> (loop back to Kumo)
```
The feedback loop is mandatory. Every automatic policy change is logged.

## 4. LOCAL LAB (must run with zero Internet egress)

Implemented in `kumomta-lab/` + `sink-mx/`:
- KumoMTA forced to route **everything** to `sink.lab.internal` (no real MX).
- `sink-mx` simulates Gmail/Yahoo/Microsoft/Apple/Proton behavior by recipient
  domain: 250 / 421 / 450 / 550, slow reads, resets, TLS refusal.
- Prometheus + Grafana + Alertmanager + Loki observe the whole stack.
- Redis governor enforces the global ceiling even under app floods.
Run `docker compose -f kumomta-lab/compose/docker-compose.yml up --build`.

## 5. PRODUCTION (VPS) — gated, non-disruptive

Before any live send on the VPS:
1. **Read-only audit** of OS, ports, Mailcow, port 25 ownership. No changes.
2. **Backup** Mailcow + Kumo config; verify integrity.
3. **Authentication validation**: SPF, DKIM, DMARC, PTR, A/AAAA, TLS, EHLO.
4. **Compliance gate**: no send unless grade ≥ B AND seed placement is Inbox
   (see `deliverability/core/gate.py` + circuit breaker).
5. Mailcow inbound preserved; Kumo handles outbound. Port 25 stays owned by the
   existing inbound path; Kumo egress uses its own flow.

## 6. TRAFFIC SHAPING (legitimate, provider-aware)

Per provider: concurrency, connection rate, message rate, messages/connection,
retry interval, backoff, timeouts. Driven by *observed* receiver behavior, not
guessed. Adaptive: healthy → maintain; deferral → reduce; instability → lower
concurrency; persistent failure → quarantine; recovery → gradual ramp.

## 7. REPUTATION & WARM-UP (adaptive, never deceptive)

- Preflight IP checks (DNSBL, rDNS, TLS, hostname consistency). No IP rotation
  to dodge blocks — only legitimate replacement + controlled warm-up.
- Warm-up profiles scale with acceptance/deferral/bounce/complaint signals.
  Deterioration → stop increasing; back off.

## 8. SUPPRESSION & PRIORITY

- Pre-send suppression: hard bounce, invalid, repeated permanent failure,
  unsubscribe, complaint. Blocked → never queued.
- Queue hierarchy: P0 security/OTP > P1 account > P2 transactional >
  P3 outreach. Under pressure, P3 stops first.

## 9. CONTENT EXPERIMENTATION (honest)

Compare legitimate variants (subject, body, headers, HTML/text, links, size,
auth alignment). Goal: learn which *legitimate* characteristics correlate with
acceptance. Never generate deceptive or filter-defeating payloads.

## 10. OBSERVABILITY & ALERTS

Dashboards for system, Kumo, providers, reputation, governor. Alerts:
critical (queue explosion, disk/mem, open relay, auth failure, rejection
spike, sending spike); warning (rising 4xx/5xx, latency, throttling, TLS/DNS
failures, IP reputation drop).

## 11. SECURITY

Kumo is never an open relay (AUTH + restricted relay_hosts; tested explicitly).
Secrets (DKIM keys, Grafana admin, API creds) live in files outside git.
SSH/firewall/admin interfaces locked down. No secret in the repo.

## 12. DR & SCRIPTS

Repo holds everything except secrets: `deploy.sh`, `rollback.sh`, `backup.sh`,
`restore.sh`, `healthcheck.sh`, `audit.sh`, `test-dns.sh`, `test-dkim.sh`,
`test-smtp.sh`. Local lab reconstructs the system if VPS access is lost.

## 13. IMPLEMENTATION ORDER (phased, no big-bang)

PHASE 1 read-only VPS+Mailcow audit → PHASE 2 local Kumo lab → PHASE 3
traffic-shaping lab → PHASE 4 failure/chaos tests → PHASE 5 prod config gen →
PHASE 6 VPS backup → PHASE 7 non-disruptive Kumo deploy → PHASE 8 Mailcow→Kumo
integration → PHASE 9 auth validation → PHASE 10 controlled external delivery →
PHASE 11 provider monitoring → PHASE 12 adaptive shaping → PHASE 13
reputation/warm-up → PHASE 14 hardening → PHASE 15 DR test.

## 14. FINAL RULE

Optimize for **measurable, honest** success. If a message is rejected, find why.
If deferred, find why. If accepted but in Spam, measure what's observable.
Improve → record the experiment. Regress → roll back. Data contradicts an
assumption → change the architecture. Never hide failures; never fake placement.
