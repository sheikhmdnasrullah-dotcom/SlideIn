"""The 14-day Warmbly mailbox-warmup rule (outreach-stage gate).

The rule under test: live (non dry-run) campaign sends stay closed until the
sending mailboxes have completed 14 days of Warmbly warmup on a domain whose
DNS (SPF/DKIM/DMARC) passes. The clock starts automatically when initial
setup saves the sending identity; Warmbly is the source of truth for warmup
progress and DNS auth, and an unreachable Warmbly blocks rather than guesses.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from tests.conftest import TENANT_A
from tests.test_journey import _prepared_draft

SENDER = "ops@northwindcloud.example"

SETUP_TRANSCRIPT = """
We are BrightPath Mortgage, a mortgage company based in Austin.
We offer first-time homebuyer loans and refinancing.
Our ideal clients are first-time buyers with steady income in the Austin area.
Our goal is to book 20 loan consultations per month.
Nothing sends without my approval.
"""


# -- helpers ---------------------------------------------------------------

def _save_policy(client, headers, senders=(SENDER,)) -> None:
    response = client.put(
        f"/v1/tenants/{TENANT_A}/policy",
        json={"allowed_senders": list(senders), "require_approval": True},
        headers=headers,
    )
    assert response.status_code == 200, response.text


def _iso_days_ago(days: int) -> str:
    moment = datetime.now(timezone.utc) - timedelta(days=days)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


class FakeWarmbly:
    """Warmbly adapter double: no network, explicit states."""

    def __init__(self, mailboxes=None, *, state: str = "ok") -> None:
        self._mailboxes = list(mailboxes or [])
        self._state = state

    @property
    def configured(self) -> bool:
        return True

    async def health(self) -> dict:
        return {"state": self._state, "reachable": self._state == "ok", "detail": ""}

    async def list_mailboxes(self, *, limit: int = 100) -> dict:
        if self._state != "ok":
            return {"state": self._state, "mailboxes": [], "detail": self._state}
        return {"state": "ok", "mailboxes": self._mailboxes,
                "pagination": {}, "detail": ""}

    async def warmup_start(self, mailbox_id: str) -> dict:
        for mailbox in self._mailboxes:
            if mailbox.get("id") == mailbox_id:
                return {"state": "ok",
                        "mailbox": {**mailbox, "warmup": _iso_days_ago(0)},
                        "detail": ""}
        return {"state": "http_error", "mailbox": None, "detail": "unknown mailbox"}

    async def auth_check(self, mailbox_id: str) -> dict:
        return {"state": "ok", "auth": {}, "detail": ""}


class FakeLiveTransport:
    name = "smtp"
    provider = "test.smtp"

    def dispatch(self, **kwargs):
        from slidein_api.services.transport import DispatchResult

        return DispatchResult(
            ok=True,
            message_id="<warmup-test@test>",
            provider=self.provider,
            detail="accepted by the fake live transport",
        )


async def _safe_reacher(email: str) -> dict:
    return {"collector": "reacher", "status": "safe", "verified": True}


async def _unsafe_reacher(email: str) -> dict:
    return {"collector": "reacher", "status": "invalid", "verified": True}


def _patch_live_send(monkeypatch, *, reacher=_safe_reacher) -> None:
    monkeypatch.setattr("slidein_api.services.outreach.reacher_verification", reacher)
    monkeypatch.setattr(
        "slidein_api.services.outreach.get_transport",
        lambda config=None: FakeLiveTransport(),
    )


def _warmed_mailbox(**overrides) -> dict:
    mailbox = {
        "id": "mb-1",
        "email": SENDER,
        "status": "active",
        "warmup": _iso_days_ago(15),
        "warmup_paused_at": None,
        "auth_state": "passing",
        "auth_failing_since": None,
    }
    mailbox.update(overrides)
    return mailbox


def _send_live(client, headers, draft):
    client.post(
        f"/v1/tenants/{TENANT_A}/drafts/{draft['id']}/approve", headers=headers
    )
    return client.post(
        f"/v1/tenants/{TENANT_A}/drafts/{draft['id']}/send",
        json={"sender_email": SENDER,
              "transport": {"transport": "smtp", "smtp_host": "127.0.0.1", "smtp_port": 1}},
        headers=headers,
    )


# -- setup hook ------------------------------------------------------------

@pytest.fixture()
def setup_client(tmp_path, monkeypatch):
    """The one-shot setup surface with its own workspace (mirrors
    tests/test_setup_flow.py: auth disabled, fresh database)."""
    monkeypatch.setenv("SLIDEIN_AUTH_MODE", "disabled")
    monkeypatch.setenv(
        "SLIDEIN_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/warmup_setup.db"
    )
    # In dev mode the tenant header only switches workspaces for tenants
    # listed in the key table, so ten_setup has to be one of them.
    monkeypatch.setenv(
        "SLIDEIN_API_KEYS",
        json.dumps({"ten_setup": {"key": "sk_setup_admin_0001", "role": "admin"}}),
    )
    from starlette.testclient import TestClient
    from slidein_api.api.app import app

    with TestClient(app) as client:
        client.headers.update({"X-Slidein-Tenant": "ten_setup"})
        yield client


def test_setup_answers_auto_start_the_warmup_clock(setup_client):
    created = setup_client.post(
        "/v1/setup/client",
        json={"materials": [{"source_ref": "call.txt", "text": SETUP_TRANSCRIPT}]},
    )
    assert created.status_code == 200, created.text

    answered = setup_client.post(
        "/v1/tenants/ten_setup/setup/answers",
        json={"answers": {
            "sender": SENDER,
            "physical_postal_address": "500 Congress Ave, Austin, TX",
            "lawful_basis": "b2b_legitimate_interest",
        }},
    )
    assert answered.status_code == 200, answered.text

    warmup = setup_client.get("/v1/tenants/ten_setup/warmup").json()["warmup"]
    assert warmup["status"] == "warming"
    assert warmup["days_required"] == 14
    assert warmup["started_at"] and warmup["due_at"]
    assert [m["email"] for m in warmup["mailboxes"]] == [SENDER]
    # No Warmbly in this deployment: the clock still runs, enforcement is off
    # and the status says so honestly instead of pretending.
    assert warmup["enforced"] is False
    assert warmup["ready"] is True
    assert warmup["warnings"][0]["code"] == "warmbly_not_configured"


# -- the gate --------------------------------------------------------------

def test_live_send_is_blocked_until_warmup_completes(configured_workspace, monkeypatch):
    client = configured_workspace["client"]
    headers = configured_workspace["headers"]
    _save_policy(client, headers)
    monkeypatch.setenv("SLIDEIN_WARMUP_ENFORCE", "required")

    started = client.post(
        f"/v1/tenants/{TENANT_A}/warmup/start", headers=headers
    ).json()["warmup"]
    assert started["enforced"] is True
    assert started["ready"] is False
    assert started["warmbly"]["state"] == "not_configured"
    assert started["blockers"][0]["code"] == "warmbly_not_configured"

    _, draft, _ = _prepared_draft(configured_workspace)
    client.post(
        f"/v1/tenants/{TENANT_A}/drafts/{draft['id']}/approve", headers=headers
    )
    send_url = f"/v1/tenants/{TENANT_A}/drafts/{draft['id']}/send"

    # Draft review shows the rule before dispatch is attempted.
    pre = client.get(
        f"/v1/tenants/{TENANT_A}/drafts/{draft['id']}/preflight", headers=headers
    ).json()
    assert pre["warmup"]["enforced"] is True
    assert pre["warmup"]["ready"] is False
    assert pre["warmup"]["blockers"]

    # Send preview (approved: false) reports the same gate.
    preview = client.post(
        send_url,
        json={"approved": False,
              "transport": {"transport": "smtp", "smtp_host": "127.0.0.1", "smtp_port": 1}},
        headers=headers,
    )
    assert preview.status_code == 409, preview.text
    assert preview.json()["error"]["code"] == "mailbox_warmup_incomplete"

    # The live send itself is refused with the warmup rule attached.
    blocked = client.post(
        send_url,
        json={"transport": {"transport": "smtp", "smtp_host": "127.0.0.1", "smtp_port": 1}},
        headers=headers,
    )
    assert blocked.status_code == 409, blocked.text
    error = blocked.json()["error"]
    assert error["code"] == "mailbox_warmup_incomplete"
    assert error["recovery_action"] == "configure_warmbly"
    assert error["details"]["warmup"]["enforced"] is True
    assert error["details"]["warmup"]["mailboxes"][0]["email"] == SENDER

    # Dry-run recording is not sending: the rule never touches it.
    retry = client.post(send_url, json={"sender_email": SENDER}, headers=headers).json()
    assert retry["status"] == "succeeded"
    assert retry["outputs"]["sent_message"]["transport"] == "dry_run"


def test_warmbly_unreachable_keeps_the_gate_closed(configured_workspace, monkeypatch):
    client = configured_workspace["client"]
    headers = configured_workspace["headers"]
    _save_policy(client, headers)
    monkeypatch.setenv("WARMBLY_URL", "http://127.0.0.1:9")  # configured, dead port

    started = client.post(
        f"/v1/tenants/{TENANT_A}/warmup/start", headers=headers
    ).json()["warmup"]
    assert started["enforced"] is True
    assert started["ready"] is False
    assert started["warmbly"]["state"] == "unreachable"
    assert any(b["code"] == "warmbly_unreachable" for b in started["blockers"])

    _, draft, _ = _prepared_draft(configured_workspace)
    blocked = _send_live(client, headers, draft)
    assert blocked.status_code == 409, blocked.text
    error = blocked.json()["error"]
    assert error["code"] == "mailbox_warmup_incomplete"
    assert error["details"]["warmup"]["warmbly"]["state"] == "unreachable"


def test_completed_warmup_opens_the_live_path(configured_workspace, monkeypatch):
    client = configured_workspace["client"]
    headers = configured_workspace["headers"]
    _save_policy(client, headers)
    monkeypatch.setenv("WARMBLY_URL", "https://warmbly.test")  # auto enforcement
    monkeypatch.setattr(
        "slidein_api.services.warmup.WarmblyAdapter",
        lambda: FakeWarmbly([_warmed_mailbox()]),
    )

    started = client.post(
        f"/v1/tenants/{TENANT_A}/warmup/start", headers=headers
    ).json()["warmup"]
    assert started["enforced"] is True
    assert started["ready"] is True
    assert started["status"] == "complete"
    assert started["blockers"] == []
    assert started["mailboxes"][0]["warmup_enabled"] is True
    assert started["mailboxes"][0]["auth_state"] == "passing"

    _patch_live_send(monkeypatch)
    _, draft, _ = _prepared_draft(configured_workspace)
    sent = _send_live(client, headers, draft)
    assert sent.status_code == 200, sent.text
    body = sent.json()
    assert body["status"] == "succeeded"
    assert body["outputs"]["sent_message"]["transport"] == "smtp"


def test_failing_dns_auth_blocks_the_live_path(configured_workspace, monkeypatch):
    client = configured_workspace["client"]
    headers = configured_workspace["headers"]
    _save_policy(client, headers)
    monkeypatch.setenv("WARMBLY_URL", "https://warmbly.test")
    monkeypatch.setattr(
        "slidein_api.services.warmup.WarmblyAdapter",
        lambda: FakeWarmbly([_warmed_mailbox(auth_state="failing")]),
    )

    started = client.post(
        f"/v1/tenants/{TENANT_A}/warmup/start", headers=headers
    ).json()["warmup"]
    assert started["ready"] is False
    dns = next(b for b in started["blockers"] if b["code"] == "dns_auth_failing")
    assert dns["recovery_action"] == "fix_dns_records"

    _patch_live_send(monkeypatch)
    _, draft, _ = _prepared_draft(configured_workspace)
    blocked = _send_live(client, headers, draft)
    assert blocked.status_code == 409, blocked.text
    assert blocked.json()["error"]["recovery_action"] == "fix_dns_records"


def test_enforcement_off_is_explicit_and_inert(configured_workspace, monkeypatch):
    client = configured_workspace["client"]
    headers = configured_workspace["headers"]
    _save_policy(client, headers)
    monkeypatch.setenv("WARMBLY_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("SLIDEIN_WARMUP_ENFORCE", "off")

    status = client.get(f"/v1/tenants/{TENANT_A}/warmup", headers=headers).json()["warmup"]
    assert status["enforced"] is False
    assert status["ready"] is True
    assert status["warnings"][0]["code"] == "warmup_enforcement_off"

    # Even with a (dead) Warmbly configured, "off" lets the send proceed to
    # the next real gate — here Reacher rejects the recipient.
    _patch_live_send(monkeypatch, reacher=_unsafe_reacher)
    _, draft, _ = _prepared_draft(configured_workspace)
    rejected = _send_live(client, headers, draft)
    assert rejected.status_code == 400, rejected.text
    assert rejected.json()["error"]["code"] == "transport_rejected"


# -- operator surface ------------------------------------------------------

def test_warmup_start_is_idempotent_and_role_gated(configured_workspace, viewer_headers):
    client = configured_workspace["client"]
    headers = configured_workspace["headers"]
    _save_policy(client, headers)

    first = client.post(
        f"/v1/tenants/{TENANT_A}/warmup/start", headers=headers
    ).json()["warmup"]
    second = client.post(
        f"/v1/tenants/{TENANT_A}/warmup/start", headers=headers
    ).json()["warmup"]
    assert first["started_at"] == second["started_at"]
    assert first["due_at"] == second["due_at"]

    # The deliverability dashboard carries the same warmup verdict.
    deliverability = client.get(
        f"/v1/tenants/{TENANT_A}/deliverability", headers=headers
    ).json()
    assert deliverability["warmup"]["started_at"] == first["started_at"]

    # Viewers cannot start or re-sync warmup.
    denied = client.post(f"/v1/tenants/{TENANT_A}/warmup/start", headers=viewer_headers)
    assert denied.status_code == 403
