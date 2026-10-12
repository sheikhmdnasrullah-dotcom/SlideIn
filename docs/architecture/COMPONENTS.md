# Components — SlideIn

## Go campaign/admin app (`gophish.go`, `controllers/`, `models/`, …)

Modified GoPhish fork: campaigns, groups/targets, templates, sending
profiles, landing pages, RBAC (`admin`/`user`), per-user API keys, IMAP
listeners, outbound webhooks (HMAC-SHA256, dial-restricted transport), mail
queue with Backoff retries (2^n min, max 8 attempts). Single-operator
tenancy. SQLite `gophish.db` (21 tables; migrations to 0.11.x).

## Deliverability engine (`deliverability/`, Python stdlib-only)

- **Approved path** `core/pipeline.py`: approval gate → placement risk →
  circuit breaker → sender/auth checks → suppression → provider dispatch.
- **Providers** `core/provider.py`: `DevSinkProvider`, `KumoMTAProvider`
  (AUTH+STARTTLS, health check), `StandardSMTPProvider`
  (SendGrid/Resend/Mailgun/SES).
- **Safety**: `core/gate.py`, `circuit_breaker.py` (trips on
  bounce/complaint/seed/grade/blacklist; never auto-resumes blindly),
  `bounce_parser.py` (DSN/ARF → `should_suppress`), `state.py`
  (suppression, `delivery_events`, warmup, daily sends).
- **Services**: `server.py` REST+UI (:8088, workspace API keys),
  `campaign_worker.py` bulk sender (eligibility-gated), `webhook_server.py`
  (provider event ingest), `cli.py` ops (incl. `show-key`/`rotate-key`),
  review dashboards (key-gated, loopback-only).
- SQLite `deliverability_state.db` (17 tables) + `campaign_outreach.db`.

## KumoMTA (`kumomta-lab/policy/*.lua`, Compose)

Local policy: AUTH ESMTP :2587, forced Mailpit route, lab DKIM.
Production policy: AUTH, per-domain 2048-bit DKIM, per-provider shaping,
TLS ≥1.2. Compose stacks for local/lab/production + monitoring
(Prometheus/Grafana/Loki/Alertmanager). Verified locally end-to-end;
production run blocked (no VPS).

## Warmup engine (`warmup-engine/`, Node + BullMQ/Redis)

Peer warmup scheduler with IMAP/SMTP workers. Installed; never run in this
environment.

## Product layer (`product/`, FastAPI + SQLAlchemy) — early stage

"Acquisition OS" API: opportunities, agents, `org_id` tenancy with 404
anti-oracle, mock-first LLM agents with an LLM-backed variant. Needs
PostgreSQL; no alembic; roles unenforced.

## Dashboard (`project/` ≡ `workspace-app/`, Next.js) — early stage

Duplicated nested repos; Appwrite/Supabase reads + optional server-only
GoPhish REST. Boots; not wired to the Go app. Canonical copy unresolved.

## Test sink (`sink-mx/`) + lab harness (`kumomta-lab/tests/`)

Hermetic mail sink and 13-scenario policy lab for offline verification.

## Store schemas (SQLite; PostgreSQL reserved for SaaS tenancy)

`deliverability_state.db`: `gate_decisions`, `seed_results`,
`circuit_state`, `campaign_state`, `send_events` (ts, recipient, provider,
result, detail, bounce/dsn), `metrics`, `suppression` (recipient, reason,
ts, detail), `sender_rotation`, `warmup_state`, `daily_sends`, plus
`workspaces → domains → sender_profiles` and `leads → conversations →
messages`. `gophish.db`: `users` (accounts, keys, RBAC), `campaigns`,
`templates`, `groups`/`targets`, `results`, `smtp` profiles, `webhooks`,
IMAP, `mail_logs`. `campaign_outreach.db`: `outreach_sent` (UNIQUE email).
`warmup.db`: `seed_accounts`, `warmup_threads`, `warmup_logs`.
SaaS migration path: `tenant_id`/`workspace_id` keys + managed PostgreSQL
with row-level security.
