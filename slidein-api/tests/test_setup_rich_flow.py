"""The operator flow behind the /setup screen.

`POST /v1/setup/client` (see `test_setup_flow.py`) is the intake of record for
a client's transcript. These tests cover the richer per-stage surface the
screen renders: generate -> answer -> status, plus the guards (role, tenant).

Acceptance: nothing is invented, every blocked step says why, and a workspace
is never reported active before it is.
"""

from __future__ import annotations

from slidein_api.services.modules import MODULE_IDS

BRIEF = (
    "Acme Mortgage Partners helps London renters become first-time buyers. "
    "We sell mortgage advice and use HubSpot. SMS would help. "
    "Approver is Dana Whitfield. Address: 12 King Street, London."
)

# Answers only a human can give — the deterministic extractor never invents them.
ANSWERS = {
    "website_url": "https://acme.example.com",
    "core_value_prop": "We get renters into their first flat within 90 days.",
    "ideal_customer_profile": "London renters, income 40k+, no saved deposit.",
    "physical_postal_address": "12 King Street, London",
    "sender": "hello@acme.example.com",
    "approver": "Dana Whitfield",
}


def _generate(client, headers, text=BRIEF):
    return client.post(
        "/v1/tenants/ten_alpha/setup/generate",
        headers=headers,
        json={"sources": [{"type": "notes", "label": "brief", "text": text}]},
    )


def test_generate_reads_context_into_profile_and_real_modules(client, operator_headers):
    r = _generate(client, operator_headers)
    assert r.status_code == 200, r.text
    d = r.json()

    fields = d["profile"]["fields"]
    assert fields["legal_name"]["value"] == "Acme Mortgage Partners"
    assert fields["industry"]["value"]

    # Only implemented modules are proposed — never a capability this build lacks.
    enabled = d["blueprint"]["modules"]["enabled"]
    assert enabled
    assert set(enabled) <= set(MODULE_IDS)

    # An unsupported ask is surfaced as a proposed enhancement, not silently kept.
    enhancements = [e["capability"] for e in d["blueprint"]["proposed_enhancements"]]
    assert any("SMS" in item for item in enhancements)

    status = d["status"]
    assert status["states"]["workspace_generated"] is True
    assert status["open_blocking_questions"]  # address, sender, approver, …


def test_generate_never_reports_active_before_it_is(client, operator_headers):
    status = _generate(client, operator_headers).json()["status"]
    assert status["state"] != "active"
    assert status["states"]["active"] is False
    assert status["activation"]["status"] != "active"


def test_status_exposes_every_stage_and_validation_report(client, operator_headers):
    _generate(client, operator_headers)
    r = client.get("/v1/tenants/ten_alpha/setup", headers=operator_headers)
    assert r.status_code == 200, r.text
    status = r.json()

    assert set(status["states"]) >= {
        "workspace_generated", "configuration_validated",
        "integrations_connected", "workflow_tested", "active",
    }
    assert status["checklist"]
    assert status["validation"]["stages"]
    assert status["blockers"]           # honest: what still stops activation
    assert status["sources"][0]["status"] in ("ready", "truncated")


def test_answers_clear_open_questions_and_persist(client, operator_headers):
    _generate(client, operator_headers)
    before = client.get("/v1/tenants/ten_alpha/setup", headers=operator_headers).json()
    open_keys = {q["key"] for q in before["open_blocking_questions"]}
    assert {"physical_postal_address", "sender", "approver"} <= open_keys

    # Every open question gets an answer: the operator's own values for the
    # decisions, and confirmation of what extraction proposed.
    payload = {}
    for question in before["open_blocking_questions"]:
        key = question["key"]
        payload[key] = ANSWERS.get(key) or question.get("value") or question.get("default") or ""
    assert payload["physical_postal_address"]
    r = client.post(
        "/v1/tenants/ten_alpha/setup/answers", headers=operator_headers,
        json={"answers": payload},
    )
    assert r.status_code == 200, r.text
    d = r.json()

    assert d["status"]["open_blocking_questions"] == []
    assert d["profile"]["saved"] is True

    # The decisions survive as real records, not just a screen render.
    bundle = client.get(
        "/v1/tenants/ten_alpha/profile", headers=operator_headers).json()
    assert "Acme Mortgage" in str(bundle["profile"])
    assert bundle["offers"], "an offer was generated from the brief"
    assert bundle["icps"], "an ICP was generated from the brief"


def test_unsafe_source_is_reported_not_read(client, operator_headers):
    """A local/private address is refused as a server-side fetch and the
    refusal is shown on the source — never silently dropped or fetched."""
    r = client.post(
        "/v1/tenants/ten_alpha/setup/generate", headers=operator_headers,
        json={"sources": [
            {"type": "website", "url": "http://localhost:9999"},
            {"type": "notes", "label": "fine", "text": BRIEF},
        ]},
    )
    assert r.status_code == 200, r.text
    d = r.json()

    by_label = {source["label"]: source for source in d["sources"]}
    blocked = by_label["http://localhost:9999"]
    assert blocked["status"] == "error"
    assert "local" in blocked["error"]
    assert by_label["fine"]["status"] == "ready"
    assert by_label["fine"]["char_count"] > 0


def test_viewer_cannot_generate_and_other_tenant_gets_404(client, viewer_headers,
                                                          other_tenant_headers):
    r = _generate(client, viewer_headers)
    assert r.status_code == 403, r.text

    r = client.post(
        "/v1/tenants/ten_alpha/setup/generate", headers=other_tenant_headers,
        json={"sources": [{"type": "notes", "label": "brief", "text": BRIEF}]},
    )
    assert r.status_code == 404, r.text


def test_regeneration_is_stable(client, operator_headers):
    first = _generate(client, operator_headers).json()
    second = _generate(client, operator_headers).json()
    assert (second["profile"]["fields"]["legal_name"]["value"]
            == first["profile"]["fields"]["legal_name"]["value"])
    assert second["status"]["attempt"] > first["status"]["attempt"]


def test_answers_require_at_least_one_value(client, operator_headers):
    r = client.post("/v1/tenants/ten_alpha/setup/answers", headers=operator_headers,
                    json={"answers": {}})
    assert r.status_code == 400, r.text
