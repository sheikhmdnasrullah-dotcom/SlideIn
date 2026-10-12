# Technical Debt — SlideIn

> Ordered roughly by risk. Each item: what, where, why it matters, and the
> cheapest credible fix. Fixed items link to their tests.

## Open

1. **Duplicated frontend trees** — `project/` vs `workspace-app/` are
   byte-identical nested repos with no canonical copy. Risk: divergent edits,
   confused contributors. Fix: diff, pick one, archive the other (roadmap
   Stage 4).
2. **Prompt-injection surface** — LLM prompts concatenate untrusted input
   (`product/agents/real_agents.py`, `llm/llm.go`) with no sanitizer. Risk:
   indirect prompt injection via fetched/research content. Fix: sanitize +
   delimit untrusted spans before prompt assembly.
3. **SNS signature verification missing** — SES webhook relies on TopicArn
   allowlist only. Risk: forged delivery events if ARNs leak. Fix: add a
   crypto dependency and verify SNS signatures (roadmap Stage 5).
4. **Three API surfaces** — Go `/api/*`, Python `/v1/*`, FastAPI product
   routes overlap conceptually. Risk: contributor confusion. Fix: nominate
   one customer-facing surface (roadmap Stage 4); done deliberately, not now.
5. **Split SQLite stores** — `gophish.db`, `deliverability_state.db`,
   `campaign_outreach.db`, `warmup.db` with no transactions across them.
   Risk: inconsistent state on partial failure. Fix: define sync boundaries
   or unify (roadmap Stage 4).
6. **Gophish REST transport stub** — `pipeline.py` raises `NotImplementedError`.
   Risk: dead option in provider config. Fix: wire it or remove the option.
7. **Redis governor wiring untraced** — compose references only; enforcement
   code path not confirmed. Fix: trace or remove.
8. **Product layer gaps** — no local Postgres run, no alembic dir,
   `test_workflows.py` in-flight, roles unenforced. Fix: per roadmap.
9. **Stale infrastructure defaults** — dead VPS IP `169.58.207.75` baked into
   deploy defaults, compose hostnames, scripts, and dashboard HTML; old
   Grafana/ssh notes in docs. Risk: confusion + information exposure on
   publication. Fix: parameterize outputs; scrub publishable surfaces (S8).
10. **No Python linters** — CI gates Go only (`gofmt`/`vet`); Python has no
    ruff/flake8/mypy config. Fix: add ruff + CI job.
11. **`refs/agents/*` checkpoint data** — local-only ref holds PII CSVs +
    session logs; travels only on full/refspec push (no remotes: latent).
    Fix: decide strip-vs-keep before adding any remote.
12. **Public-history hygiene** — `main` has 5 commits with unsuitable
    messages ("spam evasion"); publication needs a fresh history approved by
    the owner. See `PUBLICATION_CHECKLIST.md`.
13. **VERSION skew** — root `VERSION` (`0.12.1`) is inherited GoPhish
    versioning, not a SlideIn release. Fix: adopt SlideIn semver at 0.1.0.

## Fixed 2026-10-12 (with regression tests)

- S2 auth bypass → 401 + constant-time compare (11 tests).
- S3 cross-workspace conversation access → 404 scoping (4 tests).
- S1 SNS SubscribeURL SSRF → allowlist + https-only + no-redirect (9 tests).
- S5 hardcoded seed key → random per-DB keys + `rotate-key` CLI (4 tests).
- Worker + `/v1/leads/submit` suppression bypasses → gated (8 tests).
- S4 zero-auth review servers → key gate + loopback bind (6 tests).
- S6 missing `WEBHOOK_SECRET` + unvalidated unspam URL → 503 fail-closed,
  TopicArn allowlist, URL validation (10 tests).
- `deploy-production.sh` path bugs → fixed + statically verified.
- Go webhook-SSRF claim investigated and **refuted** (`RestrictedDialer`
  wired at `gophish.go:96-101`).
