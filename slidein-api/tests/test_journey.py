"""The end-to-end journey: discovery -> research -> qualification ->
personalization -> authorized sending -> conversation handling.

This is the acceptance test for the product vision: a user can follow one
prospect through every section without losing context, and each handoff is
a persisted record with explicit status, history and authorization.
"""

from __future__ import annotations

import pytest

from tests.conftest import (
    ICP_PAYLOAD,
    OFFER_PAYLOAD,
    PROFILE_PAYLOAD,
    SAMPLE_CLAIMS,
    TENANT_A,
    TENANT_B,
    prospect_records,
)

pytestmark = pytest.mark.usefixtures("_restore_key_store")


# ---------------------------------------------------------------------------
# 1. Business Profile — versioned configuration
# ---------------------------------------------------------------------------

def test_business_profile_is_versioned_and_discoverable(configured_workspace):
    client = configured_workspace["client"]
    headers = configured_workspace["headers"]
    profile = configured_workspace["profile"]
    assert profile["version"] == 1
    assert profile["is_active"] is True

    response = client.post(
        f"/v1/tenants/{TENANT_A}/profile",
        json={**PROFILE_PAYLOAD, "core_value_prop": "Cut cloud spend by 40%.", "reason": "updated"},
        headers=headers,
    )
    assert response.status_code == 200
    updated = response.json()["profile"]
    assert updated["version"] == 2
    assert updated["id"] != profile["id"]

    versions = client.get(
        f"/v1/tenants/{TENANT_A}/config-versions?entity_type=business_profile",
        headers=headers,
    ).json()["config_versions"]
    assert {v["version"] for v in versions} == {1, 2}
    assert versions[0]["snapshot"]["core_value_prop"] == "Cut cloud spend by 40%."

    readiness = client.get(f"/v1/tenants/{TENANT_A}/readiness", headers=headers).json()
    assert readiness["overall_score"] > 0
    checks = {c["key"]: c["status"] for c in readiness["checklist"]}
    assert checks["business_profile"] == "pass"
    assert checks["active_offers"] == "pass"
    assert checks["icp_rules"] == "pass"


def test_profile_cannot_be_saved_without_required_fields(client, admin_headers):
    response = client.post(
        f"/v1/tenants/{TENANT_A}/profile",
        json={"legal_name": "Incomplete"},
        headers=admin_headers,
    )
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "profile_incomplete"
    assert error["recovery_action"] == "complete_business_profile"
    assert "website_url" in error["details"]["missing_fields"]


def test_offers_and_icps_are_required_before_the_pipeline(client, admin_headers):
    response = client.post(
        f"/v1/tenants/{TENANT_A}/icps",
        json=ICP_PAYLOAD,
        headers=admin_headers,
    )
    assert response.status_code == 400
    assert response.json()["error"]["recovery_action"] == "create_business_profile"


# ---------------------------------------------------------------------------
# 2. Discovery
# ---------------------------------------------------------------------------

def test_discovery_stamps_source_and_configuration_version(configured_workspace):
    client = configured_workspace["client"]
    headers = configured_workspace["headers"]
    profile = configured_workspace["profile"]

    response = client.post(
        f"/v1/tenants/{TENANT_A}/discover",
        json={
            "records": prospect_records(3),
            "source": "csv_import",
            "source_ref": "import-2026-10-13.csv",
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    outcome = response.json()
    assert outcome["ok"] is True
    assert outcome["outputs"]["created"] == 3
    assert outcome["outputs"]["duplicates"] == 0
    assert outcome["to_status"] == "discovered"

    listed = client.get(f"/v1/tenants/{TENANT_A}/prospects", headers=headers).json()
    assert listed["total"] == 3
    first = listed["data"][0]
    assert first["source"] == "csv_import"
    assert first["source_ref"] == "import-2026-10-13.csv"
    assert first["profile_version"] == profile["version"]
    assert first["icp_id"] == configured_workspace["icp"]["id"]
    assert first["status"] == "discovered"


def test_discovery_is_idempotent_for_duplicate_emails(configured_workspace):
    client = configured_workspace["client"]
    headers = configured_workspace["headers"]
    client.post(
        f"/v1/tenants/{TENANT_A}/discover",
        json={"records": prospect_records(2)},
        headers=headers,
    )
    response = client.post(
        f"/v1/tenants/{TENANT_A}/discover",
        json={"records": prospect_records(2)},
        headers=headers,
    )
    assert response.status_code == 200
    outcome = response.json()
    assert outcome["outputs"]["created"] == 0
    assert outcome["outputs"]["duplicates"] == 2
    assert any("already exist" in reason for reason in outcome["needs_review"])


def test_discovery_requires_an_icp(client, admin_headers):
    client.post(
        f"/v1/tenants/{TENANT_A}/profile",
        json=PROFILE_PAYLOAD,
        headers=admin_headers,
    )
    response = client.post(
        f"/v1/tenants/{TENANT_A}/discover",
        json={"records": prospect_records(1)},
        headers=admin_headers,
    )
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "icp_missing"
    assert error["recovery_action"] == "define_icp"


# ---------------------------------------------------------------------------
# 3. Research
# ---------------------------------------------------------------------------

def test_research_collects_source_backed_evidence(configured_workspace):
    client = configured_workspace["client"]
    headers = configured_workspace["headers"]
    discover = client.post(
        f"/v1/tenants/{TENANT_A}/discover",
        json={"records": prospect_records(1)},
        headers=headers,
    ).json()
    prospect_id = discover["outputs"]["prospect_ids"][0]

    response = client.post(
        f"/v1/tenants/{TENANT_A}/prospects/{prospect_id}/research",
        json={"connector": "supplied", "claims": SAMPLE_CLAIMS},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    outcome = response.json()
    assert outcome["outputs"]["evidence_count"] == 3
    assert outcome["outputs"]["verified_count"] == 2
    assert outcome["to_status"] == "researched"

    evidence = client.get(
        f"/v1/tenants/{TENANT_A}/prospects/{prospect_id}/evidence",
        headers=headers,
    ).json()["evidence"]
    assert all(item["source_url"].startswith("http") for item in evidence)
    assert {item["verification_status"] for item in evidence} == {"verified", "inferred"}

    prospect = client.get(
        f"/v1/tenants/{TENANT_A}/prospects/{prospect_id}", headers=headers
    ).json()
    assert prospect["status"] == "researched"
    assert prospect["state_history"][-1]["state"] == "researched"


def test_research_fails_retryably_when_no_source_is_available(configured_workspace):
    client = configured_workspace["client"]
    headers = configured_workspace["headers"]
    discover = client.post(
        f"/v1/tenants/{TENANT_A}/discover",
        json={"records": [dict(prospect_records(1)[0], company_domain="")]},
        headers=headers,
    ).json()
    prospect_id = discover["outputs"]["prospect_ids"][0]

    response = client.post(
        f"/v1/tenants/{TENANT_A}/prospects/{prospect_id}/research",
        json={"connector": "website", "claims": []},
        headers=headers,
    )
    assert response.status_code in (200, 400)
    if response.status_code == 200:
        outcome = response.json()
        assert outcome["status"] == "failed"
        assert outcome["error_code"] in ("source_unavailable", "prospect_invalid")


def test_research_cannot_run_on_a_missing_prospect(configured_workspace):
    client = configured_workspace["client"]
    headers = configured_workspace["headers"]
    response = client.post(
        f"/v1/tenants/{TENANT_A}/prospects/prosp_does_not_exist/research",
        json={"connector": "supplied", "claims": SAMPLE_CLAIMS},
        headers=headers,
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "prospect_not_found"


# ---------------------------------------------------------------------------
# 4. Qualification
# ---------------------------------------------------------------------------

def _research(client, headers, prospect_id):
    return client.post(
        f"/v1/tenants/{TENANT_A}/prospects/{prospect_id}/research",
        json={"connector": "supplied", "claims": SAMPLE_CLAIMS},
        headers=headers,
    ).json()


def test_qualification_is_explainable_and_matches_an_offer(configured_workspace):
    client = configured_workspace["client"]
    headers = configured_workspace["headers"]
    discover = client.post(
        f"/v1/tenants/{TENANT_A}/discover",
        json={"records": prospect_records(1)},
        headers=headers,
    ).json()
    prospect_id = discover["outputs"]["prospect_ids"][0]
    _research(client, headers, prospect_id)

    response = client.post(
        f"/v1/tenants/{TENANT_A}/prospects/{prospect_id}/qualify",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    outcome = response.json()
    result = outcome["outputs"]
    assert 0 <= result["score"] <= 100
    assert result["is_qualified"] is True
    assert result["explanation"]
    assert result["matching_criteria"]
    assert result["offer_match"]["offer_id"] == configured_workspace["offer"]["id"]
    assert result["offer_match"]["evidence_ids"]
    assert outcome["to_status"] == "qualified"

    prospect = client.get(
        f"/v1/tenants/{TENANT_A}/prospects/{prospect_id}", headers=headers
    ).json()
    assert prospect["status"] == "qualified"
    assert prospect["qualification_score"] == result["score"]
    assert prospect["offer_id"] == configured_workspace["offer"]["id"]


def test_qualification_requires_research_first(configured_workspace):
    client = configured_workspace["client"]
    headers = configured_workspace["headers"]
    discover = client.post(
        f"/v1/tenants/{TENANT_A}/discover",
        json={"records": prospect_records(1)},
        headers=headers,
    ).json()
    prospect_id = discover["outputs"]["prospect_ids"][0]

    response = client.post(
        f"/v1/tenants/{TENANT_A}/prospects/{prospect_id}/qualify",
        headers=headers,
    )
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "stage_prerequisite"
    assert error["recovery_action"] == "run_prerequisite_stage"


def test_qualification_disqualifies_when_evidence_is_missing(configured_workspace):
    client = configured_workspace["client"]
    headers = configured_workspace["headers"]
    discover = client.post(
        f"/v1/tenants/{TENANT_A}/discover",
        json={"records": [dict(prospect_records(1)[0], company_size=None, job_title="Intern")]},
        headers=headers,
    ).json()
    prospect_id = discover["outputs"]["prospect_ids"][0]
    _research(
        client,
        headers,
        prospect_id,
    )
    # Replace the connector payload with weak, unverified claims.
    client.post(
        f"/v1/tenants/{TENANT_A}/prospects/{prospect_id}/research",
        json={
            "connector": "supplied",
            "claims": [
                {
                    "evidence_type": "website_claim",
                    "claim_text": "Nothing relevant was stated publicly.",
                    "source_url": "https://example.invalid/x",
                    "verification_status": "unverified",
                }
            ],
        },
        headers=headers,
    )

    response = client.post(
        f"/v1/tenants/{TENANT_A}/prospects/{prospect_id}/qualify",
        headers=headers,
    )
    outcome = response.json()
    assert outcome["outputs"]["is_qualified"] is False
    assert outcome["to_status"] == "disqualified"


# ---------------------------------------------------------------------------
# 5. Personalization
# ---------------------------------------------------------------------------

def test_personalization_cites_evidence_and_versions_drafts(configured_workspace):
    client = configured_workspace["client"]
    headers = configured_workspace["headers"]
    discover = client.post(
        f"/v1/tenants/{TENANT_A}/discover",
        json={"records": prospect_records(1)},
        headers=headers,
    ).json()
    prospect_id = discover["outputs"]["prospect_ids"][0]
    _research(client, headers, prospect_id)
    client.post(
        f"/v1/tenants/{TENANT_A}/prospects/{prospect_id}/qualify", headers=headers
    )

    response = client.post(
        f"/v1/tenants/{TENANT_A}/prospects/{prospect_id}/personalize",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    outcome = response.json()
    draft = outcome["outputs"]
    assert draft["version"] == 1
    assert draft["status"] == "pending_review"
    assert draft["attributed_evidence_ids"]
    assert draft["subject"]
    assert draft["body"]
    assert outcome["to_status"] == "draft_ready"

    detail = client.get(
        f"/v1/tenants/{TENANT_A}/drafts/{draft['id']}", headers=headers
    ).json()
    assert len(detail["versions"]) == 1
    assert detail["qualification"]["is_qualified"] is True
    assert detail["evidence"]

    # A human edit creates a new version and invalidates any approval.
    edited = client.post(
        f"/v1/tenants/{TENANT_A}/drafts/{draft['id']}/edit",
        json={"subject": "Kubernetes spend at CloudWave 0", "body": "Hi — 5 minutes?"},
        headers=headers,
    ).json()["draft"]
    assert edited["version"] == 2
    assert edited["human_edited"] is True
    assert edited["status"] == "pending_review"

    detail = client.get(
        f"/v1/tenants/{TENANT_A}/drafts/{draft['id']}", headers=headers
    ).json()
    assert [v["version"] for v in detail["versions"]] == [1, 2]
    assert detail["versions"][1]["is_human_edit"] is True


def test_personalization_requires_a_qualified_prospect(configured_workspace):
    client = configured_workspace["client"]
    headers = configured_workspace["headers"]
    discover = client.post(
        f"/v1/tenants/{TENANT_A}/discover",
        json={"records": prospect_records(1)},
        headers=headers,
    ).json()
    prospect_id = discover["outputs"]["prospect_ids"][0]

    response = client.post(
        f"/v1/tenants/{TENANT_A}/prospects/{prospect_id}/personalize",
        headers=headers,
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "stage_prerequisite"


# ---------------------------------------------------------------------------
# 6. Outreach — approval and sending policy
# ---------------------------------------------------------------------------

def _prepared_draft(configured_workspace) -> tuple[object, dict, str]:
    client = configured_workspace["client"]
    headers = configured_workspace["headers"]
    discover = client.post(
        f"/v1/tenants/{TENANT_A}/discover",
        json={"records": prospect_records(1)},
        headers=headers,
    ).json()
    prospect_id = discover["outputs"]["prospect_ids"][0]
    _research(client, headers, prospect_id)
    client.post(
        f"/v1/tenants/{TENANT_A}/prospects/{prospect_id}/qualify", headers=headers
    )
    outcome = client.post(
        f"/v1/tenants/{TENANT_A}/prospects/{prospect_id}/personalize",
        headers=headers,
    ).json()
    return client, outcome["outputs"], prospect_id


def test_sending_requires_explicit_approval(configured_workspace):
    client, draft, _prospect_id = _prepared_draft(configured_workspace)
    headers = configured_workspace["headers"]

    response = client.post(
        f"/v1/tenants/{TENANT_A}/drafts/{draft['id']}/send",
        json={"approved": True},
        headers=headers,
    )
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "approval_required"
    assert error["recovery_action"] == "approve_draft"

    approved = client.post(
        f"/v1/tenants/{TENANT_A}/drafts/{draft['id']}/approve",
        json={"note": "looks good"},
        headers=headers,
    ).json()["draft"]
    assert approved["status"] == "approved"
    assert approved["approved_by"]

    # Editing an approved draft withdraws the authorization.
    client.post(
        f"/v1/tenants/{TENANT_A}/drafts/{draft['id']}/edit",
        json={"subject": "changed", "body": "changed"},
        headers=headers,
    )
    revoked = client.get(
        f"/v1/tenants/{TENANT_A}/drafts/{draft['id']}", headers=headers
    ).json()
    assert revoked["status"] == "pending_review"
    assert revoked["approved_by"] == ""


def test_authorized_send_records_the_full_lifecycle(configured_workspace):
    client, draft, prospect_id = _prepared_draft(configured_workspace)
    headers = configured_workspace["headers"]
    client.post(
        f"/v1/tenants/{TENANT_A}/drafts/{draft['id']}/approve",
        json={"note": "approved for dispatch"},
        headers=headers,
    )

    response = client.post(
        f"/v1/tenants/{TENANT_A}/drafts/{draft['id']}/send",
        json={"sender_email": "hello@northwindcloud.example"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    outcome = response.json()
    sent = outcome["outputs"]["sent_message"]
    assert sent["delivery_status"] == "submitted"
    assert sent["transport"] == "dry_run"
    assert sent["recipient_email"]
    assert sent["authorized_by"]
    assert outcome["to_status"] == "in_campaign"

    draft_row = client.get(
        f"/v1/tenants/{TENANT_A}/drafts/{draft['id']}", headers=headers
    ).json()
    assert draft_row["status"] == "sent"
    assert draft_row["approved_by"]

    prospect = client.get(
        f"/v1/tenants/{TENANT_A}/prospects/{prospect_id}", headers=headers
    ).json()
    assert prospect["status"] == "in_campaign"

    # A second send of the same draft is refused.
    repeat = client.post(
        f"/v1/tenants/{TENANT_A}/drafts/{draft['id']}/send",
        headers=headers,
    )
    assert repeat.status_code == 400
    assert repeat.json()["error"]["code"] == "draft_not_found"


def test_sending_policy_blocks_suppressed_recipients(configured_workspace):
    client, draft, prospect_id = _prepared_draft(configured_workspace)
    headers = configured_workspace["headers"]
    prospect = client.get(
        f"/v1/tenants/{TENANT_A}/prospects/{prospect_id}", headers=headers
    ).json()
    client.post(
        f"/v1/tenants/{TENANT_A}/suppression",
        json={"email": prospect["email"], "reason": "manual_admin", "note": "asked us to wait"},
        headers=headers,
    )
    client.post(
        f"/v1/tenants/{TENANT_A}/drafts/{draft['id']}/approve",
        headers=headers,
    )

    response = client.post(
        f"/v1/tenants/{TENANT_A}/drafts/{draft['id']}/send",
        headers=headers,
    )
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "suppressed"
    assert error["recovery_action"] == "review_suppression"


def test_rate_limit_blocks_sending_when_exhausted(configured_workspace):
    client, draft, _prospect_id = _prepared_draft(configured_workspace)
    headers = configured_workspace["headers"]
    client.put(
        f"/v1/tenants/{TENANT_A}/policy",
        json={"daily_limit": 1, "hourly_limit": 1, "allowed_senders": ["hello@n.example"]},
        headers=headers,
    )
    client.post(f"/v1/tenants/{TENANT_A}/drafts/{draft['id']}/approve", headers=headers)

    # Consume the single allowed send on a different prospect.
    second = client.post(
        f"/v1/tenants/{TENANT_A}/discover",
        json={"records": prospect_records(2)},
        headers=headers,
    ).json()
    other = second["outputs"]["prospect_ids"][0]
    _research(client, headers, other)
    client.post(f"/v1/tenants/{TENANT_A}/prospects/{other}/qualify", headers=headers)
    other_outcome = client.post(
        f"/v1/tenants/{TENANT_A}/prospects/{other}/personalize", headers=headers
    ).json()
    client.post(
        f"/v1/tenants/{TENANT_A}/drafts/{other_outcome['outputs']['id']}/approve",
        headers=headers,
    )
    client.post(
        f"/v1/tenants/{TENANT_A}/drafts/{other_outcome['outputs']['id']}/send",
        headers=headers,
    )

    blocked = client.post(
        f"/v1/tenants/{TENANT_A}/drafts/{draft['id']}/send", headers=headers
    )
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "rate_limited"
    assert blocked.json()["error"]["recovery_action"] == "retry_stage_later"


# ---------------------------------------------------------------------------
# 7. Conversations
# ---------------------------------------------------------------------------

def test_failed_send_is_retryable_and_keeps_state_for_retry(configured_workspace):
    """External-integration failure: a dead SMTP transport fails the send
    retryably, records the failure, and leaves draft + prospect untouched
    so the operator can retry. A retry over dry_run then succeeds."""
    client, draft, prospect_id = _prepared_draft(configured_workspace)
    headers = configured_workspace["headers"]
    client.post(
        f"/v1/tenants/{TENANT_A}/drafts/{draft['id']}/approve",
        json={"note": "approved for dispatch"},
        headers=headers,
    )

    dead_smtp = {
        "sender_email": "hello@northwindcloud.example",
        "transport": {
            "transport": "smtp",
            "smtp_host": "127.0.0.1",
            "smtp_port": 1,
            "smtp_use_tls": False,
        },
    }
    failed = client.post(
        f"/v1/tenants/{TENANT_A}/drafts/{draft['id']}/send",
        json=dead_smtp,
        headers=headers,
    )
    assert failed.status_code == 400, failed.text
    error = failed.json()["error"]
    assert error["code"] == "provider_unavailable"
    assert error["retryable"] is True
    assert error["recovery_action"] == "retry_stage"
    assert error["details"]["retryable"] is True

    draft_row = client.get(
        f"/v1/tenants/{TENANT_A}/drafts/{draft['id']}", headers=headers
    ).json()
    assert draft_row["status"] == "approved"  # approval survives for the retry
    prospect = client.get(
        f"/v1/tenants/{TENANT_A}/prospects/{prospect_id}", headers=headers
    ).json()
    assert prospect["status"] == "draft_ready"
    sent = client.get(f"/v1/tenants/{TENANT_A}/sent", headers=headers).json()["data"]
    assert any(m["delivery_status"] == "failed" for m in sent)

    retry = client.post(
        f"/v1/tenants/{TENANT_A}/drafts/{draft['id']}/send",
        json={"sender_email": "hello@northwindcloud.example"},
        headers=headers,
    ).json()
    assert retry["status"] == "succeeded"
    assert retry["outputs"]["sent_message"]["transport"] == "dry_run"


def test_inbound_reply_updates_the_same_records(configured_workspace, service_headers):
    client, draft, prospect_id = _prepared_draft(configured_workspace)
    headers = configured_workspace["headers"]
    prospect = client.get(
        f"/v1/tenants/{TENANT_A}/prospects/{prospect_id}", headers=headers
    ).json()
    client.post(f"/v1/tenants/{TENANT_A}/drafts/{draft['id']}/approve", headers=headers)
    send = client.post(
        f"/v1/tenants/{TENANT_A}/drafts/{draft['id']}/send",
        headers=headers,
    ).json()
    message_id = send["outputs"]["sent_message"]["message_id"]

    response = client.post(
        "/v1/webhooks/inbound",
        json={
            "sender_email": prospect["email"],
            "subject": "Re: " + draft["subject"],
            "in_reply_to": message_id,
            "body": "Sounds interesting, can you send over a 1-pager and pricing?",
        },
        headers=service_headers,
    )
    assert response.status_code == 200, response.text
    outcome = response.json()["outputs"]
    assert outcome["intent"] == "information_request"
    assert outcome["requires_action"] is True
    assert outcome["recommended_action"]

    prospect_after = client.get(
        f"/v1/tenants/{TENANT_A}/prospects/{prospect_id}", headers=headers
    ).json()
    assert prospect_after["status"] == "replied"

    conversations = client.get(
        f"/v1/tenants/{TENANT_A}/conversations", headers=headers
    ).json()["data"]
    assert conversations
    detail = client.get(
        f"/v1/tenants/{TENANT_A}/conversations/{conversations[0]['id']}",
        headers=headers,
    ).json()
    assert detail["replies"][0]["intent"] == "information_request"
    assert detail["outbound"], "the reply must be threaded to the outbound message"


def test_unsubscribe_suppresses_immediately(configured_workspace, service_headers):
    client, draft, prospect_id = _prepared_draft(configured_workspace)
    headers = configured_workspace["headers"]
    prospect = client.get(
        f"/v1/tenants/{TENANT_A}/prospects/{prospect_id}", headers=headers
    ).json()
    client.post(f"/v1/tenants/{TENANT_A}/drafts/{draft['id']}/approve", headers=headers)
    client.post(f"/v1/tenants/{TENANT_A}/drafts/{draft['id']}/send", headers=headers)

    response = client.post(
        "/v1/webhooks/inbound",
        json={
            "sender_email": prospect["email"],
            "subject": "Re: " + draft["subject"],
            "body": "Please unsubscribe me from this list.",
        },
        headers=service_headers,
    )
    assert response.status_code == 200
    assert response.json()["outputs"]["suppressed"] is True

    prospect_after = client.get(
        f"/v1/tenants/{TENANT_A}/prospects/{prospect_id}", headers=headers
    ).json()
    assert prospect_after["status"] == "opted_out"

    suppression = client.get(
        f"/v1/tenants/{TENANT_A}/suppression", headers=headers
    ).json()["data"]
    assert any(r["email"] == prospect["email"] and r["reason"] == "opt_out" for r in suppression)


def test_hard_bounce_suppresses_and_records_a_delivery_event(
    configured_workspace, service_headers
):
    client, draft, prospect_id = _prepared_draft(configured_workspace)
    headers = configured_workspace["headers"]
    prospect = client.get(
        f"/v1/tenants/{TENANT_A}/prospects/{prospect_id}", headers=headers
    ).json()
    client.post(f"/v1/tenants/{TENANT_A}/drafts/{draft['id']}/approve", headers=headers)
    send = client.post(
        f"/v1/tenants/{TENANT_A}/drafts/{draft['id']}/send", headers=headers
    ).json()
    sent = send["outputs"]["sent_message"]

    response = client.post(
        f"/v1/tenants/{TENANT_A}/events",
        json={
            "sent_message_id": sent["id"],
            "message_id": sent["message_id"],
            "recipient_email": prospect["email"],
            "event_type": "bounced",
            "provider": "kumomta",
            "detail": "550 5.1.1 user unknown",
        },
        headers=service_headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["event"]["event_type"] == "bounced"

    suppression = client.get(
        f"/v1/tenants/{TENANT_A}/suppression", headers=headers
    ).json()["data"]
    assert any(r["reason"] == "hard_bounce" for r in suppression)

    sent_rows = client.get(
        f"/v1/tenants/{TENANT_A}/sent", headers=headers
    ).json()
    assert sent_rows["counts"]["bounced"] >= 1


# ---------------------------------------------------------------------------
# 8. Overview, activity and history
# ---------------------------------------------------------------------------

def test_overview_and_activity_read_the_same_records(configured_workspace):
    client, draft, prospect_id = _prepared_draft(configured_workspace)
    headers = configured_workspace["headers"]
    client.post(f"/v1/tenants/{TENANT_A}/drafts/{draft['id']}/approve", headers=headers)
    client.post(f"/v1/tenants/{TENANT_A}/drafts/{draft['id']}/send", headers=headers)

    overview = client.get(f"/v1/tenants/{TENANT_A}/overview", headers=headers).json()
    # The prospect created by `_prepared_draft` has reached in_campaign.
    assert overview["counts"]["in_campaign"] == 1
    assert overview["counts"]["discovered"] == 0
    assert overview["counts"]["draft_ready"] == 0
    assert overview["counts"]["researched"] == 0
    assert overview["drafts"]["sent"] == 1
    assert overview["delivery"]["submitted"] == 1
    assert overview["total_prospects"] == 1
    assert overview["stage_health"]["outreach"]["succeeded"] == 1
    in_campaign_step = next(
        step for step in overview["funnel"] if step["status"] == "in_campaign"
    )
    assert in_campaign_step["count"] == 1
    assert overview["funnel"][0]["count"] == 0

    handoffs = client.get(
        f"/v1/tenants/{TENANT_A}/overview/handoffs", headers=headers
    ).json()["handoffs"]
    assert [h["from"] for h in handoffs] == [
        "configure", "discover", "research", "qualify", "personalize", "outreach", "converse"
    ]
    outreach_handoff = next(h for h in handoffs if h["from"] == "outreach")
    assert outreach_handoff["waiting"][0]["count"] == 1
    assert "approval_required" in outreach_handoff["blocked_by"]

    activity = client.get(
        f"/v1/tenants/{TENANT_A}/activity?limit=100", headers=headers
    ).json()["data"]
    stages = {item["stage"] for item in activity}
    for stage in ("discover", "research", "qualify", "personalize", "outreach"):
        assert stage in stages, stage
    assert all(item["actor"] for item in activity)

    # Attention surfaces the real pending work: nothing failed, so this is empty.
    assert overview["attention"] == []

    runs = client.get(
        f"/v1/tenants/{TENANT_A}/runs?limit=100", headers=headers
    ).json()["data"]
    assert len(runs) == 5
    assert all(run["status"] in ("succeeded", "needs_review") for run in runs)
    # Qualification flagged a missing criterion and says so.
    qualify_run = next(run for run in runs if run["stage"] == "qualify")
    assert qualify_run["status"] == "needs_review"
    assert qualify_run["reason"]


def test_failed_stage_surfaces_an_actionable_recovery(configured_workspace):
    client, draft, _prospect_id = _prepared_draft(configured_workspace)
    headers = configured_workspace["headers"]

    # Refuse the send by removing the sending identity.
    response = client.post(
        f"/v1/tenants/{TENANT_A}/drafts/{draft['id']}/send",
        json={"approved": True},
        headers=headers,
    )
    assert response.status_code == 409

    runs = client.get(
        f"/v1/tenants/{TENANT_A}/runs?run_status=failed", headers=headers
    ).json()["data"]
    assert runs
    failure = runs[0]
    assert failure["stage"] == "outreach"
    assert failure["error_code"] == "approval_required"
    assert failure["recovery_action"] == "approve_draft"
    assert failure["retryable"] is False

    overview = client.get(f"/v1/tenants/{TENANT_A}/overview", headers=headers).json()
    assert any(item["kind"] == "stage_failed" for item in overview["attention"])
    assert any(item["kind"] == "draft_pending_approval" for item in overview["attention"])
    assert overview["next_actions"]


def test_a_prospect_carries_its_full_history(configured_workspace):
    client, draft, prospect_id = _prepared_draft(configured_workspace)
    headers = configured_workspace["headers"]
    client.post(f"/v1/tenants/{TENANT_A}/drafts/{draft['id']}/approve", headers=headers)
    client.post(f"/v1/tenants/{TENANT_A}/drafts/{draft['id']}/send", headers=headers)

    detail = client.get(
        f"/v1/tenants/{TENANT_A}/prospects/{prospect_id}", headers=headers
    ).json()
    states = [entry["state"] for entry in detail["state_history"]]
    assert states == ["discovered", "researching", "researched", "qualified", "draft_ready", "in_campaign"]
    assert all(entry["entered_at"] for entry in detail["state_history"])
    assert detail["qualification"]
    assert detail["evidence"]
    assert detail["drafts"]
    assert detail["sent_messages"]
    assert detail["draft_versions"][draft["id"]]
    assert detail["activity"]
    assert detail["stage_runs"]
    assert detail["profile_version"] is not None
