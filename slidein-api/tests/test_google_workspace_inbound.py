"""Google Workspace IMAP ingestion without live network access."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from slidein_api.db import session_scope
from slidein_api.integrations.google_imap import parse_mime_message
from slidein_api.models import InboundReceipt, InboundReply, Tenant
from slidein_api.services.inbound_mail import GoogleWorkspaceInboundService
import pytest

from tests.conftest import TENANT_A, prospect_records


RAW = b"""From: Prospect Tester <prospect0@cloudwave0.example>\r
To: owner@example.com\r
Subject: Re: CloudWave\r
Message-ID: <provider-message-1@mail.example>\r
In-Reply-To: <sent-1@example.com>\r
Content-Type: text/plain; charset=utf-8\r
\r
Sounds interesting. Can we talk?\r
"""


def test_parse_mime_message_uses_real_headers_and_plain_body():
    parsed = parse_mime_message(RAW)
    assert parsed["sender_email"] == "prospect0@cloudwave0.example"
    assert parsed["external_id"] == "provider-message-1@mail.example"
    assert parsed["in_reply_to"] == "sent-1@example.com"
    assert "Sounds interesting" in parsed["body"]


@pytest.mark.asyncio
async def test_google_inbound_is_idempotent_and_tenant_bound(configured_workspace, monkeypatch):
    monkeypatch.setenv("GOOGLE_WORKSPACE_IMAP_PASSWORD", "test-only")
    client = configured_workspace["client"]
    discovered = client.post(
        f"/v1/tenants/{TENANT_A}/discover",
        json={"records": prospect_records(1)}, headers=configured_workspace["headers"],
    )
    assert discovered.status_code == 200
    async with session_scope() as session:
        tenant = await session.get(Tenant, TENANT_A)
        tenant.settings = {
            **(tenant.settings or {}),
            "mail": {
                "provider": "google_workspace",
                "enabled": True,
                "imap_host": "imap.gmail.com",
                "imap_port": 993,
                "username": "owner@example.com",
                "secret_ref": "GOOGLE_WORKSPACE_IMAP_PASSWORD",
            },
        }
        service = GoogleWorkspaceInboundService(session, fetcher=lambda _config: [parse_mime_message(RAW)])
        first = await service.poll(TENANT_A)
        second = await service.poll(TENANT_A)
        replies = (await session.execute(select(InboundReply))).scalars().all()
        receipts = (await session.execute(select(InboundReceipt))).scalars().all()

    assert first["processed"] == 1
    assert second["duplicates"] == 1
    assert len(replies) == 1
    assert len(receipts) == 1
    assert receipts[0].tenant_id == TENANT_A
    assert receipts[0].external_id == "provider-message-1@mail.example"


@pytest.mark.asyncio
async def test_missing_mail_configuration_stays_disabled():
    async with session_scope() as session:
        result = await GoogleWorkspaceInboundService(session).poll(TENANT_A)
    assert result["status"] == "disabled"
    assert result["reason"] == "missing_configuration"
