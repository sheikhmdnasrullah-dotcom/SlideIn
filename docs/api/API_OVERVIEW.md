# API Overview — SlideIn

> Documents routes verified against the implementation 2026-10-12. The
> three surfaces below overlap historically; consolidation is deferred
> (see `TECHNICAL_DEBT.md`). Authenticate as documented per surface.

## Deliverability API — `deliverability/server.py` (:8088, `/v1/*`)

Workspace API key via `X-API-Key` or `Authorization: Bearer` header
(`?api_key=` also accepted on the browser UI). Missing/invalid → 401;
cross-workspace IDs → 404.

| Method | Route | Purpose |
|---|---|---|
| GET | `/health` | Public health + transport status |
| GET | `/v1/status` | Pipeline KPIs for the caller's workspace |
| GET | `/v1/workspaces` | Workspaces (key material redacted) |
| GET | `/v1/domains`, `/v1/senders`, `/v1/leads`, `/v1/conversations` | Scoped listings |
| GET | `/v1/conversations/<id>` | Thread view (workspace-scoped) |
| GET | `/v1/events/sends` | Send-event log |
| GET | `/v1/warmup/stats` | Warmup pool stats |
| POST | `/v1/leads/submit` | Lead ingest + speed-to-lead dispatch (suppression 403 / breaker 503) |
| POST | `/v1/inbound/webhook` | Inbound reply ingest (MIME/JSON), intent classify, optional AI reply |
| POST | `/v1/drafts/score` | Content score sandbox (no send) |
| POST | `/v1/conversations/<id>/reply` | In-thread reply dispatch (workspace-scoped) |

Key management: `python3 deliverability/cli.py show-key|rotate-key`.

## Go admin API — `/api/*` (:3333)

GoPhish-derived: campaigns, templates, groups/targets, sending profiles,
users, webhooks, IMAP. Session + per-user API keys + RBAC middleware. (See
GoPhish API conventions; SlideIn-specific hardening: `RestrictedDialer` on
the webhook client, ratelimit middleware.)

## Product API — `product/` (:8000, early stage)

FastAPI + Bearer [REDACTED] keys, `org_id` tenancy, 404 anti-oracle. Spec:
`product/API_SPEC.md`. Requires PostgreSQL; not part of the default local
stack.

## Inbound webhooks — `webhook_server.py` (:8080)

`POST /webhook/ses|sendgrid|postmark|mailgun|generic`. HMAC routes require
`WEBHOOK_SECRET` (503 fail-closed when unset); SES uses SNS TopicArn
allowlist (`SNS_TOPIC_ARNS`). SNS subscription fetch is allowlisted.
