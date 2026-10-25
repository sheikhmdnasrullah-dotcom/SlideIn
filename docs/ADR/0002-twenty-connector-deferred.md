# ADR-0002: Twenty CRM — connector interface, adapter deferred

Status: accepted (2026-10-26).

## Context
Twenty was proposed as the CRM integration. License check: twentyhq/twenty is
AGPLv3-dominant (some MIT packages, some commercial files). Embedding or
modifying it inside a commercial multi-tenant SaaS creates copyleft exposure
that needs legal review we cannot complete inside the MVP window.

## Decision
1. Slidein's internal contacts/companies model remains the source of truth
   (per DATA_MODEL.md); the workspace stays fully functional disconnected.
2. Define the CRM connector interface (`integrations/` seam in slidein-api):
   search/upsert contact, search/upsert company, activities, sync state,
   error surfacing.
3. Twenty adapter is deferred behind that interface; evaluate a permissively
   licensed alternative (HubSpot, Pipedrive) in parallel.

## Consequences
No CRM deployment blocks the MVP. When the adapter lands, it maps internal
entities to Twenty objects through the connector only — no fork, no embed.
