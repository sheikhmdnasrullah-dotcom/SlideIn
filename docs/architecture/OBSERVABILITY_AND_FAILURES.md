# SLIDEIN OBSERVABILITY, CIRCUIT BREAKERS & FAILURE HANDLING

> **Monitoring, Structured Logging, Health Probes & Circuit Breakers**  
> Status: Authoritative Specification  
> Version: 1.0.0

---

## 1. Structured Logging Standard

All server logs, Route Handlers, background jobs, and MTA adapters emit structured JSON to stdout and rotating logfiles:
```json
{
  "timestamp": "2026-10-13T04:12:00.123Z",
  "level": "INFO",
  "service": "slidein-api",
  "trace_id": "tr_01J...",
  "tenant_id": "ten_01J...",
  "event": "message_dispatched",
  "details": {
    "prospect_id": "prosp_01J...",
    "draft_id": "draft_01J...",
    "recipient_domain": "cloudwave.tech",
    "transport": "kumomta_smtp",
    "status": "submitted",
    "duration_ms": 142
  }
}
```

---

## 2. Deliverability Circuit Breakers

To protect IP and domain reputation, Slidein operates automated circuit breakers:

```
+--------------------------------------------------------------------------------+
|                             CIRCUIT BREAKER ENGINE                             |
+--------------------------------------------------------------------------------+
|  Normal State (CLOSED)  -->  Bounce Rate > 2.5% OR Complaint Rate > 0.1%       |
|                                         |                                      |
|                                         v                                      |
|  Tripped State (OPEN)   <--  Auto-Pause Sending for Tenant / Identity          |
|                               Alert Operator with diagnostic payload           |
|                                         |                                      |
|                                         v                                      |
|  Recovery State (HALF)  <--  Operator conducts lead scrub & initiates probe    |
+--------------------------------------------------------------------------------+
```

### Tripwire Thresholds:
1. **Rolling Bounce Rate:** $> 2.5\%$ over the trailing 100 sent messages $\rightarrow$ PAUSE campaign immediately.
2. **Spam Complaint Rate:** $> 0.1\%$ (1 complaint per 1,000 sent) $\rightarrow$ IMMEDIATE EMERGENCY PAUSE across all campaigns on that sending domain.
3. **MTA Deferral Rate:** $> 15\%$ over 30 minutes $\rightarrow$ Throttle sending speed by $50\%$ and notify operator.

---

## 3. Health Probes & Endpoints

- **`GET /api/health`** (Web console health):
  - Database connectivity (Postgres / Appwrite / SQLite)
  - Memory & runtime status
- **`GET http://localhost:8088/healthz`** (Deliverability engine health):
  - KumoMTA socket probe (port 2587)
  - Mailpit / Sink probe
  - Suppression database integrity
- **`GET /api/tenants/{tenant_id}/health`** (Tenant-specific operational health):
  - Daily sending volume vs quota
  - Unreviewed drafts count
  - Failed job count

---

## 4. Failure Recovery & Error Taxonomy

| Error Code | Classification | Automatic Recovery Action |
|---|---|---|
| `RATE_LIMIT_EXCEEDED` | Transient | Exponential backoff with jitter (delay 10s, 30s, 90s). |
| `NETWORK_TIMEOUT` | Transient | Retry up to 3 times before setting task to `FAILED`. |
| `INVALID_SYNTAX_EMAIL`| Permanent | Mark prospect `DISQUALIFIED`, record error reason, do not retry. |
| `SUPPRESSION_BLOCKED` | Policy | Abort send, record audit log, transition draft to `CANCELLED`. |
| `AUTH_FAILURE` | Critical | Halt all tenant operations, trigger high-priority operator alert. |
