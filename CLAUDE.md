PROJECT CONTEXT: Internal Gophish phishing-simulation tool for employee security training (Tanim Social / tanim.tech)

Purpose: Self-hosted, authorized internal phishing simulation tool to train own employees (editors, cold email senders). Using a friend's customized Gophish (Go) fork, source provided as raw folder, no code from official GitHub repo used.

PRODUCTION SETUP (VPS — live, working)
VPS: VPSServer.com, hostname tanim-email, IP 153.76.249.166, Singapore, 2 CPU / 2GB RAM / 20GB disk
Domain: tanim.tech (DNS on Cloudflare)
Gophish admin panel: https://email.tanim.tech, nginx reverse-proxies to gophish on 127.0.0.1:8333, gophish serves its own TLS, so nginx proxy_pass must be https://127.0.0.1:8333 with proxy_ssl_verify off and proxy_set_header Referer ""
Gophish runs as systemd service gophish.service, working dir /root/gophish
config.json: admin_server 0.0.0.0:8333, use_tls true, trusted_origins ["https://email.tanim.tech"], phish_server 0.0.0.0:8080, use_tls false
ufw: OpenSSH, 80, 443, 8080 allowed, port 8333 direct access status should be re-checked
Let's Encrypt cert on email.tanim.tech via certbot
Nightly cron backs up gophish.db, logrotate configured for gophish.log
Mailgun tanim.tech verified for sending, SPF merged, DKIM under separate selector, tracking CNAME moved to track.tanim.tech
Sending profiles: hello@, talk@, connect@ at tanim.tech
tanim.social done same way, nasrullahtanim.me not started

NEW SETUP IN PROGRESS (local MacBook + Cloudflare Tunnel, not yet working)
Goal: run gophish natively on the Mac, private by default, reachable via Cloudflare Tunnel only when needed
Source built locally at ~/Downloads/email-master raw, built via yarn install, gulp build, CGO_ENABLED=1 go build -o gophish
Local config.json: admin_server 127.0.0.1:3333, use_tls true, trusted_origins ["https://admin.tanim.tech"], phish_server 127.0.0.1:8080, use_tls false
cloudflared installed via brew, authenticated
Tunnel name admin-tunnel, ID 2c0b57cb-ec07-47c4-85c9-69c6ed0a6ce0
DNS route admin.tanim.tech to tunnel
~/.cloudflared/config.yml points admin.tanim.tech to https://localhost:3333, noTLSVerify true, protocol http2

CURRENT UNRESOLVED BUG: Login at https://admin.tanim.tech returns "Forbidden – referer invalid" after entering credentials, even though config.json confirmed correctly has trusted_origins ["https://admin.tanim.tech"] and both gophish and tunnel were restarted from correct folders. Next step: check gophish's live terminal output for the exact POST /login log line to see what referer value it actually received vs expected.

Known gotchas:
systemctl status hangs, needs q to exit the pager
Mixing up which terminal tab runs gophish vs tunnel vs plain shell has caused false alarms, check folder in tab title
nginx proxy_pass protocol must match gophish's own use_tls setting exactly
Any subdomain reused between gophish and Mailgun tracking breaks whichever was there first

Future plan (not started): custom Next.js frontend calling gophish's REST API, server side only, eventually offered to friends' companies as separate isolated instances per client, not shared multi-tenant.

 ================================================================================
 WORKING RULES
 ================================================================================
 The only working policy for this repo is **PROJECT_POLICY.md** (repo root).
 Read it first before touching email functionality.

 Old campaign-era rules (gate, circuit breaker, one-pipeline rule, copy rules,
 runbook) were archived on 2026-09-08 under `archived_rules/` and the old
 `EMAIL_SENDING_POLICY.md`; they are reference material, not binding.
