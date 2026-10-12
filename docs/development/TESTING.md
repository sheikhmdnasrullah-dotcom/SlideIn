# Testing

Every suite below must be green before considering a change complete. CI
(`.github/workflows/ci.yml`) runs the same commands on every push.

---

## Test Matrix

| Suite | Command | Expected |
|---|---|---|
| Go build & vet | `go build ./... && go vet ./...` | clean |
| Go tests | `go test ./...` | 13 packages `ok` |
| Deliverability | `./.venv/bin/python -m unittest discover -s deliverability/tests -p "test_*.py"` | 103 tests `OK` (incl. 22 auth/key/submit + 9 webhook + 5 worker-eligibility + 6 review-server-auth + 4 unspam) |
| KumoMTA lab | `./.venv/bin/python -m pytest kumomta-lab/tests -q` | 2 passed, 1 skipped (integration auto-skip) |
| Product API | `./.venv/bin/python -m pytest product/tests -q --ignore=product/tests/test_workflows.py` | 26 passed |
| Secret hygiene | `bash scripts/check-secrets.sh` | no tracked secrets |

One-time setup for the Python suites:

```bash
python3 -m venv .venv
./.venv/bin/pip install -r product/requirements.txt \
    "sqlalchemy[asyncio]>=2.0.43" "asyncpg>=0.30" pytest-asyncio pyyaml
```

(If the pinned wheels do not build on your Python, install the latest
versions of `sqlalchemy`/`asyncpg` as shown — the suites do not depend on
exact pins locally; CI pins on Python 3.12.)

---

## Suite Details

### Go (`go test ./...`)

Core Gophish-fork backend: ratelimit middleware, mailer dial backoff,
worker 503 guards, buffered error channels, `/healthz` + `/readyz`
endpoints. The root `go.mod` carries an `ignore ./project/node_modules`
directive so `./...` never descends into third-party JavaScript trees.

### Deliverability (`unittest discover`)

Stdlib-only: pre-send gate, blacklist/suppression fail-closed behaviour,
half-open circuit-breaker probes, DNS-check honesty, bounce/suppression
policy, placement risk, plus server auth/tenancy, webhook SSRF/secret,
worker eligibility, review-server auth, and unspam-client suites
(socket-free unless noted).

### KumoMTA lab (`pytest kumomta-lab/tests`)

Policy and routing cases that run without a live KumoMTA instance;
integration cases detect the absence of the lab daemon and skip.

### Product API (`pytest product/tests`)

Security contract tests: credential enforcement, tenant isolation
(cross-org reads answer 404), public-path carve-outs, documented error
envelopes, explicit dev-only auth bypass, spec path conformance.
**Requires PostgreSQL** on `localhost:5432` (override with
`DATABASE_URL`). `test_workflows.py` is excluded (in-flight suite).

### Local end-to-end (requires `./dev`)

```bash
python3 test_e2e_local_flow.py      # 8/8: gate → KumoMTA → Mailpit → trace
python3 test_slidein_platform.py   # 8/8: API, DKIM, inbound AI, stitching
```

Both terminate in the local Mailpit sink. Never run
`verify_placement.py` / `verify_template.py` without owner approval (they
send real email).

---

## CI Mapping (`.github/workflows/ci.yml`)

| Job | Contents |
|---|---|
| `go` | gofmt, `go vet`, `go build ./...`, `go test ./...` |
| `python` | deliverability unittest + KumoMTA lab tests |
| `product-api` | product tests against a `postgres:16` service container |
| `security` | `scripts/check-secrets.sh` (no tracked secrets/keys) |

---

## Last verified (2026-10-12, local runs)

| Suite | Result |
|---|---|
| Go build, vet, tests, gofmt | clean; 13 packages `ok` |
| Deliverability | 103 tests `OK` (socket-free) |
| KumoMTA lab | 2 passed, 1 skipped |
| Secret hygiene | `OK`, exit 0 |
| Product API | not run locally (no PostgreSQL); CI-owned |
| Local stack (`./dev` + `./doctor`) | FULLY OPERATIONAL |
| E2E mail flow | 8/8 green |
| Platform suite | 8/8 green incl. live API auth, DKIM verify, inbound intent |
