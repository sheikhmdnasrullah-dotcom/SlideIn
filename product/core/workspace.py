"""Slidein universal core — adaptive workspace configuration.

Versioned, tenant-scoped workspace configs built ONLY from registered
capabilities. The adaptation pipeline (adaptation.py) produces proposals;
this store validates, applies (with policy-gated approval), versions, and
rolls back. An LLM can propose structured config — only trusted code here
renders or applies it.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field, replace
from enum import Enum

from product.core.capabilities import CapabilityRegistry, UnknownModule
from product.core.errors import CrossTenantAccess
from product.core.scopes import Role


class InvalidWorkspaceConfig(ValueError):
    pass


class ProposalStatus(str, Enum):
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLIED = "applied"


class ChangeRisk(str, Enum):
    LOW = "low"                    # presentation: order, widgets, landing page
    CONSEQUENTIAL = "consequential"  # integrations, permissions, workflows, outreach


@dataclass(frozen=True)
class WidgetConfig:
    module_id: str
    widget_type: str               # must be a component of module_id
    settings: dict = field(default_factory=dict)


@dataclass(frozen=True)
class WorkspaceConfig:
    tenant_id: str
    version: int
    enabled_modules: tuple[str, ...]
    module_order: tuple[str, ...]
    nav_groups: dict[str, tuple[str, ...]] = field(default_factory=dict)
    widgets: tuple[WidgetConfig, ...] = ()
    metrics: tuple[dict, ...] = ()
    workflow_refs: tuple[str, ...] = ()
    agent_refs: tuple[str, ...] = ()
    integration_refs: tuple[str, ...] = ()
    display: dict = field(default_factory=dict)
    role_visibility: dict[str, tuple[str, ...]] = field(default_factory=dict)  # role -> modules


@dataclass(frozen=True)
class ConfigProposal:
    tenant_id: str
    changes: dict                  # validated, typed; applied onto current config
    evidence_refs: tuple[str, ...]
    risk: ChangeRisk
    rationale: str
    status: ProposalStatus = ProposalStatus.PENDING_APPROVAL


def universal_workspace(tenant_id: str) -> WorkspaceConfig:
    """Stage 1: every new tenant gets the same functional default."""
    return WorkspaceConfig(
        tenant_id=tenant_id,
        version=1,
        enabled_modules=("overview", "knowledge", "research", "contacts",
                         "workflows", "approvals", "analytics", "integrations",
                         "agents", "settings"),
        module_order=("overview", "knowledge", "research", "contacts",
                      "workflows", "approvals", "analytics", "integrations",
                      "agents", "settings"),
        nav_groups={"Workspace": ("overview", "knowledge", "research", "contacts"),
                    "Operation": ("workflows", "approvals", "analytics"),
                    "Admin": ("integrations", "agents", "settings")},
    )


class WorkspaceStore:
    def __init__(self, registry: CapabilityRegistry):
        self._registry = registry
        self._current: dict[str, WorkspaceConfig] = {}
        self._history: dict[str, list[WorkspaceConfig]] = {}
        self._proposals: dict[str, list[ConfigProposal]] = {}

    # ------------------------------------------------------------------ #
    def register(self, config: WorkspaceConfig, *, role: Role) -> WorkspaceConfig:
        if role not in (Role.TENANT_ADMIN, Role.PLATFORM_ADMIN, Role.SYSTEM):
            raise CrossTenantAccess("workspace registration requires admin")
        self.validate(config)
        self._current[config.tenant_id] = copy.deepcopy(config)
        self._history.setdefault(config.tenant_id, []).append(copy.deepcopy(config))
        return copy.deepcopy(config)

    def current(self, tenant_id: str, *, caller_tenant_id: str | None,
                role: Role) -> WorkspaceConfig:
        self._check(tenant_id, caller_tenant_id, role)
        return copy.deepcopy(self._current[tenant_id])

    def history(self, tenant_id: str, *, caller_tenant_id: str | None,
                role: Role) -> tuple[WorkspaceConfig, ...]:
        self._check(tenant_id, caller_tenant_id, role)
        return tuple(copy.deepcopy(v) for v in self._history[tenant_id])

    # ------------------------------------------------------------------ #
    def validate(self, config: WorkspaceConfig) -> None:
        errors: list[str] = []
        for mid in config.enabled_modules:
            try:
                self._registry.resolve(mid)
            except UnknownModule:
                errors.append(f"unknown module {mid!r}")
        if set(config.module_order) != set(config.enabled_modules):
            errors.append("module_order must contain exactly the enabled modules")
        for group, members in config.nav_groups.items():
            for mid in members:
                if mid not in config.enabled_modules:
                    errors.append(f"nav group {group!r} references disabled module {mid!r}")
        for w in config.widgets:
            try:
                mod = self._registry.resolve(w.module_id)
            except UnknownModule:
                errors.append(f"widget references unknown module {w.module_id!r}")
                continue
            if w.module_id not in config.enabled_modules:
                errors.append(f"widget module {w.module_id!r} is not enabled")
            if not mod.supports("widget"):
                errors.append(f"module {w.module_id!r} does not support widgets")
            errors.extend(self._registry.validate_config(w.module_id, w.settings))
        for role, mods in config.role_visibility.items():
            if not hasattr(Role, role.upper()) and role not in [r.value for r in Role]:
                errors.append(f"unknown role {role!r} in role_visibility")
            for mid in mods:
                if mid not in config.enabled_modules:
                    errors.append(f"role_visibility references disabled module {mid!r}")
        if errors:
            raise InvalidWorkspaceConfig("; ".join(errors))

    # ------------------------------------------------------------------ #
    def propose(self, tenant_id: str, *, changes: dict, evidence_refs: tuple[str, ...],
                risk: ChangeRisk, rationale: str,
                caller_tenant_id: str | None, role: Role) -> ConfigProposal:
        self._check(tenant_id, caller_tenant_id, role)
        current = self._current[tenant_id]
        proposed = self._apply_changes(current, changes, new_version=False)
        self.validate(proposed)  # invalid configs never become proposals
        proposal = ConfigProposal(tenant_id=tenant_id, changes=copy.deepcopy(changes),
                                  evidence_refs=evidence_refs, risk=risk,
                                  rationale=rationale)
        self._proposals.setdefault(tenant_id, []).append(proposal)
        return proposal

    def approve_proposal(self, tenant_id: str, proposal: ConfigProposal, *,
                         caller_tenant_id: str | None, role: Role) -> ConfigProposal:
        self._check(tenant_id, caller_tenant_id, role)
        if role not in (Role.TENANT_ADMIN, Role.PLATFORM_ADMIN):
            raise CrossTenantAccess("config approval requires tenant admin")
        return replace(proposal, status=ProposalStatus.APPROVED)

    def apply(self, tenant_id: str, proposal: ConfigProposal, *,
              caller_tenant_id: str | None, role: Role,
              auto_apply_low_risk: bool = False) -> WorkspaceConfig:
        """Low-risk changes may apply automatically when the tenant opts in;
        consequential changes always need an approved proposal."""
        self._check(tenant_id, caller_tenant_id, role)
        if proposal.risk is ChangeRisk.CONSEQUENTIAL \
                and proposal.status is not ProposalStatus.APPROVED:
            raise CrossTenantAccess("consequential config change requires approval")
        if proposal.risk is ChangeRisk.LOW and not auto_apply_low_risk \
                and proposal.status is not ProposalStatus.APPROVED:
            raise CrossTenantAccess("tenant has not opted into auto-apply")
        current = self._current[tenant_id]
        new_config = self._apply_changes(current, proposal.changes, new_version=True)
        self.validate(new_config)
        self._current[tenant_id] = new_config
        self._history[tenant_id].append(copy.deepcopy(new_config))
        return copy.deepcopy(new_config)

    def rollback(self, tenant_id: str, to_version: int, *,
                 caller_tenant_id: str | None, role: Role) -> WorkspaceConfig:
        self._check(tenant_id, caller_tenant_id, role)
        if role not in (Role.TENANT_ADMIN, Role.PLATFORM_ADMIN):
            raise CrossTenantAccess("rollback requires tenant admin")
        for config in reversed(self._history[tenant_id]):
            if config.version == to_version:
                restored = replace(config, version=self._current[tenant_id].version + 1)
                self._current[tenant_id] = copy.deepcopy(restored)
                self._history[tenant_id].append(copy.deepcopy(restored))
                return copy.deepcopy(restored)
        raise InvalidWorkspaceConfig(f"version {to_version} not found")

    # ------------------------------------------------------------------ #
    @staticmethod
    def _apply_changes(current: WorkspaceConfig, changes: dict,
                       new_version: bool) -> WorkspaceConfig:
        allowed = {"module_order", "nav_groups", "widgets", "metrics",
                   "workflow_refs", "agent_refs", "integration_refs",
                   "display", "role_visibility", "enabled_modules"}
        unknown = set(changes) - allowed
        if unknown:
            raise InvalidWorkspaceConfig(f"unsupported config keys: {sorted(unknown)}")
        return replace(current,
                       version=current.version + 1 if new_version else current.version,
                       **{k: copy.deepcopy(v) for k, v in changes.items()})

    @staticmethod
    def _check(tenant_id: str, caller_tenant_id: str | None, role: Role) -> None:
        if role in (Role.PLATFORM_ADMIN, Role.SYSTEM):
            return
        if caller_tenant_id is None or caller_tenant_id != tenant_id:
            raise CrossTenantAccess(
                f"caller for tenant {caller_tenant_id!r} cannot access tenant {tenant_id!r}"
            )
