"""Permissions, workspace scoping and tenant isolation.

These tests prove that authorization state travels with the record and
that no section can read or mutate another workspace's data.
"""

from __future__ import annotations

import pytest

from .conftest import (
    ICP_PAYLOAD,
    OFFER_PAYLOAD,
    PROFILE_PAYLOAD,
    SAMPLE_CLAIMS,
    TENANT_A,
    TENANT_B,
    prospect_records,
)


def _prepared(client, headers, records=None):
    client.post(
        f"/v1/tenants/{TENANT_A}/profile", json=PROFILE_PAYLOAD, headers=headers
    )
    client.post(f"/v1/tenants/{TENANT_A}/offers", json=OFFER_PAYLOAD, headers=headers)
    client.post(f"/v1/tenants/{TENANT_A}/icps", json=ICP_PAYLOAD, headers=headers)
    discover = client.post(
        f"/v1/tenants/{TENANT_A}/discover",
        json={"records": records or prospect_records(1)},
        headers=headers,
    ).json()
    prospect_id = discover["outputs"]["prospect_ids"][0]
    client.post(
        f"/v1/tenants/{TENANT_A}/prospects/{prospect_id}/research",
        json={"connector": "supplied", "claims": SAMPLE_CLAIMS},
        headers=headers,
    )
    client.post(
        f"/v1/tenants/{TENANT_A}/prospects/{prospect_id}/qualify", headers=headers
    )
    return prospect_id


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

def test_requests_without_a_key_are_rejected(client):
    response = client.get(f"/v1/tenants/{TENANT_A}/prospects")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "not_authorized"
    assert response.json()["error"]["recovery_action"] == "request_authorization"


def test_an_invalid_key_is_rejected(client):
    response = client.get(
        f"/v1/tenants/{TENANT_A}/prospects",
        headers={"Authorization": "Bearer sk_not_a_real_key"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "not_authorized"


def test_public_paths_need_no_key(client):
    assert client.get("/health").status_code == 200
    contracts = client.get("/v1/contracts")
    assert contracts.status_code == 200


# ---------------------------------------------------------------------------
# Workspace scoping
# ---------------------------------------------------------------------------

def test_a_key_cannot_read_another_workspace(client, admin_headers, other_tenant_headers):
    _prepared(client, admin_headers)

    # Tenant A's own key sees its records.
    own = client.get(f"/v1/tenants/{TENANT_A}/prospects", headers=admin_headers)
    assert own.status_code == 200
    assert own.json()["total"] == 1

    # Tenant B's key, pointed at tenant A, gets 404 (never 403, so the API
    # does not confirm the other workspace exists).
    other = client.get(
        f"/v1/tenants/{TENANT_A}/prospects", headers=other_tenant_headers
    )
    assert other.status_code == 404
    assert other.json()["error"]["code"] == "tenant_forbidden"
    assert other.json()["error"]["recovery_action"] == "switch_workspace"

    # Tenant B's own workspace is genuinely empty.
    empty = client.get(f"/v1/tenants/{TENANT_B}/prospects", headers=other_tenant_headers)
    assert empty.status_code == 200
    assert empty.json()["total"] == 0

    # And tenant A's key cannot read tenant B.
    cross = client.get(f"/v1/tenants/{TENANT_B}/prospects", headers=admin_headers)
    assert cross.status_code == 404


def test_a_prospect_id_from_another_workspace_is_not_found(client, admin_headers, other_tenant_headers):
    prospect_id = _prepared(client, admin_headers)

    response = client.get(
        f"/v1/tenants/{TENANT_B}/prospects/{prospect_id}",
        headers=other_tenant_headers,
    )
    assert response.status_code == 404


def test_suppression_is_workspace_scoped(client, admin_headers, other_tenant_headers):
    _prepared(client, admin_headers)
    prospects = client.get(
        f"/v1/tenants/{TENANT_A}/prospects", headers=admin_headers
    ).json()["data"]
    email = prospects[0]["email"]

    client.post(
        f"/v1/tenants/{TENANT_A}/suppression",
        json={"email": email, "reason": "manual_admin"},
        headers=admin_headers,
    )
    own = client.get(
        f"/v1/tenants/{TENANT_A}/suppression", headers=admin_headers
    ).json()
    assert any(row["email"] == email for row in own["data"])
    # The other workspace sees only the global hygiene records.
    other = client.get(
        f"/v1/tenants/{TENANT_B}/suppression", headers=other_tenant_headers
    ).json()
    assert not any(row["email"] == email for row in other["data"])
    assert all(row["tenant_id"] is None for row in other["data"])


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------

def test_a_viewer_cannot_mutate_the_pipeline(client, viewer_headers, configured_workspace):
    headers = configured_workspace["headers"]
    _prepared(client, headers)
    prospect = client.get(
        f"/v1/tenants/{TENANT_A}/prospects", headers=headers
    ).json()["data"][0]

    response = client.post(
        f"/v1/tenants/{TENANT_A}/prospects/{prospect['id']}/research",
        json={"connector": "supplied", "claims": SAMPLE_CLAIMS},
        headers=viewer_headers,
    )
    assert response.status_code == 403
    error = response.json()["error"]
    assert error["code"] == "not_authorized"
    assert error["details"]["role"] == "viewer"
    assert error["recovery_action"] == "request_authorization"


def test_a_viewer_can_read_the_workflow(client, viewer_headers, configured_workspace):
    headers = configured_workspace["headers"]
    _prepared(client, headers)

    for path in (
        f"/v1/tenants/{TENANT_A}/overview",
        f"/v1/tenants/{TENANT_A}/activity",
        f"/v1/tenants/{TENANT_A}/runs",
        f"/v1/tenants/{TENANT_A}/overview/handoffs",
    ):
        response = client.get(path, headers=viewer_headers)
        assert response.status_code == 200, path


def test_an_operator_cannot_change_the_sending_policy(client, operator_headers, configured_workspace):
    response = client.put(
        f"/v1/tenants/{TENANT_A}/policy",
        json={"daily_limit": 9999},
        headers=operator_headers,
    )
    assert response.status_code == 403
    assert response.json()["error"]["details"]["required"] == "admin"


def test_an_admin_can_change_the_sending_policy(client, admin_headers):
    response = client.put(
        f"/v1/tenants/{TENANT_A}/policy",
        json={"daily_limit": 25},
        headers=admin_headers,
    )
    assert response.status_code == 200
    assert response.json()["policy"]["daily_limit"] == 25


def test_only_a_service_can_ingest_provider_events(
    client, operator_headers, service_headers, configured_workspace
):
    headers = configured_workspace["headers"]
    prospect_id = _prepared(client, headers)
    client.post(
        f"/v1/tenants/{TENANT_A}/prospects/{prospect_id}/personalize", headers=headers
    )
    draft = client.get(
        f"/v1/tenants/{TENANT_A}/drafts", headers=headers
    ).json()["data"][0]
    client.post(f"/v1/tenants/{TENANT_A}/drafts/{draft['id']}/approve", headers=headers)
    send = client.post(
        f"/v1/tenants/{TENANT_A}/drafts/{draft['id']}/send", headers=headers
    ).json()
    assert send["ok"] is True

    # An operator is not allowed to post provider events; that boundary is
    # reserved for the integration service.
    blocked = client.post(
        f"/v1/tenants/{TENANT_A}/events",
        json={
            "message_id": send["outputs"]["sent_message"]["message_id"],
            "recipient_email": "anyone@example.invalid",
            "event_type": "delivered",
        },
        headers=operator_headers,
    )
    assert blocked.status_code == 403
    assert blocked.json()["error"]["details"]["required"] == "service"

    # The service credential can.
    allowed = client.post(
        f"/v1/tenants/{TENANT_A}/events",
        json={
            "message_id": send["outputs"]["sent_message"]["message_id"],
            "recipient_email": send["outputs"]["sent_message"]["recipient_email"],
            "event_type": "delivered",
            "provider": "kumomta",
        },
        headers=service_headers,
    )
    assert allowed.status_code == 200
    assert allowed.json()["event"]["event_type"] == "delivered"
    updated = client.get(
        f"/v1/tenants/{TENANT_A}/sent", headers=operator_headers
    ).json()["counts"]
    assert updated["delivered"] == 1


def test_inbound_webhooks_are_service_only(client, admin_headers, service_headers):
    human = client.post(
        "/v1/webhooks/inbound",
        json={"sender_email": "nobody@example.invalid", "subject": "hi", "body": "hello"},
        headers=admin_headers,
    )
    assert human.status_code == 403
    assert human.json()["error"]["details"]["required"] == "service"

    response = client.post(
        "/v1/webhooks/inbound",
        json={"sender_email": "nobody@example.invalid", "subject": "hi", "body": "hello"},
        headers=service_headers,
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "prospect_not_found"


# ---------------------------------------------------------------------------
# Authorization state travels with the record
# ---------------------------------------------------------------------------

def test_authorization_state_is_recorded_on_the_sent_message(client, admin_headers, configured_workspace):
    headers = admin_headers
    prospect_id = _prepared(client, headers)
    client.post(
        f"/v1/tenants/{TENANT_A}/prospects/{prospect_id}/personalize", headers=headers
    )
    draft = client.get(
        f"/v1/tenants/{TENANT_A}/drafts", headers=headers
    ).json()["data"][0]
    client.post(
        f"/v1/tenants/{TENANT_A}/drafts/{draft['id']}/approve",
        json={"note": "approved after review"},
        headers=headers,
    )
    send = client.post(
        f"/v1/tenants/{TENANT_A}/drafts/{draft['id']}/send", headers=headers
    ).json()

    sent = send["outputs"]["sent_message"]
    detail = client.get(
        f"/v1/tenants/{TENANT_A}/prospects/{prospect_id}", headers=headers
    ).json()
    stored = next(row for row in detail["sent_messages"] if row["id"] == sent["id"])
    # The exact draft version that was authorized is the one that went out.
    assert stored["draft_version"] == draft["version"]
    assert stored["authorized_by"]
    assert stored["authorized_by"] == send["outputs"]["draft"]["approved_by"]
    # The draft still records who approved which version.
    assert detail["drafts"][0]["approved_by"] == stored["authorized_by"]
    assert detail["drafts"][0]["approval_note"] == "approved after review"


def test_suppression_survives_in_the_same_records(
    client, admin_headers, service_headers, configured_workspace
):
    headers = admin_headers
    prospect_id = _prepared(client, headers)
    client.post(
        f"/v1/tenants/{TENANT_A}/prospects/{prospect_id}/personalize", headers=headers
    )
    draft = client.get(
        f"/v1/tenants/{TENANT_A}/drafts", headers=headers
    ).json()["data"][0]
    email = client.get(
        f"/v1/tenants/{TENANT_A}/prospects/{prospect_id}", headers=headers
    ).json()["email"]

    client.post(
        "/v1/webhooks/inbound",
        json={"sender_email": email, "subject": "Re: hi", "body": "unsubscribe me"},
        headers=service_headers,
    )
    # A fresh draft on the opted-out prospect is refused at the research /
    # qualification guard, and any approved draft cannot be sent.
    client.post(
        f"/v1/tenants/{TENANT_A}/drafts/{draft['id']}/approve", headers=headers
    )
    blocked = client.post(
        f"/v1/tenants/{TENANT_A}/drafts/{draft['id']}/send", headers=headers
    )
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "suppressed"

    blocked_research = client.post(
        f"/v1/tenants/{TENANT_A}/prospects/{prospect_id}/research",
        json={"connector": "supplied", "claims": SAMPLE_CLAIMS},
        headers=headers,
    )
    assert blocked_research.status_code == 409
    assert blocked_research.json()["error"]["code"] == "suppressed"
