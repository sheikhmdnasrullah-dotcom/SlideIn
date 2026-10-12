# InboxForge — Deliverability SaaS for Genuine Cold Email

> Design doc. Owner: Nasrullah Tanim. Status: v0 design (2026-09-08).
> This is a design for a **legitimate** cold-email deliverability product. It
> maximizes Primary-inbox placement for *compliant, personalized, 1:1*
> outreach using only legitimate levers. It does not include spam-evasion
> (header forgery, identity spoofing, filter-bypass tricks, reputation
> poisoning). See §14 for the explicit boundary.

---

## 1. One-liner

**InboxForge** is a SaaS that takes a real business's genuine cold-outreach
email and, before it goes out, *proves* where it lands (Inbox vs Promotions
vs Spam), fixes the things that sink it, ships it through a reputationally
clean transport, and then *self-heals* (auto-pause + re-validate) the moment
placement or reputation degrades.

The promise is the enforceable truth, not a fantasy:
- **Every message is placement-verified on real inboxes before it reaches a
  real lead.**
- **Sending stops automatically the instant placement/reputation regresses.**
- **Every send is fully observable** (where it landed, why, what to fix).

We do *not* promise "100% of all emails, always, inbox." No legitimate system
can, because Gmail/Outlook/Yahoo classify with opaque, shifting ML. We promise
the highest *achievable* Primary placement plus **zero silent spam** and full
explainability. That is the defensible, shippable version of "indefensible."

## 2. The honest premise (read this first)

What actually puts a 1:1 cold email in **Primary** (not Promotions) and keeps
it out of **Spam**, using only legitimate levers:

| Goal | Legitimate levers that genuinely move it |
|------|------------------------------------------|
| Not Spam | SPF=pass, DKIM=pass, DMARC aligned; warm IP+domain reputation; low bounce/complaint rate; PTR/rDNS; no spammy content; real (non-burner) sender identity |
| Primary not Promotions (Gmail) | 1:1 peer tone; plain-text; low commercial density; no pricing/CTA/buy-now; no unsubscribe header on 1:1; minimal/no links+images; personalized |
| Stays there over time | Warmup ramp; pacing/velocity control; list hygiene (verified, no catch-all blasting); engagement (replies/opens) as positive feedback; continuous reputation monitoring |

The product's entire value is owning that table end-to-end, per tenant, with
a **proof-based** gate and a **self-healing** loop. The differentiator vs. the
existing vendors is the *verification + control loop*, not just "send mail."

## 3. Product pillars

1. **Prove before send** — real-inbox seed placement of the exact message.
2. **Maximize placement** — content + identity + infra optimization.
3. **Never silently spam** — circuit breaker + auto-pause + re-validate.
4. **Fully observable** — per-provider placement, reasons, fixes, trends.
5. **Genuine by construction** — consent/compliance (CAN-SPAM, GDPR, CASL)
   baked in, not bolted on. This is what makes the whole thing legitimate.


---

## 4. Architecture

```
                        ┌────────────────────────────────────────────┐
                        │                CONTROL PLANE               │
                        │  FastAPI app · tenant DB · API keys · RBAC │
                        └──────┬─────────────────────────────┬───────┘
                               │                             │
        ┌──────────────────────┼─────────────────────────────┼───────────────┐
        │                      │                             │               │
┌───────▼────────┐   ┌─────────▼─────────┐          ┌─────────▼──────┐ ┌──────▼───────┐
│  COMPOSER      │   │   PRE-SEND GATE   │          │  TRANSPORT     │ │  OBSERVE     │
│  + SCORER      │──▶│  (gate + risk     │          │  (KumoMTA per  │ │  (monitor,   │
│  content/HTML  │   │   + seed placement│          │   tenant, warm │ │  circuit     │
│  optimizer     │   │   + DNS/auth)     │          │   IPs, pacing) │ │  breaker,    │
└────────────────┘   └─────────┬─────────┘          └─────────┬──────┘ │  placement   │
                               │ pass                         │        │  analytics)  │
                               └──────────────────────────────┘        └──────┬───────┘
                                                                             │ regress
                                                                             ▼
                                                                  ┌─────────────────────┐
                                                                  │  SELF-HEAL          │
                                                                  │  pause → diagnose → │
                                                                  │  fix → re-validate  │
                                                                  └─────────────────────┘

  Placement Lab (the moat):
  ┌───────────────────────────────────────────────────────────────┐
  │ provider simulators (Gmail/Outlook/Yahoo/iCloud heuristics)  │
  │ + real seed inboxes per tenant (IMAP read-back, folder/label)│
  │ used by the GATE and by the COMPOSER's optimization loop     │
  └───────────────────────────────────────────────────────────────┘
```

### 4.1 Component → existing code mapping (what we already have)

| Product component | Reuse from repo | Work needed |
|---|---|---|
| Pre-send gate | `deliverability/core/gate.py` | Tenant-ize; per-plan thresholds |
| Promotions/Spam classifier | `core/placement_risk.py` | Expand signals; per-provider weights; make it an API |
| Analyzer (grade A–F) | `core/analyzer.py` (happyDeliver + heuristic) | Keep as-is |
| Seed placement test | `core/seed_tester.py` | Per-tenant seed pools; scale IMAP workers |
| Circuit breaker + monitor | `core/circuit_breaker.py`, `core/monitor.py` | Tenant-scoped state; webhook/Slack/email alerts |
| Reputation signals | `core/reputation.py`, `core/dns_checks.py` | Background scheduler; per-domain dashboards |
| Bounce/complaint handling | `core/bounce_parser.py` | Wire inbound DSN/ARF receiver (Kumo → queue) |
| Warmup ramp | `core/warmup.py` | Per-domain; per-plan limits |
| Transport | `core/kumo_transport.py`, pipeline `transport:` | One KumoMTA instance; per-tenant rate shaping |
| Suppression | `core/state.py` suppression table | Tenant-scoped; auto from DSN/ARF |
| CLI/runbook | `deliverability/cli.py` | Keep as ops tooling; add `serve` (FastAPI) entrypoint |

Net: ~70% of the engine already exists and is tested. The build is
**multi-tenancy + API + placement lab + UI + compliance layer.**

### 4.2 Placement Lab (the differentiator)

Two layers, same interface:

1. **Simulator layer** (instant, in-network): models provider scoring from
   published rules + research: auth checks (SPF/DKIM/DMARC alignment, PTR),
   header hygiene, content signals (commercial density, image/link ratio,
   CTA words, HTML patterns), sender metadata (age of domain, engagement
   history). Runs in a `kumomta-lab`-style hermetic network with the sink MX.
   Gives sub-second feedback to the Composer optimizer and to users ("this
   draft scores 92 for Gmail Primary; 2 issues flagged").
2. **Real-seed layer** (authoritative): tenant's own seed inboxes (they must
   own these accounts - that's the honest way) read back over IMAP; folder +
   Gmail category label detected. Gate only passes on the real-seed layer
   for production sends.

The two layers together = fast iteration (sim) + trustworthy proof (seeds).

## 5. User flow

1. **Onboard** - verify domain (DNS TXT), point DNS to platform (SPF include,
   DKIM CNAME we generate, DMARC), create mailboxes, connect seed inboxes
   (min 4: Gmail, Outlook, Yahoo, iCloud), upload lead list.
2. **Warm** - automated warmup: daily ramp 20 -> 50 -> 100 -> 250 -> 500/
   domain, with a compliant opt-in warmup pool (documented, user-visible),
   reputation dashboard live.
3. **Compose** - write in-app or paste an .eml. Composer scores live
   (simulator): Primary-risk per provider, itemized signals, one-click fixes
   ("remove price mention", "drop the second link", "shorten subject").
4. **Prove** - one click: gate runs analyzer + placement-risk + seed test on
   the exact .eml. Result card: `Gmail: INBOX  Outlook: INBOX  Yahoo:
   PROMOTIONS (reasons)  iCloud: INBOX` + fixes.
5. **Send** - paced (60-90s default, per-tenant velocity), profile rotation
   (round-robin across their mailboxes), full per-send event logged.
6. **Watch** - dashboard: placement %, bounce/complaint rates, reputation,
   open/reply engagement, circuit status. Alert on trip.
7. **Self-heal** - trip -> pause -> diagnostic report (what degraded) ->
   recommended fix -> re-validate -> resume. Never blind auto-resume.

## 6. Tenant & domain model

- **Tenant** = company. **Workspace** = one sending program (one domain family).
- Each workspace holds: `sending_domains[]`, `profiles[]` (mailboxes),
  `seed_pool[]`, `warmup_state`, `circuit_state`, `suppression[]`,
  `velocity_policy`.
- Multi-tenancy start: single schema + `tenant_id` everywhere (simple); move
  to schema-per-tenant if isolation demands it.
- Secrets (SMTP/Kumo AUTH, IMAP app passwords): encrypted at rest,
  per-tenant, never in logs. Extends the existing "secrets only in config"
  rule to per-tenant encrypted storage.

## 7. API surface (v1)

```
POST /v1/onboarding/domains/{domain}/verify        # DNS TXT proof
POST /v1/workspaces                                # create
GET  /v1/workspaces/{id}/status                    # circuit, warmup, reputation
POST /v1/drafts                                    # create/parse .eml
POST /v1/drafts/{id}/score                         # simulator score (fast)
POST /v1/drafts/{id}/verify                        # full gate + seed test
POST /v1/campaigns/{id}/send                       # send verified draft to list
GET  /v1/events/sends?from=&to=                    # per-send results
GET  /v1/placement/summary?window=                 # per-provider placement %
POST /v1/suppression/{email}                       # add/remove suppression
GET  /v1/reputation/{domain}                       # DNSBL/auth/warmup state
WS   /v1/stream/{workspace}                        # live placement/reputation feed
```

Auth: org-scoped API keys + optional SSO. Rate limits per tenant.
Everything audit-logged (who changed template/sender/volume).

## 8. UI (v1 pages)

1. **Overview** - circuit status, placement % per provider (7/30d), velocity,
   next warmup step.
2. **Compose & Prove** - editor + live score panel + seed-test result card.
3. **Campaigns/Sends** - list, per-recipient placement result, reply/ignore.
4. **Domains & Warmup** - per-domain auth checklist (SPF/DKIM/DMARC/PTR live
   from `dns_checks`), warmup ramp chart, blacklist alerts.
5. **Seeds** - seed inbox health, last read-back, category detection log.
6. **Alerts & Audit** - circuit trips, diagnostics, config change history.

Stack (boring, matches repo style): FastAPI + SQLite per tenant (Postgres
when scaling); Next.js or plain Vue for UI; KumoMTA for transport (already
in repo); the Grafana/Loki stack in `kumomta-lab` reused for ops.

## 9. Compliance layer (what makes "genuine" defensible)

- **Consent model per tenant**: B2B opt-out (CAN-SPAM / ePrivacy-style) vs.
  B2C opt-in (GDPR / CASL) declared per campaign; source recorded per lead.
- **List hygiene**: per-address verification (your Reacher does validity) +
  catch-all detection + dedupe; suppression honored forever (existing
  suppression table becomes the tenant's permanent do-not-mail list).
- **Sender honesty**: From/Reply-To must be real mailboxes the tenant owns
  (mailbox existence verified at onboarding); no From-domain spoofing;
  Reply-To aligned (rule already in the pipeline, keep it).
- **Identity transparency**: real human sender names; platform may be named
  in a small plain "sent via" line only where law requires.
- **Opt-out honored**: reply "remove me" or spam complaint -> auto-suppress
  (ARF already; add a reply parser in v1.1).
- **Volume ceiling**: platform-side hard caps per domain (e.g. 500/day max
  even on top plan) - protects tenants and providers.
- **Data**: PII minimization, tenant export + right-to-erasure, EU
  data-residency option.
- **Abuse**: onboarding KYC-lite (domain verification + business contact);
  human review queue for anomalies (velocity/complaint spikes).

## 10. Placement-maximization stack (priority order)

1. **Authentication perfection** - SPF/DKIM/DMARC alignment automated at
   onboarding (we generate DKIM keys, give exact records, verify live via
   `dns_checks`). Most cold-emailers fail here; fixing it alone moves
   Spam -> Inbox.
2. **Reputation engineering** - warm IP/domain (platform pool or tenant's
   own VPS via our KumoMTA config template), 3-6 week ramp, MTA-STS +
   TLS-RPT, BIMI once reputation is clean.
3. **Message engineering** - Composer + `placement_risk` signals as an
   optimizer: draft -> sim-score -> fix -> re-score until Primary-likely,
   then real-seed proof. Plain-text-first, max one link, no images in
   first touch, genuine personalization.
4. **Delivery shaping** - pacing, round-robin profiles (built), per-provider
   timing, retry only on 4xx (built).
5. **Feedback loop** - bounces/complaints auto-suppression (built), replies/
   opens as positive signal, daily seed re-verify.
6. **Self-healing** - circuit breaker + diagnostics + re-validate (built);
   productized as "Incident Report" with concrete fixes.

## 11. KPIs (what we actually claim)

- Primary-inbox rate per provider: target >= 90% on verified, warmed,
  compliant 1:1 sends (measured on tenant seed inboxes, published per tenant).
- Spam-folder rate < 2%; bounce < 2%; complaint < 0.1% (these are also the
  circuit thresholds; dashboard shows live values).
- Time-to-first-verified-send < 48h after domain verification.
- Zero silent degradation: any placement regression pauses sending within
  one monitoring tick.

## 12. Build roadmap (each phase shippable)

- **P0 (2 wks)** - Multi-tenant FastAPI over existing `deliverability/core`
  (gate, risk, seed-test, circuit, warmup). CLI -> API. SQLite per tenant.
  "Prove before send" working end-to-end on one workspace.
- **P1 (2 wks)** - Onboarding DNS automation (SPF/DKIM/DMARC generator +
  verifier), warmup dashboard, KumoMTA transport (from repo), seed-pool
  management UI.
- **P2 (2 wks)** - Composer + live sim-scoring (port `kumomta-lab` sink
  heuristics into a `placement_lab` package), campaign send UI, event
  stream, alerts (Slack/email/webhook).
- **P3 (ongoing)** - Reply parser -> auto-suppress; reputation dashboards
  (Postmaster/SNDS); team/RBAC; billing; abuse review queue; EU residency.

## 13. Risks (honest)

- **Seed inboxes are per-tenant**: tenants must provision 4 real accounts.
  Friction, but it's the only honest proof; mitigate with a 15-min guided
  setup wizard.
- **Provider heuristics shift**: the sim layer needs a continuous research
  loop (this repo's lab is exactly that). The real-seed layer is the safety
  net by design.
- **Reputation is slow**: warmup can't be rushed honestly. Sell 48h to
  first *verified* send; full ramp 3-6 weeks.
- **Gmail's cold-email stance**: 1:1 personalized still works; bulk-ish
  patterns get pushed to Promotions/Spam regardless. The product keeps
  tenants in the "1:1 genuine" band and proves it.

## 14. Explicit boundary (a feature, not a limitation)

InboxForge optimizes **legitimate levers only**. Excluded by design:
header/identity forgery, From-domain spoofing, envelope/visible mismatch,
reputation poisoning, filter-evasion encoding/obfuscation, hiding sender
identity, or any mechanism whose purpose is landing *unwanted* mail in
Primary. That boundary is what makes the "genuine cold email" positioning
defensible to customers, providers, and regulators - and what makes the
product shippable.

Sibling product (the "fight back" tool): a **spam-evasion detector** - the
same `placement_lab` heuristics pointed at *inbound* mail to flag evasive
senders (header inconsistencies, reputation anomalies, evasion patterns).
Same research engine, opposite direction.