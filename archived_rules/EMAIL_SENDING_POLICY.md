# EMAIL SENDING POLICY — CANONICAL SOURCE OF TRUTH

> **This file is the authoritative email-sending policy for this project.**
> Every coding agent (Claude, Codex, Cursor, Gemini, opencode, or any other) that
> touches email functionality MUST read this file before writing or changing code.
> It is wired into `CLAUDE.md`, `AGENTS.md`, and `.claude/` so agents inherit it
> automatically. There is exactly ONE approved sending pipeline. Do not create
> another. Do not bypass the gate, the analyzer, the circuit breaker, or the
> seed-placement test.

---

## 0. PRIORITY ORDER (NON-NEGOTIABLE)

```
RESEARCH → BUILD → TEST → DETECT → FIX → RETEST → VERIFY → ONLY THEN CAMPAIGN
```

The production lead list is **FOREVER UNTOUCHED** until the deliverability
foundation below is built AND proven by passing an automated placement test.

---

## 1. MISSION

Achieve and **maintain** the strongest technically achievable inbox placement
(Gmail Inbox, Outlook Inbox, Yahoo Inbox, iCloud Inbox, not Spam/Junk/Promotions)
for the cold-outreach campaign, and **never blindly continue sending** when
placement degrades.

Practical definition of success that this project enforces automatically:
- Every production email passes an automated **pre-send gate** (Section 6).
- Placement is **continuously verified** by seed inboxes (Section 5).
- Any detected regression **auto-pauses** sending (Section 7).

> Honest engineering note (do not treat as an excuse): no external system can
> *guarantee* 100% permanent inbox placement because mailbox providers use opaque,
> shifting ML filters. This project therefore guarantees two things that ARE
> achievable: (a) every email is proven to reach Inbox on our seed accounts before
> and during sending, and (b) sending is stopped the moment seed placement or
> reputation degrades. That is the real, enforceable meaning of "never lose a lead
> to silent spam."

---

## 2. THE ONE APPROVED SENDING PIPELINE

All production email MUST flow through:

```
deliverability/core/pipeline.py  →  send_via_pipeline(recipient, eml, config, store)
```

This function is the ONLY outbound path. It enforces, in order:
1. Circuit breaker not open (Section 7).
2. Recipient not on suppression list (Section 11).
3. Anti-burst pacing enforced (Section 10).
4. Pre-send gate passed (Section 6).
5. Sender identity is approved and aligned with the .eml From header.
6. Authentication-Results in the .eml show no SPF/DKIM/DMARC failures.
7. Send via the configured transport (SMTP relay, KumoMTA submission, or
   Gophish REST API — never raw). `transport` in `config.json` selects it;
   the `kumo` transport is sanctioned in Section 15.
8. Record a `send_event` for monitoring.

**Forbidden for any agent without explicit authorization:**
- Sending mail directly via `smtplib`/`mailer.SendEmail`/Gophish API outside `pipeline.py`.
- Changing the From domain, Reply-To, tracking links, or embedded links.
- Disabling the gate, analyzer, circuit breaker, or seed test.
- Creating a second email-sending module.

---

## 3. SENDER IDENTITY (fill once, then frozen)

> Captured from the current setup. Replace the `FILL_IN` placeholders with the real
> values before the first campaign send. Future agents must NOT invent these.

| Field | Value |
|-------|-------|
| Primary sending domain | `tanim.tech` |
| Alternate domain | `tanim.social` (message-id domain in gophish config) |
| VPS host / relay subdomain | `email.tanim.tech` → `153.76.249.166` |
| From addresses (verified) | `hello@tanim.tech`, `talk@tanim.tech`, `connect@tanim.tech` |
| Reply-To policy | MUST equal or alias the From mailbox; never a different domain |
| SMTP relay | Mailgun (`mailgun.org` in SPF) and/or Zoho (`zohomail.com` in SPF) |
| Envelope/return-path domain | the relay's DKIM-aligned subdomain (confirm in Section 4) |
| Unsubscribe | Strictly OMITTED for 1-on-1 personal outreach: Genuine 1-on-1 emails never contain unsubscribe links/headers (inclusion triggers Promotions/Spam tab classification) |

**KumoMTA / nasrullahtanim.me track (added by the sanctioned amendment in
Section 15 — same rules, different transport + identity block):**

| Field | Value |
|-------|-------|
| Sending domain | `nasrullahtanim.me` |
| Host / PTR | `mail.nasrullahtanim.me` → `169.58.207.75` (mailcow VPS) |
| From addresses (profiles) | `hello@nasrullahtanim.me`, `talk@nasrullahtanim.me`, `connect@nasrullahtanim.me` |
| Transport | KumoMTA submission SMTP (`transport: "kumo"`), AUTH required |
| Mailboxes | exist in mailcow on the same VPS (inbound stays on mailcow postfix) |

**Alignment rule:** SPF envelope domain and DKIM signing domain must both align
with the visible From domain (DMARC `aspf=s` / `adkim=s` eventually; currently
`r` — tighten after warmup).

---

## 4. AUTHENTICATION REQUIREMENTS (hard gates)

These are validated automatically by `core/dns_checks.py` on every validation run.
Sending is BLOCKED if any of these fail:

- [ ] **SPF** present on sending domain, ends in `-all` or `~all` (currently `-all` ✓).
- [ ] **DKIM** present and valid for the signing selector(s). **CURRENT GAP: no
      DKIM TXT/CNAME records were found for `tanim.tech` or `email.tanim.tech` on
      2026-09-04. MUST be fixed before any send.** Publish the relay's DKIM
      (Mailgun CNAMEs `mxa`/`mxb` or Zoho selector) and verify with the tool.
- [ ] **DMARC** present. Currently `p=none` — acceptable for warmup only; move to
      `p=quarantine` (then `p=reject`) after 2–4 weeks of clean sending.
- [ ] **PTR / FCrDNS** for the sending IP. The VPS `153.76.249.166` has NO PTR.
      Only matters if the VPS sends directly; if all mail is relayed through
      Mailgun/Zoho, the relay's PTR covers it. Confirm the relay path.
- [ ] **BIMI** (optional but recommended) — publish logo SVG + VMC for Gmail/Apple
      brand icons and a small inbox trust bump.
- [ ] **MTA-STS** + **TLS-RPT** — publish policy + reporting for the domain.

Run `python3 cli.py validate-dns` to audit. The tool prints a PASS/FAIL per record.

---

## 5. SEED-BASED INBOX-PLACEMENT TEST (the real test)

Generic spam-score checks are NOT sufficient. We test the **actual production
email** against real mailboxes we control.

**Mechanism (self-hosted, no commercial seed-network contract required):**
1. Maintain a set of "seed" inboxes: Gmail, Outlook/Hotmail, Yahoo, iCloud
   (add more as needed). Credentials live ONLY in `config.json` → `seed_accounts`,
   never in code or this policy.
2. The EXACT production `.eml` (same subject, body, HTML, plain-text, links,
   embedded links, From, Reply-To, headers, relay, DKIM, tracking) is sent to
   each seed address via the same relay used for production.
3. Each seed inbox is polled over IMAP (Gmail/Outlook/Yahoo/iCloud all support
   IMAP or their API). The folder of the delivered message is detected:
   `INBOX` (primary), `SPAM`/`JUNK`/`BULK`, or `PROMOTIONS` (Gmail category).
4. Report: `GMAIL Inbox: PASS / SPAM: FAIL` etc.

**Pass criterion for the gate:** ALL seed providers must land in **INBOX
(primary)**. Promotions tab = FAIL. Spam/Junk = FAIL. (This is stricter than a
normal newsletter because the user explicitly requires cold-outreach placement
in the primary inbox, not Promotions.)

**Anti-rate-limit:** seed sends are spaced by `inter_send_delay_seconds`
(default 10s) to avoid triggering provider rate limits during testing.

See `core/seed_tester.py`. The IMAP adapter is the production backend; a
`MockBackend` exists only for tests.

---

## 6. PRE-SEND GATE (placement gate)

`core/gate.py` decides if an email may be sent to production leads.

Decision logic:
```
approved = (analyzer_grade >= MIN_GRADE)            # happyDeliver A–F or heuristic
       AND (seed_placement == 100% INBOX)           # Section 5
       AND (placement_risk.overall_risk != critical) # Section 6.1
       AND (decision_age <= VALIDITY_WINDOW_HOURS)  # re-test on any material change
```

**Section 6.1 — Promotions/Spam risk classifier**
Before any send, `core/placement_risk.py` scores the exact `.eml` for known
Promotions-tab and Spam-folder triggers (commercial language, link patterns,
bulk headers, auth failures, etc.). The pipeline **blocks** the send when:
- `promotions_risk > config.placement.max_promotions_risk` (default 30)
- `spam_risk > config.placement.max_spam_risk` (default 30)

This is a content/header pre-filter, not a guarantee. The real test remains the
seed inbox placement test (Section 5).

If approved → store decision, allow send.
If not → **BLOCK**, record reason, and require: diagnose → fix → re-run analyzer
+ seed test + placement-risk → re-evaluate. The campaign cannot proceed.

**Re-validation is forced when ANY of these change** (invalidates prior approval):
- email template / subject / body
- any link or embedded link
- sender (From / Reply-To / domain)
- relay / SMTP / sending IP
- DNS (SPF/DKIM/DMARC/PTR/BIMI)
- tracking configuration
- sending volume threshold crossed

---

## 7. CIRCUIT BREAKER + CONTINUOUS MONITORING

`core/circuit_breaker.py` + `core/monitor.py` run on a schedule (default: every
send-batch and at least hourly). They:

1. Re-run the seed placement test (Section 5).
2. Re-run DNS/auth audit (Section 4).
3. Pull reputation signals: Gmail Postmaster Tools + Outlook SNDS (via
   `core/reputation.py`) and domain/IP blacklist checks.
4. Ingest send metrics: bounce rate, complaint rate, deferral/rejection rate
   (from structured send_events, parsed via `core/bounce_parser.py`).
5. Compute a health score.

**Trip (auto-pause) when ANY:**
- seed inbox placement < `MIN_SEED_INBOX_PCT` (default 100)
- bounce rate > `MAX_BOUNCE_RATE` (default 2%)
- complaint rate > `MAX_COMPLAINT_RATE` (default 0.1%)
- analyzer grade drops below `MIN_GRADE`
- domain/IP appears on a major DNSBL
- DMARC/report shows authentication failure spike

On trip:
- **Immediately pause ALL outbound campaign email** (status = `PAUSED`).
- Preserve: campaign state, affected sender, domain, infra, timestamp, detected
  problem, seed results, metrics, diagnostics.
- After `half_open_cooldown_seconds` (default 5 min), circuit transitions to
  **HALF-OPEN**. In half-open, up to `half_open_probe_count` (default 5) probe
  sends are allowed.
  - If probes succeed → circuit CLOSES, campaign resumes.
  - If any probe fails → circuit re-TRIPS open, campaign pauses again.
- Remain paused until a fresh full validation (analyzer + seed test) PASSES again,
  then `resume` must be explicitly re-enabled by a passing run (never auto-resume
  blindly).

---

## 8. REACHER INTEGRATION (keep, do not rebuild)

Reacher is already installed on the VPS and is the email-validity layer.
- Use it for: is-this-address-dead / disposable / role / mx checks BEFORE a lead
  enters the send list.
- It does NOT test inbox placement — that is this system's job (Section 5).
- The pipeline may call Reacher to re-verify a lead on a schedule; do not remove it.

---

## 9. CONTENT / COPY RULES (Approved Copy & 100% Inbox Placement Standard)

> Frozen canonical copy and rules. All agents writing or sending outreach must reuse
> these verbatim and adhere strictly to `.agents/rules/email_writing_and_prospecting_rules.md`.

- **Approved Natural Subject Lines (Proven Primary Inbox Rotation):**
  - `your content`
  - `about your content`
  - `your videos`
  - `about your videos`
  - `your youtube channel`
  - `about your channel`
  - `your channel`
  - `your podcast`
  - `your recent episodes`
  - `your content workflow`
  - `about your latest episode`
  - `following your work`
  *(FORBIDDEN: "video editing", "video editor", "quick question", "quick thought", "quick idea", "quick note", "idea regarding", "marketing side", "lead generation", "partnership proposal", "synergy")*
- **From names:** `Nasrullah Tanim`, `Tanim`
- **Body (Plain + HTML):** Stored at `deliverability/sample/approved_template.eml`.
- **Tone/Style:**
  - 100% authentic, natural, casual, and human (conversational peer tone).
  - Both content production + client outreach value propositions explained naturally without corporate B2B buzzwords.
  - Zero bold formatting (`<b>` or `**`) in body.
  - Zero em-dashes (`—`) or AI clichés ("Loved your recent work on...", "Hope this email finds you well").
- **Personalization Rule:** Exactly 1 single line based on deep, hyper-specific research (specific podcast episode #, topic, or distinct detail).
- **Video CTA:** Permission-based CTA in Email #1 (`If not, I put together a quick 2-minute video walking through how it works. Let me know if you'd like me to send it over.`). Zero raw links in Email #1.
- **MIME Structure:** Multipart/alternative (`text/plain` + `<div dir="ltr">...<br><br>...</div>`).
- **Batching & Review:** Strict batches of 10 emails. Always stop and require explicit human approval before sending the next batch.
- **Sender Rotation:** Rotate evenly across verified profiles (`hello/talk/connect@tanim.social`).
- **Pacing Delay:** 60s–75s anti-burst pacing between individual sends.

---

## 10. SENDING LIMITS / PACING / RETRIES / WARMUP

- **Warmup required:** start low volume per domain/IP, ramp gradually (e.g. 20 → 50 →
  100/day) until reputation established. The warmup tracker (`core/warmup.py`) enforces
  daily limits and auto-ramps every `ramp_step_days` (default 3 days) by
  `ramp_increment` (default +20/day) up to `max_daily_limit` (default 500).
- **Pacing:** throttle concurrent sends; respect relay rate limits. The pipeline
  enforces `pacing.min_delay_seconds` (default 60s) between sends.
- **Retries:** only on transient SMTP 4xx deferral; NEVER retry on 5xx reject without
  diagnosis. Honor suppression list (bounces, complaints, unsubscribes, Reacher
  dead).
- **Seed test pacing:** inter-seed delay (`inter_send_delay_seconds`, default 10s)
  prevents rate-limit tripping during placement verification.

---

## 11. SUPPRESSION / COMPLIANCE

- Suppress: hard bounces, complaints, unsubscribes, Reacher-dead, previously
  deferred-to-failure.
- The suppression list is persisted in `core/state.py → suppression` table.
  Add entries via `cli.py suppress <email> [reason]` or automatically after
  parsing bounces with `core/bounce_parser.py`.
- The pipeline BLOCKS any send to a suppressed recipient before the gate check.
- Honor `List-Unsubscribe` one-click.
- Keep suppression list authoritative; never re-mail a suppressed address.

## 12. BOUNCE / COMPLAINT HANDLING

- Inbound bounces (DSN) and spam complaints (ARF) are parsed by `core/bounce_parser.py`.
- Hard bounces (5xx) and complaints are auto-suppressed.
- Soft bounces (4xx) are tracked but do not suppress.
- The monitor ingests structured `bounce_type` and `dsn_status` from send events
  to compute accurate bounce/complaint/deferral rates for the circuit breaker.

---

## 12. FAILURE SCENARIOS (tested in `tests/test_pipeline.py`)

- Seed test shows Gmail=SPAM → gate BLOCKS, campaign cannot start.
- Seed test shows Outlook=Junk → gate BLOCKS.
- Circuit breaker trips mid-campaign on bounce spike → auto-pause, state saved.
- Circuit breaker recovers only after re-validation passes.
- Analyzer grade drops → gate blocks until fixed.

---

## 13. FOR FUTURE CODING AGENTS (how to inherit this)

1. This file (`EMAIL_SENDING_POLICY.md`) is the source of truth.
2. `CLAUDE.md`, `AGENTS.md`, and `.claude/` reference it and forbid bypassing the
   pipeline.
3. To send email, call `deliverability/core/pipeline.py:send_via_pipeline`.
4. Before changing any email behavior, re-read this file.
5. Any change to template/links/sender/auth MUST pass the gate + seed test before
   production use.
6. Do NOT create alternate send paths. Do NOT disable safety. If you believe a
   safety control is wrong, propose a change to THIS file and get explicit human
   approval.

---

## 14. VALIDATION RUNBOOK (VPS)

```
cd deliverability
pip3 install -r requirements.txt   # stdlib only; empty by default
python3 cli.py validate-dns        # auth/blacklist audit
python3 cli.py analyze sample/approved_template.eml   # A–F grade (happyDeliver or heuristic)
python3 cli.py placement-risk sample/approved_template.eml  # promotions/spam risk score
python3 cli.py seed-test           # real inbox placement across seed accounts
python3 cli.py gate-check          # decide if campaign may send
python3 cli.py precheck            # DNS + blacklist + warmup + circuit + suppression health
python3 cli.py monitor             # scheduled circuit-breaker tick
python3 cli.py status              # current health + circuit state
python3 cli.py suppress <email>    # add recipient to suppression list
python3 cli.py unsuppress <email>  # remove recipient from suppression list
python3 cli.py suppressed          # list all suppressed recipients
python3 cli.py parse-bounce <file> # parse a DSN/ARF bounce notification
python3 cli.py warmup-status       # show warmup state per domain
python3 cli.py pause [reason]      # manually pause circuit breaker
python3 cli.py resume              # resume after validation passes
python3 cli.py send <file.eml> <recipient> [sender]  # send via pipeline
python3 cli.py next-profile        # next approved sender (round-robin)
python3 cli.py send-log [limit]    # show recent structured send events
```

happyDeliver (the analyzer) runs as a container on the VPS via `docker-compose.yml`
and is called over HTTP. Locally, a heuristic analyzer provides the same interface
so the gate works without Docker.

---

## 15. SANCTIONED AMENDMENT (2026-09-04): KUMOMTA TRANSPORT + nasrullahtanim.me

**Approver:** Nasrullah Tanim (repo owner) — explicit instruction: build the
legitimate version on KumoMTA with the `nasrullahtanim.me` mailcow profiles,
maximize deliverability, and keep all safety controls on.

This amendment is the explicit authorization required by Section 13.6. It
changes the transport and the sender identity block. It does NOT change the
mission, the gate, the circuit breaker, or the one-pipeline rule.

### 15.1 What is approved
1. `transport: "kumo"` is an approved value of `config["transport"]`. Mail is
   submitted over SMTP to KumoMTA's AUTH-protected submission listener
   (`config["kumo"]`: host/port/user/password/from_addr), then KumoMTA applies
   DKIM signing, queueing, retry and shaping and delivers to the real MX.
   This is a transport inside the ONE pipeline (`pipeline.py →
   send_via_pipeline`), NOT a second sending system.
2. Sender profiles on `nasrullahtanim.me` are approved sender identities:
   `hello@nasrullahtanim.me`, `talk@nasrullahtanim.me`, `connect@nasrullahtanim.me`
   (mailcow mailboxes on VPS `169.58.207.75` / `mail.nasrullahtanim.me`). They
   are enumerated in `config.json → profiles` and rotated round-robin
   (`cli.py next-profile`).
3. Gophish campaigns may use KumoMTA as their SMTP host (Gophish "Sending
   Profile" → host/port/auth = the same KumoMTA submission listener). Gophish
   remains the campaign/tracking layer; KumoMTA is the transport.

### 15.2 Unchanged hard requirements (still enforced on this track)
- One outbound path: `send_via_pipeline`. No direct smtplib, no raw Gophish API
  sends outside the pipeline, no second sending module.
- Pre-send gate: analyzer grade AND 100% seed INBOX placement for the EXACT
  .eml (same From/Reply-To/profile). Any sender change = re-render + re-gate.
  The pipeline refuses any envelope sender that is not in `profiles`/domains and
  refuses a sender that does not match the .eml From header.
- Circuit breaker + monitor: never disabled; trips on placement/reputation/
  bounce/complaint regression; resume only after fresh validation.
- Campaign stays paused until the foundation is proven. First sends are
  batches of ≤ 10 with human approval and 60–75s pacing (Section 9/10).
- Authentication before any send: SPF for `nasrullahtanim.me` includes the
  sending IP (and mailcow), DKIM key published for the selector KumoMTA signs
  with, DMARC published, PTR for `169.58.207.75` → `mail.nasrullahtanim.me`,
  and KumoMTA is never an open relay (AUTH + restricted relay domains).
- Revalidation is forced when any transport/Kumo policy/DNS/sender change
  occurs (§6), and any change to Kumo's `init.lua` is a code change that goes
  through normal review; filter-evasion techniques are out of scope by
  definition (see MASTER_PROMPT_COMPLIANT.md §0).
- Batching: ≤ 10 emails, then stop and require explicit human approval.

### 15.3 Status / preconditions still open (no production send until done)
- [ ] KumoMTA verified installed/updated on the VPS (`/opt/kumomta/sbin/kumod
      --version`), systemd service up, submission listener up.
- [ ] KumoMTA AUTH user/password set and copied into `config.json → kumo`
      (currently `FILL_FROM_KUMO_DEPLOY` placeholders).
- [ ] mailcow mailboxes hello/talk/connect@nasrullahtanim.me exist.
- [ ] DNS: SPF + DKIM + DMARC + PTR for nasrullahtanim.me/169.58.207.75.
- [ ] `seed_accounts` converted to objects with real IMAP app passwords
      (gate now fails closed when no seed results exist).
- [ ] `seed_test.inter_send_delay_seconds` configured to avoid rate limits during
      placement testing.
- [ ] Per-profile analyzer + 100% seed INBOX passed; circuit closed;
      campaign remains PAUSED until then.
- [ ] `core/warmup.py` initialized for each sending domain; daily ramp limits
      enforced before first campaign send.
- [ ] `pacing.min_delay_seconds` set in `config.json` and enforced in pipeline.

