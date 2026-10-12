# Roadmap — SlideIn

> Ordered by dependency. `(A §n)` = `docs/project/PROJECT_AUDIT.md` section.
> Status labels: ✅ done (with date) · ⬜ planned. Dates are omitted until the
> release process runs. Nothing here is claimed as done without evidence —
> see `docs/project/CURRENT_STATE.md`.

## Stage 0 — Repository safety

- [x] Credential scrub; hardened `.gitignore`; secret scan in CI
- [ ] Decide fate of `refs/agents/*` checkpoint (PII CSVs + session logs,
      local-only) before any remote is added
- [ ] Fresh publication history (old history stays local only); owner
      preflight approval

## Stage 1 — Open-source release 0.1.0

- [x] Project identity (name: **SlideIn**), canonical docs layout
- [x] README with tested quick start; architecture + audit + testing docs
- [x] Community files: CONTRIBUTING, CODE_OF_CONDUCT, SECURITY, SUPPORT,
      issue/PR templates
- [ ] GitHub repo created (private → verified → public); CI green on GitHub

## Stage 2 — Safety bypasses (complete 2026-10-12)

- [x] `campaign_worker.py` gated (suppression + breaker; A §6)
- [x] `/v1/leads/submit` eligibility checks (403/503; A §6)
- [x] `server.py` auth: 401 + constant-time compare; seed keys randomized +
      `rotate-key` CLI; local DB rotated (A §9)
- [x] Conversations scoped by workspace; inbound thread-match scoped (A §9 S3)
- [x] Review servers: key gate + loopback bind (A §9 S4)
- [x] SNS `SubscribeURL` SSRF closed: allowlist + https-only + no-redirect
      (A §11 S1)
- [x] `WEBHOOK_SECRET` required (503 fail-closed); SNS TopicArn allowlist;
      unspam URL validated (A §11 S6)

## Stage 3 — Reproducible local story

- [x] Offline suites recorded: Go, 103 deliverability tests, lab, secrets
- [x] `./dev` + `./doctor` + e2e + platform suites green on local stack
- [x] `deploy-production.sh` path bugs fixed + statically verified
- [ ] One-command production rebuild on a fresh VPS, DNS re-point, DKIM
      rotation (blocked: no VPS)

## Stage 4 — Consolidate the platform

- [ ] Canonical dashboard tree (`project/` vs `workspace-app/`)
- [ ] Single customer-facing API surface (recommend: `server.py` core +
      GoPhish operator console)
- [ ] Real workspace key issuance; unify SQLite stores or define sync
      boundaries; wire dashboard to chosen API
- [ ] Resolve Gophish REST stub; trace/remove Redis governor wiring

## Stage 5 — Multi-tenant hardening

- [ ] Server-side tenant authorization + isolation tests (CI + Postgres)
- [ ] Scoped keys, safe hashing, log redaction, rate limits/quotas
- [ ] Pre-send suppression/unsubscribe checks (done for live paths; extend
      to new senders by default)
- [ ] Human-approval workflow for new outreach (`Message.ai_approved`)
- [ ] Transactional vs marketing/outreach path separation
- [ ] Prompt-injection defenses; SNS signature verification (needs crypto dep)

## Stage 6 — Managed SaaS (intent only)

Hosted workspaces, onboarding/roles/entitlements, real billing, monitoring,
backups, support — with production secrets/customer data fully outside the
public repo. See `docs/deployment/MANAGED_SERVICE_PLAN.md`.

## Stage 7 — AI research & personalization

Evidence-tracked prospect research (URL + timestamp per claim), draft
generation with human review, no invented facts.

## Stage 8 — Portfolio & releases (parallel)

- [ ] GitHub profile README (`docs/portfolio/PROFILE_README.md` — draft)
- [ ] Technical case study (`docs/portfolio/TECHNICAL_CASE_STUDY.md`)
- [ ] Changelog discipline + tagged releases with checklists

## Explicit non-goals (for now)

Microservices decomposition; ESP feature parity; compliance/uptime/adoption
claims without evidence.
