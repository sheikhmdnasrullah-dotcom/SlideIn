# Slidein Venture — Production Runbook & Tool Execution Order

> Verified live on VPS `<PRIMARY_VPS_IP>` on 2026-10-27. Every command below
> was exercised against the running system during bring-up.

---

## 1. What runs where (single VPS, all containers `restart: unless-stopped`)

| Layer | Component | Where | Proof |
|---|---|---|---|
| Edge | Caddy (TLS termination, LE certs) | host :80/:443 | `app.`, `workspace.`, `api.`, `track.`, `console.`, `warmbly*.`, `mail.` hosts live |
| App | slidein-api (FastAPI, canonical backend) | systemd :8100 | `GET /v1/health` → healthy, 144 routes |
| App | slidein-app / workspace-app (Next.js) | pm2 :3201 / :3001 | served via Caddy |
| Mail out | KumoMTA (MTA, DKIM signer) | docker :2587 submit, :8029 admin | AUTH send verified; live relay to Gmail: dkim=pass spf=pass dmarc=pass |
| Mail in | **Stalwart Mail Server v1.0** (mailboxes) | docker host-net :25 / :465 / :993, admin :8087 loopback | inbound to INBOX + IMAP verified; outbound relays via KumoMTA |
| Campaigns | GoPhish (fork) | systemd :8333 admin, :8080 phish | 9 sending profiles via KumoMTA |
| Verify | Reacher (engine :8090, job_api :8091) | docker + host | `hello@tanim.social` → deliverable verdict |
| Warmup | Warmbly (11 containers) | docker :8180 API | 9 mailboxes connected, warming, auth passing |
| Reply pipeline | imap-poller (systemd) | reads Stalwart IMAP → POST /v1/webhooks/inbound | reply threaded + intent classified live |
| Guard | deliverability monitor (systemd timer, 15 min) | `python3 cli.py monitor` | circuit-breaker tick runs green |
| Metrics | Prometheus + Grafana + Loki + Alertmanager | docker :9090/:3000/:3100 | restored, loopback-only |

Secrets live only on the VPS: `/opt/slidein-api/.env`, `/opt/deliverability/config.json`,
`/opt/warmbly/.env`, `/root/.stalwart-mailboxes.json` (9 mailbox passwords),
`/root/.warmbly-api-key`, `/root/.imap-poller-key`, `/root/.stalwart-*-creds`,
and locally `~/.slidein-vps-credentials` (KUMO_AUTH_PASS etc.).

---

## 2. The fixed execution order (canonical 7 stages — never reorder)

Each stage's tools run **in this order**. A stage fails closed: it blocks the
next until its prerequisite is satisfied.

### Stage 1 — Configure (once, then versioned)
1. DNS: SPF/DKIM/DMARC (p=quarantine) on all 3 domains + PTR — verify: `dig TXT`, `dig -x <PRIMARY_VPS_IP>`
2. Business profile / offers / ICP in the Console (Business Setup)
3. Sending identity: the 9 mailboxes (3 domains × hello/talk/connect) live on Stalwart
4. Warmup contract: `POST /v1/tenants/{id}/warmup/start` with the mailbox list — starts the 14-day clock

### Stage 2 — Discover
1. Prospect ingest: `POST /v1/tenants/{id}/discover` (CSV batch / manual records) — idempotent, deduped
2. Suppression list auto-seeded

### Stage 3 — Research
1. `POST /v1/tenants/{id}/prospects/{pid}/research` (orchestrated: OpenOSINT → Firecrawl (key) → WebsiteConnector fallback)
2. Evidence persisted with provenance (`GET .../prospects/{pid}/evidence`)

### Stage 4 — Qualify
1. `POST .../prospects/{pid}/qualify` — deterministic ICP scoring (needs ≥ threshold), offer match
2. Personalize is blocked until status = `qualified`

### Stage 5 — Personalize
1. `POST .../prospects/{pid}/personalize` — versioned draft, cites evidence
2. `GET .../drafts/{did}/preflight` — copy spam audit + MX check (read-only)

### Stage 6 — Outreach
1. `POST .../drafts/{did}/approve` (human approval — mandatory)
2. `POST .../drafts/{did}/send`
   - Pre-send gates, in order: approval → warmup gate (14-day rule) → Reacher `safe` → spam-copy hard gate → MX advisory → circuit breaker → suppression → compliance (address, lawful basis, List-Unsubscribe)
   - Transport: `SLIDEIN_TRANSPORT=kumo` on the service. **The warmup gate blocks live sends with 409 `mailbox_warmup_incomplete` until 2026-11-10** (fail-closed by design; dry-run records the full lifecycle)
   - Wire path: API → KumoMTA :2587 (AUTH) → recipient MX. Verified: Gmail inbox, dkim=pass spf=pass dmarc=pass

### Stage 7 — Converse
1. Reply lands on Stalwart :25 → INBOX
2. imap-poller (60 s cycle) reads all 9 inboxes → `POST /v1/webhooks/inbound` (service key)
3. API threads by Message-ID → subject → sender; classifies intent (7 intents, threshold 0.5)
4. Unsubscribe → immediate suppression + opt-out
5. Interested → handoff (booking destination is versioned client config; Notion constants remain TODO)

Feedback loop: conversation outcomes → Overview/Activity → approved corrections → Configure.

---

## 3. Warmup timeline (Phase 4)

- 2026-10-27: all 9 mailboxes connected to Warmbly, warmup started, DNS auth `passing`
- Warmbly daily ramp runs automatically (worker/consumer containers)
- 2026-11-10: 14 days complete → the canonical live-send gate opens (verify via `GET /v1/tenants/ten_local/warmup?refresh=true` → `ready: true`)
- GoPhish profiles + KumoMTA shaping remain the batch/daemon path; the canonical API path is the approved one

## 4. Daily ops (in order)

```bash
ssh root@<PRIMARY_VPS_IP>
systemctl is-active slidein-api imap-poller gophish caddy   # app layer
docker ps --format '{{.Names}}\t{{.Status}}' | sort         # 19 containers
curl -s localhost:8100/v1/health                            # API
systemctl list-timers deliverability-monitor.timer          # guard tick
journalctl -u imap-poller --since today | grep -c FAILED    # reply pipeline errors
cd /opt/deliverability && python3 cli.py status             # circuit + gate
```

Red → act: circuit tripped → `cli.py pause <reason>` / fix DNS / `resume`;
Warmbly unreachable → live gate stays closed (correct); bounce spike →
suppression service auto-blocks, check `GET .../sending`.

## 5. Restart-order cheat sheet (if the whole box reboots)

1. Docker comes up on its own (restart policies set): KumoMTA, Stalwart, Warmbly, Reacher, Prometheus/Grafana/Loki
2. `systemctl start gophish slidein-api imap-poller caddy`
3. `pm2 resurrect` (slidein-app, workspace-app)
4. Verify: §4 checklist. The only known cold-start gap was KumoMTA family
   containers stopped without restart policy — now `unless-stopped`.

## 6. Known gaps / next actions (tracked, not blocking)

1. ~~MX for tanim.social / tanim.tech~~ **Done 2026-10-27**: `MX 5 mail.nasrullahtanim.me`
   is primary on both zones (Zoho kept at 10/20/50 as backup). Verified with a real
   Gmail→hello@tanim.social delivery landing in the Stalwart INBOX over TLS.
   Old mail still sits in Zoho — migrate via IMAP copy if history is needed.
2. **Booking webhook** — constants only (Notion + $350); needs versioned client config + provider webhook.
3. **happyDeliver / seed tester** not deployed → legacy monitor reports `seed inbox 0.0%` (circuit trips on the
   legacy daemon path only; canonical path unaffected). Deploy happyDeliver or wire seed inboxes to green it.
4. **Stale Mailgun + old warmup-engine configs** on the host (credentials dead); warmup-engine superseded by Warmbly.
5. Frontend slidein-app is an older pm2 build; rebuild against the current API when UI work resumes.
6. `2captcha` remains installed but unauthorized — do not enable.
