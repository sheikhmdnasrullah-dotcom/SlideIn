"""Tests for the pre-send deliverability preflight capability.

Transfers the verified operational practice from the live daemon
(MX preflight + spam-copy audit) into the canonical send path.
Tests are network-tolerant: MX resolution degrades to "unverified" offline.
"""
import shutil

import pytest

from slidein_api.services.preflight import (
    audit_copy,
    preflight_message,
    preflight_recipient,
    resolve_mx,
)

TENANT_A = "ten_alpha"

_HAS_DNS_TOOLS = shutil.which("host") or shutil.which("dig")


# -- copy audit (pure function, no network) --------------------------------

def test_audit_copy_passes_clean_message():
    audit = audit_copy("New approach for your team", "Hi there, great work.")
    assert audit["passed"] is True
    assert audit["flags"] == []


def test_audit_copy_detects_spam_phrases():
    audit = audit_copy("Act now", "Click here to buy now for 100% free")
    assert audit["passed"] is False
    assert any("spam phrase" in f for f in audit["flags"])


def test_audit_copy_detects_excessive_exclamation():
    audit = audit_copy("Subject", "Wow!!!! This is amazing!!!!!")
    assert audit["passed"] is False
    assert any("exclamation" in f.lower() for f in audit["flags"])


def test_audit_copy_allows_known_allcaps_acronyms():
    audit = audit_copy("SEO SaaS API", "Your CRM and PPM tools")
    assert audit["passed"] is True


def test_audit_copy_flags_too_many_allcaps():
    audit = audit_copy("BIG SALE NOW GET YOUR FREE STUFF", "HURRY ACT NOW")
    assert audit["passed"] is False
    assert any("all-caps" in f for f in audit["flags"])


# -- MX resolution ---------------------------------------------------------

def test_resolve_mx_empty_domain_is_not_verified():
    result = resolve_mx("")
    assert result.valid is False
    assert result.verified is False


def test_preflight_recipient_rejects_invalid_syntax():
    result = preflight_recipient("not-an-email")
    assert result.passed is False
    assert result.mx.valid is False
    assert "email syntax" in result.errors[0].lower()


@pytest.mark.skipif(not _HAS_DNS_TOOLS, reason="no host/dig available")
def test_preflight_recipient_resolves_real_domain():
    result = preflight_recipient("someone@iana.org")
    assert result.mx.domain == "iana.org"
    assert result.mx.verified is True


def test_preflight_message_records_copy_audit():
    result = preflight_message(
        "nobody@nonexistent.tld.invalid", "Act now", "Buy now for 100% free"
    )
    assert result.audit["passed"] is False
    assert result.passed is False


def test_preflight_dry_run_path_advisory_when_mx_unresolvable():
    """With an unresolvable domain the MX result is unverified; dry_run
    records this rather than blocking — verified at the service level below."""
    result = preflight_message("nobody@nonexistent.tld.invalid", "Hi", "Clean body.")
    assert result.audit["passed"] is True
    assert result.mx.verified is False


# -- API: draft preflight endpoint (read-only) -----------------------------

def test_preflight_endpoint_on_approved_draft(configured_workspace):
    from tests.test_journey import _prepared_draft

    client, draft, _pid = _prepared_draft(configured_workspace)
    headers = configured_workspace["headers"]

    resp = client.get(
        f"/v1/tenants/{TENANT_A}/drafts/{draft['id']}/preflight",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "preflight" in body
    assert "draft" in body
    p = body["preflight"]
    assert "passed" in p
    assert "mx" in p
    assert "audit" in p
    assert p["mx"]["domain"]


def test_dry_run_send_records_preflight_not_blocked(configured_workspace):
    """Dry-run transport must still dispatch even when MX fails or copy is
    borderline — no wire bytes, advisory preflight recorded in payload."""
    from tests.test_journey import _prepared_draft

    client, draft, _pid = _prepared_draft(configured_workspace)
    headers = configured_workspace["headers"]

    approved = client.post(
        f"/v1/tenants/{TENANT_A}/drafts/{draft['id']}/approve",
        json={"note": "ok"}, headers=headers,
    ).json()["draft"]
    assert approved["status"] == "approved"

    resp = client.post(
        f"/v1/tenants/{TENANT_A}/drafts/{draft['id']}/send",
        json={"sender_email": "hello@northwindcloud.example"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    sent = resp.json()["outputs"]["sent_message"]
    assert sent["transport"] == "dry_run"
    assert sent["delivery_status"] == "submitted"
    # preflight was recorded even in dry_run
    payload = sent.get("dispatch_payload", {})
    assert payload.get("preflight", {}).get("mx", {}).get("domain")


def test_spammy_copy_blocks_live_smtp_transport(configured_workspace, monkeypatch: pytest.MonkeyPatch):
    """A draft whose copy trips spam heuristics must NOT be dispatched over a
    live transport — fail closed. (dry_run is unaffected; it only records.)"""
    from tests.test_journey import _prepared_draft

    async def safe_recipient(email: str) -> dict:
        return {"collector": "reacher", "status": "safe", "verified": True}

    monkeypatch.setattr("slidein_api.services.outreach.reacher_verification", safe_recipient)
    client, draft, _pid = _prepared_draft(configured_workspace)
    headers = configured_workspace["headers"]

    # Edit the draft to introduce a high-risk phrase, then re-approve.
    client.post(
        f"/v1/tenants/{TENANT_A}/drafts/{draft['id']}/edit",
        json={"subject": "Act now!", "body": "Click here to buy now for 100% free"},
        headers=headers,
    )
    client.post(
        f"/v1/tenants/{TENANT_A}/drafts/{draft['id']}/approve",
        json={"note": "ok"}, headers=headers,
    )

    resp = client.post(
        f"/v1/tenants/{TENANT_A}/drafts/{draft['id']}/send",
        json={
            "sender_email": "hello@northwindcloud.example",
            "transport": {"transport": "smtp", "smtp_host": "127.0.0.1",
                        "smtp_port": 2587, "smtp_use_tls": True},
        },
        headers=headers,
    )
    assert resp.status_code == 400, resp.text
    error = resp.json()["error"]
    assert error["code"] == "transport_rejected"
    assert "preflight" in error["details"]

    # dry_run must still succeed on the same spammy draft (advisory only)
    dry = client.post(
        f"/v1/tenants/{TENANT_A}/drafts/{draft['id']}/send",
        json={"sender_email": "hello@northwindcloud.example"},
        headers=headers,
    )
    assert dry.status_code == 200, dry.text


def test_preflight_unknown_draft_returns_404(configured_workspace):
    client = configured_workspace["client"]
    headers = configured_workspace["headers"]
    resp = client.get(
        f"/v1/tenants/{TENANT_A}/drafts/draft_nonexistent/preflight",
        headers=headers,
    )
    # NotFoundError maps to 400 (code present in _STATUS_BY_CODE) — assert code
    assert resp.status_code in (400, 404)
    assert resp.json()["error"]["code"] == "draft_not_found"
