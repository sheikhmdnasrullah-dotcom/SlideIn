"""Workspace templates: catalog, additive apply, tenant-wins resolution.

Applying a template only moves the tenant's template pointer; reads merge
template defaults under tenant settings, so tenant customizations and data
can never be lost or silently overwritten.
"""

from __future__ import annotations

from .conftest import TENANT_A, TENANT_B


def test_template_catalog_lists_starters(client, admin_headers):
    body = client.get("/v1/templates", headers=admin_headers).json()["templates"]
    ids = {entry["id"] for entry in body}
    assert {"mortgage-starter-v1", "fitness-starter-v1"} <= ids
    assert all(entry["version"] >= 1 for entry in body)


def test_template_detail_and_unknown_is_404(client, admin_headers):
    doc = client.get("/v1/templates/mortgage-starter-v1", headers=admin_headers).json()["template"]
    assert doc["terminology"]["nouns"]["prospect"] == "borrower"
    assert "settings" in doc["modules"]["enabled"]
    assert client.get("/v1/templates/nope", headers=admin_headers).status_code == 404


def test_fresh_tenant_has_no_template(client, admin_headers):
    body = client.get(f"/v1/tenants/{TENANT_A}/template", headers=admin_headers).json()
    assert body["template"] is None
    assert body["modules"]["source"] == "default"
    assert len(body["modules"]["enabled"]) == 9


def test_apply_points_tenant_without_touching_settings(client, admin_headers):
    # Tenant customizes branding first: apply must preserve it.
    client.put(
        f"/v1/tenants/{TENANT_A}/branding",
        json={"business_name": "Mine, untouched"},
        headers=admin_headers,
    )
    applied = client.post(
        f"/v1/tenants/{TENANT_A}/template",
        json={"template_id": "mortgage-starter-v1"},
        headers=admin_headers,
    )
    assert applied.status_code == 200
    body = applied.json()
    assert body["template"]["id"] == "mortgage-starter-v1"
    assert body["template"]["version"] == 1
    assert body["modules"]["source"] == "template"
    assert body["terminology"]["nouns"]["prospect"] == "borrower"

    branding = client.get(
        f"/v1/tenants/{TENANT_A}/branding", headers=admin_headers
    ).json()["branding"]
    assert branding["business_name"] == "Mine, untouched"

    versions = client.get(
        f"/v1/tenants/{TENANT_A}/config-versions?entity_type=workspace_template",
        headers=admin_headers,
    ).json()["config_versions"]
    assert len(versions) == 1
    assert versions[0]["entity_id"] == "mortgage-starter-v1"

    rows = client.get(
        f"/v1/tenants/{TENANT_A}/activity", headers=admin_headers
    ).json()["data"]
    assert any(row["action"] == "template.applied" for row in rows)


def test_tenant_modules_win_over_template(client, admin_headers):
    client.post(
        f"/v1/tenants/{TENANT_A}/template",
        json={"template_id": "mortgage-starter-v1"},
        headers=admin_headers,
    )
    client.put(
        f"/v1/tenants/{TENANT_A}/modules",
        json={"enabled": ["overview", "settings"]},
        headers=admin_headers,
    )
    body = client.get(f"/v1/tenants/{TENANT_A}/template", headers=admin_headers).json()
    assert body["modules"]["source"] == "tenant"
    assert body["modules"]["enabled"] == ["overview", "settings"]
    # Gate honors the tenant override, not the template default.
    assert client.get(
        f"/v1/tenants/{TENANT_A}/overview", headers=admin_headers
    ).status_code == 200
    assert client.get(
        f"/v1/tenants/{TENANT_A}/prospects", headers=admin_headers
    ).status_code == 403


def test_terminology_overrides_merge_per_key(client, admin_headers):
    client.post(
        f"/v1/tenants/{TENANT_A}/template",
        json={
            "template_id": "mortgage-starter-v1",
            "terminology": {"nouns": {"prospect": "applicant"}},
        },
        headers=admin_headers,
    )
    body = client.get(f"/v1/tenants/{TENANT_A}/template", headers=admin_headers).json()
    assert body["terminology"]["nouns"]["prospect"] == "applicant"  # tenant wins
    assert body["terminology"]["nouns"]["prospects"] == "borrowers"  # template fills
    assert body["terminology"]["sections"]["discovery"] == "Borrowers"


def test_two_tenants_apply_independently(client, admin_headers, other_tenant_headers):
    client.post(
        f"/v1/tenants/{TENANT_A}/template",
        json={"template_id": "mortgage-starter-v1"},
        headers=admin_headers,
    )
    client.post(
        f"/v1/tenants/{TENANT_B}/template",
        json={"template_id": "fitness-starter-v1"},
        headers=other_tenant_headers,
    )
    a = client.get(f"/v1/tenants/{TENANT_A}/template", headers=admin_headers).json()
    b = client.get(f"/v1/tenants/{TENANT_B}/template", headers=other_tenant_headers).json()
    assert a["terminology"]["nouns"]["prospect"] == "borrower"
    assert b["terminology"]["nouns"]["prospect"] == "client"


def test_apply_rejects_unknown_missing_and_forbidden(
    client, admin_headers, viewer_headers
):
    assert client.post(
        f"/v1/tenants/{TENANT_A}/template",
        json={"template_id": "nope"},
        headers=admin_headers,
    ).status_code == 404
    assert client.post(
        f"/v1/tenants/{TENANT_A}/template", json={}, headers=admin_headers
    ).status_code == 400
    assert client.post(
        f"/v1/tenants/{TENANT_A}/template",
        json={"template_id": "mortgage-starter-v1", "terminology": {"nouns": "x"}},
        headers=admin_headers,
    ).status_code == 400
    assert client.post(
        f"/v1/tenants/{TENANT_A}/template",
        json={"template_id": "mortgage-starter-v1"},
        headers=viewer_headers,
    ).status_code == 403
