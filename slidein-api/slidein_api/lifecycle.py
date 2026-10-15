"""Explicit lifecycle transitions for every stateful record.

Transitions are declared once here and enforced by the StageRunner, so a
record can never silently change state from a UI click. Every accepted
transition is appended to the prospect's history and mirrored into the
activity log.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping

from .models import (
    ConversationState,
    DraftStatus,
    ProspectStatus,
    ReplyIntent,
    SentStatus,
)

# ---------------------------------------------------------------------------
# Prospect lifecycle
# ---------------------------------------------------------------------------

#: Guards expressed as human-readable rules; the code checks the ones it
#: can and documents the rest so the UI and the API agree.
PROSPECT_TRANSITIONS: dict[str, tuple[str, ...]] = {
    ProspectStatus.DISCOVERED.value: (
        ProspectStatus.RESEARCHING.value,
        ProspectStatus.DISQUALIFIED.value,
    ),
    ProspectStatus.RESEARCHING.value: (
        ProspectStatus.RESEARCHED.value,
        ProspectStatus.DISQUALIFIED.value,
    ),
    # Re-research is allowed so evidence can be refreshed.
    ProspectStatus.RESEARCHED.value: (
        ProspectStatus.RESEARCHING.value,
        ProspectStatus.QUALIFIED.value,
        ProspectStatus.DISQUALIFIED.value,
    ),
    ProspectStatus.QUALIFIED.value: (
        ProspectStatus.DRAFT_READY.value,
        ProspectStatus.DISQUALIFIED.value,
    ),
    ProspectStatus.DRAFT_READY.value: (
        ProspectStatus.IN_CAMPAIGN.value,
        ProspectStatus.QUALIFIED.value,  # draft rejected -> back to qualified
        ProspectStatus.OPTED_OUT.value,
    ),
    ProspectStatus.IN_CAMPAIGN.value: (
        ProspectStatus.REPLIED.value,
        ProspectStatus.OPTED_OUT.value,
        ProspectStatus.QUALIFIED.value,  # all sends failed -> retryable
    ),
    ProspectStatus.REPLIED.value: (
        ProspectStatus.IN_CAMPAIGN.value,
        ProspectStatus.OPTED_OUT.value,
    ),
    # Opt-out is absorbing.
    ProspectStatus.OPTED_OUT.value: (),
    ProspectStatus.DISQUALIFIED.value: (),
}

#: Transitions that any stage may force regardless of the current state.
FORCED_PROSPECT_TRANSITIONS: dict[str, tuple[str, ...]] = {
    ProspectStatus.OPTED_OUT.value: (
        ProspectStatus.DISCOVERED.value,
        ProspectStatus.RESEARCHING.value,
        ProspectStatus.RESEARCHED.value,
        ProspectStatus.QUALIFIED.value,
        ProspectStatus.DRAFT_READY.value,
        ProspectStatus.IN_CAMPAIGN.value,
        ProspectStatus.REPLIED.value,
    ),
}

STAGE_TRANSITIONS: dict[str, tuple[tuple[str, str], ...]] = {
    "research": (
        (ProspectStatus.DISCOVERED.value, ProspectStatus.RESEARCHING.value),
        (ProspectStatus.RESEARCHING.value, ProspectStatus.RESEARCHED.value),
    ),
    "qualify": (
        (ProspectStatus.RESEARCHED.value, ProspectStatus.QUALIFIED.value),
        (ProspectStatus.RESEARCHED.value, ProspectStatus.DISQUALIFIED.value),
    ),
    "personalize": (
        (ProspectStatus.QUALIFIED.value, ProspectStatus.DRAFT_READY.value),
    ),
    "outreach": (
        (ProspectStatus.DRAFT_READY.value, ProspectStatus.IN_CAMPAIGN.value),
    ),
    "converse": (
        (ProspectStatus.IN_CAMPAIGN.value, ProspectStatus.REPLIED.value),
        (ProspectStatus.IN_CAMPAIGN.value, ProspectStatus.OPTED_OUT.value),
        (ProspectStatus.REPLIED.value, ProspectStatus.OPTED_OUT.value),
    ),
}

#: Draft lifecycle.
DRAFT_TRANSITIONS: dict[str, tuple[str, ...]] = {
    DraftStatus.PENDING_REVIEW.value: (
        DraftStatus.APPROVED.value,
        DraftStatus.REJECTED.value,
    ),
    DraftStatus.APPROVED.value: (
        DraftStatus.SENT.value,
        DraftStatus.REJECTED.value,  # approval withdrawn before dispatch
    ),
    DraftStatus.SENT.value: (),
    DraftStatus.REJECTED.value: (),
    DraftStatus.CANCELLED.value: (),
}

#: Sent-message delivery lifecycle.
SENT_TRANSITIONS: dict[str, tuple[str, ...]] = {
    SentStatus.QUEUED.value: (SentStatus.SUBMITTED.value, SentStatus.FAILED.value),
    SentStatus.SUBMITTED.value: (
        SentStatus.ACCEPTED.value,
        SentStatus.DELIVERED.value,
        SentStatus.BOUNCED.value,
        SentStatus.DEFERRED.value,
        SentStatus.FAILED.value,
    ),
    SentStatus.ACCEPTED.value: (
        SentStatus.DELIVERED.value,
        SentStatus.BOUNCED.value,
        SentStatus.COMPLAINED.value,
    ),
    SentStatus.DELIVERED.value: (SentStatus.COMPLAINED.value,),
    SentStatus.DEFERRED.value: (
        SentStatus.SUBMITTED.value,  # retry
        SentStatus.BOUNCED.value,
        SentStatus.FAILED.value,
    ),
    SentStatus.BOUNCED.value: (),
    SentStatus.COMPLAINED.value: (),
    SentStatus.FAILED.value: (),
}

CONVERSATION_TRANSITIONS: dict[str, tuple[str, ...]] = {
    ConversationState.OPEN.value: (
        ConversationState.AWAITING_REPLY.value,
        ConversationState.CLOSED.value,
    ),
    ConversationState.AWAITING_REPLY.value: (
        ConversationState.OPEN.value,
        ConversationState.CLOSED.value,
    ),
    ConversationState.CLOSED.value: (),
}


@dataclass
class TransitionResult:
    ok: bool
    from_state: str
    to_state: str
    reason: str = ""
    error_code: str = ""

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "reason": self.reason,
            "error_code": self.error_code,
        }


def can_transition(table: Mapping[str, tuple[str, ...]], current: str, target: str,
                   forced: Mapping[str, tuple[str, ...]] | None = None) -> bool:
    if current == target:
        return True
    allowed = table.get(current, ())
    if target in allowed:
        return True
    if forced and current in forced and target in forced[current]:
        return True
    return False


def check_transition(table: Mapping[str, tuple[str, ...]], current: str, target: str,
                     *, forced: Mapping[str, tuple[str, ...]] | None = None,
                     subject: str = "record") -> TransitionResult:
    if can_transition(table, current, target, forced):
        return TransitionResult(ok=True, from_state=current, to_state=target)
    return TransitionResult(
        ok=False,
        from_state=current,
        to_state=target,
        reason=(
            f"Cannot move {subject} from {current!r} to {target!r}. "
            f"Allowed: {list(table.get(current, ()))}"
        ),
        error_code="invalid_transition",
    )


@dataclass
class ProspectHistory:
    """The append-only state trail carried on the prospect record."""

    entries: list[dict] = field(default_factory=list)

    def append(self, state: str, *, reason: str = "", actor: str = "", stage: str = "",
               run_id: str = "") -> dict:
        from .models import utcnow

        if self.entries:
            self.entries[-1]["exited_at"] = utcnow().isoformat()
        entry = {
            "state": state,
            "entered_at": utcnow().isoformat(),
            "exited_at": None,
            "reason": reason,
            "actor": actor,
            "stage": stage,
            "run_id": run_id,
        }
        self.entries.append(entry)
        return entry

    def to_list(self) -> list[dict]:
        return list(self.entries)


def stage_target_for(stage: str, outcome: Mapping) -> str:
    """Map a stage outcome onto the prospect state it implies."""
    status = outcome.get("status")
    if status != "succeeded":
        return ""
    if stage == "research":
        return ProspectStatus.RESEARCHED.value
    if stage == "qualify":
        return (
            ProspectStatus.QUALIFIED.value
            if outcome.get("is_qualified")
            else ProspectStatus.DISQUALIFIED.value
        )
    if stage == "personalize":
        return ProspectStatus.DRAFT_READY.value
    if stage == "outreach":
        return ProspectStatus.IN_CAMPAIGN.value
    if stage == "converse":
        intent = outcome.get("intent", "")
        if intent == ReplyIntent.UNSUBSCRIBE.value:
            return ProspectStatus.OPTED_OUT.value
        return ProspectStatus.REPLIED.value
    return ""


def humanize(state: str) -> str:
    return state.replace("_", " ").title()


def ordered_pipeline() -> Iterable[str]:
    return (
        ProspectStatus.DISCOVERED.value,
        ProspectStatus.RESEARCHED.value,
        ProspectStatus.QUALIFIED.value,
        ProspectStatus.DRAFT_READY.value,
        ProspectStatus.IN_CAMPAIGN.value,
        ProspectStatus.REPLIED.value,
    )
