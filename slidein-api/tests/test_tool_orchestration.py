"""Persistent, deterministic research tool orchestration."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from slidein_api.db import session_scope
from slidein_api.errors import ProviderError
from slidein_api.integrations.tool_registry import TOOL_REGISTRY
from slidein_api.models import ToolAttempt, ToolExecution
from slidein_api.services.discovery import DiscoveryService
from slidein_api.services.research import Claim, ResearchService
from tests.conftest import TENANT_A, prospect_records


async def _prospect(client, headers):
    response = client.post(
        f"/v1/tenants/{TENANT_A}/discover",
        json={"records": prospect_records(1), "source": "test"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    async with session_scope() as session:
        return await DiscoveryService(session).get_prospect(
            TENANT_A, response.json()["outputs"]["prospect_ids"][0]
        )


def _claim() -> Claim:
    return Claim(
        evidence_type="website_claim",
        claim_text="CloudWave states that it runs Kubernetes.",
        source_url="https://cloudwave0.example/about",
        source_name="CloudWave",
    )


@pytest.mark.asyncio
async def test_orchestration_accounts_for_every_tool_and_replays_without_duplicates(
    configured_workspace, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("OPENOSINT_CLI", "/nonexistent/openosint")
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    monkeypatch.setattr(
        "slidein_api.services.research.WebsiteConnector.collect",
        lambda self, prospect, depth="standard": [_claim()],
    )
    client = configured_workspace["client"]
    prospect = await _prospect(client, configured_workspace["headers"])

    async with session_scope() as session:
        first = await ResearchService(session).collect_evidence(
            tenant_id=TENANT_A,
            prospect=prospect,
            connector="orchestrated",
            execution_id="research-run-1",
        )
        second = await ResearchService(session).collect_evidence(
            tenant_id=TENANT_A,
            prospect=prospect,
            connector="orchestrated",
            execution_id="research-run-1",
        )
        executions = (await session.execute(select(ToolExecution))).scalars().all()
        attempts = (await session.execute(select(ToolAttempt))).scalars().all()

    expected = {tool.id for tool in TOOL_REGISTRY if tool.stage == "research"}
    assert first["evidence_ids"] == second["evidence_ids"]
    assert second["tool_execution"]["replayed"] is True
    assert len(executions) == 1
    assert {attempt.tool_id for attempt in attempts} == expected
    website = next(attempt for attempt in attempts if attempt.tool_id == "website_connector")
    assert website.status == "succeeded"
    assert website.evidence_ids == first["evidence_ids"]
    assert first["tool_execution"]["unresolved_capabilities"]
    assert first["tool_execution"]["mock_success"] is False

    execution_id = first["tool_execution"]["id"]
    detail = client.get(
        f"/v1/tenants/{TENANT_A}/tools/executions/{execution_id}",
        headers=configured_workspace["headers"],
    )
    assert detail.status_code == 200, detail.text
    assert len(detail.json()["attempts"]) == len(expected)
    cross_tenant = client.get(
        f"/v1/tenants/ten_beta/tools/executions/{execution_id}",
        headers={"Authorization": "Bearer sk_beta_admin_0001", "X-Slidein-Tenant": "ten_beta"},
    )
    assert cross_tenant.status_code == 404


@pytest.mark.asyncio
async def test_failed_primary_falls_back_in_order_and_records_failure(
    configured_workspace, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("OPENOSINT_CLI", "/bin/sh")
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    monkeypatch.setattr(
        "slidein_api.services.research.WebsiteConnector.collect",
        lambda self, prospect, depth="standard": [_claim()],
    )
    prospect = await _prospect(configured_workspace["client"], configured_workspace["headers"])

    async with session_scope() as session:
        result = await ResearchService(session).collect_evidence(
            tenant_id=TENANT_A,
            prospect=prospect,
            connector="orchestrated",
            capabilities=["dns_research", "website_fetch"],
        )
        attempts = (await session.execute(select(ToolAttempt))).scalars().all()

    openosint = next(attempt for attempt in attempts if attempt.tool_id == "openosint")
    website = next(attempt for attempt in attempts if attempt.tool_id == "website_connector")
    assert openosint.status == "failed"
    assert website.status == "succeeded"
    assert website.fallback_from == "openosint"
    assert result["collector"] == "orchestrated"


@pytest.mark.asyncio
async def test_no_evidence_is_a_persisted_failure_not_mock_success(
    configured_workspace, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("OPENOSINT_CLI", "/nonexistent/openosint")
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)

    def unavailable(self, prospect, depth="standard"):
        raise ProviderError("offline", code="source_unavailable")

    monkeypatch.setattr("slidein_api.services.research.WebsiteConnector.collect", unavailable)
    prospect = await _prospect(configured_workspace["client"], configured_workspace["headers"])

    async with session_scope() as session:
        with pytest.raises(ProviderError):
            await ResearchService(session).collect_evidence(
                tenant_id=TENANT_A,
                prospect=prospect,
                connector="orchestrated",
                execution_id="failed-research",
            )
        execution = (
            await session.execute(
                select(ToolExecution).where(ToolExecution.execution_key == "failed-research")
            )
        ).scalars().one()
        assert execution.status == "failed"
        assert execution.output_snapshot["mock_success"] is False


def test_complete_api_journey_uses_real_orchestration_and_dry_run_send(
    configured_workspace, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        "slidein_api.services.research.WebsiteConnector.collect",
        lambda self, prospect, depth="standard": [_claim()],
    )
    client = configured_workspace["client"]
    headers = configured_workspace["headers"]
    discovered = client.post(
        f"/v1/tenants/{TENANT_A}/discover",
        json={"records": prospect_records(1), "source": "acceptance"},
        headers=headers,
    )
    prospect_id = discovered.json()["outputs"]["prospect_ids"][0]

    researched = client.post(
        f"/v1/tenants/{TENANT_A}/prospects/{prospect_id}/research",
        json={"execution_id": "acceptance-research"},
        headers=headers,
    )
    assert researched.status_code == 200, researched.text
    execution_id = researched.json()["outputs"]["tool_execution"]["id"]
    assert researched.json()["outputs"]["tool_execution"]["complete_coverage"] is True

    qualified = client.post(
        f"/v1/tenants/{TENANT_A}/prospects/{prospect_id}/qualify",
        json={},
        headers=headers,
    )
    assert qualified.status_code == 200, qualified.text
    assert qualified.json()["outputs"]["is_qualified"] is True
    personalized = client.post(
        f"/v1/tenants/{TENANT_A}/prospects/{prospect_id}/personalize",
        json={},
        headers=headers,
    )
    assert personalized.status_code == 200, personalized.text
    draft_id = personalized.json()["outputs"]["id"]

    approved = client.post(
        f"/v1/tenants/{TENANT_A}/drafts/{draft_id}/approve",
        json={"note": "acceptance approval"},
        headers=headers,
    )
    assert approved.status_code == 200, approved.text
    sent = client.post(
        f"/v1/tenants/{TENANT_A}/drafts/{draft_id}/send",
        json={"sender_email": "hello@northwindcloud.example"},
        headers=headers,
    )
    assert sent.status_code == 200, sent.text
    assert sent.json()["outputs"]["transport"] == "dry_run"
    ledger = client.get(
        f"/v1/tenants/{TENANT_A}/tools/executions/{execution_id}", headers=headers
    )
    assert ledger.status_code == 200
    assert any(row["status"] == "succeeded" for row in ledger.json()["attempts"])
