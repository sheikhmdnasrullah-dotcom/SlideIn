# Slidein Product Specification

- Status: Active canonical product knowledge
- Version: 2.0.0
- Date: 2026-10-26
- Supersedes: conflicting product scopes, two-tier planning, retired content promises, and dashboard-first interpretations in older planning documents
- Technical companion: `../architecture/CANONICAL_ARCHITECTURE.md`
- Execution companion: `../engineering/IMPLEMENTATION_ROADMAP.md`

## 1. The product in one sentence

Slidein turns approved business knowledge into evidence-backed opportunities and controlled customer conversations, records the outcome, and uses approved feedback to improve the next run.

## 2. The simplest explanation for a client

> Tell Slidein what your business offers and who you want to reach. It finds relevant people, researches them with sources, explains why they fit, and prepares personal outreach for your approval. After you approve it, Slidein sends through controlled infrastructure, brings replies into one conversation view, and helps route interested people to the right person or booking link.

The client should not have to understand agents, graphs, queues, workflow engines, deliverability internals, or deployment architecture.

The client has four recurring jobs:

1. Describe the business and approve its knowledge.
2. Confirm the target market and exclusions.
3. Review consequential actions, especially outbound communication.
4. Handle qualified business conversations and decisions.

Everything else is presented as a clear status, an actionable exception, or a meaningful outcome.

## 3. What Slidein is and is not

### Slidein is

- A universal, configurable business workspace.
- An evidence-backed customer-acquisition workflow.
- A persistent system of business knowledge, opportunities, approvals, execution, conversations, and outcomes.
- A deployable product that can be self-hosted or operated as a service.
- A platform whose supported capabilities grow without changing its basic navigation or visual language.

### Slidein is not

- A dashboard generated for each industry or client.
- A conventional CRM with unrelated AI buttons.
- A collection of agents looking for work.
- A visual workflow editor as the main product.
- An autonomous system that changes its own source code or deploys unreviewed changes.
- A promise that every marketing, sales, content, and communication channel is already implemented.
- A per-client software fork.

## 4. The seven ideas that explain the whole system

| Idea | Plain meaning | What it is not |
|---|---|---|
| Shared product | The reviewed Slidein code and supported capabilities released by engineering | Something an agent rewrites for one client |
| Client instance | One isolated Slidein environment containing one client's data, configuration, credentials, and history | A new application built for that client |
| Business knowledge | Approved facts about the company, offers, ICP, policies, proof, and constraints | An unrestricted collection of model guesses |
| Capability | A registered product function that can be configured and authorized | A new dashboard or arbitrary generated component |
| Workflow | A supported sequence of typed stages that uses business knowledge and capabilities | A transient prompt chain |
| Run | One recorded execution with inputs, outputs, state, failures, approvals, and audit history | An invisible background process |
| Service entitlement | What Slidein is responsible for operating for the client under the selected service level | A scattered set of plan checks in UI code |

These ideas are sufficient to explain the product to owners, clients, and coding agents.

## 5. Canonical business workflow

The first complete workflow is prospect-to-conversation:

```text
Business setup
  -> Prospect discovery
  -> Source-backed research
  -> Explainable qualification and offer match
  -> Personalized draft
  -> Human approval and controlled send
  -> Real inbound reply and intent
  -> Owner or booking handoff
  -> Outcome and approved learning
```

### 5.1 Business setup

Capture and version:

- Company identity, website, industry, and description.
- Products, services, offers, and value propositions.
- Approved proof and claims.
- ICP, target markets, exclusions, and goals.
- Pricing authority and commercial constraints as client configuration, never platform constants.
- Communication policies, approval rules, sending identity, booking destination, and escalation path.

Unverified information remains explicitly unverified. Business facts, hypotheses, and proposals are different record types.

### 5.2 Prospect discovery

Create deduplicated prospect records from supported sources. Every record preserves its source, source reference, importing actor, business-profile version, and ICP version.

Initial supported input is the existing source-attributed record/CSV path. Additional discovery connectors are optional capabilities, not reasons to change the core record model.

### 5.3 Research

Attach evidence to the prospect. Evidence includes source, timestamp where available, confidence, verification status, and collector.

Research content is untrusted input. It may inform structured output but cannot change policies, permissions, or instructions.

### 5.4 Qualification and offer match

Produce an explainable result:

- Score and qualified/disqualified state.
- Matching and missing criteria.
- Exclusions and suppression concerns.
- Evidence used.
- Matched offer and justification.

A low-information result is held for review rather than presented as confident intelligence.

### 5.5 Personalization

Create a versioned draft grounded in approved business knowledge and prospect evidence. Human edits are preserved. Regeneration creates another version; it does not silently overwrite an approved draft.

Cold first-touch messages contain no booking or chat links. Booking links are introduced only after appropriate interest, using the client's verified destination.

### 5.6 Approval and controlled send

The send path remains deterministic and fail closed:

- Required approval exists.
- Tenant and actor are authorized.
- Recipient is not suppressed.
- Legal and physical-address requirements are satisfied.
- Sending route and identity are valid.
- Rate, deliverability, quarantine, and circuit-breaker checks pass.
- Transport mode is explicit.

`dry_run` remains the default until a deployment is deliberately activated. New tenants default to review-required behavior.

### 5.7 Conversation and handoff

A production inbound connector delivers real replies to the canonical webhook/workflow. Ingest is idempotent and threads replies to the original prospect and message where possible.

The system records intent, confidence, suppression, and required action. Ambiguous threading or sensitive/low-confidence intent goes to review.

An interested reply can be routed to:

- The assigned team owner.
- A verified Notion booking destination.
- A verified custom booking link.

A booking is real only after provider confirmation. A generated link is not a booked meeting.

### 5.8 Outcome and learning

Replies, human decisions, delivery events, meetings, and failures become operational history. Only approved outcomes and verified feedback may justify changes to business knowledge or workflows.

A result does not automatically rewrite targeting, messaging, navigation, or code.

## 6. First complete release boundary

### Included

- Versioned business profile, offers, ICP, exclusions, and policy configuration.
- Source-attributed prospect intake.
- Research evidence and verification states.
- Explainable qualification and offer matching.
- Versioned personalized drafts.
- Human approval, suppression, policy, deliverability, and controlled dispatch.
- Production inbound reply ingestion, threading, intent, and opt-out.
- Owner/booking-link handoff for interested replies.
- Overview, activity, failure recovery, and audit history.
- Dedicated client deployment, backup, export, and recovery procedures.
- Explicit empty, unavailable, pending, failed, and disabled states.

### Deferred until this loop is proven

- LinkedIn ghostwriting or automated account actions.
- Educational article and content-publishing operations.
- Micro-SaaS/free-tool generation.
- Visitor identification as a customer-facing capability.
- Chat and voice agents.
- Full calendar availability synchronization, reminders, and no-show recovery.
- Arbitrary visual workflow editing.
- CRM replacement.
- Shared production multi-tenancy.
- Autonomous UI rearrangement.

Deferred items may remain as audited prototypes, but must not appear operational.

## 7. Stable universal workspace

The workspace has seven stable sections. Existing stage routes may remain as nested views, record tabs, redirects, or aliases while the information architecture is consolidated incrementally.

| Section | User question | Primary data and actions |
|---|---|---|
| Overview | What needs my decision? | Attention queue, next actions, pipeline state, failures, approvals, replies, meaningful outcomes |
| Business Setup | What does the system know and use? | Versioned profile, offers, ICP, evidence, policies, readiness, approval of knowledge |
| Prospects & Research | Who is relevant and why? | Prospect records, sources, evidence, qualification, offer match, research actions |
| Outreach | What will be sent and what happened? | Draft versions, evidence links, review, approval, send state, delivery events, suppression |
| Conversations | Who replied and what happens next? | Threads, intent, confidence, owner assignment, booking handoff, human takeover |
| Activity | What did the system or a person do? | Runs, attempts, failures, approvals, configuration changes, audit history |
| Settings | How is this instance configured? | Modules, integrations, branding, users/access, entitlement, service and data controls |

Rules:

- OSINT is a research tool, not another top-level product.
- Stage contracts belong in a technical/settings view, not primary client navigation.
- A capability appears only when registered, available, and backed by real behavior.
- No fake metrics, mock opportunities, decorative agent streams, or empty sections.
- New capabilities use existing routes, record types, components, and empty/error/loading patterns.
- A new industry changes configuration and terminology, not application structure.
- Internal deployment and infrastructure controls are visible only in the operator context.

## 8. Customer and operator contexts

### Customer context

Customers see only their own:

- Business knowledge and configuration.
- Prospects, evidence, drafts, conversations, and outcomes.
- Enabled capabilities and service status.
- Relevant failures and required decisions.
- Export and access controls appropriate to their role.

### Operator context

Authorized Slidein operators additionally see:

- Deployment identity, release, lifecycle, and health.
- Connection health without secret values.
- Failed runs and required intervention.
- Client readiness and entitlement.
- Update, pause, recovery, export, and retirement actions.
- Service responsibilities and operational notes.

This is a separate permissioned context in the same codebase, not a second customer product. Client records, credentials, logs, and infrastructure details are never exposed to another client.

## 9. Controlled evolution

### Business knowledge evolution

Knowledge changes through client input, verified research, corrections, approvals, and outcomes. Every change preserves provenance, verification state, actor, and version.

### Workflow evolution

Agents may propose supported workflow/configuration changes with evidence. Changes are validated, reviewed according to risk, applied through trusted code, and reversible where appropriate.

### Product capability evolution

Engineering releases new registered modules, connectors, workflow templates, and components. Availability and activation are separate:

```text
registered -> available -> configuring -> awaiting_approval
           -> active <-> paused
           -> error
```

Only supported states with real behavior may be exposed.

### Application evolution

Source, schemas, APIs, and components change through reviewed engineering releases, migrations, tests, and rollback procedures. Production agents never modify or deploy their own code.

### Adaptive behavior at launch

- Recommend configuration and knowledge changes from evidence.
- Require approval for adaptations initially.
- Do not reorder navigation autonomously.
- Do not enable consequential capabilities from text mentions or clicks.
- Do not generate arbitrary executable modules.
- Do not equate adaptation with visual novelty.

## 10. Three service levels, one platform

No prices are part of this specification.

| Responsibility | Self-Hosted | Managed | Growth Partner |
|---|---|---|---|
| Product code | Same supported release | Same supported release | Same supported release |
| Infrastructure | Customer | Slidein-operated dedicated environment | Slidein-operated dedicated environment |
| Installation and upgrades | Customer, using documented path | Slidein | Slidein |
| Credentials and integrations | Customer configures | Slidein assists/operates within agreed scope | Slidein operates within agreed scope |
| Monitoring, backups, recovery | Customer | Slidein | Slidein |
| Business knowledge and configuration | Customer | Shared; client approves business decisions | Slidein prepares and maintains; client approves material decisions |
| Research and workflow maintenance | Customer | Defined managed scope | Agreed acquisition-program scope |
| Outreach operation | Customer | Defined managed scope | Agreed acquisition-program scope |
| Replies and sales decisions | Client | Client unless explicitly agreed | Defined responsibility; client retains material business decisions |
| Reporting | Product reports | Product plus managed reporting | Outcome/program reporting within agreed scope |
| Export and offboarding | Self-service/documented | Slidein-assisted, no artificial lock-in | Slidein-assisted, no artificial lock-in |

Entitlements and responsibilities are centralized and authorized server-side. A tier never changes the underlying domain model or creates a separate application.

Growth Partner may include content, LinkedIn, visitor, or meeting services only after those capabilities are real and explicitly included in scope.

## 11. Data ownership and retention

- Customer data and business knowledge remain exportable.
- Exports use documented, machine-readable formats and include configuration, prospects, evidence, drafts, messages, conversations, runs, and relevant audit history.
- Secret values are never included; exports contain safe connection references and reconnection instructions.
- Offboarding defines export confirmation, credential revocation, retention/deletion timing, backup expiry, and verification.
- Retention is valuable because it improves service, not because leaving is artificially difficult.

## 12. Vocabulary

Use one name per concept:

- **Workspace**: the customer-facing product context.
- **Client instance**: one isolated deployment for a client.
- **Tenant**: the technical ownership boundary inside an instance.
- **Business knowledge**: approved business facts, offers, ICP, proof, and policies.
- **Prospect**: the canonical person/opportunity record for the first workflow.
- **Evidence**: source-attributed information with verification state.
- **Draft**: a versioned communication awaiting approval or further work.
- **Run**: a recorded workflow execution.
- **Capability**: a registered product function.
- **Entitlement**: an authorized product/service scope.
- **Operator context**: internal deployment and service operations.

Avoid using opportunities, missions, leads, agents, projects, and campaigns as competing names for the same first-workflow records.

## 13. Definition of done

A feature is complete only when:

1. It supports an explicit user task in the canonical workflow.
2. It uses canonical records and typed API contracts.
3. Every read, write, job, and webhook enforces tenant and actor authorization.
4. State survives restart and upgrades through supported persistence and migrations.
5. Failure, retry, idempotency, approval, and audit behavior are defined.
6. Empty, loading, disabled, unavailable, and error states are honest.
7. It introduces no mock data presented as operational truth.
8. It reuses the existing design system and navigation.
9. Automated tests and a real acceptance path pass.
10. Documentation and capability status are updated in the same change.
