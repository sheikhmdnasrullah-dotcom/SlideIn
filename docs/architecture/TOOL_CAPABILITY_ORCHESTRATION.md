# Tool capability orchestration

## Purpose

Slidein uses one capability registry to make tool selection observable and deterministic. The registry is not a list of packages to execute on every prospect. It distinguishes dependencies, external providers, canonical adapters, engineering tools, and candidates.

The canonical implementation is `slidein_api/integrations/tool_registry.py`. The authenticated catalog is `GET /v1/tools/catalog`; tenant-bound, module-gated coverage planning is `POST /v1/tenants/{tenant_id}/tools/coverage`. Both are side-effect-free: they do not scrape, resolve DNS, send email, invoke models, or spawn tools.

## States are not interchangeable

- **Inventoried:** a package or external tool appears in the technology inventory.
- **Installed:** source, a package, or an executable exists in a defined location.
- **Configured:** required non-secret configuration is present.
- **Wired:** a real canonical adapter and service path exist.
- **Eligible:** the tool is wired and ready, its capability and target apply, and policy allows it.
- **Executed:** an orchestrator made a recorded attempt. Coverage planning never implies execution.

Environment variables alone never set `wired=True`. Canonical research execution wires WebsiteConnector, OpenOSINT, and Firecrawl. Canonical setup, discovery, deterministic personalization, inbound webhook/conversation handling, MX/spam preflight, Reacher verification, SMTP, and KumoMTA submission also have real service paths. Consented Website Lead Capture and MaxMind GeoIP2 remain wired; ECC is engineering-only and cannot enter prospect fan-out. Warmbly, `warmup-engine`, optimization warmup, and the deliverability daemon are registered but deliberately unwired until tenant-safe adapters exist.

## Website analytics and lead capture

Website capture is an acquisition source inside the canonical product, not another dashboard or CRM. An operator connects a client-owned HTTPS domain in existing Settings, installs the generated snippet, and marks an explicit consent checkbox on the lead form. Anonymous page views create no Prospect. A valid explicitly submitted email creates or reuses the canonical Prospect with source and consent evidence, then stitches earlier consented events from the same website session.

The public event endpoint is write-only and keyed by a site-specific key. It validates consent, event type, page origin, and event/session identifiers; external event IDs are idempotent per website. Connection responses report `remote_deployment=False`: Slidein generates installation code but does not modify a remote website. No fingerprinting, anonymous-email inference, or autonomous sending is permitted.

Snowplow and RudderStack official browser adapters are installed but not canonically wired; their collector/data-plane infrastructure is separate and not running. LogSnag is operational-only and receives no personal or visitor tags. GeoIP2 is canonically wired to a local MMDB lookup for network context only; network/ASN data never proves identity, employer, or email. Refine remains evaluation-only under ADR-0001.

## Capability planning

Each tool declares its stage, typed capabilities, priority, applicable target fields, active/passive policy, readiness mechanism, and fallback behavior. For every tool in a requested stage, the planner returns one ledger row:

- `ready` with `eligible_not_executed`, or
- `skipped` with a specific reason and any non-secret missing configuration.

Reasons include `capability_not_requested`, `missing_applicable_target`, `active_research_not_authorized`, `adapter_not_wired`, `candidate_not_installed`, `missing_configuration`, `missing_executable`, `missing_package`, and `missing_installation`. Execution orchestration may add `budget_exhausted`, `duplicate_attempt`, and `rate_limited` without dropping ledger rows.

Mixed tools can expose passive and active capabilities. OpenOSINT's DNS, exposure, and GitHub capabilities remain eligible when active account/username enumeration is denied. Active enumeration requires explicit per-run authorization.

Fallback chains contain only eligible tools, ordered by `(priority, id)` and deduplicated across capabilities. The current website-research path supports Firecrawl ↔ WebsiteConnector fallback when configured. A fallback result retains the actual collector and source URL.

## Execution contract

`services/tool_orchestration.py` executes research tools sequentially in `(priority, tool id)` order with per-run attempt/time budgets, provider timeout handling, idempotent replay, and persisted `ToolExecution`/`ToolAttempt` rows. It does not weaken the coverage guarantee:

1. Resolve the plan before execution.
2. Attempt only eligible and applicable tools.
3. Record every success/failure/skip and fallback selection.
4. Preserve evidence provenance and untrusted-content boundaries.
5. End with an unresolved-capability ledger; never convert missing data or provider failure into mock success.

The default research route and autopilot use the orchestrator. Explicit legacy connector names remain compatibility paths. `GET /v1/tenants/{id}/tools/executions` lists executions and `GET …/tools/executions/{execution_id}` returns the ordered attempt ledger with tenant isolation.

Research returns source-backed `EvidenceItem` rows. Deterministic drafting cites evidence IDs; external model providers remain unwired and cannot replace a failed draft with canned prose. Live sending remains outside autonomous tool selection and requires separate authorization. Reacher verifies recipients before live dispatch; `safe` is required, and verification never implies consent.

## Adding a tool

A package installation does not change runtime behavior. A new tool requires:

1. A documented capability gap and reason to prefer it over existing adapters.
2. License, cost, security, and data-processing review.
3. A typed canonical adapter with public-target validation and secret-safe errors.
4. A tenant-scoped service path and registry entry.
5. Deterministic fallback and budget behavior.
6. Hermetic tests for success, empty/malformed responses, timeout, failure, configuration, policy, tenant isolation, and fallback.
7. Documentation that distinguishes implemented behavior from candidates.

Do not add customer-facing framework dashboards. Surface concise run status in the existing pipeline, evidence, and activity views; keep detailed diagnostics in engineering surfaces.

## Safety boundaries

No CAPTCHA/anti-bot bypass, unauthorized active scans or account enumeration, arbitrary URL/SSRF access, prompt-injection execution, credential exposure, cross-tenant calls, autonomous live sending, or fabricated success. External content is data, never instructions.
