# Technical Debt — SlideIn

> Ordered roughly by risk. Each item: what, where, why it matters, and the
> cheapest credible fix. Fixed items link to their tests. Rewritten
> post-launch 2026-10-12; pre-launch history in git.

## Open

1. **Live Appwrite API key in workspace history** — a standard key sits in
   `workspace-app/.env.example` (separate nested repo, already pushed).
   Risk: anyone with it can read/write the workspace database. Fix: rotate
   in Appwrite console, update VPS `.env.local`, rebuild. Do this before
   any launch announcement.
2. **No receiving mailboxes** — mailcow died with the old VPS; our domains
   have no IMAP, MX points at a dead host, replies bounce into nothing.
   Risk: warmup/reply-tracking impossible; lost replies; bounce noise.
   Fix: revive IMAP (mailcow/dovecot project) or move mail hosting to a
   provider with OAuth; then connect Warmbly mailboxes.
3. **Open dashboard + open registration** — `DISABLE_AUTH=true` on the live
   box: no login required, anyone can read/write data, launch campaigns,
   and create accounts. Script execution is locked (403) and SMTP creds are
   stripped from API responses, but campaign-send abuse would burn domain
   reputation. Fix: Caddy `basic_auth` gate (2-minute job, offered) or
   restore login; add registration throttling either way.
4. **PTR record still default** — VPS reverse DNS is the provider default,
   not `mail.nasrullahtanim.me`. Risk: deliverability penalty at strict
   receivers. Fix: set in Contabo panel (5 minutes, manual).
5. **`agents.`/`pdf.` subdomains point at the dead VPS** — stale A records
   found during the Cloudflare audit. Risk: confusion, broken links. Fix:
   move or delete (owner decision).
6. **Warmbly mailbox not connected** — stack is healthy and the SMTP relay
   is proven, but mailbox onboarding is UI-only and unactioned. Risk:
   campaigns/warmup idle. Fix: after DNS (done), connect via UI with
   `kumomta:2587` + `outbound` creds; IMAP side blocked on item 2.
7. **Monitoring alerts unwired** — Prometheus/Alertmanager run with valid
   configs but no notifier on the default receiver. Risk: silent failures.
   Fix: add webhook/email receiver + test-fire one alert.
8. **Backups never rehearsed** — `backup.sh/restore.sh` exist; no restore
   has ever been attempted. Risk: untested recovery. Fix: rehearse on a
   scratch dir, document the run.
9. **Universal core is in-memory only** — `product/core/` registries are
   process-local. Risk: no good for multi-worker production traffic. Fix:
   SQLAlchemy persistence + RLS per `CORE_VS_TENANT_BOUNDARIES.md` §5
   (Stage 2, schema already specified).
10. **Prompt-injection surface** — LLM prompts concatenate untrusted input
    (`product/agents/real_agents.py`, `llm/llm.go`) with no sanitizer. Risk:
    indirect prompt injection via fetched/research content. Fix: sanitize +
    delimit untrusted spans before prompt assembly.
11. **SNS signature verification missing** — SES webhook relies on TopicArn
    allowlist only. Risk: forged delivery events if ARNs leak. Fix: add a
    crypto dependency and verify SNS signatures.
12. **Three API surfaces** — Go `/api/*`, Python `/v1/*`, FastAPI product
    routes overlap conceptually. Risk: contributor confusion. Fix: nominate
    one customer-facing surface deliberately, not now.
13. **Split SQLite stores** — `gophish.db`, `deliverability_state.db`,
    `campaign_outreach.db`, job data with no transactions across them. Risk:
    inconsistent state on partial failure. Fix: define sync boundaries.
14. **Gophish REST transport stub** — `pipeline.py` raises
    `NotImplementedError`. Risk: dead option in provider config. Fix: wire
    it or remove the option.
15. **Product layer gaps** — no local Postgres run, no alembic dir,
    `test_workflows.py` in-flight, roles unenforced. Fix: per roadmap.
16. **No Python linters** — CI gates Go only (`gofmt`/`vet`); Python has no
    ruff/flake8/mypy config. Fix: add ruff + CI job.
17. **Stale deploy default** — `deploy-production.sh` still defaults
    `VPS=root@169.58.207.75` (old box) when `$1` is omitted. Risk: a
    bare rerun targets a dead host. Fix: default to the live IP or require
    the argument.
18. **`refs/agents/*` checkpoint data** — local-only ref holds PII CSVs +
    session logs. A remote now exists; a full/refspec push would leak it.
    Fix: keep pushes to `main` only; decide strip-vs-keep.
19. **VERSION skew** — root `VERSION` (`0.12.1`) is inherited GoPhish
    versioning, not a SlideIn release. Fix: adopt SlideIn semver file.

## Fixed 2026-10-12 (with regression tests or live verification)

- S2 auth bypass → 401 + constant-time compare (11 tests).
- S3 cross-workspace conversation access → 404 scoping (4 tests).
- S1 SNS SubscribeURL SSRF → allowlist + https-only + no-redirect (9 tests).
- S5 hardcoded seed key → random per-DB keys + `rotate-key` CLI (4 tests).
- Worker + `/v1/leads/submit` suppression bypasses → gated (8 tests).
- S4 zero-auth review servers → key gate + loopback bind (6 tests).
- S6 missing `WEBHOOK_SECRET` + unvalidated unspam URL → 503 fail-closed,
  TopicArn allowlist, URL validation (10 tests).
- Go webhook-SSRF claim investigated and **refuted** (`RestrictedDialer`
  wired at `gophish.go:96-101`).
- Production deploy: 10 faults fixed across live VPS runs (ssh hang,
  Prometheus flag, KumoMTA spool/node-id/policy, port mismatch, API-key
  sync, profile payloads, nested copy) — all verified live, none mocked.
- Monitoring configs rewritten as valid YAML; all 6 containers healthy.
- KumoMTA policy: `require_auth` removed (rejected by kumod 2026.09),
  relay scoped to loopback + private docker nets, secrets file-mounted.
- Dashboard canonical choice resolved: `workspace-app` deployed live;
  `project/` remains local-only (excluded from this repo).
- Fresh public history published; branch protection with 4 required CI
  checks; `v0.1.0` released.
- gophish/options credential leak → server-side sanitization (verified:
  SMTP password no longer leaves the backend).
- Anonymous shell execution locked in open-dashboard mode (403).
