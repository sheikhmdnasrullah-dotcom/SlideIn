"""Slidein universal core — adaptive workspace engine.

Controlled configuration loop:

    Observe -> Extract evidence -> Infer workflow -> Propose changes
    -> Validate (registry + schema) -> Apply per tenant policy -> Measure

Rules enforced here:
- Facts carry provenance, confidence, and a verified/hypothesis distinction;
  an unverified hypothesis never justifies a change on its own.
- Workflow proposals require repeated evidence (>=2 verified observations of
  the same pattern) or one explicit user instruction.
- Workspace changes are proposals validated by WorkspaceStore before they
  can be applied; LLMs (if used) produce only this structured data.
- Everything is tenant-scoped; cross-tenant reads raise CrossTenantAccess.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from product.core.capabilities import CapabilityRegistry
from product.core.errors import CrossTenantAccess
from product.core.scopes import Role
from product.core.workspace import (ChangeRisk, ConfigProposal, WorkspaceConfig,
                                    WorkspaceStore)


class InsufficientEvidence(ValueError):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class Evidence:
    tenant_id: str
    kind: str                      # behavior | explicit_fact | workflow_run | user_feedback
    fact: str
    source_ref: str
    confidence: float = 0.5
    verified: bool = False
    evidence_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    ts: datetime = field(default_factory=_utcnow)


class EvidenceStore:
    def __init__(self) -> None:
        self._items: dict[str, list[Evidence]] = {}

    def add(self, item: Evidence, *, caller_tenant_id: str | None, role: Role) -> Evidence:
        if role not in (Role.TENANT_MEMBER, Role.TENANT_ADMIN, Role.PLATFORM_ADMIN,
                        Role.SYSTEM, Role.AGENT):
            raise CrossTenantAccess("role may not record evidence")
        if role not in (Role.PLATFORM_ADMIN, Role.SYSTEM) \
                and caller_tenant_id != item.tenant_id:
            raise CrossTenantAccess("cannot record evidence for another tenant")
        self._items.setdefault(item.tenant_id, []).append(item)
        return item

    def list(self, tenant_id: str, *, caller_tenant_id: str | None,
             role: Role) -> tuple[Evidence, ...]:
        if role not in (Role.PLATFORM_ADMIN, Role.SYSTEM) and caller_tenant_id != tenant_id:
            raise CrossTenantAccess("cannot read another tenant's evidence")
        return tuple(self._items.get(tenant_id, ()))


@dataclass(frozen=True)
class WorkflowProposal:
    tenant_id: str
    name: str
    purpose: str
    steps: tuple[str, ...]
    trigger: str
    evidence_refs: tuple[str, ...]
    approval_gate: bool = True
    status: str = "proposed"       # proposed | approved | rejected
    proposal_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])


class AdaptationEngine:
    def __init__(self, registry: CapabilityRegistry, workspaces: WorkspaceStore,
                 evidence: EvidenceStore):
        self._registry = registry
        self._workspaces = workspaces
        self._evidence = evidence
        self._workflow_proposals: dict[str, list[WorkflowProposal]] = {}

    # ------------------------------------------------------------------ #
    def record_evidence(self, *, tenant_id: str, kind: str, fact: str,
                        source_ref: str, confidence: float = 0.5,
                        verified: bool = False,
                        caller_tenant_id: str | None, role: Role) -> Evidence:
        return self._evidence.add(
            Evidence(tenant_id=tenant_id, kind=kind, fact=fact,
                     source_ref=source_ref, confidence=confidence,
                     verified=verified),
            caller_tenant_id=caller_tenant_id, role=role)

    # ------------------------------------------------------------------ #
    def propose_workflow(self, *, tenant_id: str, name: str, purpose: str,
                         steps: tuple[str, ...], trigger: str,
                         evidence_refs: tuple[str, ...],
                         caller_tenant_id: str | None, role: Role) -> WorkflowProposal:
        if role not in (Role.TENANT_MEMBER, Role.TENANT_ADMIN, Role.AGENT,
                        Role.PLATFORM_ADMIN, Role.SYSTEM):
            raise CrossTenantAccess("role may not propose workflows")
        if role not in (Role.PLATFORM_ADMIN, Role.SYSTEM) and caller_tenant_id != tenant_id:
            raise CrossTenantAccess("cannot propose workflows for another tenant")
        items = self._evidence.list(tenant_id, caller_tenant_id=caller_tenant_id,
                                    role=Role.SYSTEM)
        cited = [e for e in items if e.evidence_id in evidence_refs]
        if not cited:
            raise InsufficientEvidence("proposal must cite recorded evidence")
        verified_pattern = sum(1 for e in cited if e.verified and e.kind in
                               ("behavior", "workflow_run"))
        explicit = any(e.kind in ("explicit_fact", "user_feedback") and e.verified
                       for e in cited)
        if not explicit and verified_pattern < 2:
            raise InsufficientEvidence(
                "workflow proposals need >=2 verified repeated observations "
                "or one explicit verified instruction")
        if len(set(steps)) != len(steps) or not steps:
            raise InsufficientEvidence("steps must be a non-empty ordered set")
        proposal = WorkflowProposal(tenant_id=tenant_id, name=name, purpose=purpose,
                                    steps=tuple(steps), trigger=trigger,
                                    evidence_refs=tuple(evidence_refs))
        self._workflow_proposals.setdefault(tenant_id, []).append(proposal)
        return proposal

    def approve_workflow(self, proposal: WorkflowProposal, *,
                         caller_tenant_id: str | None, role: Role) -> WorkflowProposal:
        if role not in (Role.TENANT_ADMIN, Role.PLATFORM_ADMIN):
            raise CrossTenantAccess("workflow approval requires tenant admin")
        if caller_tenant_id is not None and caller_tenant_id != proposal.tenant_id:
            raise CrossTenantAccess("cannot approve another tenant's workflow")
        approved = WorkflowProposal(**{**proposal.__dict__, "status": "approved"})
        lst = self._workflow_proposals[proposal.tenant_id]
        lst[lst.index(proposal)] = approved
        return approved

    def workflow_proposals(self, tenant_id: str, *, caller_tenant_id: str | None,
                           role: Role) -> tuple[WorkflowProposal, ...]:
        if role not in (Role.PLATFORM_ADMIN, Role.SYSTEM) and caller_tenant_id != tenant_id:
            raise CrossTenantAccess("cannot read another tenant's proposals")
        return tuple(self._workflow_proposals.get(tenant_id, ()))

    # ------------------------------------------------------------------ #
    def propose_workspace_changes(self, *, tenant_id: str,
                                  caller_tenant_id: str | None, role: Role,
                                  rationale: str) -> ConfigProposal:
        """Analyze verified evidence frequency and propose presentation
        changes only (low risk). Consequential changes (integrations,
        permissions, outreach) always come from explicit admin action."""
        if role not in (Role.TENANT_MEMBER, Role.TENANT_ADMIN, Role.AGENT,
                        Role.PLATFORM_ADMIN, Role.SYSTEM):
            raise CrossTenantAccess("role may not propose workspace changes")
        if role not in (Role.PLATFORM_ADMIN, Role.SYSTEM) and caller_tenant_id != tenant_id:
            raise CrossTenantAccess("cannot adapt another tenant's workspace")
        items = [e for e in self._evidence.list(tenant_id, caller_tenant_id=caller_tenant_id,
                                                role=Role.SYSTEM) if e.verified]
        if not items:
            raise InsufficientEvidence("no verified evidence to adapt from")

        current = self._workspaces.current(tenant_id, caller_tenant_id=caller_tenant_id,
                                           role=Role.SYSTEM)
        # Frequent verified activity mentioning a registered module -> move it
        # earlier in navigation. Clicks alone never enable new modules.
        mentions: dict[str, int] = {}
        for e in items:
            for mid in self._registry.module_ids():
                if mid in e.fact:
                    mentions[mid] = mentions.get(mid, 0) + 1
        changes: dict = {}
        order = list(current.module_order)
        moved = False
        for mid, count in sorted(mentions.items(), key=lambda kv: -kv[1]):
            if count >= 3 and mid in order and order.index(mid) > 1:
                order.remove(mid)
                order.insert(1, mid)  # just after overview
                moved = True
        if moved:
            changes["module_order"] = tuple(order)
        # Recurring research activity -> surface a research-status widget.
        research_activity = sum(1 for e in items if "research" in e.fact)
        if research_activity >= 3 and not any(w.module_id == "research" for w in current.widgets):
            from product.core.workspace import WidgetConfig
            changes["widgets"] = current.widgets + (WidgetConfig(
                module_id="research", widget_type="agent_action",
                settings={"default_depth": "standard"}),)
        if not changes:
            raise InsufficientEvidence("no adaptation-worthy pattern found")
        return self._workspaces.propose(
            tenant_id, changes=changes,
            evidence_refs=tuple(e.evidence_id for e in items),
            risk=ChangeRisk.LOW, rationale=rationale,
            caller_tenant_id=caller_tenant_id, role=role)
