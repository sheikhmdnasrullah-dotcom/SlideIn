"""Billing acceptance tests: purchases, ledger, reservations, capture/release.

Maps to acceptance cases 1, 2, 5, 6, 7, 8, 9, 10, 11, 12, 15.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time

from tests.conftest import KEY_A_ADMIN, TENANT_A, prospect_records

from slidein_api.billing.models import PriceBookEntry
from slidein_api.db import session_scope
from sqlalchemy import select

ADMIN = {"Authorization": f"Bearer {KEY_A_ADMIN}", "X-Slidein-Tenant": TENANT_A}


def _grant_credits(client, amount_cents: int, key: str | None = None) -> None:
    """Fund a workspace through the real purchase path (manual provider)."""
    payment = client.post(
        f"/v1/tenants/{TENANT_A}/billing/purchases",
        json={"amount_cents": amount_cents, "idempotency_key": key or f"test-buy-{time.time()}-{amount_cents}"},
        headers=ADMIN,
    ).json()["payment"]
    confirmed = client.post(
        f"/v1/tenants/{TENANT_A}/billing/purchases/{payment['id']}/confirm", headers=ADMIN
    )
    assert confirmed.status_code == 200, confirmed.text


def _balance(client) -> dict:
    return client.get(f"/v1/tenants/{TENANT_A}/billing/balance", headers=ADMIN).json()


# 1. A customer purchases credits and receives the correct balance.
def test_purchase_grants_correct_balance(client):
    _grant_credits(client, 5000)  # $50 -> 5000 credits
    balance = _balance(client)
    assert balance["available_credits"] == 5000
    assert balance["purchased_credits"] == 5000
    assert balance["used_credits"] == 0


# 2a. Repeated admin confirmation cannot grant twice.
def test_duplicate_confirmation_cannot_grant_twice(client):
    payment = client.post(
        f"/v1/tenants/{TENANT_A}/billing/purchases",
        json={"amount_cents": 2500, "idempotency_key": "test-dup-confirm-1"},
        headers=ADMIN,
    ).json()["payment"]
    for _ in range(3):
        response = client.post(
            f"/v1/tenants/{TENANT_A}/billing/purchases/{payment['id']}/confirm", headers=ADMIN
        )
        assert response.status_code == 200
    assert _balance(client)["available_credits"] == 2500


# 2b. Duplicated payment webhook cannot grant credits twice.
def test_stripe_webhook_replay_cannot_grant_twice(client, monkeypatch):
    secret = "whsec_test_secret_123"
    monkeypatch.setenv("SLIDEIN_STRIPE_WEBHOOK_SECRET", secret)

    payload = json.dumps(
        {
            "id": "evt_1",
            "type": "payment_intent.succeeded",
            "data": {"object": {"id": "pi_123", "amount_received": 4000}},
        }
    ).encode()
    timestamp = str(int(time.time()))
    signed = f"{timestamp}.".encode() + payload
    signature = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    headers = {
        "stripe-signature": f"t={timestamp},v1={signature}",
        "x-slidein-tenant": TENANT_A,
    }
    first = client.post("/v1/billing/webhooks/stripe", content=payload, headers=headers)
    assert first.status_code == 200, first.text
    replay = client.post("/v1/billing/webhooks/stripe", content=payload, headers=headers)
    assert replay.status_code == 200
    assert replay.json().get("duplicate") is True
    assert _balance(client)["available_credits"] == 4000


# 2c. A webhook with a bad signature is rejected and grants nothing.
def test_stripe_webhook_bad_signature_rejected(client, monkeypatch):
    monkeypatch.setenv("SLIDEIN_STRIPE_WEBHOOK_SECRET", "whsec_test_secret_123")
    payload = json.dumps(
        {"id": "evt_2", "type": "payment_intent.succeeded",
         "data": {"object": {"id": "pi_bad", "amount_received": 9000}}}
    ).encode()
    response = client.post(
        "/v1/billing/webhooks/stripe",
        content=payload,
        headers={"stripe-signature": "t=1,v1=forged"},
    )
    assert response.status_code in (400, 403)
    assert _balance(client)["available_credits"] == 0


# 5. A job without sufficient credits cannot begin expensive execution.
def test_job_without_credits_is_refused(client, configured_workspace):
    estimate = client.post(
        f"/v1/tenants/{TENANT_A}/operations/estimate",
        json={"product_id": "prospect.discovered", "units": 5},
        headers=ADMIN,
    ).json()["estimate"]
    assert estimate["available_credits"] == 0
    response = client.post(
        f"/v1/tenants/{TENANT_A}/operations",
        json={
            "product_id": "prospect.discovered",
            "units": 5,
            "params": {"records": prospect_records(5)},
        },
        headers={**ADMIN, "Idempotency-Key": "no-credits-1"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "insufficient_credits"


# 6+7. A funded job reserves before execution; the same idempotency key
# returns the original job without a second reservation or charge.
def test_operation_reserves_then_charges_metered_amount(client, configured_workspace):
    _grant_credits(client, 10_000)
    body = {
        "product_id": "prospect.discovered",
        "units": 3,
        "params": {"records": prospect_records(3)},
    }
    headers = {**ADMIN, "Idempotency-Key": "op-reserve-1"}
    first = client.post(f"/v1/tenants/{TENANT_A}/operations", json=body, headers=headers)
    assert first.status_code == 200, first.text
    job_id = first.json()["job"]["id"]
    detail = client.get(f"/v1/tenants/{TENANT_A}/jobs/{job_id}", headers=ADMIN)
    assert detail.status_code == 200
    result = detail.json()["job"]["result"]
    assert result["accepted_units"] == 3
    assert result["charge_credits"] == 15
    assert result["released_credits"] == 0
    assert _balance(client)["available_credits"] == 10_000 - 15

    # Repeat with the same idempotency key: same job, no extra charge.
    again = client.post(f"/v1/tenants/{TENANT_A}/operations", json=body, headers=headers)
    assert again.status_code == 200
    assert again.json()["job"]["id"] == job_id
    assert _balance(client)["available_credits"] == 10_000 - 15


# 9. A partial job returns accurate outputs and bills only accepted units.
def test_partial_job_bills_accepted_units_only(client, configured_workspace):
    _grant_credits(client, 10_000)
    records = prospect_records(2)
    records.append({"email": "not-an-email", "company_name": "Broken Row Co"})
    body = {
        "product_id": "prospect.discovered",
        "units": 3,
        "params": {"records": records},
    }
    response = client.post(
        f"/v1/tenants/{TENANT_A}/operations",
        json=body,
        headers={**ADMIN, "Idempotency-Key": "op-partial-1"},
    )
    assert response.status_code == 200, response.text
    job_id = response.json()["job"]["id"]
    detail = client.get(f"/v1/tenants/{TENANT_A}/jobs/{job_id}", headers=ADMIN).json()
    result = detail["job"]["result"]
    assert result["processed"] == 3
    assert result["accepted_units"] == 2
    assert result["failed_units"] == 1
    assert result["status"] == "partial"
    assert result["charge_credits"] == 10
    usage = detail["usage"]
    assert sum(row["units"] for row in usage) == 2
    assert all(row["cost_basis"] == "estimate" for row in usage)
    assert _balance(client)["available_credits"] == 10_000 - 10


# 8/11. Total failure releases the reservation (nothing billed).
def test_total_failure_releases_reservation(client, configured_workspace):
    _grant_credits(client, 10_000)
    body = {
        "product_id": "prospect.discovered",
        "units": 2,
        # Both records are invalid -> nothing accepted, nothing billed.
        "params": {"records": [
            {"email": "not-an-email", "company_name": "Broken 1"},
            {"email": "also-not-an-email", "company_name": "Broken 2"},
        ]},
    }
    response = client.post(
        f"/v1/tenants/{TENANT_A}/operations",
        json=body,
        headers={**ADMIN, "Idempotency-Key": "op-fail-1"},
    )
    assert response.status_code == 200, response.text
    job_id = response.json()["job"]["id"]
    detail = client.get(f"/v1/tenants/{TENANT_A}/jobs/{job_id}", headers=ADMIN).json()
    assert detail["job"]["result"]["accepted_units"] == 0
    assert detail["job"]["result"]["charge_credits"] == 0
    assert detail["reservation"]["state"] == "released"
    assert _balance(client)["available_credits"] == 10_000


# 10a. Preflight refuses a job larger than the per-job record budget.
def test_preflight_refuses_over_limit_job(client, configured_workspace):
    _grant_credits(client, 50_000)

    async def _tighten_budget() -> None:
        async with session_scope() as session:
            row = (
                await session.execute(
                    select(PriceBookEntry).where(
                        PriceBookEntry.product_id == "prospect.discovered"
                    )
                )
            ).scalar_one()
            row.usage_limits = {**row.usage_limits, "max_records": 2}

    asyncio.run(_tighten_budget())
    response = client.post(
        f"/v1/tenants/{TENANT_A}/operations/estimate",
        json={"product_id": "prospect.discovered", "units": 5},
        headers=ADMIN,
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "usage_limit_exceeded"


# 10b. At execution time the budget still hard-stops a crafted job.
def test_runtime_budget_stops_processing(client, configured_workspace):
    from slidein_api.billing.execution import execute_operation_job
    from slidein_api.billing.ledger import LedgerService
    from slidein_api.services.jobs import JobService

    _grant_credits(client, 50_000)

    async def _setup() -> dict:
        async with session_scope() as session:
            row = (
                await session.execute(
                    select(PriceBookEntry).where(
                        PriceBookEntry.product_id == "prospect.discovered"
                    )
                )
            ).scalar_one()
            row.usage_limits = {**row.usage_limits, "max_records": 2}
            job = await JobService(session).enqueue(
                tenant_id=TENANT_A,
                kind="operation",
                idempotency_key="runtime-budget-1",
                payload={
                    "product_id": "prospect.discovered",
                    "units": 5,
                    "params": {"records": prospect_records(5)},
                    "price_version": 1,
                },
            )
            await LedgerService(session).reserve(
                tenant_id=TENANT_A,
                job_id=job["id"],
                product_id="prospect.discovered",
                price_version=1,
                amount=25,
            )
            return job

    job = asyncio.run(_setup())
    result = asyncio.run(execute_operation_job(job))
    assert result["processed"] == 2
    assert any(f["error_code"] == "budget_exceeded" for f in result["failures"])
    assert result["charge_credits"] == 10  # only the 2 processed units
    assert result["released_credits"] == 15
    balance = _balance(client)
    assert balance["available_credits"] == 50_000 - 10


# 12. Final charges reconcile with the usage ledger.
def test_reconciliation_matches_charges(client, configured_workspace):
    _grant_credits(client, 10_000)
    body = {
        "product_id": "prospect.discovered",
        "units": 2,
        "params": {"records": prospect_records(2)},
    }
    response = client.post(
        f"/v1/tenants/{TENANT_A}/operations",
        json=body,
        headers={**ADMIN, "Idempotency-Key": "op-recon-1"},
    )
    job_id = response.json()["job"]["id"]
    detail = client.get(f"/v1/tenants/{TENANT_A}/jobs/{job_id}", headers=ADMIN).json()
    charged = detail["job"]["result"]["charge_credits"]

    reconcile = client.get(f"/v1/tenants/{TENANT_A}/billing/reconcile", headers=ADMIN).json()
    assert reconcile["consistent"] is True
    assert reconcile["used_credits"] == charged
    assert reconcile["available_credits"] == 10_000 - charged

    ledger = client.get(f"/v1/tenants/{TENANT_A}/billing/ledger", headers=ADMIN).json()["entries"]
    charges = [row for row in ledger if row["entry_type"] == "usage_charge"]
    assert sum(-row["amount"] for row in charges) == charged


# 15. Responses never expose provider credentials or key material.
def test_no_secrets_in_billing_responses(client, configured_workspace):
    _grant_credits(client, 1000)
    balance = client.get(f"/v1/tenants/{TENANT_A}/billing/balance", headers=ADMIN)
    catalog = client.get(f"/v1/tenants/{TENANT_A}/capabilities", headers=ADMIN)
    for response in (balance, catalog):
        text = response.text.lower()
        for forbidden in ("key_hash", "sk-", "password", "secret", "whsec", "kumo"):
            assert forbidden not in text
