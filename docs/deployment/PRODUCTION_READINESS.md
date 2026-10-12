# Production Readiness — SlideIn

> Honest status 2026-10-12: a production deployment **exists and is
> healthy** (single VPS, public HTTPS, green mail auth), operated by the
> owner as a single-tenant reference. It is not yet hardened for scale,
> and several readiness items below remain open. Do not present this
> project as enterprise-ready.

## Verified ready

- VPS live: 18 containers healthy (KumoMTA, GoPhish backend
  deps, monitoring, reacher, 11 Warmbly services), GoPhish + Caddy +
  job_api on systemd, dashboard on pm2.
- Public HTTPS on 6 hosts with auto-issued certificates; loopback-only
  admin surfaces (KumoMTA API, GoPhish admin, Grafana); UFW 22/80/443.
- SPF/DKIM/DMARC published for 3 domains; `precheck` green.
- SMTP AUTH over STARTTLS verified; GoPhish 3/3 profiles relay via
  KumoMTA; relay permission proven with zero-send probes.
- Lead verification lifecycle verified with real verdicts; dashboard
  reads live backends (sanitized responses).
- Auth, tenancy scoping, suppression, breaker, SSRF, and secret hygiene
  enforced with regression tests (103 deliverability + 22 core tests).
- Deploy script completed live runs and is idempotent; DNS values
  documented (`docs/deployment/DNS_RECORDS.md`).

## Open before bulk/production sending at scale

- [ ] Credentials rotated post-deploy (VPS, KumoMTA, GoPhish, Grafana —
      Grafana secret is generated; Appwrite key rotation is urgent, see
      debt #1).
- [ ] Receiving mailboxes exist (currently none; replies go nowhere).
- [ ] PTR record set to `mail.nasrullahtanim.me` (Contabo panel).
- [ ] Backup/restore rehearsed (`kumomta-lab/scripts/backup.sh/restore.sh`).
- [ ] Alert notifier wired; test alert fired and received.
- [ ] Warmup completed per engine schedule before bulk volume
      (Warmbly connected + warming, or legacy engine run).
- [ ] Abuse contact + complaint handling process defined.
- [ ] Human-approval queue for new outreach (currently unenforced).
- [ ] SNS signature verification (currently TopicArn allowlist only).
- [ ] Access gate on the open dashboard (Caddy basic-auth or restored
      login) before any public announcement.

## Non-goals for readiness claims

No uptime commitment, no compliance certification, no guaranteed inbox
placement — the engine reports delivery signals honestly and must never
claim otherwise.
