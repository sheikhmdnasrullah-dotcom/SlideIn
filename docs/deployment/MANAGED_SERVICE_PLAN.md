# Managed Service Plan — public code vs. hosted offering

> Intent document. **No managed service exists today.** Nothing here is an
> available product, and no pricing, uptime, or feature commitments are made.

## Model

The open-core pattern: the full self-hosting stack stays open source under
MIT; a separately operated hosted service charges for convenience
(availability, maintenance, backups, monitoring, onboarding, support).

| Stays public (this repo) | Stays private (hosted operations) |
|---|---|
| All engine/runtime source code | Production secrets & environment files |
| Deploy scripts, compose files, Lua policies | Customer data, databases, mailboxes |
| Docs, architecture, roadmaps | Billing credentials & payment webhooks |
| Placeholder configs (`.env.example`) | Internal monitoring endpoints/dashboards |
| Sample templates (`.eml`) | Customer-specific configuration |
| Test suites & CI definitions | Proprietary integrations, if any are added |

## Boundary rules

1. Customer data never enters this repository — not in code, tests, logs,
   screenshots, or fixtures. Test fixtures use fabricated data only.
2. Production configuration lives on the serving infrastructure (or a private
   ops repository), never alongside public source.
3. The hosted instance runs from the same tagged releases the public repo
   publishes, so the open-source artifact is the real thing — not a cut-down
   version.
4. Premium/hosted features, if any are ever introduced, must be documented
   honestly in this file and in the changelog — no bait-and-switch of
   already-published capabilities.

## What a hosted offering would need (future work)

- Tenant-isolated deployment with enforced server-side authorization
  (roadmap Stage 4)
- Signup/onboarding, entitlements, and usage metering (roadmap Stage 5)
- A real payment provider integration — none exists today
- Backup/restore drills, monitoring, and a support channel
- Published terms, privacy policy, and DPA — none exist today

## Self-hosters first

Self-hosting must remain a first-class path: the README quickstart, the lab
stack, and the production deploy scripts are part of the public project and
are maintained as such.
