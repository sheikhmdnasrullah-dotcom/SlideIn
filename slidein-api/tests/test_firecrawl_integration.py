"""Hermetic Firecrawl adapter and deterministic website fallback tests."""

from __future__ import annotations

import httpx
import pytest

from slidein_api.errors import ProviderError, SlideinError
from slidein_api.integrations.firecrawl import FirecrawlAdapter, public_company_url
from slidein_api.models import Prospect
from slidein_api.services.research import Claim, ResearchService, WebsiteConnector


@pytest.mark.asyncio
async def test_firecrawl_persists_only_returned_content_with_provenance():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://api.firecrawl.dev/v1/scrape"
        assert request.headers["Authorization"] == "Bearer test-only"
        assert request.content == b'{"url":"https://example.com/","formats":["markdown"],"onlyMainContent":true}'
        return httpx.Response(200, json={
            "success": True,
            "data": {
                "markdown": "Example builds research software.",
                "metadata": {"sourceURL": "https://example.com/"},
            },
        })

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        claims = await FirecrawlAdapter(api_key="test-only", client=client).scrape("example.com")
    assert len(claims) == 1
    assert claims[0]["claim_text"].endswith("Example builds research software.")
    assert claims[0]["source_url"] == "https://example.com/"
    assert claims[0]["collector"] == "firecrawl"
    assert claims[0]["verification_status"] == "verified"


@pytest.mark.asyncio
async def test_firecrawl_failure_is_explicit_not_empty_success():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"success": False})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ProviderError) as caught:
            await FirecrawlAdapter(api_key="test-only", client=client).scrape("example.com")
    assert caught.value.code == "source_unavailable"


@pytest.mark.asyncio
async def test_firecrawl_requires_configuration():
    with pytest.raises(ProviderError) as caught:
        await FirecrawlAdapter(api_key="").scrape("example.com")
    assert caught.value.details["missing"] == ["FIRECRAWL_API_KEY"]


@pytest.mark.parametrize("domain", ["localhost", "127.0.0.1", "example.internal", "https://example.com", "bad"])
def test_public_target_validation_is_offline(domain: str):
    with pytest.raises(SlideinError):
        public_company_url(domain)


class _Session:
    def __init__(self):
        self.rows = []

    def add(self, row):
        self.rows.append(row)

    async def flush(self):
        return None


@pytest.mark.asyncio
async def test_failed_firecrawl_falls_back_to_canonical_website(monkeypatch: pytest.MonkeyPatch):
    async def fail(self, domain):
        raise ProviderError("test failure", code="source_unavailable", recovery_action="retry_stage")

    def website(self, prospect, *, depth="standard"):
        return [Claim(
            evidence_type="website_claim",
            claim_text="Actual website text",
            source_url="https://example.com/",
            source_name="example.com",
        )]

    monkeypatch.setattr(FirecrawlAdapter, "scrape", fail)
    monkeypatch.setattr(WebsiteConnector, "collect", website)
    session = _Session()
    prospect = Prospect(
        id="prosp_firecrawl", tenant_id="tenant_test", email="ada@example.com",
        company_domain="example.com", source="test",
    )
    result = await ResearchService(session).collect_evidence(
        tenant_id="tenant_test", prospect=prospect, connector="firecrawl",
    )
    assert result["evidence_count"] == 1
    assert session.rows[0].claim_text == "Actual website text"
    assert session.rows[0].collector == "website_connector"
