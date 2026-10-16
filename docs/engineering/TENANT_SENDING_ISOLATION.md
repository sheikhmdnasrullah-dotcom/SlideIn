# Tenant-Level Sending Reputation Isolation

> Status: Implemented for the slidein-api path (2026-10-16). Design and audit
> below are the authoritative record for what this feature does, why, and
> what it does not do.
> Code: `slidein-api/slidein_api/services/sending.py`,
> `slidein-api/slidein_api/services/outreach.py`,
> `slidein-api/slidein_api/api/routes/outreach.py`,
> `slidein-api/slidein_api/models.py`,
> `slidein-api/tests/test_sending_isolation.py`.

---

## 1. Audit — what the code actually does today

The workspace has two Python programs that can move bytes:

* **`deliverability/`** — the *original* deliverability engine
  (`core/pipeline.py::send_via_pipeline` is documented as "THE ONE
  approved outbound path"). It has **no tenant concept at all**: its
  configuration is a single global `config.json` (one `sending_ip`,
  one `sending_domain`, one set of profiles). Its SQLite state tables
  (`send_events`, `suppression`, `circuit_state`) are keyed by recipient
  and domain only, not by tenant. It is still wired to KumoMTA in
  production (`transport = "kumo"`).
* **`slidein-api/`** — the newer FastAPI workflow layer
  (`slidein_api/services/outreach.py`). Every entity carries a
  `tenant_id`, and every query filters on it. This is the path the
  Next.js client actually uses for sends today
  (`workspace-app/lib/send-gate.ts` →
  `POST /tenants/{tenant_id}/drafts/{draft_id}/send`). It supports
  `dry_run` and `smtp` transports only — KumoMTA is not one of them.

Both paths terminate in an SMTP client that connects to the KumoMTA
submission listener; from there KumoMTA decides which source IP the
bytes leave from.

### 1.1 Confirmed answers to the nine audit questions

| Question | Confirmed answer |
|---|---|
| Do all tenants currently use one public IP? | **Yes.** Live DNS (`docs/deployment/DNS_RECORDS.md`) authorizes exactly one address — `ip4:169.58.206.20` (SPF), and the same address is `sending_ip` in `deliverability/config.production.json`. There is no `egress_pool` / `make_egress_source` configuration anywhere: `kumomta-lab/policy/production_init.lua` never calls `kumo.make_egress_source` / `make_egress_pool`, so every message uses the host's default interface. |
| Can KumoMTA select a tenant-specific egress pool today? | **Yes, but it is not used.** The vendored KumoMTA docs (`kumomta-src/docs/userguide/configuration/sendingips.md`) document egress sources, pools, and weighted round-robin, and `queue.lua` supports per-tenant `egress_pool` assignment (`queues.toml` / `[tenant.'x'] egress_pool = '...'`). Nothing in our production `production_init.lua` calls the queue helper, so no tenant is ever assigned a pool. |
| Is the tenant identity passed into KumoMTA as metadata or otherwise reliably preserved? | **No.** KumoMTA can read a `X-Tenant`/`X-Campaign` header (`queue.lua` reads `tenant_header`/`campaign_header`), but our production policy never calls `queue_helper:apply(msg)`, so KumoMTA never learns a tenant. `slidein-api` stamps `X-Slidein-Tenant` and `X-Slidein-Draft-Id` **server-side** on the message it injects (`services/outreach.py`), so the identity is trusted there — but it is a header for attribution, not a routing decision. |
| Is tenant-to-egress routing deterministic, or could messages accidentally fall back? | **Fallback is real and currently happens.** KumoMTA's own FAQ (`kumomta-src/docs/faq/egress_pool_unspecified.md`) states that an undefined pool makes mail leave from the host default, and `queuemanagement.md` says an unspecified pool is used when no pool is set. Our policy file neither defines pools nor assigns them, so every message implicitly uses the host default. |
| Are sending domains owned by Slidein, by each client, or a mixture? | **A mixture, but all on Slidein's own DNS and IP.** The three domains `nasrullahtanim.me`, `tanim.social`, `tanim.tech` are Slidein's own; each has its own DKIM key and EHLO identity (`mail.nasrullahtanim.me` or `email.tanim.tech`). There is no per-client domain ownership in the current model — the `slidein-api` `Tenant` is a workspace, not a customer domain. |
| Are bounce and complaint signals attributed to the correct tenant and campaign? | **Partially.** `slidein-api` attributes `DeliveryEvent` rows to the tenant that dispatched them, and hard bounces/complaints suppress the recipient for that tenant only. The older `deliverability/` engine attributes nothing: its `send_events` and `suppression` tables have no tenant column, and `circuit_state`/`campaign_state` are keyed by a hard-coded campaign name (`cold-outreach`). |
| Can we stop one tenant's traffic without stopping every tenant? | **Yes — once the tenant-scoped path is used.** Tenant A's sends are filtered by `tenant_id` in every query and the pre-send gate; pausing tenant A never touches tenant B. But *KumoMTA itself* has no tenant awareness, so a pause in `slidein-api` cannot stop bytes already queued inside KumoMTA. |
| What would happen if a tenant's dedicated IP became unavailable? | **Nothing in the code handles it.** No dedicated IPs exist, so the case is hypothetical today; when it arrives, the operator would remove/replace the `TenantSendingConfig` row and re-verify the route. Until then, the failure mode is exactly today's shared-IP behaviour (KumoMTA silently falls back to the default interface). |
| What is the current behaviour when tenant routing configuration is missing or invalid? | **Silently shared.** A tenant with no sending-mode configuration resolves to shared mode. An invalid mode string is never rejected; the config is only read from a JSON blob inside `Tenant.settings`, which no code interprets for egress. |

### 1.2 Where things live

| Concern | File |
|---|---|
| Send path used by the Next.js client | `slidein-api/slidein_api/services/outreach.py` (`OutreachService.send_draft`) |
| Transport selection | `slidein-api/slidein_api/services/transport.py` (`TransportRegistry`) |
| Trusted identity headers | `slidein-api/slidein_api/services/outreach.py` (`X-Slidein-Tenant`, `X-Slidein-Draft-Id`, `X-Slidein-Campaign`) |
| Per-tenant policy (limits, lawful basis, quarantine flag) | `slidein-api/slidein_api/services/outreach.py`, `deliverability_guard.py` |
| Per-tenant circuit-breaker evaluation | `slidein-api/slidein_api/services/outreach.py::_evaluate_quarantine` |
| Delivery event ingestion (webhook) | `slidein-api/slidein_api/api/routes/outreach.py` (`POST /tenants/{tenant_id}/events`) |
| Tenant / settings model | `slidein-api/slidein_api/models.py` (`Tenant.settings` JSONMap) |
| Authentication and tenant scoping | `slidein-api/slidein_api/security.py` (`resolve_workspace`) |
| Approved outbound path used by `deliverability/` | `deliverability/core/pipeline.py` (`send_via_pipeline`), `kumo_transport.py`, `campaign_worker.py` |
| KumoMTA production policy | `kumomta-lab/policy/production_init.lua` |
| KumoMTA capability reference | `kumomta-src/docs/userguide/configuration/` (vendored in-repo) |
| Live DNS / EHLO / PTR records | `docs/deployment/DNS_RECORDS.md` |
| Live KumoMTA configuration | `deliverability/config.production.json` (`kumo`, `sending_ip`, `sending_domains`) |
| Live KumoMTA service definition | `kumomta-lab/compose/docker-compose.production.yml` (`kumomta` service, ports `127.0.0.1:2587/8029`) |

---

## 2. Isolation model

Four modes, exactly four:

**A. Shared IP — explicitly shared reputation.** Several tenants share one
public IP and know it. They keep separate queues, rate limits, suppression
lists and circuit breakers, but their combined sender reputation is one
shared reputation. The product labels this honestly everywhere
("Shared IP — reputation is shared with other tenants using this IP.") and
never claims otherwise.

**B. Dedicated IP — tenant-specific reputation.** A tenant is assigned real,
dedicated public IPs. The assignment is stored only after an operator has
provisioned and routed them, and only `verified` routes carry the
`dedicated` mode. Database rows cannot pretend infrastructure exists.

**C. Provider-managed sending.** An external provider's own infrastructure
carries the tenant's mail (for example a provider's shared pool behind a
verified domain). Isolation then depends on the provider account/IP
configuration, which Slidein does not control — that dependency is stated
explicitly, never assumed.

**D. Future multi-IP / warm-up configuration.** Extensible, not built.
Dedicated mode is a single assigned route today; a tenant may list several
dedicated IPs without automatic rotation. No automatic IP or account
rotation exists, and none will be added to evade filtering.

---

## 3. Implemented in this change (Phase 3)

1. **Trusted identity propagation.** Every message injected by
   `slidein-api` carries `X-Slidein-Tenant` (from the authenticated
   workspace), `X-Slidein-Campaign` (derived server-side from the draft's
   id — the draft is the campaign in this model) and
   `X-Slidein-Draft-Id`. Client-supplied values in headers are ignored;
   the server always stamps the tenant of the authenticated request.
2. **Explicit sending mode and route.** New tables
   `tenant_sending_configs` (mode, egress pool, provider account, dedicated
   IPs, verification) and `circuit_breaker_states`. Operators set the mode
   through `PUT /v1/tenants/{tenant_id}/sending` (admin role).
3. **Deterministic, fail-closed routing.** `SendingService.resolve_route`
   derives the route from trusted application data only. `shared` always
   resolves to the shared route; `dedicated` requires an assigned egress
   pool; `provider_managed` requires a provider account. Without an
   assignment the send is **held** (`sending_route_unresolved`) and an
   operator is pointed at the misconfiguration — never silently sent
   through the shared IP.
4. **Tenant-specific policy enforcement.** Rate limits, suppression, the
   physical address / lawful-basis gate, and the per-tenant circuit
   breaker were already tenant-scoped and are preserved. The breaker state
   now lives in `circuit_breaker_states` (one row per tenant) instead of
   only inside the tenant's settings blob, and can be opened, probed,
   and resumed per tenant by an operator.
5. **Operator controls.** `POST /v1/tenants/{tenant_id}/circuit/pause`,
   `/circuit/probe` and `/circuit/resume` (admin role). Only the addressed
   tenant's state is touched.
6. **Honest admin view.** `GET /v1/tenants/{tenant_id}/sending` reports the
   sending mode, assigned route, verification state, isolation wording,
   circuit state, and the honest copy for each mode. `GET
   /v1/tenants/{tenant_id}/deliverability` additionally reports the circuit
   state and the sending configuration.
7. **Tests.** `slidein-api/tests/test_sending_isolation.py` proves routing
   determinism, fail-closed behaviour, shared-mode preservation, per-tenant
   breaker isolation, pause/resume scoping, and tenant-scoped reads.

## 4. Reputation protection

Existing tenant-scoped safeguards (unchanged, now backed by the
circuit-breaker state table):

* Per-tenant daily/hourly send limits (`policy.daily_limit`,
  `policy.hourly_limit`).
* Suppression: hard bounces, spam complaints, opt-outs and admin removals
  are recorded per tenant and enforced before send.
* Per-domain throttling and backoff are **not** implemented: KumoMTA's
  traffic-shaping policy is operator-authored Lua and Slidein does not
  consume its response-time data. This is a documented gap.
* Complaint feedback loops (Google Postmaster, Outlook SNDS) are **not**
  ingested: `deliverability/core/reputation.py` can *check* them but no
  code posts complaint events into `slidein-api`. This is a documented gap.
* Circuit breaker: rolling window over the tenant's own delivery events
  (`accepted`/`delivered`/`bounced`/`complained`, last 100). Hard-bounce
  rate > 3% or complaint rate > 0.05% trips the tenant. Open, half-open
  probe, resume — all operator-driven, never automatic.

Open signals are treated as telemetry only (as before); opens are never
used for reputation decisions.

## 5. Admin view

`GET /v1/tenants/{tenant_id}/sending` returns, per tenant:

* `sending_mode` (`shared` / `dedicated` / `provider_managed`),
* `egress_pool`, `provider`, `provider_account`, `dedicated_ips`,
* `verified` / `verified_by` / `verification_note`,
* `isolation_copy` — the honest sentence for that mode,
* circuit state (`status`, `reason`, `opened_by`, metrics),
* the tenant's rate-limit policy.

All endpoints are tenant-scoped (`resolve_workspace` returns 404 for a
workspace the caller's key cannot see).

## 6. Data model

New tables (created by `Base.metadata.create_all`; additive, no
destructive migration):

* `tenant_sending_configs` — one row per tenant: mode + route assignment +
  verification. Credentials are never stored (only a provider-account
  nickname).
* `circuit_breaker_states` — one row per tenant: status (`open`,
  `half-open`, `closed`), reason, metrics, operator who acted, when.
* `Tenant.settings` (existing JSONMap) keeps the human-editable policy
  (limits, lawful basis, the legacy `quarantined` flag); the breaker state
  table is now authoritative for the operator view, while the flag is
  still honoured so already-quarantined tenants keep working.

## 7. Infrastructure checklist (recommendations only — nothing done)

* **Additional public IPv4 addresses on the VPS.** Not yet provisioned.
  The VPS is a single host; Contabo's customer portal must authorize new
  addresses. No code or DNS changes were made.
* **Routing / binding.** A dedicated IP must be added to the host, the
  KumoMTA container must be given that address (egress source), and
  EHLO/PTR must match. This requires the operator — it is not a code task.
* **Required DNS/rDNS per sending domain.** Already established for the
  three SlideIn domains (SPF, DKIM, DMARC, PTR for
  `169.58.206.20`). New IPs need new A/AAAA + PTR records pushed via
  Cloudflare (see `docs/deployment/DNS_RECORDS.md`).
* **KumoMTA egress configuration.** `kumomta-lab/policy/production_init.lua`
  is the file to edit (operator-authored, reviewed per
  `PROJECT_POLICY.md`). When dedicated IPs exist, define
  `sources`/`pools` there and assign pools per tenant in the queue helper.
* **Firewall.** Dedicated egress IPs must be allowed by UFW while the SMTP
  listener stays loopback-only (it already is).
* **Monitoring.** Prometheus/Alertmanager scrape KumoMTA metrics
  (`kumo.prometheus` counters). Per-tenant attribution requires tenant
  metadata to reach KumoMTA — which needs the queue helper (see §1.1).
* **Warm-up.** No warm-up automation exists. If/when dedicated IPs are
  used, warm-up must be operator-driven (volume ramp) — never automatic
  rotation.
* **Backup/recovery.** Existing `kumomta-lab/scripts/backup.sh` covers the
  KumoMTA spool; new tables live in the slidein-api SQLite database, which
  `deploy-production.sh` already snapshots.
* **Cost.** One more public IP costs the VPS provider's per-IP fee and
  operator time; a shared route is correct while a tenant's volume is low
  (a dedicated IP performs poorly without sufficient consistent volume).

## 8. Test plan and results

Automated coverage lives in
`slidein-api/tests/test_sending_isolation.py` (12 tests, all green, plus the
rest of `slidein-api` tests unchanged and green):

1. Dedicated tenant resolves to its own pool; shared default preserved.
2. Provider-managed mode names the provider account.
3. Shared mode always clears a dedicated assignment.
4. Dedicated/provider-managed without an assignment fails closed
   (`sending_route_unresolved`, not retried).
5. Another tenant's configuration is not readable (404).
6. Circuit-breaker state is per tenant; only the offending tenant trips.
7. Operator pause / resume affects exactly one tenant.
8. Honest wording is produced for every mode (never "isolated" for shared).

What could **not** be tested here, honestly: real outbound IP attribution
and KumoMTA-side tenant routing (requires production infrastructure), and
deferral backoff per domain (not implemented).

## 9. Migration and rollback

* New tables are additive (`Base.metadata.create_all` only creates missing
  tables; existing rows are untouched).
* `PUT /v1/tenants/{tenant_id}/sending` defaults existing tenants to
  `shared` — existing delivery is unchanged until an operator chooses
  otherwise.
* Rollback is a code revert plus dropping the two new tables (their rows
  are operator-controlled bookkeeping only); no existing column is ever
  edited or removed.
