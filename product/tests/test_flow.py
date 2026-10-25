"""The universal flow is canonical, ordered, and enforced.

- Stage order and provenance requirements are fixed.
- Legacy aliases resolve onto canonical stages.
- The adaptation engine rejects off-flow workflow proposals.
"""

import pytest

from product.core.adaptation import InsufficientEvidence
from product.core.flow import (FlowViolation, STAGE_IDS, UNIVERSAL_FLOW,
                               assert_flow_aligned, canonical_stage,
                               is_canonical_order)
from product.core.capabilities import CapabilityRegistry
from product.core.adaptation import AdaptationEngine, EvidenceStore
from product.core.workspace import WorkspaceStore, universal_workspace
from product.core.scopes import Role


def test_canonical_order_and_provenance():
    assert STAGE_IDS == ("configure", "discover", "research", "qualify",
                         "personalize", "outreach", "converse")
    for stage in UNIVERSAL_FLOW:
        assert stage.outputs, f"{stage.stage_id} must declare outputs"
        assert stage.provenance, f"{stage.stage_id} must require provenance"
    assert is_canonical_order(STAGE_IDS)
    assert not is_canonical_order(("research", "discover"))


def test_legacy_aliases_resolve():
    assert canonical_stage("match_offer") == "qualify"
    assert canonical_stage("Validate") == "outreach"
    assert canonical_stage("measure") == "converse"
    assert canonical_stage("converse") == "converse"
    assert canonical_stage("quantum_leap") is None


def test_off_flow_steps_rejected():
    with pytest.raises(FlowViolation):
        assert_flow_aligned(("research", "teleport", "outreach"))
    with pytest.raises(FlowViolation):
        assert_flow_aligned(("spam_everyone",))
    assert assert_flow_aligned(("discover", "qualify")) == ("discover", "qualify")


def test_adaptation_engine_enforces_flow():
    registry = CapabilityRegistry()
    ws = WorkspaceStore(registry)
    ev = EvidenceStore()
    engine = AdaptationEngine(registry, ws, ev)
    for t in ("t1",):
        ws.register(universal_workspace(t), role=Role.SYSTEM)
    e = engine.record_evidence(tenant_id="t1", kind="explicit_fact",
                               fact="user wants a weekly digest",
                               source_ref="chat", confidence=1.0, verified=True,
                               caller_tenant_id="t1", role=Role.TENANT_MEMBER)
    with pytest.raises(FlowViolation):
        engine.propose_workflow(tenant_id="t1", name="bad", purpose="x",
                                steps=("research", "hacked_stage"), trigger="daily",
                                evidence_refs=(e.evidence_id,),
                                caller_tenant_id="t1", role=Role.TENANT_MEMBER)
    prop = engine.propose_workflow(tenant_id="t1", name="digest",
                                   purpose="weekly digest",
                                   steps=("research", "personalize", "outreach"),
                                   trigger="weekly",
                                   evidence_refs=(e.evidence_id,),
                                   caller_tenant_id="t1", role=Role.TENANT_MEMBER)
    assert prop.steps == ("research", "personalize", "outreach")
