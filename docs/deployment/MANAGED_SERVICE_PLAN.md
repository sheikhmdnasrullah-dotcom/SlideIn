# Service Deployment and Operating Plan

- Status: Active service-boundary guidance
- Date: 2026-10-26
- Product model: `../product/PRODUCT_SPECIFICATION.md`
- Technical model: `../architecture/CANONICAL_ARCHITECTURE.md`

No managed multi-customer control plane is claimed as complete. No prices, uptime commitments, or unimplemented capabilities are included.

## 1. One product, three service levels

Self-Hosted, Managed, and Growth Partner use the same tagged product release, canonical records, workflow, and workspace. They differ in operating responsibility and centrally authorized service entitlement, not in application architecture.

| Responsibility | Self-Hosted | Managed | Growth Partner |
|---|---|---|---|
| Infrastructure | Customer | Slidein dedicated client environment | Slidein dedicated client environment |
| Install, update, backup, recovery | Customer | Slidein | Slidein |
| Credentials and integrations | Customer | Agreed shared/operated scope | Agreed operated scope |
| Business configuration | Customer | Shared with client approval | Slidein prepares/maintains within scope; client approves material decisions |
| Research/workflow operation | Customer | Defined managed scope | Agreed acquisition-program scope |
| Sales conversations and material business decisions | Client | Client unless explicitly agreed | Defined responsibility; client retains material decisions |
| Export/offboarding | Documented self-service | Slidein-assisted | Slidein-assisted |

Growth Partner does not automatically include content, LinkedIn, visitor identification, chat, voice, or full meeting operations. Those require real implemented capabilities and explicit scope.

## 2. Public code and private operations

### Shared product artifacts

- Application and workflow source.
- Supported deployment scripts and migrations.
- Placeholder configuration.
- Product/architecture/operations documentation.
- Fabricated test fixtures and test suites.
- Tagged releases and changelogs.

### Private client/operations artifacts

- Production secrets and environment files.
- Customer databases, knowledge, prospects, messages, and logs.
- Client-specific configuration and credentials.
- Mailboxes and private sending keys.
- Internal support notes and monitoring endpoints.
- Billing and commercial records if introduced.

Customer data never enters public source, tests, screenshots, logs, or fixtures.

## 3. Dedicated managed environment

Each managed client receives an isolated environment containing:

- One client's configuration and business data.
- Workflow and approval state.
- Credentials and secret references.
- Logs and audit history.
- Backup and recovery boundary.

Every environment runs the same supported product release. Do not fork source per client.

Dedicated isolation reduces blast radius but creates operational duties: patching, health checks, backup, restore, access control, upgrade, rollback, and retirement must be repeatable for every host.

## 4. Operator responsibilities

The operator context tracks:

- Client/instance and deployment model.
- Product release and configuration version.
- Lifecycle and health.
- Integration health without secret values.
- Failed runs and required intervention.
- Entitlement and agreed operating responsibilities.
- Backup/restore and update status.
- Export, retirement, and deletion history.

Start with reliable records and runbooks. Add operator screens only when they expose real state.

## 5. Activation boundary

A new instance begins with review-required behavior, autopilot disabled, and `dry_run` transport.

Live operation requires:

- Complete business and sending configuration.
- Verified connections and least-privilege credentials.
- Required human approval and support responsibilities.
- Passed readiness and safety checks.
- Tested backup and send-stop behavior.
- Explicit activation by an authorized operator.

No live send, DNS change, production deployment, or provider mutation is an ordinary development side effect.

## 6. Required operating procedures

Before third-party managed rollout, demonstrate:

1. Fresh installation from a tagged release.
2. Supported upgrade and rollback with preserved data.
3. Backup and isolated restore rehearsal.
4. Credential rotation and revocation.
5. Monitoring and tested alert delivery.
6. Tenant/global emergency send stop.
7. Provider outage and incident response.
8. Full customer export without secret values.
9. Offboarding with export confirmation, revocation, deletion/retention schedule, backup expiry, and verification.

## 7. Data portability

Clients can export business knowledge, configuration, prospects, evidence, drafts, messages, conversations, runs, and relevant audit history in documented machine-readable formats.

Secret values are excluded. Safe connection references and reconnection instructions are included.

Retention must come from service quality and accumulated operational value, not artificial lock-in.

## 8. Licensing boundary

The repository currently contains BSL 1.1 terms and conflicting MIT messaging in the README. Engineering must not silently change licensing terms or interpret the badge as permission.

The owner must explicitly decide and record the managed-service licensing approach before third-party managed rollout. After that decision, align the license, README, service terms, and documentation together.

## 9. Shared deployment later

Shared production multi-tenancy is not part of the initial plan. Reconsider only after PostgreSQL/migrations, customer identity, enforced authorization everywhere, central entitlements, tenant-scoped jobs/events/exports, resource controls, observability, recovery, and dedicated security review are proven.
