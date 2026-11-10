# SlideIn: instructions for coding agents

## What this repo is

SlideIn is a self-hosted, evidence-backed, approval-gated outreach system.
It researches prospects, qualifies them against a saved business profile,
drafts personalized messages that cite only supported evidence, and sends
only what a human has approved. See `README.md` and
`docs/product/PRODUCT_CONSTITUTION.md` (binding).

## Read first

1. `PROJECT_POLICY.md`: the working rules, before touching any email functionality.
2. `docs/product/PRODUCT_CONSTITUTION.md`: the product principles.
3. `docs/project/CURRENT_STATE.md`: what is actually implemented.
4. `docs/README.md`: index of everything else.

## The workflow is fixed

`configure -> discover -> research -> qualify -> personalize -> outreach -> converse`

Do not add, rename, reorder or skip stages. Industry and client differences
belong in versioned configuration and knowledge, never in forks or a second
dashboard. Stage contracts live in `slidein-api/slidein_api/contracts.py`.

## Non-negotiables

- Nothing sends to a prospect without dashboard approval. Default to dry-run and fail closed.
- Never add header forgery, spam-filter evasion or inbox-placement tricks. Use SPF/DKIM/DMARC, warmup, verification and suppression.
- Every outbound message needs a lawful basis, an unsubscribe path and the sender's postal address.
- Never read, print, commit or export secrets, `.env` files or `.initial_admin_credentials`.
- Do not mark a feature operational unless its backend behavior is real. Use the status vocabulary in `docs/project/CURRENT_STATE.md`.
- Send and publish actions, and changes to live infrastructure, need explicit owner approval.

## Before you open a PR

Run the commands listed in `CONTRIBUTING.md`. Keep one concern per PR and
update `CHANGELOG.md` for user-visible changes.

## Live infrastructure

Hostnames, IPs and operational runbooks are deliberately not kept in this
file. See `docs/deployment/` and keep operational specifics out of the
public repository.
