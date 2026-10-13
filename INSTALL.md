# Install SlideIn on your own VPS

One command installs the complete self-hosted outreach stack on a fresh
Ubuntu VPS: mail server (KumoMTA), campaign backend (GoPhish), web
dashboard, HTTPS (Caddy), lead verification, warmup platform, monitoring,
and the deliverability CLI. No shared infrastructure — your VPS, your IP,
your domains, your reputation.

## Prerequisites

- A VPS with **Ubuntu 22.04/24.04 x86_64**, 4GB+ RAM, 20GB+ disk, root SSH.
- The VPS host must allow **outbound port 25** (email cannot send without
  it — ask for unblocking *before* installing; the installer checks this).
- One **base domain** for the software (`app.`/`console.`/`track.` hosts).
- One or more **sender domains** for mail (can differ from the base domain).
- DNS control for all of them (any provider; Cloudflare or otherwise).

## Install

As root on the fresh VPS:

```bash
curl -fsSL https://raw.githubusercontent.com/sheikhmdnasrullah-dotcom/SlideIn/main/install.sh \
  | bash -s -- --base-domain client.com \
             --mail-domains send1.com,send2.com \
             --admin-email you@client.com
```

Optional flags: `--senders hello,talk,connect` (default shown),
`--minimal` (skip the Warmbly warmup platform),
`--non-interactive`, `--dry-run` (preview anywhere, changes nothing),
`--regenerate-secrets` (rotate generated secrets on rerun).

The installer is **idempotent** — rerunning it after adding DNS finishes
verification without duplicating anything, and never sends email by itself.

## What you get

| URL | Service |
|---|---|
| `https://app.<base>/` | Dashboard (campaigns, leads, verification) |
| `https://console.<base>/login` | Campaign console (user `admin`, first-login password rotation) |
| `https://track.<base>/` | Landing + tracking pixels (404 on `/` is correct) |
| `https://warmbly.<base>/` | Warmup platform (unless `--minimal`) |

Sending profiles (`sender × domain`) relay through KumoMTA on loopback
`:2587` with per-domain DKIM signing. Secrets live root-only in
`/opt/slidein/.secrets.env`. Your exact DNS table is saved to
`/opt/slidein/dns-records.txt` during install.

## After install (required, ~30 min + propagation)

1. Add the DNS records from `/opt/slidein/dns-records.txt`, wait ~5 min,
   rerun the installer to re-verify.
2. Set reverse DNS (PTR) in your **VPS panel**: your IP →
   `mail.<first-sender-domain>`.
3. Verify: `cd /opt/deliverability && python3 cli.py precheck`.
4. Register sender domains in Gmail Postmaster Tools + Microsoft SNDS.
5. Connect mailboxes in the Warmbly UI; ramp volume gradually (new IPs
   have no reputation — start ~20–50/day and double weekly).
6. Dashboard ships **open** (no login) for first-run simplicity. Before
   inviting users, put Caddy `basic_auth` in front of the app host (see
   `/etc/caddy/Caddyfile`) or wire auth keys into
   `/var/www/workspace-app/.env.local` and rebuild.

## Run it locally instead

The installer targets servers, but local development uses the repo's dev
stack (`./dev` + `./doctor` — see `docs/development/LOCAL_SETUP.md`).
Campaign sending from a laptop is not recommended (residential IPs are
blocklisted); develop locally, send from the VPS.

## Managed installs

If you'd rather not operate this yourself, managed private installs
(setup on your VPS, monitoring, deliverability reviews) are available
from the author at a flat monthly rate — open an issue on GitHub to ask.

## Licenses (all permissive, no paid seats)

KumoMTA (Apache-2.0), GoPhish base (MIT), Warmbly (Apache-2.0),
check-if-email-exists (MIT), Agent-Reach (MIT), SlideIn code (MIT).
See `NOTICE`. You may self-host commercially, including for clients.

## Troubleshooting

- `port 25 outbound is BLOCKED`: only your host can fix this. Contabo,
  Hetzner (on request), and most KVM hosts unblock on ticket.
- HTTPS shows nothing: DNS hasn't propagated — check
  `dig +short A app.<base>`, wait, rerun installer.
- `KumoMTA metrics never came up`: `docker logs kumomta`, then
  `cd /opt/kumomta-lab/compose && docker compose -p kumomta-production logs`.
- GoPhish login loops with CSRF errors: the console host must be a **bare
  host** in `admin_server.trusted_origins` (no `https://`) —
  the installer does this; hand edits often break it.
- Full reset: unfortunately there is no uninstaller yet — wipe the VPS
  and reinstall (it takes ~15 minutes).
