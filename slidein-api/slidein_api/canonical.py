"""Canonical convergence — one authority for sections, flow, navigation.

Owner decisions absorbed here (Canonical Convergence ADR):
- Seven STABLE workspace sections (§3.5). Navigation is a *projection* of
  enabled, implemented capabilities onto these sections — never a new
  frontend per client, never autonomous reordering.
- One machine flow authority for slidein-api. `product/core/flow.py` remains
  an interim guard; this module is the canonical caller surface and adds the
  tested `synthesize -> converse` compatibility mapping (§9.1) so persisted
  history with the legacy eighth stage keeps validating.
- Adaptations REQUIRE approval (§3.4): no auto-apply bypass at the API layer.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Seven stable sections (do not add/rename without an owner architecture
# decision). Each maps to registered capabilities — the projection, not new
# code per industry.
# --------------------------------------------------------------------------- #
SEVEN_SECTIONS: tuple[str, ...] = (
    "overview",
    "business_setup",
    "prospects_research",
    "outreach",
    "conversations",
    "activity",
    "settings",
)

SECTION_LABELS: dict[str, str] = {
    "overview": "Overview",
    "business_setup": "Business Setup",
    "prospects_research": "Prospects & Research",
    "outreach": "Outreach",
    "conversations": "Conversations",
    "activity": "Activity",
    "settings": "Settings",
}

# Adaptive capability module_id -> canonical section. Every catalog module
# maps to exactly one section; a section may hold several modules.
SECTION_CAPABILITIES: dict[str, tuple[str, ...]] = {
    "overview": ("overview", "analytics", "approvals"),
    "business_setup": ("knowledge",),
    "prospects_research": ("research", "contacts", "qualification"),
    "outreach": ("outreach",),
    "conversations": (),            # canonical conversation capability added below
    "activity": ("workflows",),
    "settings": ("integrations", "agents", "settings"),
}

# Conversations is first-class in the canonical journey but had no adaptive
# catalog module yet; register it as an alias entry so the projection is total.
_CONVERSATION_MODULE = "conversations"


def project_navigation(enabled_modules: tuple[str, ...] | list[str]) -> list[dict]:
    """Project enabled capability modules onto the seven stable sections.

    Server-side authorization still governs access; this only decides what the
    navigation may show. Unknown modules are ignored (never crash the nav)."""
    enabled = set(enabled_modules)
    projected = []
    for section in SEVEN_SECTIONS:
        modules = [m for m in SECTION_CAPABILITIES[section]
                   if m in enabled or (m == _CONVERSATION_MODULE and _CONVERSATION_MODULE in enabled)]
        projected.append({"section": section, "label": SECTION_LABELS[section],
                          "modules": modules, "visible": bool(modules)})
    return projected


# --------------------------------------------------------------------------- #
# One flow authority (§9.1): canonical surface over product/core/flow.py with
# the deliberate synthesize reconciliation — synthesis/learning behavior lives
# under converse; legacy records/routes keep validating via this mapping.
# --------------------------------------------------------------------------- #
LEGACY_STAGE_COMPAT: dict[str, str] = {
    "synthesize": "converse",   # synthesis folded into converse + feedback loop
}


# THE machine flow definition — owned here (Architecture §6). The interim
# guard in product/core/flow.py must stay byte-identical (equality-tested);
# its removal condition is recorded in docs/project/CURRENT_STATE.md.
STAGE_IDS: tuple[str, ...] = (
    "configure", "discover", "research", "qualify",
    "personalize", "outreach", "converse",
)

_LEGACY_ALIASES: dict[str, str] = {
    "match_offer": "qualify", "evaluate": "qualify",
    "validate": "outreach", "execute": "outreach",
    "measure": "converse", "booking": "converse", "nurture": "converse",
    **LEGACY_STAGE_COMPAT,
}


class FlowViolation(ValueError):
    """Raised when a workflow proposes steps outside the universal flow."""


def canonical_flow() -> tuple[str, ...]:
    return STAGE_IDS


def assert_canonical_flow(steps: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    """Validate steps against the universal flow, accepting the reconciled
    legacy `synthesize` stage by mapping it onto converse. Off-flow steps are
    rejected before persistence."""
    resolved = []
    for step in steps:
        s = step.strip().lower()
        if s in STAGE_IDS:
            resolved.append(s)
            continue
        aliased = _LEGACY_ALIASES.get(s)
        if aliased is None:
            raise FlowViolation(
                f"step {step!r} is off-flow; canonical stages: {' -> '.join(STAGE_IDS)}"
            )
        resolved.append(aliased)
    return tuple(resolved)
