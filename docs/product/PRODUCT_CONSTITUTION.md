# Slidein Product Constitution

- Status: Active and binding
- Version: 2.0.0
- Date: 2026-10-26
- Owner: Nasrullah Tanim
- Canonical product detail: `PRODUCT_SPECIFICATION.md`

## 1. North star

Slidein helps a business find the right people, understand them with evidence, reach out with permission and control, and turn replies into well-handled conversations.

> Find the right people. Understand their business. Reach out personally. Start more conversations.

The long-term platform is a universal configurable business workspace. The first complete workflow is prospect-to-conversation.

## 2. Inviolable principles

### 2.1 One workflow before many features

A complete, reliable business outcome is more valuable than another page, agent, integration, or dashboard. Do not expand the visible product faster than the canonical workflow can support it.

### 2.2 One product, not client forks

Industry and client differences belong in versioned knowledge, configuration, registered capabilities, integrations, permissions, and service entitlements. They do not justify separate frontends or divergent domain models.

### 2.3 The workspace is not the product

The product is the business knowledge, workflow, execution, controls, and outcomes. The workspace is one stable window into them. Never start a feature by redesigning the dashboard.

### 2.4 Evidence over invented intelligence

Business claims, qualification reasons, and personalization hooks must be traceable to approved knowledge or attributed evidence. Verified facts, inferences, unverified claims, and proposals remain distinct.

### 2.5 Human control over consequential action

New instances default to review-required operation and dry-run transport. External communication and irreversible actions require explicit policy, permission, and audit controls.

### 2.6 Reliable execution over prompt chains

Workflow stages have typed inputs and outputs, durable state, idempotency, explicit retry behavior, failure recovery, and audit history. Long-running work must survive process restarts.

### 2.7 Isolation at every boundary

Tenant and actor context applies to UI routes, API calls, background jobs, event streams, exports, integrations, and data deletion. Application-level tenancy is not a substitute for dedicated-environment isolation and operational discipline.

### 2.8 Persistence and controlled upgrades

Business data, configuration, approvals, workflow state, and audit history survive restarts and upgrades. Production schemas change through migrations, not implicit table creation alone.

### 2.9 Honest capability states

A feature is shown as operational only when its backend behavior is real. Prototypes are labeled, mock data never appears as client truth, and disabled or unavailable capabilities remain explicit.

### 2.10 No autonomous product mutation

Agents may propose knowledge, workflow, or configuration changes. They may not autonomously rearrange the product, create arbitrary executable modules, alter source code, or deploy releases.

### 2.11 Deliverability and consent over volume

Suppression, sender health, lawful configuration, authentication, rate limits, and provider requirements override throughput. Slidein does not evade anti-spam systems or misrepresent acceptance as inbox placement.

### 2.12 No artificial lock-in

Clients can export their business knowledge and operational data under a documented policy. Retention comes from continued service quality and results.

## 3. Canonical implementation

- Customer workspace: `slidein-app/`.
- Customer workflow API and domain: `slidein-api/`.
- Sending and deliverability infrastructure: existing audited adapters and services behind the canonical API.
- Adaptive ideas from `product/core/`: absorb selectively behind the canonical domain; do not create a third product model.
- `workspace-app/`: internal/legacy tooling, not the customer workspace.
- `osint_core/`, `visitor_core/`, and `unified/`: prototypes/engines that require tenant-safe adapters before customer exposure.

## 4. Stable client navigation

Overview · Business Setup · Prospects & Research · Outreach · Conversations · Activity · Settings

A new capability must fit this model or provide a demonstrated reason to amend the product specification. It must not introduce a parallel dashboard.

## 5. Engineering stop conditions

Stop and escalate rather than proceeding when a task would require:

- Creating another customer acquisition data model.
- Adding a new frontend to solve a domain or workflow problem.
- Displaying an unimplemented capability as active.
- Bypassing approval, suppression, tenancy, or transport safety.
- Autonomous live sending from a new or unready instance.
- Introducing a major framework without a demonstrated gap in existing code.
- Changing licensing terms without an explicit owner decision.
- Performing live sends, modifying production, or exposing client data without explicit authorization.

## 6. Definition of done

A change is complete only when its user task, domain behavior, persistence, permissions, failure handling, audit history, honest UI states, tests, and documentation are all updated together.

Visual polish never substitutes for a working business loop.
