# visitor_core — Website Visitor Identity Capture & CRM Ingestion

Client sites embed one script; every hit is resolved through a tiered
identity chain and streamed to the dashboard CRM over an exact wire schema.
Zero-latency local lookups first, commercial fallback last, graceful
ANONYMOUS terminal state — the engine can never deadlock.

## Flow

```
browser (tracker/snippet.js)
  │  Snowplow-style fingerprint (canvas/browser/hardware) + first-party __sl_vid
  │  POST /api/v1/capture/track          (RudderStack-shaped, 202 ack, async)
  ▼
Celery worker (queue "visitor", acks_late)
  VisitorPipeline.resolve():
    COOKIE_STITCH    ?he= / __sl_vid present → stitch session, done
    LOCAL_GEOIP      embedded MaxMind MMDB (geoip2.database.Reader) isolates
                     the corporate network in-process — zero external calls
    RETENTION_API    unstitched + residential/anonymous network → proxy-routed
                     curl_cffi (JA3 chrome124 + rotating SOCKS5) call to the
                     Retention.com wrapper → email/name/LinkedIn
    ANONYMOUS        terminal graceful state; traceback in error_logs; the
                     record still lands in the DB ledger
  every step → Redis Pub/Sub (visitor:crm:live, visitor:crm:site:{domain})
  every step → internal event ledger (LogSnag design: Visitor Intercepted,
               Session Stitched, Corporate Domain Isolated, …)
  final    → SQLAlchemy async DB (SQLite default = mock DB; VISITOR_DB_URL
             points at Postgres in production)
  ▼
WS /api/v1/ws/crm/live  → dashboard renders envelopes verbatim
```

## CRM wire envelope (exact)

```json
{
  "task_id": "celery-uuid",
  "site_domain": "prospectmarketingsite.com",
  "resolution_tier": "COOKIE_STITCH | LOCAL_GEOIP | RETENTION_API | ANONYMOUS",
  "status": "QUEUED | TRACKING | STITCHING | FALLBACK_TRIGGERED | COMPLETED",
  "live_crm_delta": {
    "email": "resolved_prospect@domain.com",
    "company_domain": "company.com",
    "prospect_name": "Full Name",
    "linkedin_url": "https://linkedin.com/in/prospect"
  },
  "error_logs": "traceback string or null",
  "visitor_id": "…", "ts": "…"
}
```

## API

| Route | Purpose |
|---|---|
| `POST /api/v1/capture/track` | RudderStack-style ingestion; 202 + `visitor_id`, hands off to Celery (inline degradation if broker down) |
| `GET /api/v1/tracker.js?site_key=…&api_origin=…` | templated client embed (origin/site key injected) |
| `GET /api/v1/crm/visitors?site=…` | resolved visitor ledger (dashboard feed) |
| `GET /api/v1/crm/visitors/{id}` | one record |
| `GET /api/v1/crm/ledger` | internal event ledger |
| `WS /api/v1/ws/crm/live?site=…` | live envelope stream (global or per-site channel) |

## Client embed

```html
<script async src="https://<backend>/api/v1/tracker.js?site_key=SITE_KEY"></script>
```

The tracker (Snowplow-modelled, clean-room) intercepts `?he=<token>` on any
page load, writes the first-party `__sl_vid` cookie immediately, strips the
marker from the URL via `replaceState`, and posts fingerprint + page context
to `/api/v1/capture/track` (fetch keepalive + sendBeacon on pagehide; errors
never touch the client page).

## Setup

```bash
cd saas && .venv/bin/pip install -r visitor_core/requirements.txt   # geoip2

# MaxMind local DB (zero-latency corporate resolution; optional but recommended)
export GEOIP_MMDB_PATH=/opt/maxmind/GeoLite2-City.mmdb

# Retention.com fallback layer (optional; pipeline degrades without it)
export RETENTION_API_URL="https://wrapper.internal/resolve"
export RETENTION_API_KEY="…"
export VISITOR_PROXY_LIST="socks5://user:pass@gateway:1080,…"

# storage/broker
export VISITOR_DB_URL="sqlite+aiosqlite:///./visitor_core.db"   # or postgresql+asyncpg://…

.venv/bin/uvicorn visitor_core.app.main:create_app --factory --port 8500
.venv/bin/celery -A visitor_core.app.workers.celery_app.celery worker \
    -Q visitor --pool=threads --concurrency=16 --loglevel=info
```

## Fault model

- Ingestion never blocks: 202 ack, worker resolves async; broker outage →
  inline degradation in the API process.
- Pipeline wrapped in `asyncio.wait_for` (VISITOR_PIPELINE_TIMEOUT, default
  120s); any exception → tier ANONYMOUS + traceback in `error_logs`, record
  still persisted.
- GeoIP: missing/corrupt MMDB or unmapped/private IP → treated as anonymous
  network, chain falls through.
- Retention call: strict timeout (VISITOR_FALLBACK_TIMEOUT + 5s), any failure
  → ANONYMOUS, never raised.
- Celery `acks_late` + `prefetch=1`: worker death re-queues the hit.

## Compliance

First-party cookie only (`SameSite=Lax`, no third-party storage); tracker
honors `credentials: "omit"` on its own requests. MMDB is a licensed MaxMind
database — keep the GeoLite2 license attribution on the client-facing
privacy policy. Retention.com usage must comply with their contract and the
client site's privacy disclosures. Resolved identities feed the CRM and are
subject to the same suppression/opt-out invariants as the outbound stack
(`PROJECT_POLICY.md` §2.8).
