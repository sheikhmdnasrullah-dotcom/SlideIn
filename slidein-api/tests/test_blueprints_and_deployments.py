"""Foundation tests: blueprints, adapters, deployment lifecycle."""

from __future__ import annotations

import pytest

from slidein_api.blueprints import (
    get_blueprint,
    list_blueprints,
    validate_deployment_config,
)
from slidein_api.blueprints.registry import PROSPECT_TO_CONVERSATION_V1
from slidein_api.contracts import StageName
from slidein_api.deployments import (
    DeploymentModel,
    DeploymentRecord,
    DeploymentStatus,
    TransitionError,
    can_transition,
)
from slidein_api.integrations import (
    AdapterStatus,
    DryRunCalendarAdapter,
    DryRunCrmAdapter,
    DryRunEnrichmentAdapter,
    DryRunMailTransport,
    DryRunMessagingAdapter,
)


def _full_config(**overrides):
    config = {
        "transport": "dry_run",
        "profile": {"business_name": "Acme Mortgages"},
        "offers": [{"name": "First-time buyer review"}],
        "icps": [{"name": "London renters 25-35"}],
        "sending": {
            "sender": "sam@acme.example",
            "physical_address": "1 High St, London",
            "lawful_basis": "B2B legitimate interest, verified list",
        },
        "approvals": {"approver": "sam@acme.example", "sla_hours": 24},
    }
    config.update(overrides)
    return config


# -- blueprints ---------------------------------------------------------------

def test_blueprint_is_registered_and_versioned():
    found = get_blueprint("prospect_to_conversation", "1.0.0")
    assert found is PROSPECT_TO_CONVERSATION_V1
    assert found in list_blueprints()
    with pytest.raises(KeyError):
        get_blueprint("prospect_to_conversation", "9.9.9")


def test_blueprint_stages_match_implemented_contracts():
    known = {s.value for s in StageName}
    assert set(PROSPECT_TO_CONVERSATION_V1.stages) <= known
    assert "outreach" in PROSPECT_TO_CONVERSATION_V1.stages
    gates = {g.name for g in PROSPECT_TO_CONVERSATION_V1.approval_gates}
    assert {"draft_approval", "live_send_enable"} <= gates


def test_complete_config_validates_ready():
    result = validate_deployment_config(
        PROSPECT_TO_CONVERSATION_V1, _full_config()
    )
    assert result.ok, result.reasons()


def test_missing_required_blocks_readiness():
    config = _full_config()
    del config["offers"]
    del config["sending"]["physical_address"]
    result = validate_deployment_config(PROSPECT_TO_CONVERSATION_V1, config)
    assert not result.ok
    assert "offers" in result.missing_required
    assert "sending.physical_address" in result.missing_required


def test_smtp_transport_requires_smtp_integration():
    config = _full_config(transport="smtp")
    result = validate_deployment_config(PROSPECT_TO_CONVERSATION_V1, config)
    assert not result.ok
    assert "integrations.smtp" in result.missing_integrations

    config["integrations"] = {"smtp": {"secret_ref": "client/smtp"}}
    result = validate_deployment_config(PROSPECT_TO_CONVERSATION_V1, config)
    assert result.ok, result.reasons()


def test_unsupported_requirements_block_with_reasons():
    config = _full_config(
        unsupported_requirements=["voice outbound calling", "auto-reply without IMAP"]
    )
    result = validate_deployment_config(PROSPECT_TO_CONVERSATION_V1, config)
    assert not result.ok
    assert len(result.unsupported) == 2
    assert any("voice" in r for r in result.reasons())


def test_unknown_keys_warn_but_do_not_block():
    result = validate_deployment_config(
        PROSPECT_TO_CONVERSATION_V1, _full_config(department="sales")
    )
    assert result.ok
    assert any("department" in w for w in result.warnings)


# -- adapters -----------------------------------------------------------------

def test_dry_run_mail_records_without_sending():
    transport = DryRunMailTransport()
    out = transport.dispatch(
        sender="a@x.example", recipient="b@y.example",
        subject="hi", body="hello",
    )
    assert out["ok"] and out["provider"] == "slidein.dry_run"
    assert len(transport.sent) == 1
    assert transport.health().status is AdapterStatus.DISCONNECTED


def test_calendar_requires_configured_provider():
    adapter = DryRunCalendarAdapter()
    assert adapter.health().status is AdapterStatus.DISCONNECTED
    assert adapter.create_event(
        title="t", start_iso="2026-01-01T10:00:00Z",
        end_iso="2026-01-01T10:30:00Z", attendees=[],
    )["ok"] is False
    assert DryRunCalendarAdapter(configured_url="https://cal.example/sam").health(
    ).status is AdapterStatus.CONNECTED


def test_other_dry_runs_are_safe_noops():
    assert DryRunCrmAdapter().upsert_contact(
        external_id="c1", fields={"name": "n"})["dry_run"] is True
    assert DryRunEnrichmentAdapter().enrich(domain="x.example")["signals"] == []
    assert DryRunMessagingAdapter().send_message(
        channel="email", to="a@x.example", text="t")["ok"] is True


def test_connection_summary_carries_no_secret_values():
    info = DryRunMailTransport().health()
    summary = info.summary()
    assert summary["secret_ref"] == ""
    assert "sk_" not in str(summary)


# -- lifecycle ----------------------------------------------------------------

def test_happy_path_lifecycle_with_history():
    record = DeploymentRecord(
        deployment_id="dep_1", client_name="Acme",
        workspace_id="ten_acme", blueprint_name="prospect_to_conversation",
        blueprint_version="1.0.0", model=DeploymentModel.DEDICATED,
        environment="vps-acme",
    )
    for to in ("awaiting_client", "ready", "deploying", "active"):
        record = record.transition(
            DeploymentStatus(to), reason=f"move to {to}", actor="founder")
    assert record.status is DeploymentStatus.ACTIVE
    assert len(record.history) == 4
    assert record.history[0][0] == "planned"
    assert not record.is_terminal


def test_illegal_transition_rejected_and_reason_required():
    record = DeploymentRecord(
        deployment_id="dep_2", client_name="Acme",
        workspace_id="ten_acme", blueprint_name="prospect_to_conversation",
        blueprint_version="1.0.0", model=DeploymentModel.DEDICATED,
        environment="vps-acme",
    )
    assert not can_transition(DeploymentStatus.PLANNED, DeploymentStatus.ACTIVE)
    with pytest.raises(TransitionError):
        record.transition(DeploymentStatus.ACTIVE, reason="skip", actor="founder")
    with pytest.raises(TransitionError):
        record.transition(DeploymentStatus.READY, reason="  ", actor="founder")


def test_pause_resume_and_retire_archive():
    record = DeploymentRecord(
        deployment_id="dep_3", client_name="Acme",
        workspace_id="ten_acme", blueprint_name="prospect_to_conversation",
        blueprint_version="1.0.0", model=DeploymentModel.DEDICATED,
        environment="vps-acme", status=DeploymentStatus.ACTIVE,
    )
    paused = record.transition(DeploymentStatus.PAUSED, reason="client holiday",
                               actor="founder")
    active = paused.transition(DeploymentStatus.ACTIVE, reason="resume",
                               actor="founder")
    retiring = active.transition(DeploymentStatus.RETIRING,
                                 reason="contract ended", actor="founder")
    archived = retiring.transition(DeploymentStatus.ARCHIVED,
                                   reason="data exported, keys revoked",
                                   actor="founder")
    assert archived.is_terminal
    assert len(archived.history) == 4


def test_attention_states_flagged():
    kwargs = dict(
        deployment_id="d", client_name="c", workspace_id="t",
        blueprint_name="b", blueprint_version="1.0.0",
        model=DeploymentModel.DEDICATED, environment="e",
    )
    assert DeploymentRecord(status=DeploymentStatus.DEGRADED, **kwargs
                            ).needs_attention
    assert DeploymentRecord(status=DeploymentStatus.AWAITING_CLIENT, **kwargs
                            ).needs_attention
    assert not DeploymentRecord(status=DeploymentStatus.ACTIVE, **kwargs
                                ).needs_attention
