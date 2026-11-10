"""Hermetic free-form intake and source-grounded LLM setup tests."""

from __future__ import annotations

import pytest

from slidein_api.errors import SlideinError
from slidein_api.setup.extract import extract_profile
from slidein_api.setup.llm import merge_extraction
from slidein_api.setup.sources import Source

BUSINESS_CONTEXT = """Business name: Northwind Cloud
Website: https://northwind.example
Industry: Cloud infrastructure
Business description: Northwind Cloud reduces infrastructure waste for SaaS teams.
Core value proposition: Cut cloud spend without manual rightsizing.
Products: Automated cloud cost audits and continuous rightsizing.
Ideal customer: SaaS companies with Kubernetes and growing cloud bills.
Geography: North America; Europe
Tone: Direct and evidence-led.
"""


def _llm_fields():
    return {
        "legal_name": {
            "value": "Northwind Cloud", "status": "confirmed", "confidence": 0.98,
            "source_id": "src_1", "quote": "Business name: Northwind Cloud",
        },
        "products_services": {
            "value": "Cloud cost audits and continuous rightsizing",
            "status": "confirmed", "confidence": 0.96, "source_id": "src_1",
            "quote": "Automated cloud cost audits and continuous rightsizing.",
        },
        "ideal_customer_profile": {
            "value": "SaaS companies with Kubernetes and growing cloud bills",
            "status": "confirmed", "confidence": 0.97, "source_id": "src_1",
            "quote": "SaaS companies with Kubernetes and growing cloud bills.",
        },
        "differentiators": {
            "value": "Automated continuous rightsizing rather than manual cleanup",
            "status": "assumption", "confidence": 0.72, "source_id": "src_1",
            "quote": "Cut cloud spend without manual rightsizing.",
        },
    }


def _configure_llm(monkeypatch):
    monkeypatch.setenv("SLIDEIN_LLM_BASE_URL", "https://llm.invalid/v1")
    monkeypatch.setenv("SLIDEIN_LLM_API_KEY", "test-secret-not-a-provider-key")
    monkeypatch.setenv("SLIDEIN_LLM_MODEL", "test-grounded-model")


def test_async_intake_builds_existing_profile_offer_and_icp(client, operator_headers, monkeypatch):
    _configure_llm(monkeypatch)

    async def fake_provider(**_kwargs):
        return {"fields": _llm_fields()}, False

    monkeypatch.setattr("slidein_api.setup.llm._request_extraction", fake_provider)
    response = client.post(
        "/v1/tenants/ten_alpha/setup/intake",
        headers=operator_headers,
        json={"sources": [{
            "type": "transcript", "label": "founder-call.vtt",
            "filename": "founder-call.vtt", "text": BUSINESS_CONTEXT,
        }]},
    )
    assert response.status_code == 200, response.text
    run_id = response.json()["run"]["id"]

    completed = client.get(
        f"/v1/tenants/ten_alpha/setup/runs/{run_id}", headers=operator_headers,
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["run"]["state"] == "complete"
    status = completed.json()["status"]
    assert status["extraction"]["mode"] == "llm_grounded"
    assert status["extraction"]["provider"] == "test-grounded-model"
    assert status["profile"]["differentiators"]["source_spans"][0]["source_id"] == "src_1"

    bundle = client.get("/v1/tenants/ten_alpha/profile", headers=operator_headers).json()
    assert bundle["profile"]["legal_name"] == "Northwind Cloud"
    assert bundle["offers"]
    assert bundle["icps"]
    assert "test-secret-not-a-provider-key" not in completed.text


def test_provider_failure_is_a_failed_run_not_mock_success(client, operator_headers, monkeypatch):
    _configure_llm(monkeypatch)

    async def failed_provider(**_kwargs):
        raise SlideinError("Provider unavailable", code="llm_unavailable")

    monkeypatch.setattr("slidein_api.setup.llm._request_extraction", failed_provider)
    response = client.post(
        "/v1/tenants/ten_alpha/setup/intake", headers=operator_headers,
        json={"sources": [{"type": "notes", "text": BUSINESS_CONTEXT}]},
    )
    run_id = response.json()["run"]["id"]
    result = client.get(
        f"/v1/tenants/ten_alpha/setup/runs/{run_id}", headers=operator_headers,
    ).json()
    assert result["run"]["state"] == "failed"
    assert result["run"]["error"] == "Provider unavailable"
    assert client.get(
        "/v1/tenants/ten_alpha/profile", headers=operator_headers,
    ).json()["profile"] is None


def test_model_cannot_invent_a_field_without_an_exact_source_quote():
    source = Source(id="src_1", type="notes", label="notes", text="We offer cloud audits.")
    draft = extract_profile([source])
    original = draft["fields"]["legal_name"]["value"]
    merge_extraction(draft, {"fields": {
        "legal_name": {
            "value": "Invented Corporation", "status": "confirmed", "confidence": 1.0,
            "source_id": "src_1", "quote": "a quote absent from the source",
        },
    }}, [source], provider="test-model", truncated=False)
    assert draft["fields"]["legal_name"]["value"] == original
    assert draft["extraction"]["rejected_fields"] == ["legal_name"]


def test_setup_run_is_tenant_bound(client, operator_headers, other_tenant_headers):
    response = client.post(
        "/v1/tenants/ten_alpha/setup/intake", headers=operator_headers,
        json={"sources": [{"type": "notes", "text": BUSINESS_CONTEXT}]},
    )
    run_id = response.json()["run"]["id"]
    forbidden = client.get(
        f"/v1/tenants/ten_alpha/setup/runs/{run_id}", headers=other_tenant_headers,
    )
    assert forbidden.status_code == 404


@pytest.mark.parametrize("env_name", ["SLIDEIN_LLM_BASE_URL", "SLIDEIN_LLM_API_KEY", "SLIDEIN_LLM_MODEL"])
def test_partial_llm_configuration_fails_explicitly(client, operator_headers, monkeypatch, env_name):
    _configure_llm(monkeypatch)
    monkeypatch.delenv(env_name)
    response = client.post(
        "/v1/tenants/ten_alpha/setup/generate", headers=operator_headers,
        json={"sources": [{"type": "notes", "text": BUSINESS_CONTEXT}]},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "llm_configuration"


@pytest.mark.asyncio
async def test_provider_network_failure_is_explicitly_retryable(monkeypatch):
    import httpx

    from slidein_api.setup.llm import _request_extraction

    async def offline_post(_self, *_args, **_kwargs):
        raise httpx.ConnectError("hermetic offline test")

    monkeypatch.setattr(httpx.AsyncClient, "post", offline_post)
    with pytest.raises(SlideinError) as failure:
        await _request_extraction(
            base_url="https://llm.invalid/v1",
            api_key="test-secret-not-a-provider-key",
            model="test-model",
            sources=[Source(id="src_1", type="notes", label="notes", text=BUSINESS_CONTEXT)],
        )
    assert failure.value.code == "llm_unavailable"
    assert failure.value.retryable is True
