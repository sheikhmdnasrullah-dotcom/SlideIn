# Contributing to SlideIn

Thanks for your interest in contributing. This project is in **alpha**:
small, focused contributions that improve correctness, tests, or docs are the
most helpful right now.

## Getting started

```bash
git clone <repo-url>
cd SlideIn
./dev          # starts the local stack (Docker required)
./doctor       # health check — exit 0 = operational
```

Full details: `docs/development/LOCAL_SETUP.md`.

## Before you open a pull request

Every PR must keep these green (CI runs the same commands):

```bash
# Go
gofmt -l .            # must print nothing (excluding vendored/nested dirs)
go vet ./...
go build ./...
go test ./...

# Python — deliverability + lab
./.venv/bin/python -m pytest deliverability/tests/ -q
./.venv/bin/python -m pytest kumomta-lab/tests -q

# Secret hygiene — never commit credentials
bash scripts/check-secrets.sh
```

See `docs/development/TESTING.md` for the full matrix (including the
product-API suite, which needs PostgreSQL).

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
6. **Keep it simple.** This is a modular monolith on purpose. New services or
   dependencies need a documented reason in the PR description.

## Code map

- `deliverability/core/` — gate, risk, breaker, providers, suppression.
- `deliverability/server.py`, `campaign_worker.py`, `webhook_server.py`,
  `cli.py` — API, bulk sender, event ingest, ops.
- `kumomta-lab/policy/` — KumoMTA Lua policy; `compose/` — stacks.
- `controllers/`, `models/`, `mailer/`, `worker/` — Go backend.
- `warmup-engine/`, `product/`, `project/` — warmup, product API, dashboard.
- `docs/` — see `docs/decisions/ADR-0002-documentation-layout.md`.

## Reporting bugs

Use the bug report issue template. Include exact commands, versions
(`go version`, `python3 --version`, `docker --version`), and logs with
credentials redacted.

## Security issues

Do not open a public issue. Follow `SECURITY.md`.

## License

By contributing, you agree that your contributions are licensed under the
MIT License (see `LICENSE`), the same license as the rest of the project.
