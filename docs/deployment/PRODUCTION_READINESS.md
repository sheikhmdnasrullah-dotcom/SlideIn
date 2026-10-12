# Production Readiness — SlideIn

> Honest status: the software runs locally end-to-end, but **no production
> deployment exists today** and several readiness items are open. Do not
> present this project as production-ready.

## Verified ready

- Local stack boots and passes e2e + platform suites (2026-10-12).
- Auth, tenancy scoping, suppression, breaker, SSRF, and secret hygiene
  enforced with regression tests (103 deliverability tests).
- Deploy scripts statically verified; DNS/precheck tooling present.

## Open before first production send

- [ ] Fresh VPS provisioned; deploy script completes a live run.
- [ ] DNS (SPF/DKIM/DMARC) published and `precheck.py` green.
- [ ] Credentials rotated post-deploy (VPS, KumoMTA, GoPhish, Grafana).
- [ ] Admin surfaces restricted (no public :8029/:8333/Grafana without TLS +
      access control).
- [ ] Backup/restore rehearsed (`kumomta-lab/scripts/backup.sh/restore.sh`).
- [ ] Monitoring stack receiving metrics; alert routes tested.
- [ ] Warmup completed per engine schedule before bulk volume.
- [ ] Abuse contact + complaint handling process defined.
- [ ] Human-approval queue for new outreach (currently unenforced).
- [ ] SNS signature verification (currently TopicArn allowlist only).

## Non-goals for readiness claims

No uptime commitment, no compliance certification, no guaranteed inbox
placement — the engine reports delivery signals honestly and must never
claim otherwise.
