# unified — the whole engine, one process

This package integrates `osint_core` (lead enrichment matrix + agent cluster)
and `visitor_core` (website visitor identity capture) into one deployable
unit: a single FastAPI server and a single Celery worker consuming both
queues, plus a live dashboard.

## What's mounted

| Surface | Source |
|---|---|
| `POST /api/v1/enrich`, `/enrich/bulk`, `/result/{email}`, `/dossier/{email}`, `/jobs/{job_id}` | osint_core |
| `GET /api/v1/campaigns/{id}`, `/approval/queue`, `POST /approval/{email}` | osint_core workflow |
| `WS/SSE /api/v1/ws/jobs/{id}`, `/ws/leads/{email}`, `/stream/jobs/{id}`, `/stream/leads/{email}` | osint_core streaming |
| `POST /api/v1/capture/track`, `GET /tracker.js`, `GET /crm/visitors…`, `WS /ws/crm/live` | visitor_core |
| `GET /` | live dashboard (enrich form, campaign form, live firehose, approval queue, CRM visitors) |
| `GET /stream/all` | merged firehose: every envelope from both engines, one SSE feed |

## Run it

```bash
cd saas
unified/run_local.sh            # starts docker redis (if needed) + worker + server
# → dashboard: http://localhost:8400
```

Or manually:

```bash
docker run -d --name osint-redis -p 6379:6379 redis:7-alpine
.venv/bin/celery -A unified.worker.celery worker -Q osint,visitor \
    --pool=threads --concurrency=8 --loglevel=info
.venv/bin/python -m uvicorn unified.server:app --host 0.0.0.0 --port 8400
```

Verified live (2026-10-26): real enrichment of a probe lead through the
worker — 14/14 modules (73 subdomains from crt.sh, MX/DMARC parsed, 10 SEC
EDGAR filings, website contact slots + tech-stack vectors from the real site,
entity graph 90 nodes, three-agent cluster draft), draft through the approval
queue, visitor capture resolving COOKIE_STITCH, all streamed to `/stream/all`.

## Notes

- Worker pool: `threads` (dnspython + curl_cffi behave poorly in prefork).
- Both engines share Redis but use separate key/channel prefixes
  (`osint:*`, `visitor:*`, `wf:*`, `approval:*`) — no collisions.
- Visitor DB defaults to `visitor_core.db` (SQLite); set `VISITOR_DB_URL`.
- Optional keys/envs per engine are documented in each module's README;
  everything degrades gracefully without them.
