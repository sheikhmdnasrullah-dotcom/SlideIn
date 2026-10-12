# GoPhish ↔ KumoMTA Coordination

Verified and wired on VPS `169.58.207.75` (2026-09-08).

## What's set up

- **KumoMTA** (`/opt/kumomta`, systemd `kumomta.service`) listens on `0.0.0.0:2587`
  (submission) and `127.0.0.1:8000` (admin). Signs DKIM for `nasrullahtanim.me`
  with selector `dkim`; egress source `169.58.207.75`, EHLO `mail.nasrullahtanim.me`.
- **GoPhish** SMTP sending profiles (IDs 9/10/11) point at KumoMTA:
  - `KumoMTA - hello@nasrullahtanim.me`  → `127.0.0.1:2587`, auth `admin`
  - `KumoMTA - talk@nasrullahtanim.me`   → `127.0.0.1:2587`, auth `admin`
  - `KumoMTA - connect@nasrullahtanim.me`→ `127.0.0.1:2587`, auth `admin`
  All authenticate to KumoMTA and send as their respective `nasrullahtanim.me` address.

## Deliverability baseline (verified)

- FCrDNS: `mail.nasrullahtanim.me` ↔ `169.58.207.75` ↔ PTR — **match**
- SPF `v=spf1 mx -all` — **pass** (mx = `169.58.207.75`)
- DKIM selector `dkim._domainkey.nasrullahtanim.me` — **published & matches key**
- DMARC `v=DMARC1; p=quarantine` — **enforcing**
- VPS IP `169.58.207.75` — **not on Spamhaus/SpamCop/SORBS/AbuseAT/CBL**
- Test send from all 3 profiles → owned seed Gmail: **all 3 landed in INBOX**

## Notes / next steps

- One-click `List-Unsubscribe` should be added at the **template/sending-app** layer
  (not the MTA — KumoMTA has no simple header-injection API and editing the live
  policy risks the running service). Required for Gmail/Yahoo bulk-sender rules.
- Keep volume within the warmup-engine envelope; monitor seed placement via the
  existing `deliverability/` tooling (happydeliver + seed IMAP checks).
- No system can guarantee 100% inbox; the above is the legitimate ceiling.
