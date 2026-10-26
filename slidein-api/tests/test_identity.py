"""Identity, sessions and cross-interface behaviour.

These tests are the proof that Console and Dashboard are two views of one
system: a session minted by the login endpoint is accepted by every
existing endpoint, hits the same `require_role` ladder as an API key, is
bound to one workspace, and reads/writes the same records the other
interface uses.
"""

from __future__ import annotations

from slidein_api.db import session_scope
from slidein_api.identity import token_digest
from slidein_api.models import UserSession

from .conftest import TENANT_A, TENANT_B


# -- helpers -----------------------------------------------------------------

def _provision(client, headers, tenant_id: str, owner_email: str | None = None) -> dict:
    payload = {"tenant_id": tenant_id, "name": tenant_id}
    if owner_email:
        payload["owner"] = {"email": owner_email, "name": "Owner"}
    response = client.post("/v1/factory/tenants", json=payload, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _login(client, email: str, password: str) -> dict:
    return client.post(
        "/v1/auth/login", json={"email": email, "password": password}
    )


def _session_headers(token: str, tenant_id: str = TENANT_A) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "X-Slidein-Tenant": tenant_id}


async def _expire_session(token: str) -> None:
    from datetime import datetime, timedelta, timezone

    async with session_scope() as session:
        row = await session.get(UserSession, token_digest(token))
        row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)


# -- bootstrap ---------------------------------------------------------------

def test_bootstrap_creates_first_admin_and_closes_itself(client):
    first = client.post(
        "/v1/auth/bootstrap",
        json={"email": "founder@example.com", "password": "correct-horse", "name": "Founder"},
    )
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["role"] == "admin"
    assert body["interfaces"] == ["console", "dashboard"]
    assert body["token"].startswith("st_")

    second = client.post(
        "/v1/auth/bootstrap",
        json={"email": "attacker@example.com", "password": "sneaky"},
    )
    assert second.status_code == 400
    assert second.json()["error"]["code"] == "already_initialized"


# -- login -------------------------------------------------------------------

def test_login_round_trip_and_identity(client, admin_headers):
    body = _provision(client, admin_headers, TENANT_A, owner_email="owner@example.com")
    password = body["owner"]["password"]

    ok = _login(client, "owner@example.com", password)
    assert ok.status_code == 200, ok.text
    token = ok.json()["token"]

    who = client.get("/v1/auth/session", headers=_session_headers(token))
    assert who.status_code == 200, who.text
    payload = who.json()
    assert payload["email"] == "owner@example.com"
    assert payload["role"] == "admin"
    assert payload["tenant_id"] == TENANT_A
    assert payload["interfaces"] == ["console", "dashboard"]


def test_wrong_password_is_rejected_with_the_same_envelope(client, admin_headers):
    _provision(client, admin_headers, TENANT_A, owner_email="owner@example.com")

    bad = _login(client, "owner@example.com", "wrong-password")
    assert bad.status_code == 403
    error = bad.json()["error"]
    assert error["code"] == "not_authorized"
    assert error["recovery_action"] == "sign_in"


def test_session_endpoint_rejects_api_key_credentials(client, admin_headers):
    _provision(client, admin_headers, TENANT_A)
    response = client.get("/v1/auth/session", headers=admin_headers)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "session_invalid"


def test_expired_session_is_rejected(client, admin_headers):
    body = _provision(client, admin_headers, TENANT_A, owner_email="owner@example.com")
    token = _login(client, "owner@example.com", body["owner"]["password"]).json()["token"]

    import asyncio

    asyncio.run(_expire_session(token))

    response = client.get("/v1/auth/session", headers=_session_headers(token))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "session_invalid"


def test_logout_revokes_the_session(client, admin_headers):
    body = _provision(client, admin_headers, TENANT_A, owner_email="owner@example.com")
    token = _login(client, "owner@example.com", body["owner"]["password"]).json()["token"]
    assert client.get("/v1/auth/session", headers=_session_headers(token)).status_code == 200

    out = client.post("/v1/auth/logout", headers=_session_headers(token))
    assert out.status_code == 200

    after = client.get("/v1/auth/session", headers=_session_headers(token))
    assert after.status_code == 403
    assert after.json()["error"]["code"] == "session_invalid"


def test_session_cookie_is_accepted_like_a_bearer_token(client, admin_headers):
    """The BFF forwards the shared HttpOnly cookie verbatim."""
    body = _provision(client, admin_headers, TENANT_A, owner_email="owner@example.com")
    token = _login(client, "owner@example.com", body["owner"]["password"]).json()["token"]

    response = client.get(
        "/v1/auth/session", cookies={"slidein_session": token}
    )
    assert response.status_code == 200, response.text
    assert response.json()["email"] == "owner@example.com"


# -- roles and interfaces ----------------------------------------------------

def test_viewer_session_may_only_open_the_dashboard(client, admin_headers):
    _provision(client, admin_headers, TENANT_A)
    created = client.post(
        "/v1/auth/users",
        json={"email": "reader@example.com", "role": "viewer"},
        headers=admin_headers,
    )
    assert created.status_code == 200, created.text
    password = created.json()["password"]
    assert created.json()["interfaces"] == ["dashboard"]

    token = _login(client, "reader@example.com", password).json()["token"]
    who = client.get("/v1/auth/session", headers=_session_headers(token)).json()
    assert who["role"] == "viewer"
    assert who["interfaces"] == ["dashboard"]


def test_viewer_session_cannot_mutate_but_can_read(client, admin_headers):
    _provision(client, admin_headers, TENANT_A)
    created = client.post(
        "/v1/auth/users",
        json={"email": "reader@example.com", "role": "viewer", "password": "read-only-1"},
        headers=admin_headers,
    )
    assert created.status_code == 200, created.text
    token = _login(client, "reader@example.com", "read-only-1").json()["token"]
    headers = _session_headers(token)

    read = client.get(f"/v1/tenants/{TENANT_A}/prospects", headers=headers)
    assert read.status_code == 200, read.text

    write = client.post(
        f"/v1/tenants/{TENANT_A}/discover",
        json={"records": [{"first_name": "A", "last_name": "B",
                           "email": "ab@example.com", "company_name": "AB"}]},
        headers=headers,
    )
    assert write.status_code == 403
    assert write.json()["error"]["code"] == "not_authorized"


def test_operator_session_may_run_pipeline_actions(client, admin_headers, configured_workspace):
    _provision(client, admin_headers, TENANT_A)
    client.post(
        "/v1/auth/users",
        json={"email": "ops@example.com", "role": "operator", "password": "operator-1"},
        headers=admin_headers,
    )
    token = _login(client, "ops@example.com", "operator-1").json()["token"]
    headers = _session_headers(token)

    who = client.get("/v1/auth/session", headers=headers).json()
    assert who["interfaces"] == ["console", "dashboard"]

    write = client.post(
        f"/v1/tenants/{TENANT_A}/discover",
        json={"records": [{"first_name": "A", "last_name": "B",
                           "email": "ab@example.com", "company_name": "AB"}]},
        headers=headers,
    )
    assert write.status_code == 200, write.text


def test_session_is_bound_to_its_own_workspace(client, admin_headers, other_tenant_headers):
    body = _provision(client, admin_headers, TENANT_A, owner_email="owner@example.com")
    _provision(client, other_tenant_headers, TENANT_B)
    token = _login(client, "owner@example.com", body["owner"]["password"]).json()["token"]

    cross = client.get(
        f"/v1/tenants/{TENANT_B}/overview", headers=_session_headers(token, TENANT_B)
    )
    assert cross.status_code == 404
    assert cross.json()["error"]["code"] == "tenant_forbidden"

    own = client.get(
        f"/v1/tenants/{TENANT_A}/overview", headers=_session_headers(token)
    )
    assert own.status_code == 200, own.text


def test_cannot_create_users_without_admin_role(client, admin_headers):
    _provision(client, admin_headers, TENANT_A)
    client.post(
        "/v1/auth/users",
        json={"email": "ops@example.com", "role": "operator", "password": "operator-1"},
        headers=admin_headers,
    )
    token = _login(client, "ops@example.com", "operator-1").json()["token"]

    attempt = client.post(
        "/v1/auth/users",
        json={"email": "sneak@example.com", "role": "admin"},
        headers=_session_headers(token),
    )
    assert attempt.status_code == 403


def test_non_human_role_cannot_be_assigned(client, admin_headers):
    _provision(client, admin_headers, TENANT_A)
    response = client.post(
        "/v1/auth/users",
        json={"email": "bot@example.com", "role": "service"},
        headers=admin_headers,
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"


# -- shared state across the two interfaces ----------------------------------

def test_both_interfaces_see_the_same_record(client, admin_headers, configured_workspace):
    """A prospect created through the Console's API-key path is visible to
    a Dashboard viewer session — one authoritative row, two views."""
    _provision(client, admin_headers, TENANT_A)
    client.post(
        "/v1/auth/users",
        json={"email": "reader@example.com", "role": "viewer", "password": "read-only-1"},
        headers=admin_headers,
    )
    token = _login(client, "reader@example.com", "read-only-1").json()["token"]

    created = client.post(
        f"/v1/tenants/{TENANT_A}/discover",
        json={"records": [{"first_name": "Shared", "last_name": "Prospect",
                           "email": "shared@example.com", "company_name": "SharedCo"}]},
        headers=admin_headers,
    )
    assert created.status_code == 200, created.text

    console_view = client.get(
        f"/v1/tenants/{TENANT_A}/prospects", headers=admin_headers
    ).json()["data"]
    dashboard_view = client.get(
        f"/v1/tenants/{TENANT_A}/prospects", headers=_session_headers(token)
    ).json()["data"]

    assert len(console_view) == 1
    assert [row["email"] for row in console_view] == ["shared@example.com"]
    assert [row["email"] for row in dashboard_view] == ["shared@example.com"]
    assert console_view[0]["id"] == dashboard_view[0]["id"]


def test_session_approval_is_reflected_for_api_key_readers(
    client, admin_headers, configured_workspace
):
    """Approve a draft as an operator session, read it back with the
    Console's API key — same row, same status, no sync step."""
    from .conftest import SAMPLE_CLAIMS, prospect_records

    _provision(client, admin_headers, TENANT_A)
    client.post(
        "/v1/auth/users",
        json={"email": "approver@example.com", "role": "operator", "password": "approve-1"},
        headers=admin_headers,
    )
    token = _login(client, "approver@example.com", "approve-1").json()["token"]
    op_headers = _session_headers(token)

    discovered = client.post(
        f"/v1/tenants/{TENANT_A}/discover",
        json={"records": prospect_records(1)},
        headers=admin_headers,
    ).json()
    prospect_id = discovered["outputs"]["prospect_ids"][0]

    research = client.post(
        f"/v1/tenants/{TENANT_A}/prospects/{prospect_id}/research",
        json={"connector": "supplied", "claims": SAMPLE_CLAIMS},
        headers=admin_headers,
    )
    assert research.status_code == 200, research.text
    qualified = client.post(
        f"/v1/tenants/{TENANT_A}/prospects/{prospect_id}/qualify",
        headers=admin_headers,
    )
    assert qualified.status_code == 200, qualified.text
    personal = client.post(
        f"/v1/tenants/{TENANT_A}/prospects/{prospect_id}/personalize",
        headers=admin_headers,
    )
    assert personal.status_code == 200, personal.text

    drafts = client.get(f"/v1/tenants/{TENANT_A}/drafts", headers=admin_headers).json()
    draft_id = (drafts["data"] if isinstance(drafts, dict) else drafts)[0]["id"]

    approved = client.post(
        f"/v1/tenants/{TENANT_A}/drafts/{draft_id}/approve",
        json={"note": "looks good"},
        headers=op_headers,
    )
    assert approved.status_code == 200, approved.text

    listed = client.get(f"/v1/tenants/{TENANT_A}/drafts", headers=admin_headers).json()
    rows = listed["data"] if isinstance(listed, dict) else listed
    approved_row = next(row for row in rows if row["id"] == draft_id)
    assert approved_row["status"] == "approved"


# -- issued API keys ---------------------------------------------------------

def test_api_key_issued_at_provisioning_authenticates(client, admin_headers):
    provisioning = _provision(client, admin_headers, TENANT_A)
    raw_key = provisioning["api_key"]["key"]
    assert raw_key.startswith("sk_live_")

    response = client.get(
        f"/v1/tenants/{TENANT_A}/overview",
        headers={"Authorization": f"Bearer {raw_key}", "X-Slidein-Tenant": TENANT_A},
    )
    assert response.status_code == 200, response.text


def test_unknown_credential_is_rejected(client, admin_headers):
    _provision(client, admin_headers, TENANT_A)
    response = client.get(
        f"/v1/tenants/{TENANT_A}/overview",
        headers={"Authorization": "Bearer not-a-real-key"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "not_authorized"


# -- provisioning: one action prepares both interfaces -----------------------

def test_provisioning_creates_workspace_key_and_owner(client, admin_headers):
    body = _provision(client, admin_headers, TENANT_A, owner_email="client@example.com")
    assert body["api_key"]["key"]
    assert body["owner"]["password"]
    assert body["owner"]["user"]["email"] == "client@example.com"
    assert body["interfaces"] == ["console", "dashboard"]

    login = _login(client, "client@example.com", body["owner"]["password"])
    assert login.status_code == 200, login.text
    assert login.json()["interfaces"] == ["console", "dashboard"]


def test_setup_owner_endpoint_is_idempotent(client, admin_headers):
    _provision(client, admin_headers, TENANT_A)

    first = client.post(
        f"/v1/tenants/{TENANT_A}/setup/owner",
        json={"email": "client@example.com", "name": "Client Owner"},
        headers=admin_headers,
    )
    assert first.status_code == 200, first.text
    assert first.json()["created"] is True
    password = first.json()["password"]

    again = client.post(
        f"/v1/tenants/{TENANT_A}/setup/owner",
        json={"email": "someone-else@example.com"},
        headers=admin_headers,
    )
    assert again.status_code == 200
    assert again.json()["created"] is False
    assert again.json()["reason"] == "owner_exists"

    # The first owner's credentials still work and the new email never existed.
    assert _login(client, "client@example.com", password).status_code == 200
    assert _login(client, "someone-else@example.com", "whatever").status_code == 403


def test_setup_status_reports_owner_access_stage(client, admin_headers):
    _provision(client, admin_headers, TENANT_A)

    before = client.get(f"/v1/tenants/{TENANT_A}/setup", headers=admin_headers).json()
    assert "owner_ready" in before["states"]
    assert before["states"]["owner_ready"] is False
    assert any(b["kind"] == "owner_access" for b in before["blockers"])
    keys = [item["key"] for item in before["checklist"]]
    assert keys.index("owner_ready") < keys.index("ready_for_approval")

    client.post(
        f"/v1/tenants/{TENANT_A}/setup/owner",
        json={"email": "client@example.com"},
        headers=admin_headers,
    )

    after = client.get(f"/v1/tenants/{TENANT_A}/setup", headers=admin_headers).json()
    assert after["states"]["owner_ready"] is True
    assert not any(b["kind"] == "owner_access" for b in after["blockers"])
