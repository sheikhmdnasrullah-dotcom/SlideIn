# osint_core — Lead Enrichment Matrix + Agentic Personalization Cluster

Single lead email address in → unified `EnrichmentResult` out: recon across a
14-module matrix, multi-hop entity graph, three-agent reasoning loop, and a
compliant outreach draft — with every state transition streamed live to the
client dashboard over an exact wire schema.

## Architecture

```
Founder terminal (CLI)                Client dashboard
  python -m osint_core.cli …          WebSocket / SSE  (verbatim envelopes)
        │                                   │
        ▼                                   ▼
POST /api/v1/enrich ──► FastAPI ──► Celery (Redis broker, acks_late, prefetch=1)
POST /api/v1/enrich/bulk (campaign)  └──► EnrichmentPipeline (per lead)
POST /api/v1/campaigns/{id}                 modules, each isolated + timeout:
GET  /api/v1/approval/queue                 WebsiteScraper → FireEnrich →
POST /api/v1/approval/{email}               Maigret → Blackbird → Holehe →
                                            Dnsrecon → Subfinder → Spiderfoot →
                                            Bomkesh → MailAccess → Noimosiny →
                                            BrightData → EntityGraph → AI-Agents
GET /api/v1/result/{email}  ──► EnrichmentResult (Redis, 30d TTL)
```

## Wire schema (worker → dashboard, exact)

Every transition is one JSON envelope; percentages are real chunk math:

```json
{
  "task_id": "celery-uuid",
  "active_framework": "FireEnrich | WebsiteScraper | Maigret | Blackbird | Holehe | Bomkesh | Subfinder | Dnsrecon | Spiderfoot | MailAccess | Noimosiny | BrightData | EntityGraph | AI-Agent-Reasoning",
  "lifecycle_status": "QUEUED | ROUTING_PROXIES | PARSING_DOM | PROCESSING_AI | COMPLETED | FAILED",
  "progress_percentage": 61.3,
  "extracted_delta": {"target_avatar": "https://…", "dns_record": {"type": "MX", "count": 2}},
  "error_logs": "Traceback … or null",
  "job_id": "…", "lead_email": "…",
  "chunk_progress": {"completed_chunks": 12, "total_chunks": 600},
  "ts": "2026-10-26T…"
}
```

Transport: `WS /api/v1/ws/jobs/{job_id}`, `WS /api/v1/ws/leads/{email}`,
`SSE /api/v1/stream/jobs/{job_id}`, `SSE /api/v1/stream/leads/{email}`.
Each scope channel carries all its envelopes exactly once (subscribe to the
single most specific channel — no duplication).

## Modules

| Module | Engine integration |
|---|---|
| WebsiteScraper | omkarcloud scraper via `WEBSITE_SCRAPER_CMD` (headless, JSON), or built-in JA3 fetch of `/`, `/contact`, `/about` — contact emails, phones, socials |
| FireEnrich | `FIRECRAWL_API_KEY` → scrape+extract (company profile, funding tracks, tech stack, 3 parallel sub-agents); heuristic fallback over WebsiteScraper slots |
| Maigret / Blackbird | registry sweep (Maigret `data.json`-compatible; import full export for 600+ platforms) across ALL derived handle candidates; Blackbird engine via `BLACKBIRD_CMD` |
| Holehe / Bomkesh | `HOLEHE_CMD` engine or gravatar-derived registrations; Bomkesh aggregates structural footprint slots |
| Dnsrecon / Subfinder | dnspython asyncio (A/AAAA/MX/TXT/NS/SOA + 11 DKIM selectors + DMARC); passive subdomain aggregation (crt.sh, bufferover, hackertarget, local binary) |
| Spiderfoot | breach registries (HIBP), crypto-address sweep, SEC EDGAR filings, darkweb seam — OpenOSINT/MCP-style adapter contracts |
| MailAccess / Noimosiny | `MAILACCESS_CMD` (5,300+ corpus) or breach-merged sampler; Noimosiny risk index from exposure signals (`NOIMOSINY_CMD` optional) |
| BrightData | company/leadership/funding dataset adapter (key-gated stub) |
| AI-Agent-Reasoning | Investigator ∥ Researcher → Copywriter (LLM via `LLM_BASE_URL/API_KEY/MODEL`, deterministic fallback) |

## Anti-bot & fault isolation

- **JA3**: `curl_cffi` Chrome TLS fingerprint (`CURL_IMPERSONATE`, default
  `chrome124`) + per-request SOCKS5 residential rotation with exponential
  per-proxy cooldown; empty pool = direct egress (lab only).
- **Isolation**: every module runs under its own asyncio timeout in
  `ProgressTracker.guard` — failure → FAILED envelope with traceback in
  `error_logs`, empty block handed to aggregation, pipeline continues.
  Per-probe hard timeouts; 4xx fails fast; 429 rotates identity.

## Agentic workflow (runs while the client sleeps)

Per-lead state machine, Redis-backed, Celery `acks_late` re-queues on worker
death: `ENRICHING → PENDING_APPROVAL → APPROVED | REJECTED`. Everything up to
the draft is autonomous; drafts park in `approval:pending` until a human
decides (CLI or API). Approved drafts are ready for the sender/export layer.

## Founder CLI (no dashboard needed for ops)

```bash
cd saas
.venv/bin/python -m osint_core.cli enrich jane.doe@acme.com --sync
.venv/bin/python -m osint_core.cli bulk leads.txt --name "Series B fintech"
.venv/bin/python -m osint_core.cli watch <job_id>          # or an email + --lead
.venv/bin/python -m osint_core.cli queue                   # drafts awaiting decision
.venv/bin/python -m osint_core.cli approve jane.doe@acme.com --note "fits ICP"
.venv/bin/python -m osint_core.cli result jane.doe@acme.com --out dossier.json
.venv/bin/python -m osint_core.cli campaign <job_id>
```

## Setup

```bash
cd saas && .venv/bin/pip install -r osint_core/requirements.txt
.venv/bin/uvicorn osint_core.app.main:create_app --factory --port 8400
.venv/bin/celery -A osint_core.app.workers.celery_app.celery worker \
    -Q osint --pool=threads --concurrency=8
```

Optional env: `OSINT_PROXY_LIST` (SOCKS5 pool), `HIBP_API_KEY`,
`FIRECRAWL_API_KEY`, `WEBSITE_SCRAPER_CMD`, `BLACKBIRD_CMD`, `HOLEHE_CMD`,
`BOMKESH_CMD`, `MAILACCESS_CMD`, `NOIMOSINY_CMD`, `BRIGHTDATA_API_KEY`,
`OPENOSINT_BIN` (default `openosint` on PATH), `OPENOSINT_ALLOW_ACTIVE`
(off — gates the noisy email/username enumerators),
`LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL`. All degrade gracefully.

## OpenOSINT CLI bridge

`app/modules/openosint_tool.py` spawns the OpenOSINT CLI
(`openosint --json <tool> <target>`) for the passive dns/exposure/github
lookups and flattens its JSON envelope — plus the exposure report-object
exception — into plain text lines. The pipeline runs it quietly before the
agent cluster (no wire module; failures degrade to error rows and never
block agents) and passes results via `ctx.extras["openosint"]`:

* **Investigator** — the account-declared GitHub name adds one vote to name
  verification (still needs ≥2 independent sources; never beats gravatar) and
  the output gains `osint` (github profile, email/username hits, runs/failures).
* **Researcher** — the exposure grade/score lands in `posture_notes` and the
  `osint_exposure` output key, and is included in the LLM prompt.

Active lookups (email/username) only run with `OPENOSINT_ALLOW_ACTIVE=1` or
a per-call `allow_active=True`. Tests (stdlib-only, fake CLI — no network):
`python -m unittest discover -s tests` from `saas/osint_core`.

## Compliance

Outputs feed Slidein cold-email generation; subject to `PROJECT_POLICY.md`
§2.8 (B2B lawful basis, opt-out + RFC 8058, postal address — enforced in the
Copywriter schema and again at the send gate). Copywriter is barred from
breach/dark-web/on-chain mentions; verified professional signals only. No
credential testing anywhere in the matrix. All probes passive.
