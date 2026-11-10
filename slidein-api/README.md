# Slidein workflow API (slidein-api)

The backend for the Slidein client workspace. One domain model, one set of
shared services, explicit contracts between stages, and persistent records
for everything the UI shows.

## The workflow

```
configure ──▶ discover ──▶ research ──▶ qualify ──▶ personalize ──▶ outreach ──▶ converse
   │             │            │            │             │             │            │
 profile      prospects    evidence    qualification   drafts      sent mails   replies
 offers       provenance  provenance   offer match   (versioned)   + policy   + intent
 icps
                                                                                   │
                                                        overview ◀── activity ◀────┘
```

Every arrow is a declared contract in `slidein_api/contracts.py`: required
inputs, produced outputs, permitted status transitions, failure codes with
retry behaviour, and the recovery action to surface. Nothing advances
implicitly — `StageRunner` validates each call, records a `stage_runs` row
before and after, and writes one `activity_logs` entry.

## Run it

```bash
pip install -r requirements.txt
SLIDEIN_API_KEYS='{"ten_local": {"key": "dev-key", "role": "admin"}}' python run.py
# http://127.0.0.1:8100/docs
```

Local development shortcut:

```bash
SLIDEIN_AUTH_MODE=disabled python run.py     # single-workspace, admin role
```

### Environment

| Variable | Default | Meaning |
| --- | --- | --- |
| `SLIDEIN_DATABASE_URL` | `sqlite+aiosqlite:///data/slidein.db` | Any SQLAlchemy async URL. Use `postgresql+asyncpg://…` for deployment. |
| `SLIDEIN_API_KEYS` | – | JSON `{"<tenant_id>": {"key": …, "role": …}}`. |
| `SLIDEIN_AUTH_MODE` | `enforced` | `disabled` resolves every request to the first configured workspace as `admin`. |
| `SLIDEIN_HOST` / `SLIDEIN_PORT` | `127.0.0.1` / `8100` | Bind address. |

### Sending

The default transport is `dry_run`: a dispatch is recorded end-to-end
(message id, delivery events, timestamps) but no mail leaves the process.
Real sending is an explicit choice — set `transport: "smtp"` plus
`smtp_host` / `smtp_port` / `smtp_username` / `smtp_password` on the send
call. This matches the repository policy against accidental live traffic.
For KumoMTA, set `SLIDEIN_TRANSPORT=kumo` (uses `KUMO_HOST`/`KUMO_SMTP_PORT`/
`KUMO_AUTH_USER`/`KUMO_AUTH_PASS`, defaulting to the local submission port
2587) — the per-send `transport` payload still wins over the environment.

### Autopilot

An autonomous background loop, executed inline or through the durable
Celery/Redis job path. On each tick it advances every explicitly enabled
workspace through the same services and contracts Console uses —
ingest CSV leads, research, qualify, personalize, auto-approve (optional),
send (optional), count replies — and persists its state to the
`autopilot_state` table so Console shows the last tick, totals and
pipeline live. New workspaces default to disabled, review-required,
send-disabled, and dry-run transport.

| Variable | Default | Meaning |
| --- | --- | --- |
| `SLIDEIN_AUTOPILOT` | `0` | Master switch. `1` enables the loop deliberately. |
| `SLIDEIN_AUTOPILOT_INTERVAL` | `300` | Seconds between ticks. |
| `SLIDEIN_AUTOPILOT_BATCH` | `10` | Prospects advanced per stage per tick. |
| `SLIDEIN_AUTOPILOT_MAX_SENDS` | `5` | Dispatches per tick (still gated by policy). |
| `SLIDEIN_AUTOPILOT_INGEST` | – | Comma-separated CSV lead files polled each tick (idempotent). |
| `SLIDEIN_AUTOPILOT_CONNECTOR` | `orchestrated` | Research connector chain, tried in order. |

Per-workspace switches (autopilot on/off, auto-approve, sending) live in
the database and are toggled from the dashboard's Overview. Every send
still passes the full gate stack — approval policy, suppression, rate
limits, deliverability guard, compliance headers — and the transport
respects `SLIDEIN_TRANSPORT` (default `dry_run`). Successful free-form
setup enables research only after a profile, offer, and ICP exist; it does
not enable auto-approval or sending.

### Durable workers

Set `SLIDEIN_EXECUTION_MODE=celery` to disable the API's in-process loop and
use the `work_jobs` database ledger plus Celery/Redis dispatch. Jobs have
idempotency keys, per-tenant leases, bounded exponential retry, dead-letter
review, cancellation, and expired-lease recovery. Redis is not authoritative:
an undispatched or lost broker message is recovered from the database by the
scheduler. Duplicate delivery returns the existing job instead of repeating
its canonical tick.

```bash
celery -A slidein_api.workers.celery_app.celery_app worker \
  --queues=workflow,control --concurrency=2
celery -A slidein_api.workers.celery_app.celery_app beat
```

From `saas/`, `docker compose -f docker-compose.workers.yml up --build -d`
starts PostgreSQL, persistent Redis, the API, one worker, and exactly one
scheduler. Set `POSTGRES_PASSWORD` and `SLIDEIN_API_KEYS` first. This Phase C
slice pins `SLIDEIN_TRANSPORT=dry_run`; it does not activate live sending.
The frontend and production backup/upgrade procedure remain separate
deployment work. No live broker/VPS acceptance is implied by local tests.
A crash between an external provider accepting a message and the database
commit still requires provider-id reconciliation; that is a live-sending
acceptance gate, not something the dry-run replay test claims to solve.

Control plane: `GET/POST /v1/tenants/{id}/autopilot`,
`POST /v1/tenants/{id}/autopilot/run` (immediate tick or durable job),
`GET/DELETE /v1/tenants/{id}/autopilot/jobs/{job_id}`, and
`POST /v1/tenants/{id}/autopilot/jobs/{job_id}/retry`. Pausing a tenant
cancels its queued/retrying autopilot jobs; running canonical sends still
rely on their existing policy and idempotency gates.

## Test it

```bash
python -m pytest                 # contracts, journey, permissions, autopilot, osint
```

The suite runs against a throwaway SQLite file, so it needs no external
services. `tests/test_journey.py` walks a prospect through discovery,
research, qualification, draft preparation, authorized sending and inbound
reply handling; `tests/test_permissions.py` proves workspace isolation and
role enforcement; `tests/test_contracts.py` proves the contracts are
complete and self-consistent.

## Layout

```
slidein_api/
  contracts.py    stage inputs/outputs/transitions/failures/retries
  lifecycle.py    the state machines for prospects, drafts, sends, conversations
  runtime.py      StageRunner + StageOutcome (the only way stages advance)
  models.py       the canonical domain model
  security.py     API keys, workspace scoping, roles
  services/       shared business services (one per stage, plus activity/overview)
  api/            FastAPI routes — thin adapters over the services
```
