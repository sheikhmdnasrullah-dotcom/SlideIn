"""Unified external API acceptance tests: keys, isolation, jobs, usage,
restricted packages.

Maps to acceptance cases 3, 4, 13, 14, 17, plus key lifecycle.
"""

from __future__ import annotations

import time

from tests.conftest import (
    KEY_A_ADMIN,
    KEY_A_OPERATOR,
    KEY_A_VIEWER,
    TENANT_A,
    TENANT_B,
    SAMPLE_CLAIMS,
    prospect_records,
)

ADMIN = {"Authorization": f"Bearer {KEY_A_ADMIN}", "X-Slidein-Tenant": TENANT_A}
OPERATOR = {"Authorization": f"Bearer {KEY_A_OPERATOR}", "X-Slidein-Tenant": TENANT_A}
VIEWER = {"Authorization": f"Bearer {KEY_A_VIEWER}", "X-Slidein-Tenant": TENANT_A}
TENANT_B_ADMIN = {"Authorization": "Bearer sk_beta_admin_0001", "X-Slidein-Tenant": TENANT_B}


def _fund(client, amount_cents: int) -> None:
    payment = client.post(
        f"/v1/tenants/{TENANT_A}/billing/purchases",
        json={"amount_cents": amount_cents, "idempotency_key": f"fund-{time.time()}"},
        headers=ADMIN,
    ).json()["payment"]
    client.post(
        f"/v1/tenants/{TENANT_A}/billing/purchases/{payment['id']}/confirm", headers=ADMIN
    )


def _ingest_prospects(client, configured_workspace, count: int = 2) -> list[str]:
    response = client.post(
        f"/v1/tenants/{TENANT_A}/operations",
        json={
            "product_id": "prospect.discovered",
            "units": count,
            "params": {"records": prospect_records(count)},
        },
        headers={**ADMIN, "Idempotency-Key": f"ingest-{count}-{time.time()}"},
    )
    assert response.status_code == 200, response.text
    job_id = response.json()["job"]["id"]
    result = client.get(f"/v1/tenants/{TENANT_A}/jobs/{job_id}", headers=ADMIN).json()
    return [row["reference_id"] for row in result["job"]["result"]["outputs"] if row["accepted"]]


# 3. A valid API key can access only its authorized workspace.
def test_key_cannot_access_other_workspace(client):
    response = client.get(
        f"/v1/tenants/{TENANT_B}/billing/balance",
        headers={"Authorization": f"Bearer {KEY_A_ADMIN}", "X-Slidein-Tenant": TENANT_B},
    )
    assert response.status_code == 404


# 4. An invalid or revoked key is rejected.
def test_invalid_key_rejected(client):
    response = client.get(
        f"/v1/tenants/{TENANT_A}/billing/balance",
        headers={"Authorization": "Bearer sk_nonsense", "X-Slidein-Tenant": TENANT_A},
    )
    assert response.status_code == 403


def test_revoked_key_rejected(client):
    created = client.post(
        f"/v1/tenants/{TENANT_A}/api-keys",
        json={"role": "viewer", "label": "temporary"},
        headers=ADMIN,
    )
    assert created.status_code == 200, created.text
    secret = created.json()["secret"]
    key_id = created.json()["api_key"]["id"]
    ok = client.get(
        f"/v1/tenants/{TENANT_A}/billing/balance",
        headers={"Authorization": f"Bearer {secret}", "X-Slidein-Tenant": TENANT_A},
    )
    assert ok.status_code == 200
    revoked = client.delete(f"/v1/tenants/{TENANT_A}/api-keys/{key_id}", headers=ADMIN)
    assert revoked.status_code == 200
    denied = client.get(
        f"/v1/tenants/{TENANT_A}/billing/balance",
        headers={"Authorization": f"Bearer {secret}", "X-Slidein-Tenant": TENANT_A},
    )
    assert denied.status_code == 403
    # Listing never shows secrets — only metadata.
    listing = client.get(f"/v1/tenants/{TENANT_A}/api-keys", headers=OPERATOR).json()
    assert all("secret" not in row and "key" not in row for row in listing["api_keys"])


# Key roles are honored: viewer cannot submit billable operations.
def test_key_role_limits_write_access(client, configured_workspace):
    _fund(client, 5000)
    response = client.post(
        f"/v1/tenants/{TENANT_A}/operations",
        json={"product_id": "prospect.discovered", "units": 1,
              "params": {"records": prospect_records(1)}},
        headers={**VIEWER, "Idempotency-Key": "viewer-submit-1"},
    )
    assert response.status_code == 403


# 13. A customer can see their usage and completed deliverables.
def test_customer_sees_usage_and_deliverables(client, configured_workspace):
    _fund(client, 20_000)
    prospect_ids = _ingest_prospects(client, configured_workspace, 2)
    assert len(prospect_ids) == 2

    research = client.post(
        f"/v1/tenants/{TENANT_A}/operations",
        json={
            "product_id": "prospect.research",
            "units": 2,
            "params": {
                "prospect_ids": prospect_ids,
                "connector": "supplied",
                "claims": SAMPLE_CLAIMS,
            },
        },
        headers={**OPERATOR, "Idempotency-Key": f"research-{time.time()}"},
    )
    assert research.status_code == 200, research.text
    job_id = research.json()["job"]["id"]
    detail = client.get(f"/v1/tenants/{TENANT_A}/jobs/{job_id}", headers=VIEWER).json()
    assert detail["job"]["result"]["accepted_units"] == 2
    assert detail["usage"][0]["product_id"] == "prospect.research"

    # The deliverable is the evidence itself, visible through the pipeline API.
    evidence = client.get(
        f"/v1/tenants/{TENANT_A}/prospects/{prospect_ids[0]}/evidence", headers=VIEWER
    )
    assert evidence.status_code == 200
    assert len(evidence.json()["evidence"]) > 0

    usage = client.get(f"/v1/tenants/{TENANT_A}/usage", headers=VIEWER).json()
    products = {row["product_id"] for row in usage["usage"]}
    assert "prospect.discovered" in products
    assert "prospect.research" in products


# 14. A customer cannot access another customer's records or balances.
def test_cross_tenant_isolation_of_jobs_and_balance(client, configured_workspace):
    _fund(client, 5000)
    prospect_ids = _ingest_prospects(client, configured_workspace, 1)
    jobs = client.get(f"/v1/tenants/{TENANT_A}/jobs", headers=ADMIN).json()["jobs"]
    assert jobs, "expected at least one job"
    job_id = jobs[0]["id"]

    # Tenant B's admin cannot read tenant A's job, usage, balance, or ledger.
    for path in (
        f"/v1/tenants/{TENANT_A}/jobs/{job_id}",
        f"/v1/tenants/{TENANT_A}/usage",
        "/v1/tenants/ten_alpha/billing/balance",
        "/v1/tenants/ten_alpha/billing/ledger",
    ):
        response = client.get(path, headers={
            "Authorization": "Bearer sk_beta_admin_0001",
            "X-Slidein-Tenant": TENANT_A,
        })
        assert response.status_code == 404, path
    # And cannot see tenant A's prospects.
    response = client.get(
        f"/v1/tenants/{TENANT_A}/prospects/{prospect_ids[0]}",
        headers={
            "Authorization": "Bearer sk_beta_admin_0001",
            "X-Slidein-Tenant": TENANT_A,
        },
    )
    assert response.status_code == 404


# 17. The 350-prospect package is visible but cannot be purchased publicly.
def test_restricted_package_not_publicly_purchasable(client, configured_workspace):
    catalog = client.get(f"/v1/tenants/{TENANT_A}/capabilities", headers=VIEWER).json()
    package = next(
        row for row in catalog["capabilities"] if row["product_id"] == "campaign.package.350"
    )
    assert package["status"] == "restricted"
    assert package["purchasable"] is False
    assert package["package_price_credits"] == 100_000
    assert package["cost_model_validated"] is False

    _fund(client, 200_000)
    response = client.post(
        f"/v1/tenants/{TENANT_A}/operations",
        json={
            "product_id": "campaign.package.350",
            "units": 350,
            "params": {"records": prospect_records(3)},
        },
        headers={**OPERATOR, "Idempotency-Key": "pkg-public-1"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "product_restricted"


# The package executes end-to-end only with explicit admin authorization,
# and bills per accepted qualified prospect at the package per-unit rate.
def test_restricted_package_executes_with_admin_authorization(client, configured_workspace):
    from tests.conftest import SAMPLE_CLAIMS

    _fund(client, 200_000)
    records = prospect_records(3)
    response = client.post(
        f"/v1/tenants/{TENANT_A}/operations",
        json={
            "product_id": "campaign.package.350",
            "units": 350,
            "allow_restricted": True,
            "params": {"records": records, "connector": "supplied", "claims": SAMPLE_CLAIMS},
        },
        headers={**ADMIN, "Idempotency-Key": "pkg-admin-1"},
    )
    assert response.status_code == 200, response.text
    job_id = response.json()["job"]["id"]
    detail = client.get(f"/v1/tenants/{TENANT_A}/jobs/{job_id}", headers=ADMIN).json()
    result = detail["job"]["result"]
    # All 3 synthetic prospects pass ingest -> research -> qualify -> draft.
    assert result["accepted_units"] == 3, result["failures"]
    per_unit = 100_000 // 350  # 285 credits per accepted prospect
    assert result["charge_credits"] == 3 * per_unit
    assert result["released_credits"] == 100_000 - 3 * per_unit
    balance = client.get(f"/v1/tenants/{TENANT_A}/billing/balance", headers=ADMIN).json()
    assert balance["available_credits"] == 200_000 - 3 * per_unit
    # Every pipeline stage is metered for margin reporting.
    metered = {row["product_id"] for row in detail["usage"]}
    assert {
        "prospect.discovered", "prospect.research",
        "prospect.qualified", "draft.generated",
    } <= metered


# Operators get consistent, honest cost previews.
def test_estimate_shows_price_and_provider_cost_basis(client, configured_workspace):
    estimate = client.post(
        f"/v1/tenants/{TENANT_A}/operations/estimate",
        json={"product_id": "draft.generated", "units": 10},
        headers=VIEWER,
    ).json()["estimate"]
    assert estimate["estimated_charge_credits"] == 300
    assert estimate["provider_cost_basis"] == "estimate"
    assert estimate["estimated_provider_cost_cents"] == 120  # 10 x 12c, internal only
    assert estimate["budgets"]["max_records"] == 1000
