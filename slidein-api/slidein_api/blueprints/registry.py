"""Blueprint registry and deployment-config validation.

`PROSPECT_TO_CONVERSATION_V1` is the first versioned blueprint: it names
the stages the API already implements, the configuration a client must
supply, and the gates that must pass before anything sends.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from ..contracts import StageName


@dataclass(frozen=True)
class ConfigField:
    """One piece of client configuration a blueprint needs."""

    name: str
    kind: str  # required | optional | integration_dependent
    description: str = ""
    integration: str = ""  # e.g. "smtp" when kind == integration_dependent


@dataclass(frozen=True)
class ApprovalGate:
    """A human-approval checkpoint inside a blueprint."""

    name: str
    stage: str
    approver_role: str = "operator"
    sla_hours: int = 24


@dataclass(frozen=True)
class WorkflowBlueprint:
    name: str
    version: str
    title: str
    summary: str
    stages: tuple[str, ...]
    config_fields: tuple[ConfigField, ...] = ()
    approval_gates: tuple[ApprovalGate, ...] = ()
    retry_policy: str = ""
    monitoring: tuple[str, ...] = ()


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    missing_required: tuple[str, ...] = ()
    missing_integrations: tuple[str, ...] = ()
    unsupported: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def reasons(self) -> list[str]:
        out = [f"missing required: {n}" for n in self.missing_required]
        out += [f"missing integration: {n}" for n in self.missing_integrations]
        out += [f"unsupported requirement: {n}" for n in self.unsupported]
        return out


PROSPECT_TO_CONVERSATION_V1 = WorkflowBlueprint(
    name="prospect_to_conversation",
    version="1.0.0",
    title="Prospect to conversation",
    summary=(
        "Discover prospects, research and qualify them, draft personalized "
        "outreach, hold every send for human approval, dispatch, and track "
        "replies. Dry-run transport until real sending is configured."
    ),
    stages=tuple(
        s.value
        for s in (
            StageName.CONFIGURE,
            StageName.DISCOVER,
            StageName.RESEARCH,
            StageName.QUALIFY,
            StageName.PERSONALIZE,
            StageName.OUTREACH,
            StageName.CONVERSE,
        )
    ),
    config_fields=(
        ConfigField("profile.business_name", "required", "Client business name"),
        ConfigField("offers", "required", "At least one active offer"),
        ConfigField("icps", "required", "At least one ideal-customer profile"),
        ConfigField("sending.sender", "required", "Sending identity (email)"),
        ConfigField(
            "sending.physical_address", "required", "Postal address for footer (legal gate)"
        ),
        ConfigField("sending.lawful_basis", "required", "B2B lawful basis note (legal gate)"),
        ConfigField("approvals.approver", "required", "Who approves drafts"),
        ConfigField("approvals.sla_hours", "optional", "Approval SLA in hours"),
        ConfigField("voice.examples", "optional", "Tone/examples for personalization"),
        ConfigField("qualification.criteria", "optional", "Qualify/disqualify rules"),
        ConfigField("qualification.exclusions", "optional", "Never-contact rules"),
        ConfigField("booking.url", "optional", "Client booking link (injected in replies only)"),
        ConfigField(
            "integrations.smtp", "integration_dependent",
            "SMTP credentials", integration="smtp",
        ),
        ConfigField(
            "integrations.enrichment", "integration_dependent",
            "Enrichment provider key", integration="enrichment",
        ),
        ConfigField(
            "integrations.calendar", "integration_dependent",
            "Calendar/booking access", integration="calendar",
        ),
    ),
    approval_gates=(
        ApprovalGate("draft_approval", StageName.OUTREACH.value, "operator", 24),
        ApprovalGate("live_send_enable", StageName.OUTREACH.value, "admin", 72),
    ),
    retry_policy="StageRunner contract retries; quarantine on breaker trip; manual resume.",
    monitoring=("stage_runs", "activity_log", "delivery_events", "quarantine_state"),
)

BLUEPRINTS: dict[tuple[str, str], WorkflowBlueprint] = {
    (PROSPECT_TO_CONVERSATION_V1.name, PROSPECT_TO_CONVERSATION_V1.version): (
        PROSPECT_TO_CONVERSATION_V1
    ),
}


def get_blueprint(name: str, version: str) -> WorkflowBlueprint:
    try:
        return BLUEPRINTS[(name, version)]
    except KeyError:
        raise KeyError(f"unknown blueprint {name}@{version}") from None


def list_blueprints() -> list[WorkflowBlueprint]:
    return sorted(BLUEPRINTS.values(), key=lambda b: (b.name, b.version))


def _present(config: Mapping, dotted: str) -> bool:
    node: object = config
    for part in dotted.split("."):
        if not isinstance(node, Mapping) or part not in node:
            return False
        node = node[part]
    if node is None:
        return False
    if isinstance(node, (str, list, tuple, dict)) and len(node) == 0:
        return False
    return True


def validate_deployment_config(
    blueprint: WorkflowBlueprint, config: Mapping
) -> ValidationResult:
    """A deployment is ready only when required config is present, the
    integrations its transport needs are connected, and no unsupported
    requirement is outstanding. Unknown extras are warnings, never blocks."""
    missing_required: list[str] = []
    missing_integrations: list[str] = []
    warnings: list[str] = []

    transport = str(config.get("transport") or "dry_run").lower()
    declared = {f.name for f in blueprint.config_fields}

    for f in blueprint.config_fields:
        if f.kind == "required" and not _present(config, f.name):
            missing_required.append(f.name)
        elif f.kind == "integration_dependent":
            needed = (
                (f.integration == "smtp" and transport != "dry_run")
                or (f.integration != "smtp" and _present(config, f.name) is False
                    and str(config.get(f"require_{f.integration}", "")).lower()
                    in ("1", "true", "yes"))
            )
            if needed and not _present(config, f.name):
                missing_integrations.append(f.name)

    unsupported = [
        str(item)
        for item in (config.get("unsupported_requirements") or [])
        if str(item).strip()
    ]

    known_top = {name.split(".")[0] for name in declared} | {
        "transport", "unsupported_requirements",
    }
    for key in config:
        if key.split(".")[0] not in known_top and not key.startswith("require_"):
            warnings.append(f"unrecognized config key ignored: {key}")

    ok = not missing_required and not missing_integrations and not unsupported
    return ValidationResult(
        ok=ok,
        missing_required=tuple(missing_required),
        missing_integrations=tuple(missing_integrations),
        unsupported=tuple(unsupported),
        warnings=tuple(warnings),
    )
