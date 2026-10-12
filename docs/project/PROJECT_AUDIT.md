# Project Audit — SlideIn

> Audit window: 2026-10-12 (initial file-inspection audit) through Stage 2
> safety fixes and Stage 3 live verification. Evidence is cited per finding:
> "inspected" (code read), "executed" (command run this session), or "prior
> audit reported" (same-day local run, attributed). Secrets are referenced by
> location only, never by value.

Status vocabulary: **Implemented and verified** · **Implemented but
unverified** · **Partially implemented** · **Planned but not implemented** ·
**Blocked**.

---

## 1. Repository inventory (executed)

| Item | Value |
|---|---|
| Working directory | `/Users/nasrullahtanim/Downloads/01-Projects/email-master raw` |
| Branch | `main`; remotes: none |
| Commits on `main` | 5 (all 2026-09-10; messages unsuitable for public history) |
| Tracked files | 2 (`If your directory has`, `config/kumomta_policy.lua`) |
| On-disk size | ~17 GB (dominated by `node_modules/`, venvs, `kumomta-src/`) |
| Product name in code | **SlideIn** (`server.py`, `SLIDEIN_*` env, docs, UI strings) |

Top-level areas: Go campaign/admin app (`gophish.go`, `controllers/`,
`models/`, `mailer/`, `worker/`, `webhook/`, `auth/`, `middleware/`, `imap/`,
`dialer/`, `llm/`), Python deliverability engine (`deliverability/`),
KumoMTA lab (`kumomta-lab/`), warmup engine (`warmup-engine/`, Node),
optimization engine (`optimization-engine/`), product API (`product/`,
FastAPI), two Next.js trees (`project/`, `workspace-app/`, nested repos),
`kumomta-src/` (vendored, nested), `sink-mx/`, containers, private data
(`Leads to Mail/`, `conversations/`, `bash_events/`, `*.csv`, `*.db`,
`*.log`). `VERSION` = `0.12.1` (inherited GoPhish versioning, not a SlideIn
release).

## 2. Languages, frameworks, runtimes (inspected)

| Layer | Stack | Evidence |
|---|---|---|
| Campaign/admin backend | Go (~90 files), gorilla/mux, gorm | `go.mod`, `gophish.go` |
| Deliverability engine | Python, stdlib-only (zero deps, verified) | `deliverability/requirements.txt` |
| MTA policy | Lua (KumoMTA) | `kumomta-lab/policy/*.lua` |
| Warmup/optimization | Node.js, BullMQ, ioredis | `warmup-engine/package.json` |
| Product API | FastAPI, SQLAlchemy, pytest | `product/requirements.txt` |
| Dashboards | Next.js 16, React 19, TS, Tailwind, Playwright | `project/package.json` ≡ `workspace-app/package.json` (byte-identical) |
| Ops | Bash deploy/test scripts | `kumomta-lab/scripts/`, `deliverability/*.sh` |

## 3. Entry points (inspected; local paths executed 2026-10-12)

| Component | Entrypoint | Status |
|---|---|---|
| Campaign/admin app | `gophish.go` → `controllers/route.go` (:3333) | Implemented and verified (boots; `./doctor` HEALTHY) |
| Deliverability API | `deliverability/server.py` (:8088) | Implemented and verified (live suite 8/8) |
| Ops CLI | `deliverability/cli.py` (+ `show-key`, `rotate-key`) | Implemented and verified (rotation executed) |
| Bulk sender | `deliverability/campaign_worker.py` | Implemented but unverified live (gated + unit-tested; never run — sends real mail) |
| Product API | `product/api/main.py` (:8000) | Partially implemented, Blocked locally (needs PostgreSQL :5432) |
| Warmup engine | `warmup-engine/src/index.js` | Implemented but unverified (installed, never run here) |
| Local stack | `./dev` + `docker-compose.local.yml` | Implemented and verified (FULLY OPERATIONAL 2026-10-12) |
| Dashboard | Next.js `app/layout.tsx` (:3000) | Partially implemented (duplicated tree; boots) |

## 4. Databases, migrations, queues (inspected)

- `gophish.db` (SQLite, 21 tables): migrations to 0.11.x in `db/db_sqlite3|mysql/migrations/`. Verified present + healthy.
- `deliverability/deliverability_state.db` (SQLite, 17 tables): suppression, delivery events/stats, workspaces, circuit state. Schema via `core/repository.py` + `state.py`; no migration tool (CREATE TABLE IF NOT EXISTS).
- `campaign_outreach.db`: `outreach_sent.email` UNIQUE.
- `warmup-engine/warmup.db`: warmup state.
- Product layer: PostgreSQL models only, no alembic dir, no local instance.
- Queues/retries: Go worker 1-min poll + `models/maillog.go` Backoff 2^n min (max 8 attempts); BullMQ/Redis for warmup. Single-host only — no distributed mail queue / exactly-once broker. Partially implemented.

## 5. Dashboard (inspected) — Partially implemented

Two Next.js trees (`project/`, `workspace-app/`): byte-identical
`package.json`, identical e2e specs, each with its own `.git`, both gitignored
here. Connects via Appwrite/Supabase SDKs + optional server-only GoPhish REST.
Not wired to the Go app's own UI. Canonical copy unresolved (see
`TECHNICAL_DEBT.md`).

## 6. Email flows (inspected + executed)

Approved path (`core/pipeline.py`): gate → placement risk → circuit breaker
→ sender/auth checks → suppression → provider dispatch (`kumo` / `dev-sink` /
`mailpit` / standard SMTP relays). **All live-path bypasses found in the
initial audit were fixed and tested 2026-10-12:**

- `campaign_worker.py` now gates every lead (`process_lead()`: duplicate +
  breaker + suppression; 5 tests). Fix verified by tests, never run live.
- `/v1/leads/submit` enforces suppression (403) + breaker (503; 3 tests).
  Verified live in the platform suite (eligible submit → 201 → Mailpit).
- Gophish REST transport remains an explicit `NotImplementedError` stub
  (`pipeline.py`); SMTP-profile path is the working integration.
- IMAP ingests campaign-report events only; no DSN/ARF mailbox ingestion.

## 7. KumoMTA / GoPhish / SMTP (executed 2026-10-12)

Local path **Implemented and verified**: `./dev` boots KumoMTA + Mailpit +
Redis; e2e test dispatched via ESMTP AUTH :2587, KumoMTA DKIM-signed (2048-bit
RSA, verified from Mailpit payload), routed to Mailpit :1025, traced in
SQLite. Production policy (`production_init.lua`: AUTH, per-domain DKIM,
per-provider shaping, TLS ≥1.2) and `deploy-production.sh` exist;
deploy-script path bugs were fixed and statically verified (`bash -n` + all
19 source paths), but no live VPS run was possible (previous VPS destroyed).
Production sending is **Blocked** on fresh infrastructure.

## 8. AI, approval, suppression (inspected)

Partially implemented. Dual LLM path exists (`product/agents/llm.py`:
OpenAI/Anthropic; `llm/llm.go`: OpenRouter) but the wired default is
mock/template agents; `real_agents.py` is the LLM-backed variant. Research
dossiers use mock signals (no real web fetch). `Message.ai_approved` exists
but is unset-at-send; no human-approval queue. Prompt construction
concatenates untrusted input with no sanitizer (see `TECHNICAL_DEBT.md`).
Suppression core (`state.py`, `bounce_parser.py`) is enforced on all live
paths as of 2026-10-12.

## 9. Auth, API keys, tenancy (inspected + executed)

- Go app: bcrypt + RBAC middleware + per-user API keys. Implemented but
  unverified (no auth-focused Go tests run).
- Product API: Bearer [REDACTED] org-scoped keys, per-query `org_id`, 404
  anti-oracle. Implemented but unverified locally (CI-owned, needs Postgres).
- Deliverability HTTP: **fixed 2026-10-12** — 401 on missing/invalid keys
  (constant-time compare), workspace-scoped conversation access (404),
  random per-DB seed keys + `rotate-key` CLI (local DB rotated + verified),
  key redaction on `/v1/workspaces`. 28 tests, all green; live-verified.
- Review servers (`dashboard_server.py`, `sent_emails_review_server.py`):
  key gate + loopback-only bind (6 tests). SNS webhook SSRF closed
  (allowlist + https-only + no-redirect; 9 webhook tests). `WEBHOOK_SECRET`
  enforced on HMAC routes (503 fail-closed); SNS TopicArn allowlist added.
  Full SNS signature verification still needs non-stdlib crypto (planned).

## 10. Tests and CI (executed)

| Suite | Result (this session) |
|---|---|
| Go (`go test ./...`) | 13 pkgs ok, 4 no-test-files; `go vet` + `gofmt` clean |
| Deliverability (`unittest discover`) | **103 tests OK** (57 inherited + 46 added, all socket-free) |
| KumoMTA lab (`pytest`) | 2 passed, 1 skipped (integration auto-skip) |
| Product API | Not run locally (no PostgreSQL); CI job owns it |
| Secret hygiene (`check-secrets.sh`) | OK, exit 0 |
| Local e2e (`test_e2e_local_flow.py`) | 8/8 green against live stack |
| Platform suite (`test_slidein_platform.py`) | 8/8 green against live stack |
| CI (`.github/workflows/ci.yml`) | go + python + product-api(postgres:16) + security jobs; never run on GitHub (no remote yet) |

## 11. Deployment (inspected + partially executed)

Local: `./dev` / `./doctor` / `./stop` + compose — verified working.
Production: single-VPS design (`deploy-production.sh` + compose + DNS scripts
+ GoPhish config) — scripts fixed and statically verified; end-to-end
unexercised and **Blocked** (no VPS; mailcow config unrecoverable).
`docs/deployment/PRODUCTION_READINESS.md` lists the remaining checklist.

## 12. Technical debt and security — summary

All initial High/Medium findings (S1–S6) are fixed and tested; S7 (prompt
injection), S8 (infrastructure details in publishable surfaces), and the
`refs/agents/*` checkpoint data question remain open. Full register:
`TECHNICAL_DEBT.md`. Publication gate: `docs/security/PUBLICATION_CHECKLIST.md`.

## 13. Missing for a first useful release

Canonical dashboard choice, product-API Postgres run, SNS signature
verification, human-approval queue, README quickstart publication (this
reorganization), tagged 0.1.0 release, and the publication preflight approval.
