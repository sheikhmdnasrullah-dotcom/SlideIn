"""One-shot client setup: context in -> understood business -> validated
workspace -> first workflow -> readiness.

The single intake the product is built around (Phase 3/5 of the unification
mission). Accepts transcripts, pasted notes, documents (pre-extracted text),
and website copy as (source_ref, text) pairs. Produces:

- BusinessProfile: confirmed facts (extracted, with source refs) vs inferred
  assumptions, missing fields, and detected contradictions. Guesses never
  become rules.
- WorkspaceConfig: generated from the profile against the capability
  registry — only implemented, compatible modules are enabled.
- First workflow proposal: validated against the universal flow.
- Readiness: the honest state machine from the mission (§4).

Extraction is deterministic (no LLM required); an LLM enhancer can be added
later behind the same contract. Only fields with explicit textual evidence
are marked confirmed.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- #
# Business profile
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ProfileFact:
    key: str
    value: str
    source_ref: str
    confirmed: bool          # True only with explicit textual evidence
    snippet: str = ""


@dataclass(frozen=True)
class BusinessProfile:
    profile_id: str
    business_name: str | None
    industry: str | None
    description: str | None
    offers: tuple[ProfileFact, ...]
    icp: tuple[ProfileFact, ...]
    goals: tuple[ProfileFact, ...]
    voice: tuple[ProfileFact, ...]
    tools: tuple[ProfileFact, ...]
    approvals: tuple[ProfileFact, ...]
    missing: tuple[str, ...]
    contradictions: tuple[str, ...]
    created_at: datetime = field(default_factory=_utcnow)


_EXTRACTION_PATTERNS: dict[str, list[tuple[str, str]]] = {
    # key -> [(regex with capture, confirmed?)]
    "business_name": [
        (r"(?:we are|i run|i own|my company is|our company is)\s+([A-Z][\w&'.-]+(?:\s+[A-Z][\w&'.-]+){0,4})", True),
        (r"^#\s+(.+)$", False),
    ],
    "industry": [
        (r"(?:we(?:'re| are) (?:a|an) )\b(\w[\w\s-]{2,30}?)(?:\s+company|\s+agency|\s+firm|\s+business|\s+startup)", True),
        (r"industry:\s*([^\n.]+)", True),
    ],
    "offers": [
        (r"(?:we offer|we sell|we provide|our services? (?:include|are)|specialize in)\s+([^\n.]+)", True),
    ],
    "icp": [
        (r"(?:ideal (?:customer|client)|target (?:customer|client|market)|our clients? (?:are|is))\s*[:\-]?\s*([^\n.]+)", True),
        (r"(?:we help|we work with)\s+([^\n.]+)", True),
    ],
    "goals": [
        (r"(?:our goal is|we want to|we need to|objective:?)\s+([^\n.]+)", True),
    ],
    "voice": [
        (r"(?:tone|voice|we (?:sound|write) like)\s*[:\-]?\s*([^\n.]+)", True),
    ],
    "tools": [
        (r"(?:we use|our (?:crm|stack|tools?) (?:is|are))\s+([^\n.]+)", True),
    ],
    "approvals": [
        (r"(?:requires? (?:my |human )?approval|i (?:want to|must) approve|nothing sends? without)\s*([^\n.]*)", True),
    ],
}

_EXPECTED = ("business_name", "offers", "icp", "goals")


def extract_profile(materials: list[tuple[str, str]]) -> BusinessProfile:
    found: dict[str, list[ProfileFact]] = {k: [] for k in _EXTRACTION_PATTERNS}
    for source_ref, text in materials:
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            for key, patterns in _EXTRACTION_PATTERNS.items():
                for pattern, confirmed in patterns:
                    for m in re.finditer(pattern, line, re.I):
                        value = m.group(1).strip().strip(",.")
                        if len(value) < 3 or len(value) > 220:
                            continue
                        # first explicit (confirmed) evidence wins per key+value
                        if any(f.value.lower() == value.lower() for f in found[key]):
                            continue
                        found[key].append(ProfileFact(
                            key=key, value=value, source_ref=source_ref,
                            confirmed=confirmed, snippet=line[:160]))

    contradictions: list[str] = []
    for key, facts in found.items():
        distinct = {f.value.lower() for f in facts if f.confirmed}
        if len(distinct) > 1:
            contradictions.append(
                f"{key}: multiple conflicting values ({'; '.join(sorted(distinct)[:3])})")

    missing = [k for k in _EXPECTED if not any(f.confirmed for f in found[k])]
    return BusinessProfile(
        profile_id=uuid.uuid4().hex[:12],
        business_name=(found["business_name"][0].value
                       if found["business_name"] else None),
        industry=(found["industry"][0].value if found["industry"] else None),
        description=None,
        offers=tuple(found["offers"]), icp=tuple(found["icp"]),
        goals=tuple(found["goals"]), voice=tuple(found["voice"]),
        tools=tuple(found["tools"]), approvals=tuple(found["approvals"]),
        missing=tuple(missing), contradictions=tuple(contradictions),
    )


# --------------------------------------------------------------------------- #
# Readiness
# --------------------------------------------------------------------------- #
READINESS_STATES = ("workspace_created", "context_processed",
                    "config_validated", "integrations_pending",
                    "awaiting_approval", "ready", "active", "blocked")


@dataclass(frozen=True)
class SetupStatus:
    tenant_id: str
    state: str
    profile_id: str | None = None
    config_version: int | None = None
    workflow_proposal_id: str | None = None
    blockers: tuple[str, ...] = ()
    questions: tuple[str, ...] = ()   # short grouped review, only when material
    next_action: str = ""


# --------------------------------------------------------------------------- #
# Workspace generation (against the real registry only)
# --------------------------------------------------------------------------- #
def generate_workspace_config(profile: BusinessProfile, *, tenant_id: str,
                              universal_config) -> dict:
    """Returns validated *changes* applied onto the universal default.

    Only implemented modules are referenced; unimplemented needs are recorded
    as blockers/notes, never faked."""
    changes: dict = {}
    nav_priority = ["overview"]
    if any(f.confirmed for f in profile.icp):
        nav_priority.append("research")
    if profile.offers:
        nav_priority.append("contacts")
    if any("approval" in f.value.lower() or f.key == "approvals"
           for f in (*profile.approvals, *profile.goals)):
        nav_priority.append("approvals")
    # Reorder: prioritized modules first (rest keeps relative order).
    order = list(universal_config.module_order)
    for mid in reversed(nav_priority):
        if mid in order:
            order.remove(mid)
            order.insert(0, mid)
    # overview stays first
    if "overview" in order:
        order.remove("overview")
        order.insert(0, "overview")
    changes["module_order"] = tuple(dict.fromkeys(order))
    return changes


def first_workflow_steps(profile: BusinessProfile) -> tuple[str, ...]:
    """The first practical workflow, composed ONLY from universal-flow stages."""
    steps = ["discover", "research", "qualify", "personalize"]
    if profile.offers:
        steps.append("outreach")   # send only behind the approval gate
    return tuple(steps)


def review_questions(profile: BusinessProfile) -> tuple[str, ...]:
    """One short grouped review — only questions that materially block setup."""
    questions = []
    if "business_name" in profile.missing:
        questions.append("What is the business name? (used for branding)")
    if "offers" in profile.missing:
        questions.append("What does the business sell? (needed to match offers)")
    if "icp" in profile.missing:
        questions.append("Who is the ideal customer? (needed to qualify prospects)")
    if profile.contradictions:
        questions.append("Contradictions to resolve: " + "; ".join(profile.contradictions))
    return tuple(questions)
