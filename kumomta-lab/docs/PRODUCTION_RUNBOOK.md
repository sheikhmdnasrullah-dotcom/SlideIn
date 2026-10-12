# PRODUCTION RUNBOOK — KumoMTA + nasrullahtanim.me + Gophish (legitimate track)

This is the operator runbook for the version approved in
`EMAIL_SENDING_POLICY.md` §15. Everything here is **legitimate, measured,
consent-aware deliverability engineering** — no filter evasion, no guaranteed
inbox claims. Nothing in this file sends to a real recipient until the last
section, and even then only in batches of ≤ 10 with explicit human approval.

> ⚠️ Run every command from **your own terminal** (the machine that can reach
> the VPS). This sandbox has no SSH/network egress, so nothing below was
> executed here. Commands marked **[READ]** are read-only; **[WRITE]** changes
> the server. Never run a [WRITE] until you have a backup (Section 9).

---

## 1. Where things stand (facts from the 2026-09-04 audit in this repo)

Server `169.58.207.75` = `mail.nasrullahtanim.me` (Ubuntu 24.04, Docker).
Running today:

| Service | State | Ports |
|---|---|---|
| mailcow (postfix inbound, dovecot, rspamd) | ✅ up 2 weeks | 25/465/587 (postfix), 110/143/993/995/4190 |
| Gophish (native binary) | ✅ up | 127.0.0.1:3333 admin, 127.0.0.1:8080 phish |
| happyDeliver (analyzer) | ✅ up | 127.0.0.1:2525, 127.0.0.1:8095 |
| reacher (validity) | ✅ up | 127.0.0.1:8090 |
| theHarvester, temporal, stirling-pdf | ✅ up | 5005 / 7233,8233 / 3002 |
| **KumoMTA (`kumod`)** | ❌ **not present** in the audit (no process, no container, no submission port) | — |

So: **KumoMTA is almost certainly NOT yet installed on the VPS.** A local
source clone exists in this repo at `kumomta-src/` (with the official docs
mirror) and the lab image is `ghcr.io/kumocorp/kumomta` (used by
`kumomta-lab/compose/docker-compose.yml`).

---

## 2. Fresh read-only verification (run from your terminal)

```bash
VPS=root@169.58.207.75
sshpass -p "$VPS_PASS" ssh -o ConnectTimeout=15 $VPS bash -s <<'EOF'
  echo "--- kumod? ---"; ls -l /opt/kumomta/sbin/kumod 2>&1
  /opt/kumomta/sbin/kumod --version 2>&1 || true
  echo "--- systemd ---"; systemctl status kumomta --no-pager 2>&1 | head -8
  echo "--- processes ---"; ps aux | grep -i kumo | grep -v grep || echo none
  echo "--- kumo ports ---"; ss -tlnp | grep -E ':(5872|8029|2587|8025)' || echo "no kumo listener"
  echo "--- docker images ---"; docker images | grep -i kumo || echo "no kumo image"
  echo "--- DNS now ---"
  dig +short MX nasrullahtanim.me; dig +short TXT nasrullahtanim.me
  dig +short TXT _dmarc.nasrullahtanim.me
  dig +short -x 169.58.207.75
EOF
```

If `kumod --version` prints a version → KumoMTA is installed; record the
version and compare to the latest release on
https://github.com/KumoCorp/kumomta/releases and upgrade via the same method
used to install (Section 3), then re-verify. If it prints nothing → install it
(Section 3).

The live DNS section tells you what SPF/DKIM/DMARC/PTR already exist for
`nasrullahtanim.me` — do not blindly add records that already exist.

---

## 3. Install / update KumoMTA on the VPS

### Option A — native package (recommended for production)
KumoMTA publishes prebuilt packages; the exact repo URL changes, so follow the
official guide mirrored locally in this repo at
`kumomta-src/docs/userguide/installation/linux.md` (also at
https://docs.kumomta.com/userguide/installation/linux/ ). Summary for Ubuntu:

```bash
# [WRITE] — run on the VPS, per the official guide
# 1) add the KumoMTA package repo + key (commands in installation/linux.md)
# 2) apt-get update && apt-get install -y kumomta
# 3) verify
/opt/kumomta/sbin/kumod --version
systemctl enable --now kumomta
```

Upgrading later = the same `apt-get install -y kumomta` after `apt-get update`.

### Option B — container (uses the same image the lab already pulls)
```bash
# [WRITE] on the VPS. Kumo runs as its own container; mailcow keeps :25 inbound.
docker pull ghcr.io/kumocorp/kumomta:latest   # pin a release tag in production
mkdir -p /opt/kumomta/etc/policy /opt/kumomta/dkim /var/log/kumo
docker run -d --name kumomta --restart unless-stopped \
  -p 127.0.0.1:5872:5872 \
  -v /opt/kumomta/etc/policy:/etc/kumo/policy:ro \
  -v /opt/kumomta/dkim:/etc/kumo/dkim:ro \
  ghcr.io/kumocorp/kumomta:latest
docker logs kumomta --tail 50
```
Confirm the exact entrypoint/volume expectations of the pinned tag before
relying on it.

### Whatever you choose
- Never let Kumo bind `0.0.0.0:25` (mailcow owns port 25). Kumo's submission
  listener binds `127.0.0.1:5872`; Kumo egress is a normal outbound client on
  port 25 and needs no listener.
- Confirm it is never an open relay: submission requires AUTH (Section 4) and
  only approved sender domains are relayed.
- Re-run the Section 2 checks — you must now see a version and a listener.

---

## 4. Configure KumoMTA (starter policy — adapted from the working lab policy)

The lab policy `kumomta-lab/policy/init.lua` is known-good KumoMTA Lua API.
Below is the **production** starter adapted from it. Place it as
`/opt/kumomta/etc/policy/init.lua` (native) or the mounted path (container).

```lua
-- /opt/kumomta/etc/policy/init.lua  (production starter — review + restart)
local kumo = require 'kumo'

-- Load auth secrets from a file outside version control.
local SECRETS = {}
pcall(function() SECRETS = dofile('/opt/kumomta/etc/policy/secrets.lua') end)

kumo.on('pre_init', function()
  kumo.set_readyq_threads(math.ceil(kumo.available_parallelism() / 2))
end)

kumo.on('init', function()
  kumo.configure_accounting_db_path('/var/lib/kumo/accounting.db')
  kumo.define_spool { name = 'data', path = '/var/lib/kumo/spool/data', kind = 'RocksDB' }
  kumo.define_spool { name = 'meta', path = '/var/lib/kumo/spool/meta', kind = 'RocksDB' }

  -- Submission listener: loopback ONLY + AUTH. Not an open relay.
  kumo.start_esmtp_listener {
    listen = '127.0.0.1:5872',
    relay_hosts = { '127.0.0.1', '::1' },
    banner = 'mail.nasrullahtanim.me ESMTP',
    max_messages_per_connection = 50,
    max_recipients_per_message = 1,   -- 1-on-1 outreach only
  }

  kumo.start_http_listener {
    listen = '127.0.0.1:8029',
    trusted_hosts = { '127.0.0.1', '::1' },
  }

  kumo.configure_local_logs {
    log_dir = '/var/log/kumo',
    max_segment_duration = '5 minutes',
  }
end)

kumo.on('smtp_server_auth_plain', function(_authz, authc, password)
  return (SECRETS.users or {})[authc] == password
end)

kumo.on('http_server_validate_auth_basic', function(user, password)
  return (SECRETS.users or {})[user] == password
end)

-- Only our own verified domain may be injected; anything else is rejected
-- before it can ever be queued.
local ALLOWED_SENDER_DOMAINS = { ['nasrullahtanim.me'] = true }

kumo.on('smtp_server_message_received', function(msg)
  local from = msg:from_header()
  if not from then
    kumo.reject(552, '5.6.0 Missing From header')
  end
  if not ALLOWED_SENDER_DOMAINS[from.domain] then
    kumo.reject(550, '5.7.1 Sender domain not authorized')
  end

  -- DKIM sign with the key for the From domain (selector 'kumo').
  local ok, signer = pcall(function()
    return kumo.dkim.rsa_sha256_signer {
      domain = from.domain,
      selector = 'kumo',
      headers = { 'From', 'To', 'Subject', 'Date', 'Message-ID', 'Reply-To' },
      key = '/etc/kumo/dkim/nasrullahtanim.me.private.key',
    }
  end)
  if ok then
    msg:dkim_sign(signer)
  else
    kumo.reject(451, '4.7.0 DKIM signer unavailable')
  end
end)

-- No get_egress_path_config override: use KumoMTA built-in defaults
-- (port 25, opportunistic TLS). Add shaping/TSA later via the official docs.
```

Secrets file `/opt/kumomta/etc/policy/secrets.lua`:

```lua
return {
  users = {
    ['outbound'] = 'CHANGE_ME_LONG_RANDOM_PASSWORD',
  },
}
```

```bash
# [WRITE] on the VPS — DKIM key + restart + verify
mkdir -p /etc/kumo/dkim /var/log/kumo /var/lib/kumo/spool/data /var/lib/kumo/spool/meta
openssl genrsa -out /etc/kumo/dkim/nasrullahtanim.me.private.key 2048
chown -R kumod:kumod /etc/kumo/dkim /var/log/kumo /var/lib/kumo 2>/dev/null || true
openssl rsa -in /etc/kumo/dkim/nasrullahtanim.me.private.key -pubout -outform der | openssl base64 -A
# ^ prints the public key value you publish as the DKIM TXT record (Step 5)
systemctl restart kumomta          # native
# docker restart kumomta           # container
systemctl status kumomta --no-pager | head -12
journalctl -u kumomta --no-pager -n 30   # confirm clean start (native)
# docker logs kumomta --tail 30          # (container)
```

If `kumod` fails to start, the policy has an error — fix it before continuing;
a failed start means **nothing sends** (fail-safe).

**Smoke-test submission (no real recipient):** submit to your own mailcow
mailbox `hello@nasrullahtanim.me` over IMAP, or a seed Gmail inbox, and confirm
it arrives with a valid DKIM signature
(`Authentication-Results: dkim=pass`).

---

## 5. DNS records (registrar/Cloudflare zone for nasrullahtanim.me)

Check what already exists first (Section 2) and merge — never duplicate.

| Record | Name | Value |
|---|---|---|
| MX | `nasrullahtanim.me` | existing mailcow MX (do NOT change) |
| SPF | `nasrullahtanim.me` TXT | `v=spf1 ip4:169.58.207.75 <keep existing mx/a includes> -all` |
| DKIM | `kumo._domainkey.nasrullahtanim.me` TXT | `v=DKIM1; k=rsa; p=<public key from Step 4>` |
| DMARC | `_dmarc.nasrullahtanim.me` TXT | `v=DMARC1; p=none; rua=mailto:dmarc@nasrullahtanim.me; adkim=s; aspf=s` (tighten to `quarantine` after 2–4 clean weeks) |
| TLS-RPT (optional) | `_smtp._tls.nasrullahtanim.me` TXT | `v=TLSRPTv1; rua=mailto:tlsrpt@nasrullahtanim.me` |
| PTR | `169.58.207.75` (host panel / ticket) | `mail.nasrullahtanim.me` — request from the host; not settable in DNS |

Verify with the repo tooling:
```bash
cd deliverability
python3 cli.py validate-dns nasrullahtanim.me 169.58.207.75
```

---

## 6. mailcow mailboxes + Gophish wiring

**Mailcow** (already running on the VPS):
- Create (or confirm) the three mailboxes / aliases:
  `hello@nasrullahtanim.me`, `talk@nasrullahtanim.me`, `connect@nasrullahtanim.me`.
- Keep inbound on mailcow postfix (port 25). KumoMTA is outbound only.

**Gophish** (native, `127.0.0.1:3333`):
- Add a **Sending Profile** per From profile:
  - Host: `127.0.0.1:5872`
  - From: `hello@nasrullahtanim.me` (and `talk@`/`connect@` for the others)
  - Username/Password: the `outbound` credentials from `secrets.lua`
- Gophish is now the campaign/tracking layer and KumoMTA is the transport.
  Any campaign created in Gophish is subject to the same gate rule: run the
  placement gate on the exact template before a real campaign send.

---

## 7. Deliverability pipeline setup (the safety rails)

On the VPS (localhost is simplest, since the Kumo listener is loopback-bound):

```bash
mkdir -p /opt/deliverability && cp -r deliverability/* /opt/deliverability/
cd /opt/deliverability
python3 -m unittest discover -s tests -v    # control-logic tests must pass
```

Edit `config.json` (currently has `FILL_FROM_KUMO_DEPLOY` placeholders):
- `kumo.user` / `kumo.password` → the real `outbound` credentials.
- `seed_accounts`: replace the plain-string addresses with objects that include
  real IMAP app passwords (see `config.example.json` for the shape — one Gmail,
  one Outlook, one Yahoo, one iCloud minimum). The gate **fails closed** with no
  seed results, so this is mandatory before anything can send.

Run the acceptance sequence (per profile — render the .eml with that profile's
From/Reply-To first):

```bash
python3 cli.py validate-dns nasrullahtanim.me 169.58.207.75
python3 cli.py analyze sample/approved_template.eml        # grade must be >= A
python3 cli.py seed-test <profile.eml>                     # must be 100% INBOX
python3 cli.py gate-check <profile.eml>                    # must print APPROVED
python3 cli.py monitor                                     # circuit breaker tick
python3 cli.py status                                      # CAMPAIGN stays PAUSED
```

Only after every profile passes and the circuit is closed may the campaign be
moved to ACTIVE — and even then only in batches (Section 8).

---

## 8. First-batch protocol (human-gated, never automated beyond this)

1. Prepare ≤ 10 personalized `.eml` files using the canonical template rules in
   `.agents/rules/email_writing_and_prospecting_rules.md`.
2. Rotate senders evenly: `python3 cli.py next-profile` before each render, and
   set that address as From + Reply-To in the .eml.
3. Send each through the ONE pipeline:
   `python3 cli.py send <profile.eml> <recipient> [sender]`
   with 60–75 s pacing between sends.
4. After the batch: run `python3 cli.py monitor` and check placement/bounce/
   complaint signals. **Stop and get human approval before the next batch.**
5. Kill-switch at any time: `python3 cli.py pause "reason"` (trips the circuit
   breaker; no mail can leave).

---

## 9. Rollback / safety

- Config backups exist for mailcow + Kumo under `kumomta-lab/scripts/`
  (`backup.sh`, `restore.sh`, `rollback.sh` — run before any [WRITE]).
- Re-run `kumomta-lab/scripts/audit.sh` read-only after any change.
- Firewall: never open Kumo's submission port beyond loopback; keep port 25 on
  mailcow. Re-test that Kumo rejects unauthenticated relay attempts.

---

## 10. Honest expectations (what "maximum deliverability" means here)

- Google/Yahoo require (since Feb 2024): DKIM+SPF+DMARC aligned, one-click
  unsubscribe on bulk, spam-complaint rate < ~0.1–0.3%, and a clean IP/domain
  reputation. Those are enforced per-domain/IP and cannot be "bypassed" — they
  are earned by warmup, pacing, engagement, and suppression.
- This system's enforceable guarantee is: **every send is proven to reach the
  Inbox on your own seed accounts before and during sending, and sending
  auto-pauses the moment placement/reputation degrades.** That is what the
  gate, seed test, and circuit breaker enforce here.
- Watch Gmail Postmaster Tools + Outlook SNDS for the sending IP/domain and
  react to complaint/bounce spikes — that is the reputation feed the circuit
  breaker consumes via `core/reputation.py`.


