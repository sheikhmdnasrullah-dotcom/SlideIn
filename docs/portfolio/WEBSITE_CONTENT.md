# Website Content — SlideIn project page

> Draft for a personal-website project entry. No secrets, customer data, or
> internal dashboards appear here or in any linked artifact.

## Short introduction

SlideIn is a self-hosted email infrastructure and deliverability platform:
authenticated sending through KumoMTA, pre-send safety gates, suppression
hygiene, and verifiable delivery telemetry — all runnable on one machine.

## Problem and solution

Owning email infrastructure means owning its unglamorous parts
(authentication, bounces, warmup, audit trails). SlideIn assembles them
into one test-covered stack where every send is eligibility-checked and
every outcome is traced by Message-ID.

## How it works

A Python engine gates each message (content analysis, placement risk,
suppression, circuit breaker) and dispatches through a provider
abstraction to KumoMTA, which DKIM-signs and routes. Locally, all mail
terminates in Mailpit; events feed back into suppression and breaker state.

## Feature status

Working and verified: local stack, e2e send path, API auth/tenancy,
suppression enforcement, webhook ingest, CLI ops. Early-stage: product
API, Next.js dashboard, AI research agents. Planned: managed hosting,
human-approval queue, production bring-up. Source of truth:
`../project/CURRENT_STATE.md`.

## Diagrams

Publish the ASCII deployment diagram from `../../README.md` and the
sequence diagram from `../architecture/DATA_FLOW.md` (both contain only
public architecture, no operational data).

## Repository

Repository: `https://github.com/sheikhmdnasrullah-dotcom/SlideIn`
(public since 2026-10-12).

## Timeline

- 2026-09: initial commits; Go backend, Python engine, KumoMTA lab assembled.
- 2026-10-12: repository audit; 8 safety fixes with 46 regression tests;
  deploy-script repair; local stack verified end-to-end; docs reorganization.
- Next: 0.1.0 release, dashboard consolidation, production rehearsal.

## Case-study outline

Motivation → requirements → architecture decisions → personal
contributions → security approach → verification evidence → limitations →
next experiments. Full text: `TECHNICAL_CASE_STUDY.md`.

## Limitations and next steps

Single-host alpha; production unexercised; no hosted offering. Next: fresh
VPS rehearsal, canonical dashboard, human-approval queue. Debt register:
`../project/TECHNICAL_DEBT.md`.
