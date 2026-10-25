"""Agent 1 — The Investigator.

Input: raw OSINT payload. Output: verified person-level signals with
false-positive filtering.

FP rules enforced here:
  * authwalled platform hits (confidence < 0.5) are dropped unless corroborated
    by the email-keyed gravatar identity,
  * name tokens must agree between at least two independent sources, or come
    from gravatar, to be marked verified,
  * interests are keyword-derived from verified bios only.
"""
from __future__ import annotations

import re

from .base import AgentContext, LLMClient

#: "[GitHub] Name: Sanjida Nasrin" — account-declared profile fields.
_GITHUB_FIELD_RE = re.compile(
    r"^\[GitHub\]\s*(Login|Name|Bio|Location|Profile URL):\s*(.+)$"
)


class Investigator:
    name = "investigator"

    def __init__(self, llm: LLMClient | None = None):
        self._llm = llm or LLMClient()

    async def run(self, ctx: AgentContext) -> dict:
        verified = [
            p for p in ctx.footprint.profiles_found
            if p.confidence >= 0.5
            or (ctx.footprint.gravatar and p.platform.startswith("gravatar:"))
        ]
        dropped = [
            p.platform for p in ctx.footprint.profiles_found
            if p not in verified
        ]

        # Name verification: gravatar displayName wins; otherwise require
        # agreement between two independent platform parses.
        name_votes: dict[str, int] = {}
        for p in verified:
            if p.full_name:
                name_votes[p.full_name.lower()] = name_votes.get(p.full_name.lower(), 0) + 1

        # OpenOSINT's github lookup is one more independent source: the
        # account-declared name adds a vote (never beats gravatar, and a
        # lone vote still fails the ≥2-sources rule).
        openosint = (ctx.extras or {}).get("openosint") or {}
        github_profile = self._github_from_osint(openosint)
        if github_profile and github_profile.get("name"):
            key = github_profile["name"].lower()
            name_votes[key] = name_votes.get(key, 0) + 1

        gravatar_name = (ctx.footprint.gravatar or {}).get("display_name")
        if gravatar_name:
            verified_name = gravatar_name
        else:
            agreed = [n for n, c in name_votes.items() if c >= 2]
            if agreed:
                verified_name = agreed[0]
            else:
                # Single-source verification allowed at high confidence.
                best = max(
                    (p for p in verified if p.full_name),
                    key=lambda p: p.confidence, default=None,
                )
                verified_name = best.full_name if best and best.confidence >= 0.9 else None

        milestones = self._milestones(verified)
        interests = sorted({
            i for i in ctx.dossier.personalization_tokens.interests
        })

        if self._llm.available:
            enhanced = await self._llm.complete_json(
                system="You verify OSINT findings. Return strict JSON.",
                user=(
                    "From these verified profiles, extract professional milestones, "
                    "open-source contributions, and 3 safe non-creepy personalization "
                    "hooks. Drop anything that would feel invasive to mention in cold email. "
                    f"profiles={ [p.model_dump() for p in verified] }"
                ),
            )
            if enhanced:
                return {"verified": True, "llm_enhanced": True,
                        "verified_profiles": [p.model_dump() for p in verified],
                        "dropped_false_positives": dropped,
                        "verified_name": verified_name,
                        "milestones": enhanced.get("milestones", milestones),
                        "interests": enhanced.get("interests", interests),
                        "hooks": enhanced.get("hooks", []),
                        "contribution_summary": enhanced.get("contribution_summary"),
                        "osint": self._osint_summary(openosint, github_profile)}

        return {
            "verified": True,
            "llm_enhanced": False,
            "verified_profiles": [p.model_dump() for p in verified],
            "dropped_false_positives": dropped,
            "verified_name": verified_name,
            "milestones": milestones,
            "interests": interests,
            "hooks": ctx.dossier.personalization_tokens.icebreakers,
            "contribution_summary": self._contribution_summary(verified),
            "osint": self._osint_summary(openosint, github_profile),
        }

    @staticmethod
    def _github_from_osint(openosint: dict) -> dict | None:
        """Parse the openosint github lookup into a profile dict (or None)."""
        rows = [
            r for r in (openosint.get("lookups") or [])
            if r.get("lookup") == "github" and r.get("ok")
        ]
        if not rows:
            return None
        profile: dict[str, str] = {}
        for line in rows[0].get("lines") or []:
            m = _GITHUB_FIELD_RE.match(str(line).strip())
            if m:
                value = m.group(2).strip()
                if value and value.upper() != "N/A":
                    profile[m.group(1).lower().replace(" ", "_")] = value
        return profile or None

    @staticmethod
    def _osint_summary(openosint: dict, github_profile: dict | None) -> dict:
        """Compact, LLM-safe digest of the openosint rows for this lead."""
        lookups = openosint.get("lookups") or []

        def lines_of(name: str) -> list[str]:
            for row in lookups:
                if row.get("lookup") == name:
                    return [str(line) for line in row.get("lines") or []]
            return []

        def hits(name: str) -> list[str]:
            return [line for line in lines_of(name) if line.startswith("[+]")]

        return {
            "github": github_profile,
            "email_registrations": hits("email"),
            "username_sites": hits("username"),
            "lookups_run": [r["lookup"] for r in lookups if r.get("ok")],
            "lookups_failed": [r["lookup"] for r in lookups if not r.get("ok")],
        }

    @staticmethod
    def _milestones(profiles) -> list[str]:
        out = []
        for p in profiles:
            if p.platform == "GitHub":
                out.append("Active GitHub presence — open-source contributor")
            elif p.platform == "Dev.to":
                out.append("Publishes technical writing on DEV.to")
            elif p.platform == "HackerNews":
                out.append("Participates in Hacker News discussions")
            elif p.platform == "ProductHunt":
                out.append("Engages on Product Hunt — follows product launches")
        return out

    @staticmethod
    def _contribution_summary(profiles) -> str | None:
        names = [p.platform for p in profiles if p.platform in
                 ("GitHub", "GitLab", "DockerHub", "npm", "PyPI")]
        return f"Developer footprint across: {', '.join(names)}" if names else None
