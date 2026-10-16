"""Unit tests for Deliverability Guard, shared IP isolation, and cold-email statutory compliance."""

import asyncio
import os
from datetime import timedelta

import pytest

from slidein_api.services.deliverability_guard import (
    DeliverabilityGuard,
    DeliverabilityQuarantineError,
    MissingPhysicalAddressError,
    LawfulBasisMissingError,
    MAX_ALLOWED_BOUNCE_RATE,
    MAX_ALLOWED_COMPLAINT_RATE,
)
from tests.conftest import TENANT_A, TENANT_B


# ---------------------------------------------------------------------------
# Integration: rolling-window breaker, quarantine, and abuse review
# ---------------------------------------------------------------------------


def _seed_outcomes(tenant_id: str, outcomes: list[tuple[str, int]]) -> str:
    """Seed SentMessage + DeliveryEvent rows with staggered timestamps so the
    rolling-window ordering is deterministic. Returns the last sent_message_id."""

    async def _seed() -> str:
        from slidein_api.db import session_scope
        from slidein_api.ids import new_id
        from slidein_api.models import DeliveryEvent, Prospect, SentMessage, utcnow
        from slidein_api.services.config import ConfigService

        last_id = ""
        base = utcnow()
        async with session_scope() as session:
            await ConfigService(session).ensure_tenant(tenant_id)
            prospect = Prospect(
                id=new_id("prospect"),
                tenant_id=tenant_id,
                email=f"seeded-{tenant_id}@slidein-test.example",
                source="test",
                first_name="Seed",
                last_name="Data",
            )
            session.add(prospect)
            await session.flush()
            tick = 0
            for event_type, count in outcomes:
                for _ in range(count):
                    tick += 1
                    sent = SentMessage(
                        id=new_id("sent"),
                        tenant_id=tenant_id,
                        draft_id=new_id("draft"),
                        prospect_id=prospect.id,
                        sender_email="talk@slidein-test.example",
                        recipient_email=prospect.email,
                        message_id=f"<{new_id('sent')}@slidein-test.example>",
                        transport="dry_run",
                    )
                    session.add(sent)
                    await session.flush()
                    session.add(
                        DeliveryEvent(
                            id=new_id("delivery_event"),
                            tenant_id=tenant_id,
                            sent_message_id=sent.id,
                            prospect_id=prospect.id,
                            event_type=event_type,
                            provider="test",
                            occurred_at=base + timedelta(seconds=tick),
                            recorded_by="test",
                        )
                    )
                    last_id = sent.id
            await session.flush()
        return last_id

    return asyncio.run(_seed())


def _record_event(client, tenant_id: str, sent_message_id: str, event_type: str, headers):
    return client.post(
        f"/v1/tenants/{tenant_id}/events",
        json={
            "sent_message_id": sent_message_id,
            "recipient_email": f"seeded-{tenant_id}@slidein-test.example",
            "event_type": event_type,
            "detail": "seeded test outcome",
        },
        headers=headers,
    )


def test_missing_physical_address_raises_error():
    guard = DeliverabilityGuard("tenant_demo")
    settings = {
        "physical_postal_address": "",  # Empty!
        "lawful_basis": "b2b_legitimate_interest",
        "quarantined": False,
    }

    with pytest.raises(MissingPhysicalAddressError) as exc_info:
        guard.validate_pre_send_compliance(settings)
    assert "valid physical postal address is required" in str(exc_info.value)


def test_missing_lawful_basis_raises_error():
    guard = DeliverabilityGuard("tenant_demo")
    settings = {
        "physical_postal_address": "Suite 100, 100 Main St, Austin, TX 78701",
        "lawful_basis": "",  # Empty!
        "quarantined": False,
    }

    with pytest.raises(LawfulBasisMissingError) as exc_info:
        guard.validate_pre_send_compliance(settings)
    assert "Lawful basis" in str(exc_info.value)


def test_quarantined_tenant_is_blocked():
    guard = DeliverabilityGuard("tenant_abusive")
    settings = {
        "physical_postal_address": "Suite 100, 100 Main St, Austin, TX 78701",
        "lawful_basis": "b2b_legitimate_interest",
        "quarantined": True,
        "quarantine_reason": "High bounce rate (4.2%) on shared VPS IP",
    }

    with pytest.raises(DeliverabilityQuarantineError) as exc_info:
        guard.validate_pre_send_compliance(settings)
    assert "is quarantined from sending on shared IPs" in str(exc_info.value)


def test_compliant_settings_pass():
    guard = DeliverabilityGuard("tenant_healthy")
    settings = {
        "physical_postal_address": "Suite 100, 100 Main St, Austin, TX 78701",
        "lawful_basis": "b2b_legitimate_interest",
        "quarantined": False,
    }
    # Should not raise any error
    guard.validate_pre_send_compliance(settings)


def test_circuit_breaker_bounce_threshold():
    # 25 events: 2 bounces = 8.0% bounce rate (> 3.0% limit)
    events = ["delivered"] * 23 + ["bounced", "bounced"]
    tripped, reason = DeliverabilityGuard.evaluate_circuit_breaker(events)
    assert tripped is True
    assert "Hard bounce rate" in str(reason)

    # 50 events: 1 bounce = 2.0% bounce rate (< 3.0% limit)
    events_safe = ["delivered"] * 49 + ["bounced"]
    tripped, reason = DeliverabilityGuard.evaluate_circuit_breaker(events_safe)
    assert tripped is False
    assert reason is None


def test_circuit_breaker_complaint_threshold():
    # 100 events: 1 complaint = 1.0% (> 0.05% limit)
    events = ["delivered"] * 99 + ["complained"]
    tripped, reason = DeliverabilityGuard.evaluate_circuit_breaker(events)
    assert tripped is True
    assert "Spam complaint rate" in str(reason)


def test_format_compliant_body():
    body = "Hello Alex, loved your work on real-time event systems."
    address = "456 Market St, Suite 500, San Francisco, CA"
    
    formatted = DeliverabilityGuard.format_compliant_body(body, physical_address=address)
    assert "To stop receiving emails" in formatted
    assert "456 Market St, Suite 500, San Francisco, CA" in formatted


def test_build_compliance_headers():
    headers = DeliverabilityGuard.build_compliance_headers(
        tenant_id="tenant_123",
        sender_email="talk@nasrullahtanim.me",
        recipient_email="alex@company.com",
    )
    assert "List-Unsubscribe" in headers
    assert "List-Unsubscribe-Post" in headers
    assert headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert headers["X-Tenant-ID"] == "tenant_123"


def test_license_invariants():
    license_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../LICENSE"))
    assert os.path.exists(license_path)
    with open(license_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "Business Source License 1.1" in content
    assert "Nasrullah Tanim" in content
    assert "Additional Use Grant" in content
    assert "Apache License, Version 2.0" in content
    assert "OPENOUTREACH (GPLv3)" in content
    assert "Clean-Room" in content


def test_circuit_breaker_quarantines_abusive_tenant(client, service_headers, other_tenant_headers):
    # 23 healthy + 2 bounced outcomes, then one more bounce through the API:
    # 3/26 = 11.5% bounce, far above the 3% shared-IP safety threshold.
    last_id = _seed_outcomes(TENANT_A, [("delivered", 23), ("bounced", 2)])
    response = _record_event(client, TENANT_A, last_id, "bounced", service_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["quarantined"] is True
    assert "bounce" in body["quarantine_reason"].lower()

    # The quarantine is persisted on this tenant's sending policy, and the
    # pre-send gate (the one send_draft runs) now refuses the workspace.
    policy = client.get(
        f"/v1/tenants/{TENANT_A}/policy", headers=service_headers
    ).json()["policy"]
    assert policy["quarantined"] is True

    async def _gate():
        from slidein_api.db import session_scope
        from slidein_api.services.outreach import OutreachService

        async with session_scope() as session:
            outreach = OutreachService(session)
            with pytest.raises(DeliverabilityQuarantineError):
                DeliverabilityGuard(TENANT_A).validate_pre_send_compliance(
                    await outreach.policy(TENANT_A)
                )

    asyncio.run(_gate())

    # Isolation guarantee: the neighbor tenant on the same shared IPs is
    # untouched and keeps its clean policy.
    other_policy = client.get(
        f"/v1/tenants/{TENANT_B}/policy", headers=other_tenant_headers
    ).json()["policy"]
    assert other_policy["quarantined"] is False


def test_abuse_review_resolves_quarantine(
    client, admin_headers, operator_headers, viewer_headers, service_headers
):
    last_id = _seed_outcomes(TENANT_A, [("delivered", 23), ("bounced", 2)])
    _record_event(client, TENANT_A, last_id, "bounced", service_headers)

    # The operator view shows the tripped window, live rates and the caps.
    status = client.get(
        f"/v1/tenants/{TENANT_A}/deliverability", headers=admin_headers
    ).json()["deliverability"]
    assert status["quarantined"] is True
    assert status["window_size"] == 26
    assert status["bounce_rate"] == pytest.approx(3 / 26, abs=1e-3)
    assert status["complaint_rate"] == 0.0
    assert status["thresholds"]["bounce_rate"] == MAX_ALLOWED_BOUNCE_RATE
    assert status["thresholds"]["complaint_rate"] == MAX_ALLOWED_COMPLAINT_RATE
    assert status["limits"]["hourly_limit"] == 10
    assert status["limits"]["daily_limit"] == 50

    # Resolving a quarantine is an admin decision; viewer and operator cannot.
    for headers in (viewer_headers, operator_headers):
        response = client.post(
            f"/v1/tenants/{TENANT_A}/quarantine/resolve", json={"note": "review"}, headers=headers
        )
        assert response.status_code == 403

    # Admin resolves with an audit note; the flag clears and sending is allowed again.
    response = client.post(
        f"/v1/tenants/{TENANT_A}/quarantine/resolve",
        json={"note": "bad list purged; re-verified clean seed"},
        headers=admin_headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["policy"]["quarantined"] is False

    async def _gate_open():
        from slidein_api.db import session_scope
        from slidein_api.services.outreach import OutreachService

        async with session_scope() as session:
            policy = await OutreachService(session).policy(TENANT_A)
        DeliverabilityGuard(TENANT_A).validate_pre_send_compliance(policy)  # must not raise

    asyncio.run(_gate_open())

    # The abuse review is auditable: both the trip and the decision are in
    # the activity log with the reviewer and the note.
    activity = client.get(
        f"/v1/tenants/{TENANT_A}/activity?limit=50", headers=admin_headers
    ).json()["data"]
    actions = {item["action"] for item in activity}
    assert "tenant_quarantined" in actions
    assert "tenant_quarantine_resolved" in actions
    resolved = next(
        item for item in activity if item["action"] == "tenant_quarantine_resolved"
    )
    assert resolved["actor"] == "user:admin"
    assert "bad list purged" in resolved["summary"]

    # History is retained on the policy for the audit trail.
    policy = client.get(
        f"/v1/tenants/{TENANT_A}/policy", headers=admin_headers
    ).json()["policy"]
    assert policy["quarantine_history"]
    assert policy["quarantine_history"][0]["resolved_by"] == "user:admin"

    # Resolving again is a conflict, not a silent success.
    response = client.post(
        f"/v1/tenants/{TENANT_A}/quarantine/resolve", json={}, headers=admin_headers
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "not_quarantined"


def test_healthy_delivery_history_does_not_trip(client, service_headers, admin_headers):
    last_id = _seed_outcomes(TENANT_A, [("delivered", 25)])
    response = _record_event(client, TENANT_A, last_id, "delivered", service_headers)
    assert response.status_code == 200, response.text
    assert response.json()["quarantined"] is False

    status = client.get(
        f"/v1/tenants/{TENANT_A}/deliverability", headers=admin_headers
    ).json()["deliverability"]
    assert status["would_trip"] is False
    assert status["bounce_rate"] == 0.0
    assert status["window_size"] == 26


def test_pre_send_check_surfaces_compliance_blocks(configured_workspace, admin_headers):
    from tests.test_journey import _prepared_draft

    client, draft, _prospect_id = _prepared_draft(configured_workspace)
    client.post(
        f"/v1/tenants/{TENANT_A}/drafts/{draft['id']}/approve", headers=admin_headers
    )

    # Clear the physical address: CAN-SPAM invariant, blocked at the gate.
    client.put(
        f"/v1/tenants/{TENANT_A}/policy",
        json={"physical_postal_address": ""},
        headers=admin_headers,
    )
    response = client.post(
        f"/v1/tenants/{TENANT_A}/drafts/{draft['id']}/send",
        json={"approved": False},  # dry run: checks only, nothing sent
        headers=admin_headers,
    )
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "missing_physical_postal_address"
    assert error["recovery_action"] == "update_workspace_physical_address"

    # And nothing was dispatched.
    sent = client.get(f"/v1/tenants/{TENANT_A}/sent", headers=admin_headers).json()
    assert sent["total"] == 0
