"""Tenant-level sending isolation: routing, fail-closed, circuit breaker.

Covers:
* dedicated / provider-managed route assignment and the honest
  isolation wording,
* fail-closed when a dedicated or provider-managed tenant has no route,
* the shared route being the default for existing tenants,
* circuit-breaker state being per tenant,
* operator pause / probe / resume affecting one tenant only,
* tenant-scoped reads refusing another tenant's configuration.
"""

from __future__ import annotations

import asyncio

import pytest

from slidein_api.db import session_scope
from slidein_api.ids import new_id
from slidein_api.models import (
    DeliveryEvent,
    MessageDraft,
    Prospect,
    SentMessage,
    utcnow,
)
from tests.conftest import TENANT_A, TENANT_B


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


async def _seed_sent_messages(tenant_id: str, count: int) -> list[str]:
    """Insert SentMessage rows only (no delivery events)."""
    ids: list[str] = []
    async with session_scope() as session:
        prospect = Prospect(
            id=new_id("prospect"),
            tenant_id=tenant_id,
            email=f"isolation-{tenant_id}-{count}@slidein-test.example",
            source="test",
            first_name="Iso",
            last_name="Test",
        )
        session.add(prospect)
        await session.flush()
        for index in range(count):
            sent = SentMessage(
                id=new_id("sent"),
                tenant_id=tenant_id,
                draft_id=new_id("draft"),
                prospect_id=prospect.id,
                sender_email="talk@slidein-test.example",
                recipient_email=prospect.email,
                message_id=f"<{new_id('sent')}@{tenant_id}-{index}>",
                transport="dry_run",
            )
            session.add(sent)
            await session.flush()
            ids.append(sent.id)
    return ids


async def _seed_bounced_events(tenant_id: str, sent_message_ids: list[str], count: int) -> None:
    """Insert DeliveryEvent rows of type `bounced` for this tenant only."""
    async with session_scope() as session:
        for index in range(count):
            sent_id = sent_message_ids[index % len(sent_message_ids)]
            session.add(
                DeliveryEvent(
                    id=new_id("delivery_event"),
                    tenant_id=tenant_id,
                    sent_message_id=sent_id,
                    prospect_id=tenant_id,
                    event_type="bounced",
                    provider="test",
                    occurred_at=utcnow(),
                    recorded_by="test",
                )
            )
        await session.flush()


def _save_sending(client, tenant_id: str, payload: dict, headers: dict) -> dict:
    response = client.put(
        f"/v1/tenants/{tenant_id}/sending",
        json=payload,
        headers=headers,
    )
    return response.json()


def _get_sending(client, tenant_id: str, headers: dict) -> dict:
    response = client.get(f"/v1/tenants/{tenant_id}/sending", headers=headers)
    return response.json()


def _get_deliverability(client, tenant_id: str, headers: dict) -> dict:
    response = client.get(
        f"/v1/tenants/{tenant_id}/deliverability", headers=headers
    )
    return response.json()["deliverability"]


# ---------------------------------------------------------------------------
# routing: dedicated and provider-managed modes
# ---------------------------------------------------------------------------


def test_existing_tenant_defaults_to_the_shared_route(client, admin_headers):
    """A tenant without any sending configuration keeps the shared route,
    so current working delivery is never disrupted."""
    body = _get_sending(client, TENANT_A, admin_headers)
    sending = body["sending"]
    assert sending["sending_mode"] == "shared"
    assert sending["egress_pool"] == ""
    assert sending["isolation_copy"].startswith("Shared IP — reputation is shared")


def test_dedicated_mode_assigns_an_egress_pool(client, admin_headers):
    saved = _save_sending(
        client,
        TENANT_A,
        {"sending_mode": "dedicated", "egress_pool": "pool-tenant-a"},
        admin_headers,
    )
    assert saved["sending"]["sending_mode"] == "dedicated"
    assert saved["sending"]["egress_pool"] == "pool-tenant-a"

    body = _get_sending(client, TENANT_A, admin_headers)
    sending = body["sending"]
    assert sending["verified"] is False
    assert sending["isolation_copy"] == (
        "Dedicated IP configured, but outbound route not yet verified."
    )


def test_verified_dedicated_route_reports_verified(client, admin_headers):
    _save_sending(
        client,
        TENANT_A,
        {"sending_mode": "dedicated", "egress_pool": "pool-tenant-a"},
        admin_headers,
    )
    saved = _save_sending(
        client,
        TENANT_A,
        {
            "sending_mode": "dedicated",
            "egress_pool": "pool-tenant-a",
            "verified": True,
            "verification_note": "checked live route",
        },
        admin_headers,
    )
    assert saved["sending"]["verified"] is True
    assert saved["sending"]["verified_by"] == "user:admin"

    body = _get_sending(client, TENANT_A, admin_headers)
    assert body["sending"]["isolation_copy"] == "Dedicated IP — routing verified."


def test_provider_managed_mode_names_the_provider_account(client, admin_headers):
    saved = _save_sending(
        client,
        TENANT_A,
        {
            "sending_mode": "provider_managed",
            "provider": "resend",
            "provider_account": "acme-news",
        },
        admin_headers,
    )
    sending = saved["sending"]
    assert sending["sending_mode"] == "provider_managed"
    assert sending["provider"] == "resend"
    assert sending["provider_account"] == "acme-news"
    assert "Provider route —" in sending["isolation_copy"]


# ---------------------------------------------------------------------------
# fail-closed routing
# ---------------------------------------------------------------------------


def test_dedicated_without_a_route_fails_closed(client, admin_headers):
    response = client.put(
        f"/v1/tenants/{TENANT_A}/sending",
        json={"sending_mode": "dedicated"},
        headers=admin_headers,
    )
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "sending_route_unresolved"
    assert error["retryable"] is False


def test_provider_managed_without_an_account_fails_closed(client, admin_headers):
    response = client.put(
        f"/v1/tenants/{TENANT_A}/sending",
        json={"sending_mode": "provider_managed", "provider": "resend"},
        headers=admin_headers,
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "sending_route_unresolved"


def test_shared_mode_clears_a_dedicated_assignment(client, admin_headers):
    _save_sending(
        client,
        TENANT_A,
        {"sending_mode": "dedicated", "egress_pool": "pool-tenant-a"},
        admin_headers,
    )
    saved = _save_sending(
        client,
        TENANT_A,
        {"sending_mode": "shared"},
        admin_headers,
    )
    assert saved["sending"]["sending_mode"] == "shared"
    assert saved["sending"]["egress_pool"] == ""
    assert saved["sending"]["isolation_copy"].startswith("Shared IP —")


# ---------------------------------------------------------------------------
# tenant isolation of the configuration itself
# ---------------------------------------------------------------------------


def test_tenant_cannot_read_another_tenants_sending_config(
    client, admin_headers, other_tenant_headers
):
    _save_sending(
        client,
        TENANT_B,
        {"sending_mode": "dedicated", "egress_pool": "pool-tenant-b"},
        other_tenant_headers,
    )
    response = client.get(
        f"/v1/tenants/{TENANT_B}/sending",
        headers=admin_headers,
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# circuit breaker is per tenant
# ---------------------------------------------------------------------------


def _seed_circuit_history(tenant_id: str) -> list[str]:
    """Seed SentMessage rows plus bounced DeliveryEvents for one tenant."""

    async def _seed() -> None:
        sent_message_ids = await _seed_sent_messages(tenant_id, 30)
        await _seed_bounced_events(tenant_id, sent_message_ids, 25)

    asyncio.run(_seed())
    return []


def _record_bounced_via_api(
    client, tenant_id: str, headers: dict, count: int, sent_message_id: str
) -> None:
    """Record `bounced` provider events through the API.

    Every recorded event makes the evaluation run, so the circuit opens
    as soon as the rolling window crosses the configured threshold.
    """
    for _ in range(count):
        response = client.post(
            f"/v1/tenants/{tenant_id}/events",
            json={
                "sent_message_id": sent_message_id,
                "recipient_email": f"isolation-{tenant_id}@example.test",
                "event_type": "bounced",
                "provider": "test",
            },
            headers=headers,
        )
        assert response.status_code == 200, response.text


def test_circuit_open_for_the_offending_tenant_only(client, service_headers):
    sent_message_ids = asyncio.run(_seed_sent_messages(TENANT_A, 30))

    _record_bounced_via_api(
        client,
        TENANT_A,
        service_headers,
        count=25,
        sent_message_id=sent_message_ids[0],
    )

    body = _get_deliverability(client, TENANT_A, service_headers)
    assert body["circuit"]["status"] == "open"
    assert body["quarantined"] is True


def test_circuit_state_of_a_healthy_tenant_stays_closed(client, other_tenant_headers):
    async def _setup() -> None:
        await _seed_sent_messages(TENANT_B, 10)

    asyncio.run(_setup())

    body = _get_deliverability(client, TENANT_B, other_tenant_headers)
    assert body["circuit"]["status"] == "closed"
    assert body["quarantined"] is False


def test_pause_and_resume_affect_only_the_paused_tenant(
    client, admin_headers, service_headers, other_tenant_headers
):
    async def _setup() -> None:
        await _seed_sent_messages(TENANT_B, 5)

    asyncio.run(_setup())

    paused = client.post(
        f"/v1/tenants/{TENANT_A}/circuit/pause",
        json={"reason": "temporary ISP issue"},
        headers=admin_headers,
    ).json()["circuit"]
    assert paused["status"] == "open"
    assert paused["reason"] == "temporary ISP issue"

    body_a = _get_deliverability(client, TENANT_A, service_headers)
    assert body_a["circuit"]["status"] == "open"

    body_b = _get_deliverability(client, TENANT_B, other_tenant_headers)
    assert body_b["circuit"]["status"] == "closed"
    assert body_b["quarantined"] is False


def test_resume_closes_the_circuit(client, admin_headers, service_headers):
    client.post(
        f"/v1/tenants/{TENANT_A}/circuit/pause",
        json={"reason": "operator review"},
        headers=admin_headers,
    )
    resumed = client.post(
        f"/v1/tenants/{TENANT_A}/circuit/resume",
        json={"note": "routes restored"},
        headers=admin_headers,
    ).json()["circuit"]
    assert resumed["status"] == "closed"

    body = _get_deliverability(client, TENANT_A, service_headers)
    assert body["circuit"]["status"] == "closed"
    assert body["quarantined"] is False
