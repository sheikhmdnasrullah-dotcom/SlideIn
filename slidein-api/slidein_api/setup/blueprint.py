"""Workspace blueprint: turn a business profile into a proposed workspace.

The proposal only ever names capabilities that exist. It is validated
against the module registry, a registered workflow blueprint, and the
deployment-config schema before anything is persisted. A capability the
product does not have is recorded as a proposed core-product enhancement —
never as an enabled module or a fake integration.
"""

from __future__ import annotations

import re
from typing import Any

from ..blueprints import get_blueprint, validate_deployment_config
from ..services.modules import DEFAULT_ENABLED, MODULE_IDS, MODULE_REGISTRY

MODULE_LABELS: dict[str, str] = {
    entry["id"]: entry["label"] for entry in MODULE_REGISTRY
}

#: Reading the scope honestly. Absence of these phrases means the default
#: managed-service scope (find, research, qualify, write, approve, send).
_NO_OUTBOUND = re.compile(
    r"\b(?:no\s+(?:cold\s+)?email|without\s+(?:email|outbound)|"
    r"organic\s+only|inbound[- ]only|no\s+outbound|do\s+not\s+send\b)",
    re.IGNORECASE,
)
_NO_INBOX = re.compile(
    r"\b(?:no\s+(?:reply|replies|inbox)|without\s+(?:replies|inbox)|"
    r"no\s+inbound\s+mail)\b",
    re.IGNORECASE,
)
_NO_PROSPECTING = re.compile(
    r"\b(?:no\s+prospecting|no\s+discovery|no\s+lead\s+generation)\b",
    re.IGNORECASE,
)

#: Requested things the product cannot do today. Kept honest: named as
#: enhancements, never silently enabled.
UNSUPPORTED_CAPABILITIES: tuple[tuple[str, str], ...] = (
    (r"\b(?:sms|text message|texting|twilio)\b",
     "SMS outreach is not a supported capability; would be a core-product enhancement."),
    (r"\b(?:voice call|cold call|phone call|dialer|telephony)\b",
     "Automated calling is not a supported capability; would be a core-product enhancement."),
    (r"\b(?:whatsapp|telegram message|slack message)\b",
     "Messaging-channel outreach is not a supported capability; would be a core-product enhancement."),
    (r"\b(?:linkedin|social (?:dm|outreach)|twitter dm)\b",
     "Social-platform outreach is not a supported capability; would be a core-product enhancement."),
    (r"\b(?:live chat|chat widget|website chat|intercom)\b",
     "On-site chat is not a supported capability; would be a core-product enhancement."),
    (r"\b(?:receiving mailbox|imap|inbound (?:mail|email) sync|read (?:their|the) inbox)\b",
     "Reading a client mailbox is not supported in this build (no inbound mail path); "
     "reply handling currently relies on forwarded or webhook replies."),
    (r"\b(?:payment|billing|invoic|stripe)\b",
     "Billing is not a supported capability; would be a core-product enhancement."),
)

CRM_HINTS: tuple[tuple[str, str], ...] = (
    (r"hubspot", "hubspot"),
    (r"pipedrive", "pipedrive"),
    (r"salesforce", "salesforce"),
    (r"zoho", "zoho"),
    (r"close\.io|close crm", "close"),
    (r"\bcrm\b", "crm"),
)


def _detect_crm(text: str) -> str:
    lowered = (text or "").lower()
    for pattern, provider in CRM_HINTS:
        if re.search(pattern, lowered):
            return provider
    return ""


def _unsupported_requests(draft: dict) -> list[dict]:
    corpus = " ".join(
        str((draft.get("fields", {}).get(key) or {}).get("value") or "")
        for key in (
            "service_scope", "integrations_required", "operational_constraints",
            "data_available", "processes", "approval_requirements",
        )
    )
    found: list[dict] = []
    for pattern, reason in UNSUPPORTED_CAPABILITIES:
        if re.search(pattern, corpus, re.IGNORECASE):
            found.append({
                "capability": reason.split(";")[0].rstrip("."),
                "reason": reason,
                "status": "proposed_core_enhancement",
            })
    return found


def _scope_flags(draft: dict, answers: dict) -> dict:
    scope_text = " ".join([
        str((draft.get("fields", {}).get("service_scope") or {}).get("value") or ""),
        str((draft.get("fields", {}).get("approval_requirements") or {}).get("value") or ""),
        str(answers.get("service_scope") or ""),
    ])
    include_prospecting = not _NO_PROSPECTING.search(scope_text)
    include_outreach = include_prospecting and not _NO_OUTBOUND.search(scope_text)
    include_inbox = include_outreach and not _NO_INBOX.search(scope_text)
    return {
        "include_prospecting": include_prospecting,
        "include_outreach": include_outreach,
        "include_inbox": include_inbox,
        "scope_text": scope_text.strip(),
    }


def _enabled_modules(flags: dict) -> list[str]:
    enabled = ["overview", "activity", "settings"]
    if flags["include_prospecting"]:
        enabled += ["discovery", "research", "qualification"]
    if flags["include_outreach"]:
        enabled += ["personalization", "outreach"]
    if flags["include_inbox"]:
        enabled += ["inbox"]
    # Keep registry order, never drop `settings`, never invent an id.
    ordered = [m for m in DEFAULT_ENABLED if m in enabled]
    if "settings" not in ordered:
        ordered.append("settings")
    assert set(ordered) <= set(MODULE_IDS), f"unknown module in proposal: {ordered}"
    return ordered


def _terminology(draft: dict, answers: dict, industry_key: str) -> dict:
    """Business-specific wording. Only replaces a label when the profile
    actually supplies the noun — no invented vocabulary."""
    from ..factory.compiler import INDUSTRY_TERMINOLOGY

    terms = dict(INDUSTRY_TERMINOLOGY.get(industry_key,
                                           INDUSTRY_TERMINOLOGY["agency"]))
    sections: dict[str, str] = {}
    products = str((draft.get("fields", {}).get("products_services") or {}).get("value") or "")
    if products:
        first = re.split(r"[;\n,]", products)[0].strip()
        if 0 < len(first) <= 40:
            sections["personalization"] = f"{first} drafts"
    icp = str((draft.get("fields", {}).get("ideal_customer_profile") or {}).get("value") or "")
    if icp:
        noun = re.split(r"[.,;]", icp)[0].strip()
        if 0 < len(noun) <= 40:
            sections["discovery"] = f"Find {noun}"
            sections["qualification"] = f"Qualify {noun}"
    if answers.get("meeting_label"):
        terms["meeting"] = str(answers["meeting_label"]).strip()
    return {"sections": sections, "entities": terms}


def propose_blueprint(
    draft: dict,
    answers: dict,
    *,
    tenant_name: str = "",
) -> dict:
    """Build the proposed workspace for this business."""
    blueprint = get_blueprint("prospect_to_conversation", "1.0.0")
    flags = _scope_flags(draft, answers)
    enabled = _enabled_modules(flags)
    nav_order = list(enabled)

    scope_corpus = " ".join([
        flags["scope_text"],
        str((draft.get("fields", {}).get("integrations_required") or {}).get("value") or ""),
        str(answers.get("crm_provider") or ""),
    ])
    crm_provider = str(answers.get("crm_provider") or "").strip() or _detect_crm(scope_corpus)

    transport = str(answers.get("transport") or "dry_run").lower()
    if transport not in ("dry_run", "smtp"):
        transport = "dry_run"

    required_integrations: list[dict] = []
    if flags["include_outreach"]:
        required_integrations.append({
            "id": "sending_account",
            "label": "Email sending account",
            "provider": "smtp" if transport == "smtp" else "smtp",
            "required": transport != "dry_run",
            "probe": "supported" if transport == "smtp" else "not_required",
            "reason": ("Live sending needs an authenticated sending account."
                       if transport == "smtp" else
                       "Transport is dry-run: no live account is contacted until you switch."),
            "secret_ref": "SMTP_CONNECTION" if transport == "smtp" else "",
        })
        required_integrations.append({
            "id": "sending_domain_dns",
            "label": "Sending domain DNS (SPF/DKIM/DMARC)",
            "provider": "dns",
            "required": transport == "smtp",
            "probe": "manual",
            "reason": "Verify DNS authentication before any live send.",
            "secret_ref": "",
        })
        required_integrations.append({
            "id": "suppression",
            "label": "Suppression and unsubscribe list",
            "provider": "builtin",
            "required": True,
            "probe": "builtin",
            "reason": "Opt-outs must be honoured before the first send.",
            "secret_ref": "",
        })
    if crm_provider:
        required_integrations.append({
            "id": "crm",
            "label": f"{crm_provider.title()} CRM",
            "provider": crm_provider,
            "required": str(answers.get("crm_required") or "").lower() in ("1", "true", "yes"),
            "probe": "unsupported",
            "reason": "Field maps and credentials are needed before records sync.",
            "secret_ref": f"{crm_provider.upper()}_API_KEY",
        })

    success_measures = [
        line.strip()
        for line in re.split(r"[;\n]", str(
            (draft.get("fields", {}).get("success_measures") or {}).get("value") or ""))
        if line.strip()
    ]
    approver = str(answers.get("approver") or "").strip()
    approval_policy = {
        "require_approval": str(answers.get("require_approval", "true")).lower() != "false",
        "approver": approver,
        "sla_hours": int(answers.get("approval_sla_hours") or 24),
        "boundaries": [
            "Every send waits for human approval before dispatch.",
            "Suppression and rate limits are enforced regardless of approval state.",
        ],
    }
    if not flags["include_outreach"]:
        approval_policy["boundaries"].append(
            "Outreach is out of scope for this workspace: no drafts are dispatched."
        )

    deployment_config: dict[str, Any] = {
        "blueprint_name": blueprint.name,
        "blueprint_version": blueprint.version,
        "sending": {
            "sender": str(answers.get("sender") or "").strip(),
            "physical_postal_address": str(answers.get("physical_postal_address") or "").strip(),
            "lawful_basis": str(answers.get("lawful_basis") or "").strip(),
            "transport": transport,
        },
        "limits": {
            "hourly_limit": int(answers.get("hourly_limit") or 10),
            "daily_limit": int(answers.get("daily_limit") or 50),
        },
        "approvals": {
            "require_approval": approval_policy["require_approval"],
            "approver": approver,
            "sla_hours": approval_policy["sla_hours"],
        },
        "assignment_policy": str(answers.get("assignment_policy") or "manual"),
        "crm_provider": crm_provider,
        "modules": enabled,
    }

    validation = validate_deployment_config(blueprint, deployment_config)
    module_violations = [m for m in enabled if m not in MODULE_IDS]

    stages = list(blueprint.stages)
    active_stages = [
        stage for stage, module in _STAGE_MODULES.items()
        if module in enabled or stage in ("configure",)
    ]

    return {
        "blueprint": {
            "name": blueprint.name,
            "version": blueprint.version,
            "title": blueprint.title,
            "summary": blueprint.summary,
            "declared_stages": stages,
            "active_stages": [s for s in stages if s in active_stages],
            "approval_gates": [
                {"name": g.name, "stage": g.stage, "approver_role": g.approver_role,
                 "sla_hours": g.sla_hours}
                for g in blueprint.approval_gates
            ],
        },
        "modules": {"enabled": enabled, "nav_order": nav_order,
                    "registry_labels": MODULE_LABELS},
        "terminology": _terminology(draft, answers, draft.get("industry_key", "agency")),
        "required_integrations": required_integrations,
        "approval_policy": approval_policy,
        "reporting": {
            "success_measures": success_measures,
            "sections": [MODULE_LABELS[m] for m in enabled],
        },
        "scope": flags,
        "deployment_config": deployment_config,
        "proposed_enhancements": _unsupported_requests(draft),
        "validation": {
            "ok": validation.ok and not module_violations,
            "missing_required": list(validation.missing_required),
            "missing_integrations": list(validation.missing_integrations),
            "unsupported": list(validation.unsupported),
            "warnings": list(validation.warnings),
            "module_violations": module_violations,
            "reasons": validation.reasons(),
        },
        "client_name": tenant_name,
    }


#: Stage → the module that fronts it, so the workflow preview matches the
#: sections the workspace will actually expose.
_STAGE_MODULES: dict[str, str] = {
    "configure": "settings",
    "discover": "discovery",
    "research": "research",
    "qualify": "qualification",
    "personalize": "personalization",
    "outreach": "outreach",
    "converse": "inbox",
}
