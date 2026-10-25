"""Adaptive workspace: registry validation, versioning, approval policy,
rollback, adaptation evidence rules, and tenant isolation."""

import pytest

from product.core.adaptation import (AdaptationEngine, EvidenceStore,
                                     InsufficientEvidence)
from product.core.capabilities import CapabilityRegistry
from product.core.errors import CrossTenantAccess
from product.core.scopes import Role
from product.core.workspace import (ChangeRisk, InvalidWorkspaceConfig,
                                    WorkspaceStore, universal_workspace)


@pytest.fixture
def env():
    registry = CapabilityRegistry()
    workspaces = WorkspaceStore(registry)
    evidence = EvidenceStore()
    engine = AdaptationEngine(registry, workspaces, evidence)
    for tenant in ("tenant-a", "tenant-b"):
        workspaces.register(universal_workspace(tenant), role=Role.SYSTEM)
    return registry, workspaces, evidence, engine


# --------------------------------------------------------------------------- #
def test_universal_workspace_default(env):
    _, ws, _, _ = env
    cfg = ws.current("tenant-a", caller_tenant_id="tenant-a", role=Role.TENANT_ADMIN)
    assert cfg.version == 1
    assert "overview" in cfg.enabled_modules and "settings" in cfg.enabled_modules
    assert cfg.widgets == ()


def test_invalid_config_rejected(env):
    _, ws, _, _ = env
    bad = universal_workspace("tenant-x")
    object.__setattr__(bad, "enabled_modules", ("overview", "nope"))
    with pytest.raises(InvalidWorkspaceConfig):
        ws.register(bad, role=Role.SYSTEM)
    # widget from a module that doesn't support widgets
    from product.core.workspace import WidgetConfig
    bad2 = universal_workspace("tenant-y")
    object.__setattr__(bad2, "widgets", (WidgetConfig("contacts", "widget"),))
    with pytest.raises(InvalidWorkspaceConfig):
        ws.register(bad2, role=Role.SYSTEM)


def test_versioning_and_rollback(env):
    _, ws, _, engine = env
    for _ in range(3):
        engine.record_evidence(tenant_id="tenant-a", kind="behavior",
                               fact="user opened research module daily",
                               source_ref="ui.nav", confidence=0.9, verified=True,
                               caller_tenant_id="tenant-a", role=Role.TENANT_MEMBER)
    prop = engine.propose_workspace_changes(
        tenant_id="tenant-a", caller_tenant_id="tenant-a",
        role=Role.TENANT_MEMBER, rationale="frequent research use")
    cfg = ws.apply("tenant-a", prop, caller_tenant_id="tenant-a",
                   role=Role.TENANT_MEMBER, auto_apply_low_risk=True)
    assert cfg.version == 2
    assert cfg.module_order.index("research") < cfg.module_order.index("contacts")
    assert any(w.module_id == "research" for w in cfg.widgets)
    restored = ws.rollback("tenant-a", 1, caller_tenant_id="tenant-a",
                           role=Role.TENANT_ADMIN)
    assert restored.version == 3
    assert restored.module_order == universal_workspace("x").module_order
    assert ws.history("tenant-a", caller_tenant_id="tenant-a",
                      role=Role.TENANT_ADMIN)[-1].version == 3


def test_consequential_requires_approval(env):
    _, ws, _, _ = env
    prop = ws.propose("tenant-a", changes={"integration_refs": ("twenty_crm",)},
                      evidence_refs=("e1",), risk=ChangeRisk.CONSEQUENTIAL,
                      rationale="CRM needed",
                      caller_tenant_id="tenant-a", role=Role.TENANT_MEMBER)
    with pytest.raises(CrossTenantAccess):
        ws.apply("tenant-a", prop, caller_tenant_id="tenant-a",
                 role=Role.TENANT_MEMBER)
    approved = ws.approve_proposal("tenant-a", prop, caller_tenant_id="tenant-a",
                                   role=Role.TENANT_ADMIN)
    cfg = ws.apply("tenant-a", approved, caller_tenant_id="tenant-a",
                   role=Role.TENANT_ADMIN)
    assert cfg.integration_refs == ("twenty_crm",)


def test_low_risk_requires_opt_in(env):
    _, ws, _, engine = env
    engine.record_evidence(tenant_id="tenant-a", kind="explicit_fact",
                           fact="user_feedback: pin analytics first",
                           source_ref="chat", confidence=1.0, verified=True,
                           caller_tenant_id="tenant-a", role=Role.TENANT_MEMBER)
    engine.record_evidence(tenant_id="tenant-a", kind="behavior",
                           fact="user opened analytics module",
                           source_ref="ui.nav", confidence=0.9, verified=True,
                           caller_tenant_id="tenant-a", role=Role.TENANT_MEMBER)
    engine.record_evidence(tenant_id="tenant-a", kind="behavior",
                           fact="user opened analytics module again",
                           source_ref="ui.nav", confidence=0.9, verified=True,
                           caller_tenant_id="tenant-a", role=Role.TENANT_MEMBER)
    prop = engine.propose_workspace_changes(
        tenant_id="tenant-a", caller_tenant_id="tenant-a",
        role=Role.TENANT_MEMBER, rationale="analytics heavy use")
    with pytest.raises(CrossTenantAccess):
        ws.apply("tenant-a", prop, caller_tenant_id="tenant-a",
                 role=Role.TENANT_MEMBER)  # no opt-in


def test_tenant_isolation(env):
    _, ws, evidence, engine = env
    with pytest.raises(CrossTenantAccess):
        ws.current("tenant-b", caller_tenant_id="tenant-a", role=Role.TENANT_MEMBER)
    with pytest.raises(CrossTenantAccess):
        evidence.list("tenant-b", caller_tenant_id="tenant-a", role=Role.TENANT_MEMBER)
    engine.record_evidence(tenant_id="tenant-a", kind="behavior",
                           fact="user opened research module",
                           source_ref="ui", confidence=0.9, verified=True,
                           caller_tenant_id="tenant-a", role=Role.TENANT_MEMBER)
    with pytest.raises(CrossTenantAccess):
        engine.record_evidence(tenant_id="tenant-b", kind="behavior", fact="x",
                               source_ref="ui", caller_tenant_id="tenant-a",
                               role=Role.TENANT_MEMBER)
    # tenant-b's workspace untouched by tenant-a's adaptation
    cfg_b = ws.current("tenant-b", caller_tenant_id="tenant-b", role=Role.TENANT_ADMIN)
    assert cfg_b.version == 1


def test_workflow_proposal_evidence_threshold(env):
    _, _, _, engine = env
    e1 = engine.record_evidence(tenant_id="tenant-a", kind="behavior",
                                fact="import prospects then research then qualify",
                                source_ref="wf:1", confidence=0.8, verified=True,
                                caller_tenant_id="tenant-a", role=Role.AGENT)
    with pytest.raises(InsufficientEvidence):
        engine.propose_workflow(tenant_id="tenant-a", name="prospecting",
                                purpose="recurring prospecting",
                                steps=("research", "qualify"), trigger="manual",
                                evidence_refs=(e1.evidence_id,),
                                caller_tenant_id="tenant-a", role=Role.AGENT)
    e2 = engine.record_evidence(tenant_id="tenant-a", kind="workflow_run",
                                fact="import prospects then research then qualify",
                                source_ref="wf:2", confidence=0.85, verified=True,
                                caller_tenant_id="tenant-a", role=Role.AGENT)
    prop = engine.propose_workflow(tenant_id="tenant-a", name="prospecting",
                                   purpose="recurring prospecting",
                                   steps=("research", "qualify"), trigger="manual",
                                   evidence_refs=(e1.evidence_id, e2.evidence_id),
                                   caller_tenant_id="tenant-a", role=Role.AGENT)
    assert prop.status == "proposed"
    approved = engine.approve_workflow(prop, caller_tenant_id="tenant-a",
                                       role=Role.TENANT_ADMIN)
    assert approved.status == "approved"


def test_explicit_instruction_suffices(env):
    _, _, _, engine = env
    e = engine.record_evidence(tenant_id="tenant-a", kind="explicit_fact",
                               fact="user wants a weekly research digest workflow",
                               source_ref="chat:42", confidence=1.0, verified=True,
                               caller_tenant_id="tenant-a", role=Role.TENANT_MEMBER)
    prop = engine.propose_workflow(tenant_id="tenant-a", name="weekly_digest",
                                   purpose="weekly research digest",
                                   steps=("research", "evaluate"), trigger="weekly",
                                   evidence_refs=(e.evidence_id,),
                                   caller_tenant_id="tenant-a", role=Role.TENANT_MEMBER)
    assert prop.trigger == "weekly"
