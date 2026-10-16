"""Tenant branding + module registry: isolation, validation, enforcement.

Exercises the white-label configuration surface end to end through the API:
two tenants with different brands, cross-tenant 404s, role gates, payload
validation, and the server-side module check.
"""

from __future__ import annotations

import pytest

from .conftest import TENANT_A, TENANT_B
from slidein_api.errors import PermissionDenied
from slidein_api.services.modules import check_module_enabled


def _branding(tenant_id: str) -> str:
    return f"/v1/tenants/{tenant_id}/branding"


def _modules(tenant_id: str) -> str:
    return f"/v1/tenants/{tenant_id}/modules"


def test_branding_defaults_for_fresh_tenant(client, admin_headers):
    body = client.get(_branding(TENANT_A), headers=admin_headers).json()["branding"]
    assert body["business_name"] == ""
    assert body["colors"] == {
        "primary": "#1a56db",
        "surface": "#ffffff",
        "ink": "#111827",
    }
    assert body["domain_verified"] is False


def test_branding_update_persists_and_merges_colors(client, admin_headers):
    first = client.put(
        _branding(TENANT_A),
        json={
            "business_name": "Acme Mortgage",
            "logo_url": "https://acme.example/logo.png",
            "colors": {"primary": "#B00020"},
        },
        headers=admin_headers,
    )
    assert first.status_code == 200
    body = first.json()["branding"]
    assert body["business_name"] == "Acme Mortgage"
    assert body["colors"]["primary"] == "#b00020"
    assert body["colors"]["surface"] == "#ffffff"  # untouched default kept

    again = client.get(_branding(TENANT_A), headers=admin_headers).json()["branding"]
    assert again["business_name"] == "Acme Mortgage"


def test_two_tenants_have_independent_brands(
    client, admin_headers, other_tenant_headers
):
    client.put(
        _branding(TENANT_A),
        json={"business_name": "Tenant A Fitness"},
        headers=admin_headers,
    )
    client.put(
        _branding(TENANT_B),
        json={"business_name": "Tenant B Finance"},
        headers=other_tenant_headers,
    )
    a = client.get(_branding(TENANT_A), headers=admin_headers).json()["branding"]
    b = client.get(_branding(TENANT_B), headers=other_tenant_headers).json()["branding"]
    assert a["business_name"] == "Tenant A Fitness"
    assert b["business_name"] == "Tenant B Finance"


def test_cross_tenant_branding_is_404(client, other_tenant_headers):
    resp = client.get(_branding(TENANT_A), headers=other_tenant_headers)
    assert resp.status_code == 404


def test_viewer_and_service_cannot_update_branding(
    client, viewer_headers, service_headers
):
    for headers in (viewer_headers, service_headers):
        resp = client.put(
            _branding(TENANT_A), json={"business_name": "Nope"}, headers=headers
        )
        assert resp.status_code == 403


@pytest.mark.parametrize(
    "payload",
    [
        {"colors": {"primary": "red"}},  # not hex
        {"colors": {"primary": "#12345"}},  # wrong length
        {"colors": {"accent": "#112233"}},  # unknown token
        {"logo_url": "http://acme.example/logo.png"},  # not https
        {"logo_url": "javascript:alert(1)"},
        {"logo_url": "https://user:pass@acme.example/l.png"},  # credentials
        {"business_name": "x" * 121},
        {"motto": "unknown field rejected"},
        {"domain_verified": True},  # must come from verification flow
        {"custom_domain": "not a domain!!"},
    ],
)
def test_branding_validation_rejects_bad_payloads(client, admin_headers, payload):
    resp = client.put(_branding(TENANT_A), json=payload, headers=admin_headers)
    assert resp.status_code == 400


def test_custom_domain_is_stored_unverified(client, admin_headers):
    body = client.put(
        _branding(TENANT_A),
        json={"custom_domain": "Portal.Acme-Example.COM."},
        headers=admin_headers,
    ).json()["branding"]
    assert body["custom_domain"] == "portal.acme-example.com"
    assert body["domain_verified"] is False


def test_branding_update_records_activity(client, admin_headers):
    client.put(
        _branding(TENANT_A),
        json={"business_name": "Audit Me"},
        headers=admin_headers,
    )
    rows = client.get(
        f"/v1/tenants/{TENANT_A}/activity", headers=admin_headers
    ).json()["data"]
    assert any(row["action"] == "branding.updated" for row in rows)


def test_modules_default_to_full_registry(client, admin_headers):
    body = client.get(_modules(TENANT_A), headers=admin_headers).json()
    assert body["enabled"] == [entry["id"] for entry in body["registry"]]
    assert body["nav_order"] == body["enabled"]
    assert "settings" in body["enabled"]


def test_modules_update_narrows_enabled_set(client, admin_headers):
    body = client.put(
        _modules(TENANT_A),
        json={
            "enabled": ["overview", "discovery", "outreach", "settings"],
            "nav_order": ["discovery", "overview"],
        },
        headers=admin_headers,
    ).json()
    assert body["enabled"] == ["overview", "discovery", "outreach", "settings"]
    assert body["nav_order"] == ["discovery", "overview", "outreach", "settings"]


def test_modules_reject_unknown_ids_and_settings_lockout(client, admin_headers):
    resp = client.put(
        _modules(TENANT_A), json={"enabled": ["overview", "teleport"]},
        headers=admin_headers,
    )
    assert resp.status_code == 400
    resp = client.put(
        _modules(TENANT_A), json={"enabled": ["overview"]}, headers=admin_headers
    )
    assert resp.status_code == 400


def test_two_tenants_have_independent_modules(
    client, admin_headers, other_tenant_headers
):
    client.put(
        _modules(TENANT_A),
        json={"enabled": ["overview", "discovery", "settings"]},
        headers=admin_headers,
    )
    a = client.get(_modules(TENANT_A), headers=admin_headers).json()["enabled"]
    b = client.get(_modules(TENANT_B), headers=other_tenant_headers).json()["enabled"]
    assert a == ["overview", "discovery", "settings"]
    assert len(b) == 9  # tenant B untouched


def test_module_gate_blocks_disabled_module_server_side():
    stored = {"enabled": ["overview", "settings"]}
    check_module_enabled(stored, "overview")  # allowed
    with pytest.raises(PermissionDenied):
        check_module_enabled(stored, "outreach")  # hidden AND forbidden
