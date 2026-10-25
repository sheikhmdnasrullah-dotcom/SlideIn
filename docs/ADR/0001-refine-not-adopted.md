# ADR-0001: Refine not adopted for the dashboard

Status: accepted (2026-10-26).

## Context
The mission proposed Refine as the dashboard application framework.

## Decision
Do not adopt Refine. The existing slidein-app (Next.js 16 App Router, Tailwind 4,
established component system, production branding) already provides routing,
auth, and data fetching integrated with slidein-api. Refine would introduce a
parallel router/auth/data-provider model and a duplicate component stack for
zero net capability.

## Consequences
Dashboard adaptivity is implemented as: persisted workspace config (versioned,
validated) + a module renderer over the existing component system — the same
"config over code" principle Refine uses for CRUD, without the framework lock-in.
Revisit only if a genuine data-provider need (multi-backend admin CRUD) emerges.
