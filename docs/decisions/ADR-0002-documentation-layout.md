# ADR-0002: Canonical documentation layout

- Status: Accepted
- Date: 2026-10-12

## Context

Docs grew organically as lowercase files (`docs/*.md`) with overlapping
coverage (audit vs current-state vs roadmap; api vs deployment notes) and
stale references after the Stage 2/3 fixes. Contributors need one predictable
layout.

## Decision

Adopt the canonical layout used by this repository:

- `docs/project/` — audit, current state, technical debt
- `docs/architecture/` — overview, components, data flow, deployment model
- `docs/development/` — local setup, testing
- `docs/deployment/` — self-hosting, production readiness, managed-service plan
- `docs/security/` — threat model, publication checklist
- `docs/api/` — API overview
- `docs/decisions/` — ADRs (this file)
- `docs/portfolio/` — case study, website content, profile draft (proposals)

UPPERCASE filenames within each area. Superseded lowercase files were
retired after content migration (backup kept at `/tmp/docs-pre-restructure.tar.gz`).

## Consequences

- All in-repo doc links were updated to the new paths in the same change.
- `docs/project/CURRENT_STATE.md` is the single source of truth for
  implementation status; other docs link to it instead of restating status.
