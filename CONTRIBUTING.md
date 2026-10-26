# Contributing to SlideIn

Thanks for your interest in contributing. This project is in **beta**:
small, focused contributions that improve correctness, tests, or docs are
the most helpful right now.

## Getting started

```bash
git clone https://github.com/sheikhmdnasrullah-dotcom/SlideIn.git
cd SlideIn
./dev          # starts the local stack (Docker required)
./doctor       # health check — exit 0 = operational
```

Full details: `docs/development/LOCAL_SETUP.md`.

## Before you open a pull request

Every PR must keep these green (CI runs the same commands):

```bash
# Go (campaign/admin app + core libraries)
gofmt -l .            # must print nothing (excluding vendored/nested dirs)
go vet ./...
go build ./...
go test ./...

# Python — deliverability engine + KumoMTA lab
.venv/bin/python -m pytest deliverability/tests/ -q
.venv/bin/python -m pytest kumomta-lab/tests -q

# Python — universal core boundary tests (DB-free, fast)
.venv/bin/python -m pytest product/tests/test_core_boundaries.py -q

# Secret hygiene — never commit credentials
bash scripts/check-secrets.sh
```

See `docs/development/TESTING.md` for the full matrix (including the
agent-workflow suite under `slidein-api/`, which needs the local stack
running).

## Contribution guidelines

1. **One concern per PR.** Bug fix, feature, or docs — not all three.
2. **Add or update tests** for behavior changes. Bug fixes should include a
   regression test where practical.
3. **Never commit secrets.** Credentials belong in gitignored config/`.env`
   files (see `PROJECT_POLICY.md` §2.1). `.env.example` documents the shape.
4. **No claims without evidence.** Don't add benchmark numbers, badges, or
   feature statuses you haven't verified. `docs/project/CURRENT_STATE.md`
   defines the status vocabulary (Verified / Implemented-unverified /
   Partial / Not implemented / Blocked).
5. **No email evasion content.** Contributions must not add header forgery,
   spam-filter bypass, or inbox-placement guarantees. This project is about
   legitimate deliverability engineering: authentication (SPF/DKIM/DMARC),
   warmup, suppression hygiene, and honest telemetry. Cold outreach tooling
   here assumes consent-based, compliant sending.
6. **Stay in the flow.** Every feature maps onto the canonical
   seven-stage workflow: `configure → discover → research → qualify →
   personalize → outreach → converse`. Do not add, reorder, or skip stages
   — see `docs/architecture/CONTRACTS.md`.
7. **Keep it simple.** This is a modular monolith on purpose. New services or
   dependencies need a documented reason in the PR description.
8. **One app, one shell.** The Console and Dashboard are two modes of one
   workspace, toggled by a single `ModeSwitcher`. Do not create a second
   dashboard, route tree, or shell — report gaps instead. See
   `AGENTS.md` §3.

## Code map

- `slidein-api/` — agent workflow API (FastAPI, stage contracts, stage runs,
  activity audit, preflight/copy-audit capability).
- `slidein-app/` — client workspace UI (Next.js 16, App Router, two-mode shell).
- `workspace-app/` — reference dashboard UI.
- `controllers/`, `models/`, `worker/`, `gophish.go` — Go campaign/admin app.
- `deliverability/` — gate, risk, circuit breaker, suppression, CLI, server.
  `core/` holds the reusable deliverability primitives.
- `kumomta-lab/` — KumoMTA Lua policy; `compose/` — local + production stacks.
- `product/` — universal multi-tenant core (FastAPI).
- `warmup-engine/`, `warmbly/`, `reacher/` — warmup and verification.
- `docs/` — architecture, security, development, deployment, decisions.

## Reporting bugs

Use the bug report issue template. Include exact commands, versions
(`go version`, `python3 --version`, `docker --version`), and logs with
credentials redacted.

## Security issues

Do not open a public issue. Follow `SECURITY.md`.

## License

By contributing, you agree that your contributions are licensed under the
same license as the rest of the project (Business Source License 1.1 — see
`LICENSE`). The Go backend derives from Gophish (MIT); see `NOTICE` for
third-party component licenses.
