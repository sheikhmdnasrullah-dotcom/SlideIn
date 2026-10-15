"""Explicit backend contracts for every handoff between stages.

Nothing in Slidein connects two sections implicitly. Each stage declares:

  * `requires`  — the input keys it must receive, with their types
  * `produces`  — the output keys it guarantees to return on success
  * `transitions` — the subject lifecycle states it may move through
  * `failures`  — the failure codes it may raise, whether each is
                  retryable, and the recovery action for it
  * `permission` — the minimum role allowed to invoke it
  * `needs_review_when` — when a successful run must be held for a human

`StageRunner` validates a call against the contract before it touches the
database and records the run afterwards, so a caller that skips a
prerequisite gets `STAGE_PREREQUISITE` instead of silently bad data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class StageName(str, Enum):
    CONFIGURE = "configure"
    DISCOVER = "discover"
    RESEARCH = "research"
    QUALIFY = "qualify"
    PERSONALIZE = "personalize"
    OUTREACH = "outreach"
    CONVERSE = "converse"
    SYNTHESIZE = "synthesize"


class FieldKind(str, Enum):
    STRING = "string"
    INT = "int"
    BOOL = "bool"
    LIST = "list"
    MAP = "map"
    ID = "id"
    NUMBER = "number"


@dataclass(frozen=True)
class Field:
    name: str
    kind: FieldKind
    required: bool = True
    description: str = ""


@dataclass(frozen=True)
class FailureMode:
    code: str
    retryable: bool
    recovery_action: str
    description: str = ""


@dataclass(frozen=True)
class StageContract:
    stage: StageName
    title: str
    summary: str
    requires: tuple[Field, ...]
    produces: tuple[Field, ...]
    transitions: tuple[tuple[str, str], ...]
    failures: tuple[FailureMode, ...]
    permission: str
    needs_review_when: tuple[str, ...] = ()
    max_attempts: int = 3
    notes: str = ""

    @property
    def failure_codes(self) -> tuple[str, ...]:
        return tuple(f.code for f in self.failures)

    def validate_input(self, payload: dict) -> list[str]:
        """Return a list of contract violations for `payload`."""
        problems: list[str] = []
        for spec in self.requires:
            if not spec.required:
                continue
            value = payload.get(spec.name)
            if value is None or value == "" or value == []:
                problems.append(f"{self.stage.value}.{spec.name} is required")
                continue
            expected = {
                FieldKind.STRING: str,
                FieldKind.INT: int,
                FieldKind.NUMBER: (int, float),
                FieldKind.BOOL: bool,
                FieldKind.LIST: list,
                FieldKind.MAP: dict,
                FieldKind.ID: str,
            }[spec.kind]
            if spec.kind is FieldKind.INT and isinstance(value, bool):
                problems.append(f"{self.stage.value}.{spec.name} must be an int")
            elif not isinstance(value, expected):
                problems.append(
                    f"{self.stage.value}.{spec.name} must be {expected.__name__}"
                )
        return problems

    def produces_named(self, name: str) -> Field:
        for spec in self.produces:
            if spec.name == name:
                return spec
        raise KeyError(f"{self.stage.value} does not produce {name!r}")


def _f(
    code: str,
    retryable: bool,
    recovery: str,
    description: str = "",
) -> FailureMode:
    return FailureMode(
        code=code,
        retryable=retryable,
        recovery_action=recovery,
        description=description,
    )


# ---------------------------------------------------------------------------
# The contracts
# ---------------------------------------------------------------------------

CONTRACTS: dict[StageName, StageContract] = {
    StageName.CONFIGURE: StageContract(
        stage=StageName.CONFIGURE,
        title="Business Profile",
        summary=(
            "Writes the versioned business configuration (profile, offers, "
            "ICP) that every later stage consumes. No prospect record can be "
            "created, researched or qualified without an active profile "
            "version."
        ),
        requires=(
            Field("legal_name", FieldKind.STRING),
            Field("website_url", FieldKind.STRING),
            Field("industry", FieldKind.STRING),
            Field("company_description", FieldKind.STRING),
            Field("core_value_prop", FieldKind.STRING),
        ),
        produces=(
            Field("profile_id", FieldKind.ID),
            Field("profile_version", FieldKind.INT),
            Field("offer_ids", FieldKind.LIST, required=False),
            Field("icp_ids", FieldKind.LIST, required=False),
        ),
        transitions=(),
        failures=(
            _f("profile_incomplete", False, "complete_business_profile",
               "A required profile field is empty."),
            _f("config_version_conflict", False, "review_config_version",
               "A newer profile version exists than the one referenced."),
        ),
        permission="operator",
        needs_review_when=(
            "profile has no active offer (an offer is needed before Outreach)",
            "profile has no active ICP (an ICP is needed before Qualification)",
        ),
        max_attempts=1,
        notes=(
            "Saving always creates a new version. The previous version stays "
            "readable so existing prospects can be traced to it."
        ),
    ),
    StageName.DISCOVER: StageContract(
        stage=StageName.DISCOVER,
        title="Discovery",
        summary=(
            "Creates source-attributed prospect records for the active ICP "
            "and stamps them with the profile version that produced them."
        ),
        requires=(
            Field(
                "icp_id",
                FieldKind.ID,
                required=False,
                description=(
                    "The ICP the records must satisfy. Defaults to the active "
                    "ICP; a workspace with no ICP fails with icp_missing."
                ),
            ),
            Field("records", FieldKind.LIST, "1..n raw prospect records."),
        ),
        produces=(
            Field("prospect_ids", FieldKind.LIST),
            Field("prospect_id", FieldKind.ID, required=False,
                  description="Each created prospect record, carried to Research."),
            Field("created", FieldKind.INT),
            Field("duplicates", FieldKind.INT),
            Field("skipped", FieldKind.INT, required=False),
            Field("profile_version", FieldKind.INT),
            Field("source", FieldKind.STRING, required=False,
                  description="How the record was sourced; attribution moves with it."),
        ),
        transitions=(("discovered", "discovered"),),
        failures=(
            _f("icp_missing", False, "define_icp",
               "No active ICP exists for the tenant."),
            _f("profile_missing", False, "create_business_profile",
               "No active business profile exists for the tenant."),
            _f("prospect_duplicate", False, "merge_duplicate",
               "The email already exists in this workspace."),
            _f("prospect_invalid", False, "fix_prospect_record",
               "A record is missing a usable email or company."),
            _f("source_unavailable", True, "retry_stage",
               "The configured discovery source could not be reached."),
            _f("rate_limited", True, "retry_stage_later",
               "The discovery source rate-limited the request."),
        ),
        permission="operator",
        needs_review_when=(
            "one or more records were skipped as duplicates",
            "an ICP exclusion keyword matched a record (kept, but flagged)",
        ),
        max_attempts=3,
    ),
    StageName.RESEARCH: StageContract(
        stage=StageName.RESEARCH,
        title="Research",
        summary=(
            "Gathers source-backed evidence about one prospect. Every claim "
            "must carry a source URL and a verification status; the stage may "
            "not invent facts."
        ),
        requires=(
            Field("prospect_id", FieldKind.ID),
            Field("profile_id", FieldKind.ID, required=False),
            Field("profile_version", FieldKind.INT, required=False),
            Field("depth", FieldKind.STRING, required=False),
            Field(
                "claims",
                FieldKind.LIST,
                required=False,
                description="Pre-collected claims supplied by a connector.",
            ),
        ),
        produces=(
            Field("evidence_ids", FieldKind.LIST),
            Field("evidence_count", FieldKind.INT),
            Field("verified_count", FieldKind.INT),
            Field("collector", FieldKind.STRING, required=False),
            Field("research_summary", FieldKind.MAP, required=False),
        ),
        transitions=(
            ("discovered", "researching"),
            ("researching", "researched"),
        ),
        failures=(
            _f("prospect_not_found", False, "return_to_discovery",
               "The prospect does not exist in this workspace."),
            _f("source_unavailable", True, "retry_stage",
               "No research connector returned usable claims."),
            _f("rate_limited", True, "retry_stage_later",
               "A research connector rate-limited the request."),
            _f("suppressed", False, "review_suppression",
               "The prospect is on the suppression list."),
            _f("invalid_transition", False, "review_prospect_status",
               "The prospect is in a state Research may not run from."),
        ),
        permission="operator",
        needs_review_when=(
            "no verified evidence was collected (only inferred/unverified)",
            "the prospect has already been researched before",
        ),
        max_attempts=3,
    ),
    StageName.QUALIFY: StageContract(
        stage=StageName.QUALIFY,
        title="Qualification",
        summary=(
            "Scores a researched prospect against the active ICP and the "
            "selected offer, producing an explainable result plus a "
            "justified offer match."
        ),
        requires=(
            Field("prospect_id", FieldKind.ID),
            Field("icp_id", FieldKind.ID, required=False),
            Field("offer_id", FieldKind.ID, required=False),
        ),
        produces=(
            Field("qualification_id", FieldKind.ID),
            Field("score", FieldKind.INT),
            Field("is_qualified", FieldKind.BOOL),
            Field("matching_criteria", FieldKind.LIST),
            Field("missing_criteria", FieldKind.LIST),
            Field("explanation", FieldKind.STRING),
            Field("offer_match_id", FieldKind.ID, required=False),
        ),
        transitions=(
            ("researched", "qualified"),
            ("researched", "disqualified"),
        ),
        failures=(
            _f("stage_prerequisite", False, "run_prerequisite_stage",
               "Research has not produced any evidence for this prospect."),
            _f("icp_missing", False, "define_icp",
               "No active ICP exists to score against."),
            _f("offer_missing", False, "add_offer",
               "No active offer exists to match against."),
            _f("suppressed", False, "review_suppression",
               "The prospect is on the suppression list."),
        ),
        permission="operator",
        needs_review_when=(
            "score falls in the review band around the ICP threshold",
            "some criteria are missing but the score still qualifies",
        ),
        max_attempts=2,
    ),
    StageName.PERSONALIZE: StageContract(
        stage=StageName.PERSONALIZE,
        title="Personalization",
        summary=(
            "Builds a versioned message draft from the qualification result, "
            "the selected offer and the prospect's evidence. Every sentence "
            "may only rest on an attributed evidence id."
        ),
        requires=(
            Field("prospect_id", FieldKind.ID),
            Field("offer_id", FieldKind.ID, required=False),
            Field("qualification_id", FieldKind.ID, required=False),
        ),
        produces=(
            Field("draft_id", FieldKind.ID),
            Field("draft_version", FieldKind.INT),
            Field("subject", FieldKind.STRING),
            Field("body", FieldKind.STRING),
            Field("attributed_evidence_ids", FieldKind.LIST),
            Field("evidence_coverage", FieldKind.NUMBER, required=False),
        ),
        transitions=(("qualified", "draft_ready"),),
        failures=(
            _f("stage_prerequisite", False, "run_prerequisite_stage",
               "The prospect is not qualified yet."),
            _f("offer_missing", False, "add_offer",
               "No offer is selected for this prospect."),
            _f("draft_not_found", False, "regenerate_draft",
               "The referenced draft does not exist."),
        ),
        permission="operator",
        needs_review_when=(
            "evidence coverage is below the configured floor",
            "the draft was regenerated after an earlier version was sent",
        ),
        max_attempts=3,
    ),
    StageName.OUTREACH: StageContract(
        stage=StageName.OUTREACH,
        title="Outreach",
        summary=(
            "Approves a draft (explicit human authorization when the tenant "
            "requires it), enforces suppression and sending policy, then "
            "dispatches through the configured transport."
        ),
        requires=(
            Field("draft_id", FieldKind.ID),
            Field("sender_email", FieldKind.STRING, required=False),
            Field(
                "approved",
                FieldKind.BOOL,
                required=True,
                description="True when this call is the authorization itself.",
            ),
        ),
        produces=(
            Field("draft_status", FieldKind.STRING),
            Field("sent_message_id", FieldKind.ID, required=False),
            Field("message_id", FieldKind.STRING, required=False),
            Field("delivery_status", FieldKind.STRING, required=False),
            Field("transport", FieldKind.STRING, required=False),
        ),
        transitions=(
            ("draft_ready", "in_campaign"),
        ),
        failures=(
            _f("approval_required", False, "approve_draft",
               "The tenant requires explicit human approval before sending."),
            _f("draft_not_approved", False, "review_draft",
               "The draft is not in an approved state."),
            _f("suppressed", False, "review_suppression",
               "The recipient is on the suppression list."),
            _f("rate_limited", True, "retry_stage_later",
               "The tenant sending rate limit is exhausted."),
            _f("transport_rejected", True, "retry_stage",
               "The transport rejected the message."),
            _f("provider_unavailable", True, "retry_stage",
               "The transport could not be reached."),
        ),
        permission="operator",
        needs_review_when=(
            "the transport accepted the message but did not confirm delivery",
        ),
        max_attempts=3,
    ),
    StageName.CONVERSE: StageContract(
        stage=StageName.CONVERSE,
        title="Conversations",
        summary=(
            "Records an inbound reply against the same prospect and "
            "conversation, classifies intent, and applies policy effects "
            "(suppression on opt-out)."
        ),
        requires=(
            Field("prospect_id", FieldKind.ID, required=False),
            Field("sender_email", FieldKind.STRING),
            Field("subject", FieldKind.STRING),
            Field("body", FieldKind.STRING),
            Field("in_reply_to", FieldKind.STRING, required=False),
        ),
        produces=(
            Field("conversation_id", FieldKind.ID),
            Field("reply_id", FieldKind.ID),
            Field("intent", FieldKind.STRING),
            Field("intent_confidence", FieldKind.NUMBER),
            Field("recommended_action", FieldKind.STRING),
            Field("requires_action", FieldKind.BOOL, required=False,
                  description="True when a human still has to respond."),
            Field("suppressed", FieldKind.BOOL, required=False),
        ),
        transitions=(
            ("in_campaign", "replied"),
            ("in_campaign", "opted_out"),
        ),
        failures=(
            _f("prospect_not_found", False, "return_to_discovery",
               "No prospect matches the sender in this workspace."),
            _f("prospect_invalid", False, "fix_prospect_record",
               "The reply could not be threaded to an outbound message."),
        ),
        permission="service",
        needs_review_when=(
            "intent could not be classified with enough confidence",
            "the reply is not a reply to a tracked outbound message",
        ),
        max_attempts=1,
    ),
    StageName.SYNTHESIZE: StageContract(
        stage=StageName.SYNTHESIZE,
        title="Overview",
        summary=(
            "Reads the persisted pipeline and reports what needs attention. "
            "Synthesize never mutates pipeline records."
        ),
        requires=(),
        produces=(
            Field("counts", FieldKind.MAP),
            Field("attention", FieldKind.LIST),
            Field("next_actions", FieldKind.LIST),
            Field("health", FieldKind.MAP),
        ),
        transitions=(),
        failures=(
            _f("not_authorized", False, "request_authorization",
               "The caller lacks read access to the workspace."),
        ),
        permission="viewer",
        max_attempts=1,
    ),
}


# Convenience: deliberate alias — the pipeline-facing name of CONFIGURE.
CONFIGURE = StageName.CONFIGURE


def contract_for(stage: StageName | str) -> StageContract:
    key = StageName(stage)
    try:
        return CONTRACTS[key]
    except KeyError as exc:  # pragma: no cover - defensive
        raise KeyError(f"no contract registered for stage {key!r}") from exc


@dataclass(frozen=True)
class Handoff:
    """A documented handoff between two stages, for the UI timeline."""

    from_stage: StageName
    to_stage: StageName
    carried: tuple[str, ...] = field(default_factory=tuple)
    blocked_by: tuple[str, ...] = field(default_factory=tuple)


HANDOFFS: tuple[Handoff, ...] = (
    Handoff(
        StageName.CONFIGURE, StageName.DISCOVER,
        carried=("profile_id", "profile_version", "icp_id", "icp_version"),
        blocked_by=("profile_missing", "icp_missing"),
    ),
    Handoff(
        StageName.DISCOVER, StageName.RESEARCH,
        carried=("prospect_id", "source", "profile_version"),
        blocked_by=("prospect_not_found", "suppressed"),
    ),
    Handoff(
        StageName.RESEARCH, StageName.QUALIFY,
        carried=("evidence_ids", "profile_version", "icp_version"),
        blocked_by=("stage_prerequisite", "icp_missing"),
    ),
    Handoff(
        StageName.QUALIFY, StageName.PERSONALIZE,
        carried=("qualification_id", "score", "offer_match_id", "evidence_ids"),
        blocked_by=("stage_prerequisite", "offer_missing"),
    ),
    Handoff(
        StageName.PERSONALIZE, StageName.OUTREACH,
        carried=("draft_id", "draft_version", "attributed_evidence_ids"),
        blocked_by=("approval_required", "suppressed", "rate_limited"),
    ),
    Handoff(
        StageName.OUTREACH, StageName.CONVERSE,
        carried=("sent_message_id", "message_id", "conversation_id"),
        blocked_by=(
            "prospect_not_found",
            "approval_required",
            "suppressed",
            "rate_limited",
        ),
    ),
    Handoff(
        StageName.CONVERSE, StageName.SYNTHESIZE,
        carried=("intent", "requires_action", "suppressed"),
    ),
)


__all__ = [
    "CONTRACTS",
    "CONFIGURE",
    "HANDOFFS",
    "Field",
    "FieldKind",
    "FailureMode",
    "Handoff",
    "StageContract",
    "StageName",
    "contract_for",
]
