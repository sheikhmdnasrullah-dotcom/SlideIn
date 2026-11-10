"""Hermetic Reacher email-verification adapter tests."""

from __future__ import annotations

import httpx
import pytest

from slidein_api.errors import ProviderError
from slidein_api.integrations.reacher import ReacherAdapter


@pytest.mark.asyncio
@pytest.mark.parametrize("reachable", ["safe", "risky", "invalid", "unknown"])
async def test_reacher_preserves_provider_verdict(reachable: str):
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v0/check_email"
        assert request.content == b'{"to_email":"ada@example.com"}'
        return httpx.Response(200, json={"is_reachable": reachable})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await ReacherAdapter(
            base_url="http://127.0.0.1:8090", client=client
        ).verify("ada@example.com")
    assert result["status"] == reachable
    assert result["collector"] == "reacher"
    assert result["verified"] is True


@pytest.mark.asyncio
async def test_reacher_failure_is_explicit():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: (_ for _ in ()).throw(httpx.ConnectError("down")))
    ) as client:
        with pytest.raises(ProviderError) as caught:
            await ReacherAdapter(base_url="http://127.0.0.1:8090", client=client).verify(
                "ada@example.com"
            )
    assert caught.value.code == "source_unavailable"


@pytest.mark.asyncio
async def test_reacher_requires_configuration():
    with pytest.raises(ProviderError) as caught:
        await ReacherAdapter(base_url="").verify("ada@example.com")
    assert caught.value.details["missing"] == ["REACHER_URL"]


def test_live_transport_is_blocked_by_unsafe_recipient(
    configured_workspace, monkeypatch: pytest.MonkeyPatch
):
    from tests.conftest import TENANT_A
    from tests.test_journey import _prepared_draft

    async def invalid_recipient(email: str) -> dict:
        return {"collector": "reacher", "status": "invalid", "verified": True}

    monkeypatch.setattr("slidein_api.services.outreach.reacher_verification", invalid_recipient)
    client, draft, _ = _prepared_draft(configured_workspace)
    headers = configured_workspace["headers"]
    client.post(f"/v1/tenants/{TENANT_A}/drafts/{draft['id']}/approve", headers=headers)
    response = client.post(
        f"/v1/tenants/{TENANT_A}/drafts/{draft['id']}/send",
        json={
            "sender_email": "hello@northwindcloud.example",
            "transport": {"transport": "smtp", "smtp_host": "127.0.0.1", "smtp_port": 1},
        },
        headers=headers,
    )
    assert response.status_code == 400, response.text
    error = response.json()["error"]
    assert error["code"] == "transport_rejected"
    assert error["details"]["email_verification"]["status"] == "invalid"
