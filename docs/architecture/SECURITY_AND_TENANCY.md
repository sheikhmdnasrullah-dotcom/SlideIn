# SLIDEIN SECURITY, TENANCY & COMPLIANCE

> **Multi-Tenant Isolation, Authentication, Secrets & Compliance Rules**  
> Status: Authoritative Specification  
> Version: 1.0.0

---

## 1. Multi-Tenant Isolation Enforcement

Slidein enforces isolation across three independent defense layers:

### Layer 1: Application Server Auth Guard
Every server action, Route Handler, and API endpoint must resolve the authenticated user and their authorized `tenant_id` before querying the database:
```typescript
// Enforced pattern across all API routes:
const session = await requireUser();
const tenantId = await resolveTenantForUser(session.id);
if (!tenantId) {
  return ApiError.forbidden("No active tenant membership").toResponse();
}
```

### Layer 2: Database Query Scoping & RLS
- All operational queries must include `WHERE tenant_id = :tenant_id`.
- On PostgreSQL, Row Level Security (RLS) policies enforce:
```sql
ALTER TABLE prospects ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_policy ON prospects
  FOR ALL
  USING (tenant_id = current_setting('app.current_tenant_id', true));
```

### Layer 3: Background Worker Context
Workers and cron jobs must carry an explicit, immutable `tenant_id` context. A worker is never permitted to execute across multiple tenants in a single unbounded query.

---

## 2. Role-Based Access Control (RBAC)

| Role | Scope | Permissions |
|---|---|---|
| **Platform Administrator** | Global | Deployments, fleet monitoring, provider keys, database backups, system metrics. |
| **Operator** | Fleet / Assigned Clients | Configure client onboarding, review readiness checks, trigger research/draft runs, adjust rate limits. |
| **Tenant Admin** | Single Tenant | Full access to tenant business profile, offers, ICP, team members, sending identities, and billing. |
| **Tenant Member** | Single Tenant | View prospects, review evidence, edit drafts, approve outreach, manage conversations. |
| **Read-Only / Auditor** | Single Tenant | View metrics, inspect logs and reports; no mutation or approval capabilities. |

---

## 3. Secret Management & Credential Isolation

1. **Zero Secrets in Code or Docs:** No API keys, database passwords, SMTP credentials, or DKIM private keys in git history or documentation.
2. **Environment Isolation:** Secrets are injected strictly through environment variables (`.env.local` for local dev; secure system env on VPS).
3. **Redaction:** All logger instances redact authorization headers, email bodies, passwords, and tokens before writing to disk or stdout.

---

## 4. Prompt Injection & External Content Defense

When researching prospects, Slidein fetches content from third-party websites, LinkedIn profiles, and emails.
- **Untrusted Input Classification:** All crawled HTML, meta tags, and inbound email bodies are classified as **Untrusted Data**.
- **Sanitization:** HTML tags, script blocks, base64 payloads, and hidden CSS are stripped before passing to LLM prompts.
- **Structural Framing:** External content is strictly encapsulated in fenced XML delimiters (`<untrusted_web_content>...</untrusted_web_content>`).
- **Tool Execution Isolation:** AI extraction models do not have tool-calling access to email dispatch or database mutation while parsing external content.

---

## 5. Suppression & Anti-Spam Compliance

- **Immediate Opt-Out:** Any recipient requesting removal (via one-click unsubscribe header or conversational reply like "stop", "unsubscribe", "remove me") is immediately added to `suppression_records`.
- **Pre-Send Tripwire:** Sending code verifies email against suppression records immediately prior to SMTP submission. If found, message is aborted and marked `BLOCKED_SUPPRESSED`.
- **Sender Transparency:** All outbound messages include valid physical address and functional opt-out instructions.
