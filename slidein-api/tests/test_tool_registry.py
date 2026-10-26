"""Tool catalog and deterministic, side-effect-free coverage planning."""

from __future__ import annotations

import pytest

from slidein_api.integrations.tool_registry import (
    TOOL_REGISTRY,
    ToolContext,
    build_coverage_plan,
    fallback_chain,
)
from tests.conftest import TENANT_A, TENANT_B


def test_registry_ids_and_priorities_are_unique_and_stable():
    ids = [tool.id for tool in TOOL_REGISTRY]
    assert len(ids) == len(set(ids))
    assert ids == sorted(ids)
    assert {"website_connector", "openosint", "ecc", "firecrawl", "crawl4ai"} <= set(ids)
    for tool in TOOL_REGISTRY:
        assert tool.capabilities
        assert tool.stage in {"engineering", "research", "personalize", "outreach", "operations"}
        for capability in tool.capabilities:
            candidates = [item for item in TOOL_REGISTRY if capability in item.capabilities]
            ordered = sorted(candidates, key=lambda item: (item.priority, item.id))
            assert [item.id for item in ordered] == sorted(
                (item.id for item in candidates),
                key=lambda id: (next(item.priority for item in candidates if item.id == id), id),
            )


def test_every_registered_research_tool_is_accounted_for(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    context = ToolContext(domain="example.com", email="ada@example.com", name="Ada Lovelace")
    plan = build_coverage_plan(context=context, stage="research", environ={})
    expected = {tool.id for tool in TOOL_REGISTRY if tool.stage == "research"}
    assert {row["tool_id"] for row in plan["ledger"]} == expected
    assert len(plan["ledger"]) == len(expected)
    firecrawl = next(row for row in plan["ledger"] if row["tool_id"] == "firecrawl")
    assert firecrawl["status"] == "skipped"
    assert firecrawl["reason"] == "missing_configuration"
    assert "FIRECRAWL_API_KEY" in firecrawl["missing"]
    assert plan["complete_coverage"] is True
    assert plan["runnable_count"] < len(expected)


def test_policy_and_applicability_skips_are_explicit():
    context = ToolContext(domain="example.com", allow_active=False)
    plan = build_coverage_plan(context=context, stage="research", environ={})
    holehe = next(row for row in plan["ledger"] if row["tool_id"] == "holehe")
    assert holehe["status"] == "skipped"
    assert holehe["reason"] == "active_research_not_authorized"
    github = next(row for row in plan["ledger"] if row["tool_id"] == "github_cli")
    assert github["reason"] == "missing_applicable_target"
    assert all("secret" not in row for row in plan["ledger"])


def test_fallback_chain_is_ordered_and_contains_only_ready_tools():
    context = ToolContext(domain="example.com")
    environ = {
        "FIRECRAWL_API_KEY": "test-only",
        "TAVILY_API_KEY": "test-only",
        "OPENOSINT_CLI": "/bin/sh",
    }
    chain = fallback_chain("website_fetch", context=context, environ=environ)
    assert chain[0] == "website_connector"
    assert "firecrawl" in chain
    assert "tavily" not in chain
    assert len(chain) == len(set(chain))


def test_failed_primary_has_documented_fallback_without_fake_success():
    context = ToolContext(domain="example.com")
    plan = build_coverage_plan(
        context=context, stage="research", environ={"FIRECRAWL_API_KEY": "test-only"},
    )
    website = next(row for row in plan["ledger"] if row["tool_id"] == "website_connector")
    assert website["status"] == "ready"
    assert website["fallbacks"] == ["firecrawl"]
    assert plan["mock_success"] is False


def test_unwired_legacy_tool_cannot_be_ready_even_with_configuration():
    plan = build_coverage_plan(
        context=ToolContext(domain="example.com"), stage="research",
        environ={"TAVILY_API_KEY": "test-only"},
    )
    tavily = next(row for row in plan["ledger"] if row["tool_id"] == "tavily")
    assert tavily["reason"] == "adapter_not_wired"


def test_openosint_passive_capabilities_remain_eligible_when_active_is_gated():
    plan = build_coverage_plan(
        context=ToolContext(domain="example.com"), stage="research",
        capabilities=["dns_research", "account_enumeration"],
        environ={"OPENOSINT_CLI": "/bin/sh"},
    )
    osint = next(row for row in plan["ledger"] if row["tool_id"] == "openosint")
    assert osint["status"] == "ready"
    assert osint["capabilities"] == ["dns_research"]


@pytest.mark.parametrize("scope", ["engineering", "operations"])
def test_non_research_tools_never_enter_prospect_fanout(scope: str):
    context = ToolContext(domain="example.com", email="ada@example.com", name="Ada")
    plan = build_coverage_plan(context=context, stage="research", environ={})
    ids = {row["tool_id"] for row in plan["ledger"]}
    assert not any(tool.id in ids for tool in TOOL_REGISTRY if tool.stage == scope)


def test_catalog_and_coverage_routes_require_auth_and_bind_tenant(client, admin_headers, other_tenant_headers):
    unauthenticated = client.get("/v1/tools/catalog")
    assert unauthenticated.status_code in {401, 403}

    response = client.get("/v1/tools/catalog", headers=admin_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["count"] == len(TOOL_REGISTRY)
    assert body["side_effects"] == "none"
    ecc = next(tool for tool in body["tools"] if tool["id"] == "ecc")
    assert ecc["stage"] == "engineering"
    assert ecc["version"] == "2.2.3"
    assert ecc["revision"] == "f3904009440af24f00617343910ee89714df8be3"

    cross_tenant = client.post(
        f"/v1/tenants/{TENANT_B}/tools/coverage",
        json={"domain": "example.com"},
        headers=other_tenant_headers,
    )
    assert cross_tenant.status_code == 200, cross_tenant.text
    assert cross_tenant.json()["tenant_id"] == TENANT_B
    wrong_tenant = client.post(
        f"/v1/tenants/{TENANT_A}/tools/coverage",
        json={"domain": "example.com"},
        headers=other_tenant_headers,
    )
    assert wrong_tenant.status_code == 404


def test_coverage_route_does_not_execute_tools(client, admin_headers, monkeypatch: pytest.MonkeyPatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("coverage planning must not spawn a tool")

    monkeypatch.setattr("subprocess.run", forbidden)
    response = client.post(
        f"/v1/tenants/{TENANT_A}/tools/coverage",
        json={"domain": "example.com", "email": "ada@example.com", "stage": "research"},
        headers=admin_headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["executed"] is False
    assert body["plan"]["complete_coverage"] is True
    assert body["plan"]["ledger"]
