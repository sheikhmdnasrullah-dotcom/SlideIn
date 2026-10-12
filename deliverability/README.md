# Deliverability System — Implementation

Self-hosted, stdlib-only (Python 3) inbox-placement + circuit-breaker system that
enforces `EMAIL_SENDING_POLICY.md`. Built to require **zero paid seed-network
contract**: we test the real email against seed inboxes we control.

## Layout
```
core/state.py          SQLite store (decisions, seed results, circuit, metrics, suppression)
core/dns_checks.py     SPF/DKIM/DMARC/BIMI/PTR/MTA-STS/TLS-RPT + DNSBL audit (dig)
core/analyzer.py       happyDeliver client + heuristic A–F fallback
core/seed_tester.py    SMTP send + IMAP read-back; folder classification per provider
core/gate.py           pre-send placement GATE
core/circuit_breaker.py auto-pause on regression (with half-open probe recovery)
core/pipeline.py       THE ONE approved outbound path (send_via_pipeline)
core/monitor.py        scheduled circuit-breaker tick
core/reputation.py     Gmail Postmaster + Outlook SNDS + blacklist (optional)
core/bounce_parser.py  DSN/ARF bounce + complaint parser
core/warmup.py         daily volume tracker + domain warmup ramp
core/placement_risk.py promotions/spam risk classifier (pre-send gate)
cli.py                 validate-dns | analyze | seed-test | gate-check | placement-risk | monitor | status | pause | resume | send | suppress | unsuppress | suppressed | parse-bounce | warmup-status | precheck | send-log | next-profile
config.example.json    config schema (copy to config.json, fill secrets)
sample/approved_template.eml   frozen canonical email copy
tests/test_pipeline.py  control-logic integration tests
tests/test_bounce_suppression.py  bounce parser, suppression, pacing, half-open tests
tests/test_warmup_e2e.py  warmup + end-to-end pipeline tests
tests/test_placement_risk.py  promotions/spam risk classifier tests
docker-compose.yml     happyDeliver (analyzer) + monitor on VPS
```

## Local smoke test (no external accounts needed)
```
python3 -m unittest tests.test_pipeline -v     # proves gate + circuit-breaker logic
python3 core/dns_checks.py tanim.tech 153.76.249.166   # live auth audit
python3 core/analyzer.py sample/approved_template.eml  # A–F grade
```

## What is proven vs. what needs you (the user)
PROVEN HERE:
- Gate logic (blocks on spam/promotions/low grade; re-validates on email change).
- Circuit breaker (trips on seed/bounce/complaint/blacklist; resume needs validation).
- Half-open probe recovery: circuit transitions to half-open after cooldown, allows
  limited probe sends, and closes only on success.
- Single approved pipeline path; DNS/auth audit runs on your real domains.
- Analyzer grades the real approved copy (currently A after unsubscribe added).
- Suppression list: hard bounces and complaints are auto-suppressed before send.
- Bounce parser: classifies DSN/ARF into hard_bounce, soft_bounce, deferred, complaint.
- Pacing enforcement: anti-burst delays between sends.
- Warmup tracker: daily volume limits and automatic ramp.
- Pre-send auth alignment check: verifies Authentication-Results show no SPF/DKIM/DMARC failures.
- Placement risk classifier: scores emails for Promotions/Spam triggers before send
  and blocks when risk exceeds configurable thresholds.

NEEDS YOUR PROVISIONING (cannot be done from this machine):
1. **Seed inbox credentials** — create 1 Gmail, 1 Outlook, 1 Yahoo, 1 iCloud
   (app passwords / IMAP enabled) and put them in config.json → seed_accounts.
2. **VPS deploy** — `docker compose up -d` (happyDeliver + monitor). happyDeliver
   is the authoritative analyzer; locally we use the heuristic fallback.
3. **Fill config.json** — SMTP relay creds, sending_ip, dkim_selectors, KumoMTA
   AUTH credentials, seed account app passwords.
4. **Run the real seed test** — `python3 cli.py seed-test sample/approved_template.eml`
   to get true inbox/spam/promotions per provider (the acceptance evidence).
5. **Fix the DKIM gap** — current DNS audit shows NO DKIM for tanim.tech; publish
   the relay's DKIM (Mailgun CNAMEs / Zoho selector) or inbox placement will fail.
6. **PTR for sending IP** — ensure PTR exists for direct-send IPs (relay PTR covers
   relay path; direct-send IP needs its own PTR).
7. **Warmup initialization** — `python3 cli.py warmup-status` to initialize daily
   limits for each sending domain before first campaign send.

## Flow
```
email created → analyze (A–F) + seed-test (real inboxes)
   → GATE approves only if grade≥B AND 100% INBOX
   → campaign allowed → monitor ticks re-run seed + DNS + reputation
   → regression → CIRCUIT BREAKER auto-pauses, preserves state
   → resume only after fresh validation passes
```

## Sender profiles & rotation (KumoMTA track)
- Approved sender identities live in `config.json` → `profiles` (e.g. the
  `hello/talk/connect@nasrullahtanim.me` mailcow mailboxes). Only those may be
  used as From/Reply-To/envelope.
- `python3 cli.py next-profile` prints the next profile (round-robin, persisted
  in the state DB) to render the next `.eml` with — so batches spread evenly
  across mailboxes instead of bursting one sender.
- `python3 cli.py send file.eml recipient [sender]` enforces that the envelope
  sender is in `profiles`/`sending_domains` AND matches the `.eml` From header.
- `transport: "kumo"` sends seed tests + production mail through the KumoMTA
  submission listener (`kumo` block) instead of the SMTP relay (`smtp` block).
  The gate fails closed if seed results are empty — no proof of 100% Inbox, no
  send.

