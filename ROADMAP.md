# Roadmap — SlideIn

> Ordered by dependency. `(A §n)` = `docs/project/PROJECT_AUDIT.md` section
> (pre-launch point-in-time). Status labels: ✅ done (with date) · ⬜ planned.
> Nothing here is claimed as done without evidence — see
> `docs/project/CURRENT_STATE.md`. Rewritten post-launch 2026-10-12.

## Stage 0 — Repository safety ✅ 2026-10-12

- [x] Credential scrub; hardened `.gitignore`; secret scan in CI
- [x] Fresh publication history (old history stays local only); owner
      preflight approval; repo public; branch protection + 4 required checks
- [ ] Decide fate of `refs/agents/*` checkpoint (PII CSVs + session logs):
      keep pushes to `main` only until strip-vs-keep is decided

## Stage 1 — Open-source release 0.1.0 ✅ 2026-10-12

- [x] Project identity (name: **SlideIn**), canonical docs layout
- [x] README with tested quick start; architecture + audit + testing docs
- [x] Community files: CONTRIBUTING, CODE_OF_CONDUCT, SECURITY, SUPPORT,
      issue/PR templates
- [x] GitHub repo created (private → verified → public); CI green; `v0.1.0`
      tagged; profile repo live

## Stage 2 — Safety bypasses ✅ 2026-10-12

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

## Stage 3 — Production VPS ✅ 2026-10-12

- [x] One-command rebuild on a fresh VPS (port 25 open); deploy script
      completed live runs; 10 faults fixed and verified live
- [x] DNS via Cloudflare API (SPF/DKIM/DMARC ×3, mail + 7 site records);
      `precheck` green; Caddy TLS auto-issued for 6 hosts
- [x] Dashboard (`workspace-app`) deployed, wired to local backends,
      open-dashboard mode with RCE lock + credential sanitization
- [x] Lead verification backend (reacher + job_api) live; bulk lifecycle
      verified with real verdicts
- [x] Warmbly warmup platform healthy (11/11); SMTP relay via KumoMTA proven
      (zero-send RCPT probes); owner account bootstrapped
- [x] Agent-Reach research tooling installed; company page-read wired into
      lead research and executed live

## Stage 4 — Universal multi-tenant core (Stage 1 ✅ 2026-10-12)

- [x] `product/core/`: tenant contexts, scoped memory, versioned shared
      defaults, learning registry, eval suites, neutral workflow runner
- [x] 22 boundary-enforcing tests, DB-free
      (`product/tests/test_core_boundaries.py`)
- [x] Boundary docs: core-vs-tenant, memory policy, learning pipeline,
      config versioning, cross-business evaluation
- [ ] Stage 2: SQLAlchemy persistence + RLS (schema specified), operational
      telemetry, outcome tracking
- [ ] Single customer-facing API surface (recommend: `server.py` core +
      GoPhish operator console)
- [ ] Resolve Gophish REST stub; trace/remove Redis governor wiring

## Stage 5 — Hardening before scale

- [ ] Rotate the live Appwrite API key (leaked in workspace history)
- [ ] Receiving mailboxes (IMAP) or provider-hosted mail + Warmbly connect
- [ ] PTR record; `agents.`/`pdf.` stale hosts; alert notifier + backup drill
- [ ] Caddy access gate or restored login before any launch announcement
- [ ] Scoped keys, safe hashing, log redaction, rate limits/quotas
- [ ] Human-approval workflow for new outreach (`Message.ai_approved`)
- [ ] Transactional vs marketing/outreach path separation
- [ ] Prompt-injection defenses; SNS signature verification (needs crypto dep)

## Stage 6 — Managed SaaS (intent only)

Hosted workspaces, onboarding/roles/entitlements, real billing, monitoring,
backups, support — with production secrets/customer data fully outside the
public repo. See `docs/deployment/MANAGED_SERVICE_PLAN.md`. The universal
core Stage 1 is the foundation; multi-customer operation is not built.

## Stage 7 — AI research & personalization (partially live)

- [x] Tavily + Agent-Reach evidence in lead research (URL-attributed)
- [ ] Draft generation with human review; no invented facts (eval harness
      per `docs/engineering/CROSS_BUSINESS_EVALUATION.md`)

## Stage 8 — Portfolio & releases (parallel)

- [x] GitHub profile README (live in profile repo)
- [x] Technical case study (`docs/portfolio/TECHNICAL_CASE_STUDY.md`)
- [ ] Changelog discipline + tagged releases with checklists (0.2.0 next)

## Explicit non-goals (for now)

Microservices decomposition; ESP feature parity; compliance/uptime/adoption
claims without evidence; autonomous model training (universal-core Stage 5).
