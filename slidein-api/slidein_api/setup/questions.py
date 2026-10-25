"""The short list of questions that actually need a human.

Everything the sources can answer is already answered. What remains is
asked once, grouped by consequence, with a proposed default wherever a
default is safe. A default is never applied silently when the answer
changes what the system is allowed to do (legal identity, who approves a
send, whether sending is live).
"""

from __future__ import annotations

import re

from .extract import FIELD_LABELS, field_value

DEFAULT_LAWFUL_BASIS = (
    "B2B legitimate interest: relevant business outreach with a clear opt-out "
    "on every message"
)

#: Which validation stage each answer unblocks, so a question can say why
#: it matters and what happens when it is skipped.
UNBLOCKS: dict[str, str] = {
    "legal_name": "intake",
    "website_url": "intake",
    "industry": "intake",
    "business_description": "intake",
    "core_value_prop": "intake",
    "products_services": "intake",
    "ideal_customer_profile": "qualification",
    "physical_postal_address": "sending",
    "lawful_basis": "sending",
    "sender": "sending",
    "approver": "approvals",
    "require_approval": "approvals",
    "crm_provider": "crm_maps",
}

_EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


def _first_email(corpus: str) -> str:
    match = _EMAIL_RE.search(corpus or "")
    return match.group(0).strip().lower() if match else ""


def _default_sender(website_url: str, corpus: str) -> str:
    host = ""
    match = re.search(r"https?://([^/\s]+)", website_url or "")
    if match:
        host = match.group(1).lower().removeprefix("www.")
    if not host:
        found = _EMAIL_RE.search(corpus or "")
        if found:
            host = found.group(0).split("@", 1)[1].lower()
    return f"hello@{host}" if host else ""


def build_questions(
    draft: dict,
    answers: dict,
    *,
    corpus: str = "",
    outreach_enabled: bool = True,
    crm_detected: str = "",
) -> list[dict]:
    """Open questions for this workspace, most consequential first."""

    def extracted(key: str) -> str:
        return field_value(draft, key, None)

    def answered(key: str) -> str:
        return str(answers.get(key) or "").strip()

    specs: list[dict] = []

    def candidate(
        key: str,
        group: str,
        prompt: str,
        help_text: str,
        *,
        blocking: bool = False,
        kind: str = "text",
        options: list[str] | None = None,
        default: str = "",
        always: bool = False,
        profile_field: bool = True,
    ) -> None:
        specs.append({
            "key": key, "group": group, "prompt": prompt, "help": help_text,
            "blocking": blocking, "kind": kind, "options": options or [],
            "default": default, "always": always, "profile_field": profile_field,
        })

    # ── business: only what the sources could not answer ────────────────
    for key, prompt, help_text in (
        ("legal_name", "What is the registered business name?",
         "Used as the workspace name and the client identity throughout."),
        ("website_url", "What is the company website?",
         "Read to confirm positioning; also names the sending domain."),
        ("industry", "Which industry is this business in?",
         "Sets terminology and the starting ICP."),
        ("business_description", "Describe the business in one or two sentences.",
         "The single line every draft and research step is grounded in."),
        ("core_value_prop", "What do you promise that competitors do not?",
         "The stated value proposition — never a slogan invented here."),
        ("products_services", "What do you sell?",
         "Becomes the first offer in the workspace."),
        ("ideal_customer_profile", "Who is the ideal customer?",
         "Becomes the ICP the qualification stage scores against."),
    ):
        candidate(key, "business", prompt, help_text, blocking=True)

    # ── legal: never defaulted silently ─────────────────────────────────
    candidate(
        "physical_postal_address", "legal",
        "What is the physical postal address for the email footer?",
        "Required by CAN-SPAM/CASL on every message. No default is applied — "
        "an address is never invented.",
        blocking=True,
    )
    candidate(
        "lawful_basis", "legal",
        "What is the lawful basis for contacting prospects?",
        "Recorded on the sending policy. A B2B legitimate-interest wording is "
        "proposed below; confirm or replace it.",
        default=DEFAULT_LAWFUL_BASIS, blocking=True,
    )

    # ── sending ─────────────────────────────────────────────────────────
    if outreach_enabled:
        candidate(
            "sender", "sending", "Which address should send?",
            "Must exist on the sending domain. Proposed from the website; "
            "confirm before any live send.",
            default=_default_sender(extracted("website_url"), corpus),
            blocking=True,
        )
        candidate(
            "transport", "sending", "How should the first test send run?",
            "Dry-run never contacts a real mailbox. Live SMTP is only used "
            "after the sending account passes its probe.",
            default="dry_run", kind="choice", options=["dry_run", "smtp"],
            always=True, profile_field=False,
        )
        candidate(
            "approver", "sending", "Who approves drafts before they send?",
            "Every outbound message waits for this person. A default from the "
            "supplied contacts is proposed; confirm it.",
            default=_first_email(corpus) or _default_sender(
                extracted("website_url"), corpus),
            blocking=True,
        )
        candidate(
            "require_approval", "approvals",
            "Require human approval before every send?",
            "Off lets automation dispatch without review. Never changed "
            "silently.",
            default="true", kind="choice", options=["true", "false"],
            always=True, profile_field=False,
        )

    # ── integrations ────────────────────────────────────────────────────
    if crm_detected:
        candidate(
            "crm_provider", "integrations", "Which CRM should this workspace use?",
            "Field maps and a credential are required before any record syncs.",
            default=crm_detected, kind="choice",
            options=["hubspot", "pipedrive", "salesforce", "zoho", "close", "none"],
            always=True, profile_field=False,
        )

    questions: list[dict] = []
    for spec in specs:
        key = spec["key"]
        given = answered(key)
        current = given or extracted(key) if spec["profile_field"] else given or spec["default"]
        if spec["profile_field"] and not given and not current:
            current = spec["default"]

        if given:
            status = "answered"
        elif current:
            status = "prefilled"
        else:
            status = "open"

        # Keep the list short: an extracted, non-blocking value needs no
        # question. Answered items always stay visible for the review step.
        if status == "prefilled" and not spec["always"] and not spec["blocking"]:
            continue

        questions.append({
            "key": key,
            "group": spec["group"],
            "prompt": spec["prompt"],
            "help": spec["help"],
            "default": spec["default"],
            "value": current,
            "status": status,
            "required": spec["blocking"],
            "blocking": spec["blocking"] and status != "answered",
            "kind": spec["kind"],
            "options": spec["options"],
            "unblocks": UNBLOCKS.get(key, ""),
            "answered_by": "operator" if given else "",
        })

    order = {"business": 0, "legal": 1, "sending": 2, "approvals": 3,
             "integrations": 4}
    questions.sort(key=lambda q: (order.get(q["group"], 9),
                                  0 if q["status"] == "open" else 1))
    return questions


def open_blocking(questions: list[dict]) -> list[dict]:
    return [q for q in questions if q["blocking"]]


def grouped(questions: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for question in questions:
        out.setdefault(question["group"], []).append(question)
    return out


def apply_answers(draft: dict, answers: dict) -> dict:
    """Fold operator answers into the profile as confirmed, sourced facts."""
    from .extract import apply_answer

    for key, value in (answers or {}).items():
        if key in FIELD_LABELS and str(value).strip():
            apply_answer(draft, key, str(value))
    return draft
