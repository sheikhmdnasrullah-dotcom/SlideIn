# SLIDEIN TESTING STRATEGY & QUALITY GATES

> **Unit, Integration, and End-to-End Verification Standards**  
> Status: Authoritative Specification  
> Version: 1.0.0

---

## 1. Testing Philosophy & Quality Standard

1. **Tests are part of implementation, not an afterthought:** No feature is marked complete without automated verification.
2. **Never mock away real integration boundaries:** When testing KumoMTA or SQLite deliverability state, test against the real local running daemon or socket.
3. **Zero tolerance for false passes:** Never weaken assertions, delete failing tests, or comment out checks to simulate success.

---

## 2. Test Pyramid & Tooling

| Level | Scope | Framework | Execution Command |
|---|---|---|---|
| **Unit** | Domain entities, qualification logic, anti-spam scoring, suppression matching | Vitest / Jest / Pytest | `npm run test:unit` or `pytest product/tests` |
| **Integration** | DB schema, tenant isolation, API Route Handlers, deliverability API | Pytest / Vitest | `pytest deliverability/tests/` |
| **End-to-End** | Full browser flows, Table interactions, draft approval, dispatch | Playwright | `npx playwright test` |

---

## 3. Mandatory End-to-End Verification Scenarios

### Scenario A: New Client Deployment & Onboarding
- Operator creates tenant "TestCo", enters business profile and offers, configures sending identity, and verifies readiness check passes ($> 90\%$).

### Scenario B: Prospect Ingestion & Deduplication
- Import 20 leads via CSV. Verify duplicate emails are de-duplicated; check records persist with source attribution.

### Scenario C: Sourced Research & Explainable Qualification
- Run research worker on prospect. Verify generated `evidence_items` contain valid `source_url` and qualification explanation states explicit matching/missing criteria.

### Scenario D: Context-Aware Message Drafting
- Generate draft for qualified prospect. Verify draft references verified evidence and contains zero fabricated claims.

### Scenario E: Deliverability Pre-Send Gate & Dispatch
- Verify message is blocked if recipient is suppressed or sending quota is reached. Verify clean message is submitted via SMTP (port 2587) with DKIM signature.

### Scenario F: Delivery Event Logging
- Send test message to Mailpit/Sink. Verify webhook logs `submitted` $\rightarrow$ `accepted` $\rightarrow$ `delivered`.

### Scenario G: Inbound Reply & Instant Opt-Out Suppression
- Ingest inbound reply with body "Unsubscribe please". Verify intent is classified as `unsubscribe` and recipient email is inserted into `suppression_records`.

### Scenario H: Circuit Breaker Auto-Pause
- Simulate 3 consecutive hard bounces. Verify rolling bounce rate trips circuit breaker and pauses campaign.

### Scenario I: Strict Tenant Isolation
- User from Tenant A attempts to fetch prospect from Tenant B via `/api/prospects/{b_id}`. Verify response is `403 Forbidden` or `404 Not Found`.

### Scenario J: Crash Recovery & Idempotent Resume
- Kill background worker during batch research job. Restart worker and verify execution resumes from last uncommitted record without duplicating drafts.
