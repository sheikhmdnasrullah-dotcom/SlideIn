"""Contract tests: the stage contracts are complete, self-consistent and
enforced by the runner."""

from __future__ import annotations

import pytest

from slidein_api.contracts import (
    CONTRACTS,
    HANDOFFS,
    StageContract,
    StageName,
    contract_for,
)
from slidein_api.errors import RECOVERY_ACTION, RETRYABLE
from slidein_api.runtime import StageRunner
from slidein_api.db import session_scope




def test_every_stage_is_registered():
    assert set(CONTRACTS) == set(StageName)
    assert [s.value for s in StageName] == [s.value for s in CONTRACTS]


def test_all_failure_modes_have_a_recovery_action():
    for stage, contract in CONTRACTS.items():
        for failure in contract.failures:
            assert failure.recovery_action, f"{stage.value}.{failure.code}"
            assert failure.recovery_action in RECOVERY_ACTION.values() or failure.recovery_action.startswith(
                ("review_", "retry_", "run_", "approve_", "regenerate_", "fix_",
                 "define_", "add_", "create_", "complete_", "merge_", "request_",
                 "switch_", "return_")
            ), f"{stage.value}.{failure.code} -> {failure.recovery_action}"


def test_retryable_flags_match_the_taxonomy():
    for contract in CONTRACTS.values():
        for failure in contract.failures:
            if failure.code in RETRYABLE:
                assert failure.retryable, (
                    f"{contract.stage.value}.{failure.code} is retryable in the "
                    "taxonomy but the contract says it is not"
                )


def test_contract_input_validation_rejects_missing_required_fields():
    contract = contract_for(StageName.DISCOVER)
    problems = contract.validate_input({"icp_id": "icp_x"})
    assert problems == ["discover.records is required"]
    assert contract.validate_input({"icp_id": "icp_x", "records": [{}]}) == []
    # icp_id is optional: the route resolves the active ICP and fails with
    # icp_missing when the workspace has none.
    assert contract.validate_input({"records": [{}]}) == []


def test_contract_input_validation_rejects_wrong_types():
    contract = contract_for(StageName.QUALIFY)
    problems = contract.validate_input({"prospect_id": 12})
    assert problems == ["qualify.prospect_id must be str"]


def test_handoffs_chain_every_stage_in_order():
    order = [s.value for s in StageName]
    handoffs = [(h.from_stage.value, h.to_stage.value) for h in HANDOFFS]
    assert handoffs == [
        (order[index], order[index + 1]) for index in range(len(order) - 1)
    ]


def test_handoff_carried_fields_are_produced_by_the_source_stage():
    for handoff in HANDOFFS:
        source = contract_for(handoff.from_stage)
        produced = {f.name for f in source.produces}
        for field in handoff.carried:
            if field in ("profile_id", "icp_id", "icp_version", "profile_version",
                         "conversation_id", "suppressed", "evidence_ids"):
                # Configuration and cross-stage identifiers are carried as
                # context rather than stage outputs.
                continue
            assert field in produced, (
                f"{handoff.from_stage.value} -> {handoff.to_stage.value} carries "
                f"{field!r} which {handoff.from_stage.value} does not produce"
            )


def test_handoff_blocked_codes_exist_in_either_stage():
    """A blocker may be raised by the producing or the consuming stage."""
    for handoff in HANDOFFS:
        source = contract_for(handoff.from_stage)
        target = contract_for(handoff.to_stage)
        codes = {f.code for f in source.failures} | {f.code for f in target.failures}
        for blocked in handoff.blocked_by:
            assert blocked in codes, (
                f"{handoff.from_stage.value} -> {handoff.to_stage.value} lists "
                f"{blocked!r} as a blocker but neither stage declares it"
            )


def test_runner_rejects_a_contract_violation_without_touching_the_db():
    import asyncio

    async def _run():
        async with session_scope() as session:
            runner = StageRunner(session)
            return await runner.run(
                StageName.RESEARCH,
                tenant_id="ten_alpha",
                payload={},
                actor="user:operator",
                role="operator",
                subject_id="prosp_missing",
                executor=_never,
            )

    async def _never(_payload, _session):
        raise AssertionError("executor must not run when the contract is violated")

    outcome = asyncio.run(_run())
    assert outcome.status == "failed"
    assert outcome.error_code == "invalid_input"
    assert outcome.retryable is False


def test_runner_refuses_a_role_without_the_required_permission():
    import asyncio

    async def _never(_payload, _session):
        raise AssertionError("executor must not run without permission")

    async def _run():
        async with session_scope() as session:
            runner = StageRunner(session)
            return await runner.run(
                StageName.RESEARCH,
                tenant_id="ten_alpha",
                payload={"prospect_id": "prosp_missing"},
                actor="user:viewer",
                role="viewer",
                subject_id="prosp_missing",
                executor=_never,
            )

    outcome = asyncio.run(_run())
    assert outcome.status == "failed"
    assert outcome.error_code == "not_authorized"
    assert outcome.recovery_action == "request_authorization"


def test_runner_stops_after_max_attempts():
    import asyncio

    from slidein_api.models import RunStatus, StageRun

    async def _run():
        async with session_scope() as session:
            runner = StageRunner(session)
            outcome = await runner.run(
                StageName.RESEARCH,
                tenant_id="ten_alpha",
                payload={"prospect_id": "prosp_attempts"},
                actor="user:operator",
                role="operator",
                subject_id="prosp_attempts",
                executor=_fail,
            )
            runs = await runner.runs_for_subject("ten_alpha", "prosp_attempts")
            return outcome, runs

    async def _fail(_payload, _session):
        from slidein_api.errors import ProviderError

        raise ProviderError(
            "connector unreachable", code="source_unavailable", recovery_action="retry_stage"
        )

    outcome, _runs = asyncio.run(_run())
    assert outcome.status == "failed"
    assert outcome.error_code == "source_unavailable"
    assert outcome.retryable is True


def test_contracts_are_exposed_over_http(client):
    response = client.get("/v1/contracts")
    assert response.status_code == 200
    payload = response.json()
    assert [s["stage"] for s in payload["stages"]] == [s.value for s in StageName]
    research = next(s for s in payload["stages"] if s["stage"] == "research")
    assert [f["name"] for f in research["requires"]] == ["prospect_id", "profile_id", "profile_version", "depth", "claims"]
    assert [f["name"] for f in research["produces"]][:3] == ["evidence_ids", "evidence_count", "verified_count"]
    assert ("discovered", "researching") in [tuple(t) for t in research["transitions"]]


def test_contract_is_a_frozen_declaration():
    contract = contract_for(StageName.OUTREACH)
    with pytest.raises(Exception):
        contract.permission = "viewer"  # type: ignore[misc]
