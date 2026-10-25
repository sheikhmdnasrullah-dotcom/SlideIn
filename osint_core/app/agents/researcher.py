"""Agent 2 — The Researcher.

Cross-references corporate domain metadata to reason about the target
company: business model inference, stack posture from mail-auth/subdomain
signals, industry, and deliverability-relevant security observations that can
double as legitimate outreach angles (never fear-mongering).
"""
from __future__ import annotations

import re

from ..schemas import CompanyIntelligence
from .base import AgentContext, LLMClient

#: "[exposure] example.com grade B score 88" — first line of the flattened
#: openosint exposure report.
_EXPOSURE_RE = re.compile(r"\[exposure\] .+? grade (\S+)(?: score (\d+))?")


class Researcher:
    name = "researcher"

    def __init__(self, llm: LLMClient | None = None):
        self._llm = llm or LLMClient()

    async def run(self, ctx: AgentContext) -> dict:
        infra = ctx.infra
        company: CompanyIntelligence = ctx.company

        business_model = self._infer_business_model(company, infra)
        industry = company.industry or self._infer_industry(infra)
        posture_notes = self._posture_notes(infra)

        # OpenOSINT exposure grade — passive, domain-scoped posture signal.
        openosint = (ctx.extras or {}).get("openosint") or {}
        exposure = self._exposure_summary(openosint)
        if exposure:
            posture_notes.append(
                f"External exposure report: grade {exposure['grade']} "
                f"({exposure['score']}/100)"
            )

        if self._llm.available:
            enhanced = await self._llm.complete_json(
                system="You analyze a company's public infrastructure to summarize its "
                       "business model and stack. Return strict JSON.",
                user=(
                    f"company={company.model_dump()}\n"
                    f"tech_hints={infra.tech_hints}\n"
                    f"subdomain_env_hints={[s.environment_hint for s in infra.subdomains if s.environment_hint]}\n"
                    f"mail_auth_dmarc_policy={infra.mail_auth.dmarc.policy}\n"
                    f"osint_exposure={exposure}\n"
                    "Infer: business_model (one sentence), primary_industry, likely_stack, "
                    "and 2 professional outreach angles based on infrastructure."
                ),
            )
            if enhanced:
                return {
                    "business_model": enhanced.get("business_model", business_model),
                    "industry": enhanced.get("primary_industry", industry),
                    "likely_stack": enhanced.get("likely_stack", ctx.dossier.personalization_tokens.likely_stack),
                    "security_posture": ctx.dossier.personalization_tokens.security_posture,
                    "posture_notes": posture_notes,
                    "outreach_angles": enhanced.get("outreach_angles", []),
                    "company_confidence": company.confidence,
                    "osint_exposure": exposure,
                }

        return {
            "business_model": business_model,
            "industry": industry,
            "likely_stack": ctx.dossier.personalization_tokens.likely_stack,
            "security_posture": ctx.dossier.personalization_tokens.security_posture,
            "posture_notes": posture_notes,
            "outreach_angles": [
                f"They run {', '.join(infra.tech_hints[:2]) or 'a custom stack'} — tailor value props accordingly",
                "Public staging/dev hosts suggest an active platform team",
            ][:2] if infra.subdomains else [],
            "company_confidence": company.confidence,
            "osint_exposure": exposure,
        }

    @staticmethod
    def _exposure_summary(openosint: dict) -> dict | None:
        """Grade/score out of the openosint exposure row, if it succeeded."""
        for row in openosint.get("lookups") or []:
            if row.get("lookup") == "exposure" and row.get("ok"):
                for line in row.get("lines") or []:
                    m = _EXPOSURE_RE.match(str(line).strip())
                    if m:
                        return {
                            "grade": m.group(1),
                            "score": int(m.group(2)) if m.group(2) else None,
                        }
        return None

    @staticmethod
    def _infer_business_model(company: CompanyIntelligence, infra) -> str:
        if company.name and company.industry:
            return f"{company.name} operates in {company.industry}"
        if any("api" == (s.environment_hint or "") for s in infra.subdomains):
            return "Product company with a public API platform (developer-facing)"
        if any(s.environment_hint == "app" for s in infra.subdomains):
            return "Product company with a hosted web application"
        if infra.mail_auth.spf.includes:
            return "Established business (managed mail via third-party ESP)"
        return "Unknown — insufficient public signals"

    @staticmethod
    def _infer_industry(infra) -> str | None:
        blob = " ".join(infra.tech_hints).lower()
        for needle, industry in (
            ("zendesk", "customer-support SaaS"), ("mailchimp", "marketing/e-commerce"),
            ("salesforce", "enterprise software"), ("kubernetes", "cloud infrastructure"),
        ):
            if needle in blob:
                return industry
        return None

    @staticmethod
    def _posture_notes(infra) -> list[str]:
        notes = []
        if not infra.mail_auth.dmarc.present:
            notes.append("No DMARC policy — email spoofing protection not deployed")
        elif infra.mail_auth.dmarc.policy == "none":
            notes.append("DMARC in monitor-only mode (p=none)")
        if infra.mail_auth.spf.all_qualifier == "-":
            notes.append("Strict SPF (-all) — disciplined sender policy")
        exposed = [s.host for s in infra.subdomains
                   if s.environment_hint in ("staging", "development", "admin")]
        if exposed:
            notes.append(f"Publicly resolvable non-prod hosts: {', '.join(exposed[:3])}")
        return notes
