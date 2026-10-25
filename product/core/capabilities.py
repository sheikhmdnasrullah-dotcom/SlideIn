"""Slidein universal core — capability and module registry.

Code-defined, typed registry of the capabilities the workspace can render.
Tenant configuration *selects and configures* registered modules; it can
never create arbitrary modules or executable code. Every module definition
declares what it needs (permissions, integrations) and what it can render
(page, widget, data views, agent actions, config controls).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from product.core.scopes import Role


class UnknownModule(KeyError):
    pass


# Components a module may contribute to the dashboard renderer.
COMPONENTS = ("nav", "page", "widget", "data_view", "agent_action", "config")


@dataclass(frozen=True)
class ModuleDefinition:
    module_id: str
    name: str
    description: str
    actions: tuple[str, ...] = ()
    required_permissions: tuple[Role, ...] = (Role.TENANT_MEMBER,)
    required_integrations: tuple[str, ...] = ()
    components: tuple[str, ...] = ("nav", "page")
    config_schema: dict[str, str] = field(default_factory=dict)  # key -> type name
    setup_required: bool = False
    version: int = 1

    def supports(self, component: str) -> bool:
        return component in self.components


def _module(**kw) -> ModuleDefinition:
    return ModuleDefinition(**kw)


# The universal workspace catalog. Industry differences are configuration
# over these modules — never new modules per industry.
CAPABILITY_CATALOG: tuple[ModuleDefinition, ...] = (
    _module(module_id="overview", name="Overview",
            description="Projects, approvals, activity, real operational metrics.",
            actions=("view",), components=("nav", "page", "widget"),
            config_schema={"landing_for_roles": "json"}),
    _module(module_id="knowledge", name="Business Knowledge",
            description="Verified business facts, offers, ICP, evidence and provenance.",
            actions=("view", "add_fact", "verify"),
            required_permissions=(Role.TENANT_MEMBER,),
            components=("nav", "page", "widget", "data_view")),
    _module(module_id="research", name="Research",
            description="Source-backed research records produced by the research agent.",
            actions=("run", "review"), components=("nav", "page", "widget", "agent_action"),
            config_schema={"default_depth": "str"}),
    _module(module_id="contacts", name="Contacts & Companies",
            description="Normalized people and company records (internal model).",
            actions=("crud", "import"), components=("nav", "page", "data_view")),
    _module(module_id="qualification", name="Qualification & Scoring",
            description="ICP fit scores with reasons and missing-data indicators.",
            actions=("run", "review"), components=("page", "agent_action")),
    _module(module_id="outreach", name="Outreach Preparation",
            description="Message drafts with verified-signal hooks; send only behind approval gates.",
            actions=("draft",), required_integrations=("email",),
            components=("nav", "page", "agent_action"), setup_required=True),
    _module(module_id="workflows", name="Workflows & Automations",
            description="Visual workflow definitions, execution status, history.",
            actions=("view", "configure", "run", "cancel"),
            components=("nav", "page", "widget", "config")),
    _module(module_id="approvals", name="Approvals",
            description="Human gates: drafts, adaptations, consequential changes.",
            actions=("view", "approve", "reject"), components=("nav", "page", "widget")),
    _module(module_id="analytics", name="Analytics",
            description="Real pipeline/activity metrics; empty state when no data.",
            actions=("view",), components=("nav", "page", "widget")),
    _module(module_id="integrations", name="Integrations",
            description="Connection management (CRM, email, calendar).",
            actions=("connect", "disconnect", "sync"),
            required_permissions=(Role.TENANT_ADMIN,),
            components=("nav", "page", "config"), setup_required=True),
    _module(module_id="agents", name="Agents & Tools",
            description="Registered agents, tool permissions, activity ledger.",
            actions=("view", "configure"),
            required_permissions=(Role.TENANT_ADMIN,),
            components=("nav", "page", "agent_action", "config")),
    _module(module_id="settings", name="Settings",
            description="Tenant configuration, branding, workspace versions.",
            actions=("view", "edit", "rollback"),
            required_permissions=(Role.TENANT_ADMIN,),
            components=("nav", "page", "config")),
)


class CapabilityRegistry:
    """Resolves and validates module references. All adaptation output must
    resolve here; anything else is rejected before persistence."""

    def __init__(self, modules: tuple[ModuleDefinition, ...] = CAPABILITY_CATALOG):
        self._modules = {m.module_id: m for m in modules}
        if len(self._modules) != len(modules):
            raise ValueError("duplicate module_id in capability catalog")

    def resolve(self, module_id: str) -> ModuleDefinition:
        try:
            return self._modules[module_id]
        except KeyError:
            raise UnknownModule(module_id) from None

    def module_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._modules))

    def validate_config(self, module_id: str, config: dict) -> list[str]:
        """Config keys must be declared in the module's config_schema."""
        mod = self.resolve(module_id)
        return [f"unknown config key {k!r} for module {module_id!r}"
                for k in config if k not in mod.config_schema]

    def available_for(self, *, role: Role,
                      integrations: frozenset[str]) -> tuple[ModuleDefinition, ...]:
        """A module is available when the caller's role meets the module's
        permission floor AND every required integration is connected."""
        out = []
        for mod in self._modules.values():
            if role not in mod.required_permissions \
                    and Role.TENANT_ADMIN not in mod.required_permissions \
                    and role not in (Role.PLATFORM_ADMIN, Role.SYSTEM):
                continue
            if any(i not in integrations for i in mod.required_integrations):
                continue
            out.append(mod)
        return tuple(out)
