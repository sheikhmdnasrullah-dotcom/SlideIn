"""The short list of questions that actually need a human.

Everything the sources can answer is already answered. What remains is
asked once, grouped by consequence, with a proposed default wherever a
default is safe. A default is never applied silently when the answer
changes what the system is allowed to do (legal identity, who approves a
send, whether sending is live).
"""

from __future__ import annotations

import re
from typing import Any

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
    """Open questions for this workspace, in the order they should be asked."""
    questions: list[dict] = []

    def value(key: str) -> str:
        return field_value(draft, key, answers)

    def add(
        key: str,
        group: str,
        prompt: str,
        help_text: str,
        *,
        default: str = "",
        blocking: bool = False,
        kind: str = "text",
        options: list[str] | None = None,
    ) -> None:
        answered = bool(str(answers.get(key, "")).strip())
        current = str(answers.get(key) or value(key) or "")
        questions.append({
            "key": key,
            "group": group,
            "prompt": prompt,
            "help": help_text,
            "default": default,
            "value": current if answered else (default if default and blocking is False else current),
            "status": "answered" if answered else ("open" if blocking or not value(key) else "prefilled"),
            "required": blocking,
            "blocking": blocking,
            "kind": kind,
            "options": options or [],
            "unblocks": UNBLOCKS.get(key, ""),
            "answered_by": "operator" if answered else "",
        })

    # ── business: only what the sources could not answer ────────────────
    if not value("legal_name"):
        add("legal_name", "business", "What is the registered business name?",
            "Used as the workspace name and the client identity throughout.")
    if not value("website_url"):
        add("website_url", "business", "What is the company website?",
            "Read to confirm positioning; also the source for the sending domain.",
            blocking=True)
    if not value("industry"):
        add("industry", "business", "Which industry is this business in?",
            "Sets terminology and the starting ICP.", blocking=True)
    if not value("business_description"):
        add("business_description", "business",
            "Describe the business in one or two sentences.",
            "The single line every draft and research step is grounded in.",
            blocking=True)
    if not value("core_value_prop"):
        add("core_value_prop", "business", "What do you promise that competitors do not?",
            "Stated value proposition — not a slogan invented here.", blocking=True)
    if not value("products_services"):
        add("products_services", "business", "What do you sell?",
            "Becomes the first offer in the workspace.", blocking=True)
    if not value("ideal_customer_profile"):
        add("ideal_customer_profile", "business", "Who is the ideal customer?",
            "Becomes the ICP the qualification stage scores against.",
            blocking=True)

    # ── legal: never defaulted silently ─────────────────────────────────
    if not value("physical_postal_address"):
        add("physical_postal_address", "legal",
            "What is the physical postal address for the email footer?",
            "Required by CAN-SPAM/CASL on every message. No default is applied — "
            "an address is never invented.",
            blocking=True)
    if not value("lawful_basis"):
        add("lawful_basis", "legal", "What is the lawful basis for contacting prospects?",
            "Recorded on the sending policy. A B2B legitimate-interest wording is "
            "proposed below; confirm or replace it.",
            default=DEFAULT_LAWFUL_BASIS, blocking=True)

    # ── sending ─────────────────────────────────────────────────────────
    if outreach_enabled:
        sender_default = _default_sender(value("website_url"), corpus)
        if not value("sender"):
            add("sender", "sending", "Which address should send?",
                "Must exist on the sending domain. Proposed from the website; "
                "confirm before any live send.",
                default=sender_default, blocking=True)
        if str(answers.get("transport") or "") == "":
            add("transport", "sending", "How should the first test send run?",
                "Dry-run never contacts a real mailbox. Live SMTP is only used "
                "after the sending account passes its probe.",
                default="dry_run", kind="choice",
                options=["dry_run", "smtp"])
        if not value("approver"):
            add("approver", "sending", "Who approves drafts before they send?",
                "Every outbound message waits for this person. A default from "
                "the supplied contacts is proposed; confirm it.",
                default=_first_email(corpus) or sender_default, blocking=True)

    # ── integrations ────────────────────────────────────────────────────
    if crm_detected and not value("crm_provider"):
        add("crm_provider", "integrations", "Which CRM should this workspace use?",
            "Field maps and a credential are required before any record syncs.",
            default=crm_detected, kind="choice",
            options=["hubspot", "pipedrive", "salesforce", "zoho", "close", "none"])

    # ── re-list answered items so the review screen shows everything ────
    for key, group, prompt, help_text in (
        ("require_approval", "approvals",
         "Require human approval before every send?",
         "Turning this off lets automation dispatch without review.",
         ),
        ("hourly_limit", "limits", "Hourly send limit", "Provider-safe default is 10/hour."),
        ("daily_limit", "limits", "Daily send limit", "Provider-safe default is 50/day."),
    ):
        if str(answers.get(key, "")).strip():
            questions.append({
                "key": key, "group": group, "prompt": prompt, "help": help_text,
                "default": "", "value": str(answers[key]),
                "status": "answered", "required": False, "blocking": False,
                "kind": "choice" if key == "require_approval" else "number",
                "options": ["true", "false"] if key == "require_approval" else [],
                "unblocks": UNBLOCKS.get(key, ""),
                "answered_by": "operator",
            })

    order = {"business": 0, "legal": 1, "sending": 2, "approvals": 3,
             "integrations": 4, "limits": 5}
    questions.sort(key=lambda q: (order.get(q["group"], 9), 0 if q["status"] == "open" else 1))
    return questions


def open_blocking(questions: list[dict]) -> list[dict]:
    return [q for q in questions if q["status"] == "open" and q["blocking"]]


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
