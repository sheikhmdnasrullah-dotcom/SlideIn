"""THE universal Slidein flow — canonical, hardcoded, non-negotiable.

Every client instance, every workflow, every agent task MUST map onto:

    CONFIGURE -> DISCOVER -> RESEARCH -> QUALIFY -> PERSONALIZE
        -> OUTREACH -> CONVERSE -> (ACTIVITY -> OVERVIEW) -> back to CONFIGURE

Stage outputs carry provenance requirements: anything a stage produces must
record where it came from. This module is the single source of truth — the
legacy stage runner (workflow.py) and any module/workflow proposal validate
against it. Coding agents: extend tools, frameworks, and logic UNDER a stage;
never add, reorder, or skip stages.

Aliases map legacy/internal names onto canonical stages so existing code
keeps validating (validate/execute/measure are quality gates that live
INSIDE outreach/converse, not separate top-level stages).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class FlowStage:
    stage_id: str
    label: str
    outputs: tuple[str, ...]          # what this stage produces
    provenance: tuple[str, ...]       # provenance each output must carry
    feedback_to: str | None = None    # next stage in the canonical order


CONFIGURE = FlowStage("configure", "Configure",
                      outputs=("profile", "offers", "icps"),
                      provenance=("source", "approved_by", "version"))
DISCOVER = FlowStage("discover", "Discover",
                     outputs=("prospects",),
                     provenance=("source", "collected_at"))
RESEARCH = FlowStage("research", "Research",
                     outputs=("evidence",),
                     provenance=("source_ref", "confidence", "collected_at"))
QUALIFY = FlowStage("qualify", "Qualify",
                    outputs=("qualification", "offer_match"),
                    provenance=("criteria_ref", "score_reasons", "missing_data"))
PERSONALIZE = FlowStage("personalize", "Personalize",
                        outputs=("drafts",),
                        provenance=("signals_used", "version", "verified_only"))
OUTREACH = FlowStage("outreach", "Outreach",
                     outputs=("sent_mails", "policy"),
                     provenance=("approval_ref", "policy_check", "sent_at"))
CONVERSE = FlowStage("converse", "Converse",
                     outputs=("replies", "intent"),
                     provenance=("channel", "received_at", "intent_source"))

# Canonical order — the loop the dashboard's overview/activity feeds close.
UNIVERSAL_FLOW: tuple[FlowStage, ...] = (
    CONFIGURE, DISCOVER, RESEARCH, QUALIFY, PERSONALIZE, OUTREACH, CONVERSE,
)
FEEDBACK_EDGES: tuple[tuple[str, str], ...] = (
    ("converse", "activity"),
    ("activity", "overview"),
    ("overview", "configure"),   # results refine configuration — the loop
)

STAGE_IDS: tuple[str, ...] = tuple(s.stage_id for s in UNIVERSAL_FLOW)

# Legacy / internal names -> canonical stage. Anything not listed and not a
# canonical id is OFF-FLOW and must be rejected.
LEGACY_ALIASES: dict[str, str] = {
    "match_offer": "qualify",        # offer match is part of qualification
    "evaluate": "qualify",           # fit evaluation is qualification
    "validate": "outreach",          # policy/validation gates live in outreach
    "execute": "outreach",           # sending is outreach execution
    "measure": "converse",           # measurement consumes conversation outcomes
    "booking": "converse",
    "nurture": "converse",
}


def canonical_stage(step: str) -> str | None:
    """Resolve a step name to its canonical stage id, or None if off-flow."""
    s = step.strip().lower()
    if s in STAGE_IDS:
        return s
    return LEGACY_ALIASES.get(s)


def assert_flow_aligned(steps: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    """Validate an ordered step list against the universal flow.

    Returns the canonical stage ids in the order given. Raises FlowViolation
    for unknown/off-flow steps. Callers (adaptation proposals, workflow
    definitions, module actions) must validate before persisting anything.
    """
    resolved = []
    for step in steps:
        stage = canonical_stage(step)
        if stage is None:
            raise FlowViolation(
                f"step {step!r} is not part of the universal flow "
                f"({ ' -> '.join(STAGE_IDS) }); extend tools/logic UNDER a "
                f"stage instead of adding new top-level stages"
            )
        resolved.append(stage)
    return tuple(resolved)


def is_canonical_order(stages: tuple[str, ...]) -> bool:
    """True when stages appear in canonical order (subsequence allowed)."""
    idx = {s: i for i, s in enumerate(STAGE_IDS)}
    last = -1
    for s in stages:
        if s not in idx or idx[s] < last:
            return False
        last = idx[s]
    return True


class FlowViolation(ValueError):
    """Raised when a workflow/module proposes steps outside the universal flow."""
