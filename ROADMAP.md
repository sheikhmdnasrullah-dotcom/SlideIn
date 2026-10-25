# Slidein Roadmap

The active dependency-ordered implementation plan is [`docs/engineering/IMPLEMENTATION_ROADMAP.md`](docs/engineering/IMPLEMENTATION_ROADMAP.md).

The working checkbox list is [`../planning/TASKS.md`](../planning/TASKS.md).

## Product sequence

1. Protect the current system and establish a reproducible baseline.
2. Converge customer behavior on `slidein-app` + `slidein-api`.
3. Unify capability, knowledge, and configuration persistence.
4. Make execution durable, idempotent, restart-safe, and review-first.
5. Complete prospect-to-conversation with real inbound and handoff.
6. Simplify the existing workspace without a visual redesign.
7. Add customer identity, team permissions, and centralized service entitlements.
8. Prove dedicated deployment, upgrades, recovery, export, and offboarding.
9. Add only the next evidence-backed capability.

## Canonical documents

- [Product Constitution](docs/product/PRODUCT_CONSTITUTION.md)
- [Product Specification](docs/product/PRODUCT_SPECIFICATION.md)
- [Canonical Architecture](docs/architecture/CANONICAL_ARCHITECTURE.md)
- [Convergence ADR](docs/decisions/ADR-2026-10-26-canonical-product-convergence.md)
- [Current State](docs/project/CURRENT_STATE.md)

## Non-goals

No big-bang rewrite, no new dashboard cycle, no competing acquisition domain, no autonomous code deployment, no unimplemented feature presented as operational, and no framework adoption without a demonstrated need.

Older roadmap phases and status labels are historical. Use the linked canonical documents for active work.
