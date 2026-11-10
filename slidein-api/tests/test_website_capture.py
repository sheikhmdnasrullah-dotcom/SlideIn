"""Hermetic website connection → consent → identified Prospect journey."""

from __future__ import annotations

import asyncio

from slidein_api.db import session_scope
from slidein_api.models import WebsiteEvent
from sqlalchemy import select
from tests.conftest import TENANT_A, TENANT_B


def _connect(client, headers):
    response = client.post(
        f"/v1/tenants/{TENANT_A}/websites",
        json={"domain": "https://client.example", "provider": "native"}, headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["remote_deployment"] is False
    return response.json()["website"]


def _event(event_id, **overrides):
    return {
        "event_id": event_id, "session_id": "session-one", "event_type": "page_view",
        "page_url": "https://client.example/pricing", "consent": True, **overrides,
    }


def test_website_snippet_requires_markup_consent_and_has_no_fingerprinting(client, admin_headers):
    website = _connect(client, admin_headers)
    snippet = client.get(website["snippet_url"])
    assert snippet.status_code == 200
    assert "http://testserver/v1/public/website-events/" in snippet.text
    assert "data-slidein-consent" in snippet.text
    assert "canvas" not in snippet.text.lower()
    assert "fingerprint" not in snippet.text.lower()
    assert "trackPage: function (consent)" in snippet.text


def test_consented_form_creates_prospect_evidence_and_stitches_session(client, admin_headers):
    website = _connect(client, admin_headers)
    capture = website["capture_url"]

    denied = client.post(capture, json=_event("denied", consent=False))
    assert denied.status_code == 400
    assert denied.json()["error"]["code"] == "consent_required"

    anonymous = client.post(capture, json=_event("page-one"))
    assert anonymous.status_code == 200, anonymous.text
    assert anonymous.json()["prospect_id"] is None

    identified = client.post(capture, json=_event(
        "form-one", event_type="form_submit", email="Ada@Example.org", first_name="Ada",
    ))
    assert identified.status_code == 200, identified.text
    assert identified.json()["lead_created"] is True
    assert identified.json()["identity_source"] == "explicit_form"
    prospect_id = identified.json()["prospect_id"]

    duplicate = client.post(capture, json=_event(
        "form-one", event_type="form_submit", email="Ada@Example.org",
    ))
    assert duplicate.json()["duplicate"] is True
    assert duplicate.json()["lead_created"] is False

    prospects = client.get(
        f"/v1/tenants/{TENANT_A}/prospects", headers=admin_headers,
    ).json()["data"]
    assert len(prospects) == 1
    assert prospects[0]["email"] == "ada@example.org"
    assert prospects[0]["source"] == "website_form"

    evidence = client.get(
        f"/v1/tenants/{TENANT_A}/prospects/{prospect_id}/evidence", headers=admin_headers,
    ).json()["evidence"]
    assert evidence[0]["collector"] == "website_form"
    assert evidence[0]["verification_status"] == "verified"

    async def events():
        async with session_scope() as session:
            return list((await session.execute(select(WebsiteEvent))).scalars().all())

    rows = asyncio.run(events())
    assert len(rows) == 2
    assert all(row.prospect_id == prospect_id for row in rows)


def test_capture_never_invents_email_and_rejects_cross_domain(client, admin_headers):
    website = _connect(client, admin_headers)
    missing = client.post(website["capture_url"], json=_event("identify", event_type="identify"))
    assert missing.status_code == 400
    assert missing.json()["error"]["code"] == "email_required"
    wrong_origin = client.post(
        website["capture_url"], json=_event("wrong", page_url="https://attacker.example/form"),
    )
    assert wrong_origin.status_code == 400
    assert wrong_origin.json()["error"]["code"] == "website_origin_mismatch"
    prospects = client.get(f"/v1/tenants/{TENANT_A}/prospects", headers=admin_headers).json()
    assert prospects["total"] == 0


def test_website_connections_are_tenant_bound(client, admin_headers, other_tenant_headers):
    _connect(client, admin_headers)
    other = client.get(f"/v1/tenants/{TENANT_B}/websites", headers=other_tenant_headers)
    assert other.status_code == 200
    assert other.json()["count"] == 0
    forbidden = client.get(f"/v1/tenants/{TENANT_A}/websites", headers=other_tenant_headers)
    assert forbidden.status_code == 404
