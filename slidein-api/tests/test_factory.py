"""Deployment factory acceptance: two clients, one template, no forks.

Proves acceptance tests 1-10 end to end over HTTP. #11 (portal shows real
outcomes) is covered by asserting the portal's backing endpoints return
real rows; #12 is the full suite staying green.
"""

from __future__ import annotations

import pytest

from tests.conftest import (
    ICP_PAYLOAD,
    OFFER_PAYLOAD,
    PROFILE_PAYLOAD,
    TENANT_A,
    TENANT_B,
    prospect_records,
)

pytestmark = pytest.mark.usefixtures("_restore_key_store")

BLUEPRINT = {"blueprint_name": "prospect_to_conversation",
             "blueprint_version": "1.0.0"}

DENTAL_PROFILE = {
    "legal_name": "Harbor Dental Clinics",
    "website_url": "https://harbordental.example",
    "industry": "Dental Services",
    "company_description": "Multi-location dental clinics offering implants.",
    "core_value_prop": "Same-week implant consultations with transparent pricing.",
    "markets_served": ["Portland Metro"],
    "target_roles": ["Practice Manager", "Owner Dentist"],
    "brand_voice": "Warm, precise, reassuring.",
}

DENTAL_OFFER = {
    "name": "Implant Consultation Drive",
    "summary": "Fill unused implant consultation slots within 14 days.",
    "pain_points_solved": ["empty consultation slots", "no-show patients"],
    "target_persona": "Practice Manager",
    "proof_points": ["Filled 40 slots in 30 days for a 3-chair clinic"],
}

DENTAL_ICP = {
    "name": "Independent Dental Clinics",
    "industries": ["Dental Services"],
    "company_size_min": 5,
    "company_size_max": 60,
    "geographies": ["Portland Metro"],
    "target_roles": ["Practice Manager"],
    "required_signals": ["implants", "3+ chairs"],
    "exclusion_keywords": ["corporate chain"],
    "qualify_threshold": 70,
}

EXPLICIT_POLICY = {
    "allowed_senders": ["sam@harbordental.example"],
    "physical_postal_address": "12 Dock Lane, Portland, OR 97201",
    "lawful_basis": "B2B legitimate interest, verified practice list",
    "require_approval": True,
    "hourly_limit": 10,
    "daily_limit": 50,
}


def _deploy_config(**overrides):
    payload = {
        **BLUEPRINT,
        "sending": {"sender": "sam@harbordental.example",
                    "physical_postal_address": EXPLICIT_POLICY["physical_postal_address"],
                    "lawful_basis": EXPLICIT_POLICY["lawful_basis"],
                    "transport": "dry_run"},
        "limits": {"hourly_limit": 10, "daily_limit": 50},
        "approvals": {"require_approval": True, "approver": "sam",
                      "sla_hours": 24},
        "assignment_policy": "manual",
        "crm_provider": "",
        "modules": ["discovery", "outreach"],
    }
    payload.update(overrides)
    return payload


def _officers(count=12):
    return [{
        "display_name": f"Officer {i:02d}",
        "email": f"officer{i:02d}@harbordental.example",
        "crm_provider": "hubspot",
        "crm_owner_id": f"hub-{1000 + i}",
        "booking_provider": "cal",
        "booking_url": f"https://cal.example/harbor/officer-{i:02d}",
        "booking_verified": True,
    } for i in range(1, count + 1)]


def _provision(client, headers, tenant_id):
    response = client.post(
        "/v1/factory/tenants",
        json={"tenant_id": tenant_id, "name": tenant_id},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


def _prospect_id_by_email(client, tenant_id, headers, email):
    rows = client.get(
        f"/v1/tenants/{tenant_id}/prospects", headers=headers,
    ).json()["data"]
    return next(r["id"] for r in rows if r["email"] == email)


# -- 1+2+3. two clients, one template, isolated ---------------------------------

def test_two_clients_share_template_with_isolated_config(
    client, admin_headers, other_tenant_headers,
):
    _provision(client, admin_headers, TENANT_A)
    _provision(client, admin_headers, TENANT_B)

    # Client A: cloud infra (existing payloads).
    client.post(f"/v1/tenants/{TENANT_A}/profile",
                json={**PROFILE_PAYLOAD, "reason": "a"}, headers=admin_headers)
    client.post(f"/v1/tenants/{TENANT_A}/offers", json=OFFER_PAYLOAD,
                headers=admin_headers)
    client.post(f"/v1/tenants/{TENANT_A}/icps", json=ICP_PAYLOAD,
                headers=admin_headers)
    # Client B: dental clinics — different business, same template.
    response = client.post(
        f"/v1/tenants/{TENANT_B}/profile",
        json={**DENTAL_PROFILE, "reason": "b"}, headers=other_tenant_headers)
    assert response.status_code == 200, response.text
    client.post(f"/v1/tenants/{TENANT_B}/offers", json=DENTAL_OFFER,
                headers=other_tenant_headers)
    client.post(f"/v1/tenants/{TENANT_B}/icps", json=DENTAL_ICP,
                headers=other_tenant_headers)

    cfg_a = client.post(
        f"/v1/tenants/{TENANT_A}/factory/configs", json=_deploy_config(),
        headers=admin_headers).json()["config"]
    cfg_b = client.post(
        f"/v1/tenants/{TENANT_B}/factory/configs",
        json=_deploy_config(
            sending={"sender": "front@harbordental.example",
                     "physical_postal_address": "12 Dock Lane, Portland",
                     "lawful_basis": "B2B list", "transport": "dry_run"},
            limits={"hourly_limit": 5, "daily_limit": 20}),
        headers=other_tenant_headers).json()["config"]

    assert (cfg_a["blueprint_name"], cfg_a["blueprint_version"]) == (
        cfg_b["blueprint_name"], cfg_b["blueprint_version"])
    assert cfg_a["payload"]["limits"] != cfg_b["payload"]["limits"]

    # Isolation: B's key sees nothing of A (404, not 403, no existence leak).
    response = client.get(f"/v1/tenants/{TENANT_A}/factory/owners",
                          headers=other_tenant_headers)
    assert response.status_code == 404
    response = client.get(f"/v1/tenants/{TENANT_A}/factory/configs/active",
                          headers=other_tenant_headers)
    assert response.status_code == 404


def test_unknown_blueprint_rejected(configured_workspace):
    client = configured_workspace["client"]
    headers = configured_workspace["headers"]
    response = client.post(
        f"/v1/tenants/{TENANT_A}/factory/configs",
        json=_deploy_config(blueprint_name="nope", blueprint_version="9.9"),
        headers=headers,
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unknown_blueprint"


# -- 4. missing config blocks activation ----------------------------------------

def test_activation_blocked_with_named_stages_and_remediation(
    client, other_tenant_headers, admin_headers,
):
    _provision(client, admin_headers, TENANT_B)
    response = client.post(
        f"/v1/tenants/{TENANT_B}/factory/activation/activate",
        headers=other_tenant_headers,
    )
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "activation_blocked"
    assert "intake" in error["details"]["failed_stages"]

    report = client.get(f"/v1/tenants/{TENANT_B}/factory/validation",
                        headers=other_tenant_headers).json()
    assert report["ready"] is False
    assert len(report["stages"]) == 16
    for stage in report["stages"]:
        assert {"key", "status", "required", "remediation",
                "human_action"} <= set(stage)
    failed = next(s for s in report["stages"] if s["key"] == "intake")
    assert failed["status"] == "fail" and failed["remediation"]


# -- 5+6. owner import, assignment, deterministic booking ------------------------

def test_owner_import_assignment_and_booking_resolution(configured_workspace):
    client = configured_workspace["client"]
    headers = configured_workspace["headers"]

    records = _officers(12) + [{"display_name": "Bad Row",
                                "email": "not-an-email"}]
    imported = client.post(
        f"/v1/tenants/{TENANT_A}/factory/owners/import",
        json={"records": records}, headers=headers).json()
    assert imported["created"] == 12
    assert len(imported["errors"]) == 1
    assert imported["errors"][0]["index"] == 12

    owners = client.get(f"/v1/tenants/{TENANT_A}/factory/owners",
                        headers=headers).json()["data"]
    assert len(owners) == 12
    target = next(o for o in owners if o["email"] == "officer03@harbordental.example")

    email = prospect_records(1)[0]["email"]
    discover = client.post(
        f"/v1/tenants/{TENANT_A}/discover",
        json={"records": [{**prospect_records(1)[0],
                           "company_name": "Acme Dental"}]},
        headers=headers)
    assert discover.status_code == 200, discover.text
    prospect_id = _prospect_id_by_email(client, TENANT_A, headers, email)

    assigned = client.post(
        f"/v1/tenants/{TENANT_A}/factory/prospects/{prospect_id}/assign",
        json={"owner_id": target["id"], "source": "manual"},
        headers=headers).json()
    assert assigned["owner_id"] == target["id"]

    resolved = client.get(
        f"/v1/tenants/{TENANT_A}/factory/prospects/{prospect_id}/booking",
        headers=headers).json()
    assert resolved["owner_email"] == "officer03@harbordental.example"
    assert resolved["booking_url"] == "https://cal.example/harbor/officer-03"


# -- 7. missing/invalid destinations fail safe ----------------------------------

def test_booking_holds_never_substitute(configured_workspace):
    client = configured_workspace["client"]
    headers = configured_workspace["headers"]

    rec = prospect_records(1)[0]
    client.post(f"/v1/tenants/{TENANT_A}/discover",
                json={"records": [{**rec, "company_name": "Acme"}]},
                headers=headers)
    prospect_id = _prospect_id_by_email(client, TENANT_A, headers, rec["email"])

    # No owner assigned at all.
    response = client.get(
        f"/v1/tenants/{TENANT_A}/factory/prospects/{prospect_id}/booking",
        headers=headers)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "owner_unassigned"

    # Owner exists but booking unverified.
    owner = client.post(
        f"/v1/tenants/{TENANT_A}/factory/owners",
        json={"display_name": "New Hire", "email": "new@harbordental.example",
              "booking_provider": "cal",
              "booking_url": "https://cal.example/harbor/new"},
        headers=headers).json()["owner"]
    client.post(
        f"/v1/tenants/{TENANT_A}/factory/prospects/{prospect_id}/assign",
        json={"owner_id": owner["id"]}, headers=headers)
    response = client.get(
        f"/v1/tenants/{TENANT_A}/factory/prospects/{prospect_id}/booking",
        headers=headers)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "booking_unverified"

    # Invalid URLs are rejected at write time, never stored.
    bad = client.post(
        f"/v1/tenants/{TENANT_A}/factory/owners",
        json={"display_name": "Bad", "email": "bad@harbordental.example",
              "booking_url": "not a url"},
        headers=headers)
    assert bad.status_code == 400

    # Deactivating the owner holds dependent prospects (no silent failover).
    client.patch(
        f"/v1/tenants/{TENANT_A}/factory/owners/{owner['id']}",
        json={"is_active": False}, headers=headers)
    response = client.get(
        f"/v1/tenants/{TENANT_A}/factory/prospects/{prospect_id}/booking",
        headers=headers)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "owner_inactive"


# -- connections + maps ----------------------------------------------------------

def test_connections_store_refs_and_probe_safely(configured_workspace):
    client = configured_workspace["client"]
    headers = configured_workspace["headers"]

    registered = client.post(
        f"/v1/tenants/{TENANT_A}/factory/connections",
        json={"provider": "smtp", "label": "primary",
              "secret_ref": "SMTP_TEN_ALPHA_MISSING",
              "scopes": ["send"]},
        headers=headers).json()["connection"]
    assert registered["secret_ref"] == "SMTP_TEN_ALPHA_MISSING"
    assert "password" not in str(registered).lower()

    probed = client.post(
        f"/v1/tenants/{TENANT_A}/factory/connections/{registered['id']}/probe",
        headers=headers).json()["connection"]
    # No such secret in the test store: honest unknown, with remediation.
    assert probed["status"] in ("unknown", "failing")
    assert probed["last_error"]

    revoked = client.delete(
        f"/v1/tenants/{TENANT_A}/factory/connections/{registered['id']}",
        headers=headers).json()
    assert revoked["revoked"] is True


def test_crm_field_map_crud(configured_workspace):
    client = configured_workspace["client"]
    headers = configured_workspace["headers"]
    saved = client.post(
        f"/v1/tenants/{TENANT_A}/factory/crm-maps",
        json={"provider": "hubspot", "slidein_field": "owner_id",
              "external_field": "hubspot_owner_id"},
        headers=headers).json()["map"]
    assert saved["slidein_field"] == "owner_id"
    listed = client.get(f"/v1/tenants/{TENANT_A}/factory/crm-maps",
                        headers=headers).json()
    assert listed["total"] == 1
    deleted = client.delete(
        f"/v1/tenants/{TENANT_A}/factory/crm-maps/{saved['id']}",
        headers=headers).json()
    assert deleted["deleted"] is True


# -- 8+9. attribution, versions, rollback -----------------------------------------

def test_config_versions_and_rollback_are_auditable(configured_workspace):
    client = configured_workspace["client"]
    headers = configured_workspace["headers"]

    v1 = client.post(f"/v1/tenants/{TENANT_A}/factory/configs",
                     json=_deploy_config(), headers=headers).json()["config"]
    v2 = client.post(
        f"/v1/tenants/{TENANT_A}/factory/configs",
        json=_deploy_config(limits={"hourly_limit": 99, "daily_limit": 999},
                            note="raise limits"),
        headers=headers).json()["config"]
    assert (v1["version_no"], v2["version_no"]) == (1, 2)
    assert v2["is_active"] is True

    rolled = client.post(
        f"/v1/tenants/{TENANT_A}/factory/configs/rollback",
        json={"to_version": 1}, headers=headers).json()["config"]
    assert rolled["version_no"] == 3
    assert rolled["payload"]["limits"] == v1["payload"]["limits"]
    assert "rollback" in rolled["note"]

    versions = client.get(f"/v1/tenants/{TENANT_A}/factory/configs",
                          headers=headers).json()["data"]
    assert [v["version_no"] for v in versions] == [3, 2, 1]
    assert sum(v["is_active"] for v in versions) == 1


# -- safe test + activation happy path --------------------------------------------

def _complete_workspace(client, headers):
    client.put(f"/v1/tenants/{TENANT_A}/policy", json=EXPLICIT_POLICY,
               headers=headers)
    client.post(f"/v1/tenants/{TENANT_A}/factory/configs",
                json=_deploy_config(), headers=headers)
    imported = client.post(
        f"/v1/tenants/{TENANT_A}/factory/owners/import",
        json={"records": _officers(12)}, headers=headers).json()
    assert imported["created"] == 12


def test_synthetic_safe_test_runs_and_cleans_up(configured_workspace):
    client = configured_workspace["client"]
    headers = configured_workspace["headers"]
    _complete_workspace(client, headers)

    report = client.post(f"/v1/tenants/{TENANT_A}/factory/test",
                         json={"mode": "synthetic"}, headers=headers).json()
    assert report["passed"] is True, report["findings"]
    assert report["last_test"]["config_version"] == 1
    assert report["draft_id"]

    # Cleanup: synthetic prospect gone from lists, draft rejected.
    rows = client.get(f"/v1/tenants/{TENANT_A}/prospects",
                      headers=headers).json()["data"]
    assert not [r for r in rows if r["email"].startswith("factory-test-")]
    drafts = client.get(f"/v1/tenants/{TENANT_A}/drafts",
                        headers=headers).json()["data"]
    test_draft = next(d for d in drafts if d["id"] == report["draft_id"])
    assert test_draft["status"] == "rejected"


def test_full_activation_and_portal_backing_are_real(configured_workspace):
    client = configured_workspace["client"]
    headers = configured_workspace["headers"]
    _complete_workspace(client, headers)

    rec = prospect_records(1)[0]
    client.post(f"/v1/tenants/{TENANT_A}/discover",
                json={"records": [{**rec, "company_name": "Acme"}]},
                headers=headers)
    prospect_id = _prospect_id_by_email(client, TENANT_A, headers, rec["email"])
    owners = client.get(f"/v1/tenants/{TENANT_A}/factory/owners",
                        headers=headers).json()["data"]
    client.post(
        f"/v1/tenants/{TENANT_A}/factory/prospects/{prospect_id}/assign",
        json={"owner_id": owners[0]["id"]}, headers=headers)

    sampled = client.post(
        f"/v1/tenants/{TENANT_A}/factory/test",
        json={"mode": "sample", "prospect_id": prospect_id},
        headers=headers).json()
    assert sampled["passed"] is True, sampled["findings"]

    report = client.get(f"/v1/tenants/{TENANT_A}/factory/validation",
                        headers=headers).json()
    assert report["ready"] is True, [
        (s["key"], s["message"]) for s in report["stages"]
        if s["status"] != "pass"]

    activated = client.post(
        f"/v1/tenants/{TENANT_A}/factory/activation/activate",
        headers=headers).json()
    assert activated["status"] == "active"
    assert "prospect_to_conversation@1.0.0" in activated["blueprint"]

    # Portal backing (#11): overview reflects the real pipeline rows.
    overview = client.get(f"/v1/tenants/{TENANT_A}/overview",
                          headers=headers).json()
    assert overview["total_prospects"] >= 1

    # Offboard path: deactivate with reason, state is visible.
    deactivated = client.post(
        f"/v1/tenants/{TENANT_A}/factory/activation/deactivate",
        json={"reason": "pilot ended"}, headers=headers).json()
    assert deactivated["status"] == "inactive"
    report = client.get(f"/v1/tenants/{TENANT_A}/factory/validation",
                        headers=headers).json()
    assert report["ready"] is False
