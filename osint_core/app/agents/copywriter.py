"""Agent 3 — The Copywriter.

Compiles the Investigator + Researcher dossiers into a compliant, hyper-
personalized cold email draft. Hard rules (always, LLM or fallback):
  * specific, value-driven opener grounded in a VERIFIED signal only,
  * no breach/dark-web mentions, no personal-life references — non-creepy,
  * CAN-SPAM/GDPR block: opt-out line + List-Unsubscribe note + placeholder
    for tenant postal address (enforced at the send gate per PROJECT_POLICY).
"""
from __future__ import annotations

from ..schemas import EmailDraft
from .base import AgentContext, LLMClient

_COMPLIANCE_BLOCK = (
    "You are receiving this one-time business outreach because of your "
    "professional role. Reply \"unsubscribe\" and you will never hear from "
    "us again. {tenant_postal_address}"
)

_TEMPLATE = """Hi {first_name},

{opener}

{value_prop}

Worth a 10-minute call next week?

Best,
{sender_name}

{compliance}"""


class Copywriter:
    name = "copywriter"

    def __init__(self, llm: LLMClient | None = None):
        self._llm = llm or LLMClient()

    async def run(self, ctx: AgentContext) -> EmailDraft:
        investigator = ctx.prior.get("investigator", {})
        researcher = ctx.prior.get("researcher", {})
        tokens = ctx.dossier.personalization_tokens

        hooks = [
            h for h in (investigator.get("hooks") or [])
            if h and "breach" not in h.lower() and "on-chain" not in h.lower()
        ]
        opener = hooks[0] if hooks else self._fallback_opener(ctx)

        if self._llm.available:
            draft = await self._llm_draft(ctx, investigator, researcher, opener)
            if draft:
                return draft

        first = tokens.first_name or "there"
        value_prop = self._value_prop(researcher, tokens)
        body = _TEMPLATE.format(
            first_name=first,
            opener=opener,
            value_prop=value_prop,
            sender_name="{sender_name}",
            compliance=_COMPLIANCE_BLOCK,
        )
        return EmailDraft(
            subject_lines=self._subjects(ctx, investigator, researcher),
            body=body,
            personalization_hooks=hooks[:3],
            verified_signals_used=self._signals_used(investigator),
            compliance={"opt_out": 'Reply "unsubscribe"',
                        "list_unsubscribe_header": True,
                        "postal_address_placeholder": "{tenant_postal_address}"},
            llm_generated=False,
        )

    async def _llm_draft(self, ctx, investigator, researcher, opener) -> EmailDraft | None:
        tokens = ctx.dossier.personalization_tokens
        result = await self._llm.complete_json(
            system=(
                "You write short, honest B2B cold emails. Rules: under 120 words, one "
                "specific verified opener, one value proposition, no flattery, no "
                "mention of breaches, personal life, or how you found them. "
                "Return strict JSON with keys subject_lines (3), body, hooks."
            ),
            user=(
                f"first_name={tokens.first_name}\nverified_hooks={investigator.get('hooks')}\n"
                f"milestones={investigator.get('milestones')}\n"
                f"business_model={researcher.get('business_model')}\n"
                f"stack={researcher.get('likely_stack')}\n"
                f"our_product=Slidein outbound personalization platform\n"
                f"opener_preference={opener}"
            ),
            max_tokens=900,
        )
        if not result or not result.get("body"):
            return None
        body = result["body"]
        if "unsubscribe" not in body.lower():
            body = body.rstrip() + "\n\n" + _COMPLIANCE_BLOCK
        return EmailDraft(
            subject_lines=result.get("subject_lines", [])[:3],
            body=body,
            personalization_hooks=(result.get("hooks") or [])[:3],
            verified_signals_used=self._signals_used(investigator),
            compliance={"opt_out": 'Reply "unsubscribe"',
                        "list_unsubscribe_header": True,
                        "postal_address_placeholder": "{tenant_postal_address}"},
            llm_generated=True,
        )

    @staticmethod
    def _fallback_opener(ctx) -> str:
        tokens = ctx.dossier.personalization_tokens
        name = tokens.first_name or "there"
        fire = ctx.extras.get("fireenrich") or {}
        funding = fire.get("funding_tracks") or []
        if funding:
            stage = funding[0].get("stage") or "recent round"
            return f"Congrats on the {stage} — watched the announcement with interest."
        if tokens.location:
            return f"Saw that you're based in {tokens.location} — reaching out from the Slidein team."
        return f"I came across your work and wanted to reach out personally, {name}."

    @staticmethod
    def _value_prop(researcher: dict, tokens) -> str:
        stack = researcher.get("likely_stack") or []
        stack_clause = f"built for teams running {', '.join(stack[:2])}" if stack else "built for outbound teams"
        return (
            f"We help companies like yours turn public research into genuinely "
            f"personal outreach at scale — a personalization engine {stack_clause}, "
            "without the manual digging."
        )

    @staticmethod
    def _subjects(ctx, investigator, researcher) -> list[str]:
        tokens = ctx.dossier.personalization_tokens
        first = tokens.first_name or "there"
        industry = (researcher.get("industry") or "your space").strip()
        return [
            f"quick question, {first}",
            f"{first} — outreach that actually sounds like you",
            f"idea for {industry} outbound",
        ]

    @staticmethod
    def _signals_used(investigator: dict) -> list[str]:
        return [
            f"{p.get('platform')}" for p in investigator.get("verified_profiles", [])
        ][:5]
