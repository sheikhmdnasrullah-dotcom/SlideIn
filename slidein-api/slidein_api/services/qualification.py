"""Qualification — an explainable, rule-based score against the active ICP.

There is no model in the loop and no generated prose: every criterion is
declared in `RUBRIC`, contributes a fixed weight, and is reported as
either matching (with the evidence that proves it) or missing. The
explanation the UI shows is assembled from those same rows.
"""

from __future__ import annotations

import re
from .config import ConfigService
from ..errors import PrerequisiteError, SlideinError
from ..ids import new_id
from ..models import Offer, Prospect, QualificationResult
from ..serialize import offer, qualification

#: criterion key -> maximum points
RUBRIC: dict[str, int] = {
    "industry_match": 20,
    "company_size_fit": 15,
    "role_match": 20,
    "geography_match": 10,
    "required_signals": 15,
    "evidence_quality": 10,
    "no_exclusions": 10,
}
MAX_SCORE = sum(RUBRIC.values())


def _norm(value: str) -> str:
    return str(value or "").strip().lower()


def _contains_any(haystack: str, needles: list[str]) -> list[str]:
    found: list[str] = []
    for needle in needles or []:
        token = _norm(needle)
        if token and token in haystack:
            found.append(str(needle))
    return found


class QualificationService:
    def __init__(self, session) -> None:
        self.session = session

    def evaluate(
        self,
        *,
        prospect: Prospect,
        icp: dict,
        evidence_rows: list[dict],
        offers: list[dict],
    ) -> dict:
        """Pure scoring. Persisted by `QualificationService.record`."""
        haystack_role = _norm(prospect.job_title)
        haystack_geo = _norm(prospect.location)
        evidence_text = " ".join(_norm(e.get("claim_text")) for e in evidence_rows)
        verified = [e for e in evidence_rows if e.get("verification_status") == "verified"]

        matching: list[dict] = []
        missing: list[dict] = []
        score = 0

        # 1. Industry -----------------------------------------------------
        industries = icp.get("industries") or []
        if not industries:
            matching.append(self._row("industry_match", 0, "No industries configured on the ICP"))
        else:
            haystack_industry = _norm(f"{prospect.company_name} {prospect.company_domain} {evidence_text}")
            hits = _contains_any(haystack_industry, industries)
            if hits:
                score += RUBRIC["industry_match"]
                matching.append(
                    self._row("industry_match", RUBRIC["industry_match"],
                              f"Matches ICP industries: {', '.join(hits)}",
                              evidence_ids=self._evidence_for(evidence_rows, hits))
                )
            else:
                missing.append(
                    self._row("industry_match", RUBRIC["industry_match"],
                              f"No evidence of ICP industries: {', '.join(industries)}")
                )

        # 2. Company size -------------------------------------------------
        low, high = int(icp.get("company_size_min", 1)), int(icp.get("company_size_max", 5000))
        size = prospect.company_size
        if isinstance(size, int) and size:
            if low <= size <= high:
                score += RUBRIC["company_size_fit"]
                matching.append(
                    self._row("company_size_fit", RUBRIC["company_size_fit"],
                              f"Company size {size} is inside the ICP range {low}-{high}")
                )
            else:
                missing.append(
                    self._row("company_size_fit", RUBRIC["company_size_fit"],
                              f"Company size {size} is outside the ICP range {low}-{high}")
                )
        else:
            missing.append(
                self._row("company_size_fit", RUBRIC["company_size_fit"],
                          "Company size is unknown")
            )

        # 3. Role ---------------------------------------------------------
        roles = icp.get("target_roles") or []
        if not roles:
            matching.append(self._row("role_match", 0, "No target roles configured on the ICP"))
        elif haystack_role:
            hits = _contains_any(haystack_role, roles)
            if hits:
                score += RUBRIC["role_match"]
                matching.append(
                    self._row("role_match", RUBRIC["role_match"],
                              f"Job title matches target roles: {', '.join(hits)}")
                )
            else:
                missing.append(
                    self._row("role_match", RUBRIC["role_match"],
                              f"Job title {prospect.job_title!r} does not match target roles")
                )
        else:
            missing.append(
                self._row("role_match", RUBRIC["role_match"], "Job title is unknown")
            )

        # 4. Geography ----------------------------------------------------
        geos = icp.get("geographies") or []
        if not geos or not haystack_geo:
            matching.append(
                self._row("geography_match", 0,
                          "Geography not constrained by the ICP" if not geos
                          else "Prospect location unknown")
            )
        else:
            hits = _contains_any(haystack_geo, geos)
            if hits:
                score += RUBRIC["geography_match"]
                matching.append(
                    self._row("geography_match", RUBRIC["geography_match"],
                              f"Location matches: {', '.join(hits)}")
                )
            else:
                missing.append(
                    self._row("geography_match", RUBRIC["geography_match"],
                              f"Location {prospect.location!r} is outside the ICP geographies")
                )

        # 5. Required signals ---------------------------------------------
        signals = icp.get("required_signals") or []
        if not signals:
            matching.append(self._row("required_signals", 0, "No required signals configured"))
        else:
            hits = _contains_any(evidence_text, signals)
            if len(hits) >= max(1, len(signals) // 2):
                score += RUBRIC["required_signals"]
                matching.append(
                    self._row("required_signals", RUBRIC["required_signals"],
                              f"Evidence covers {len(hits)}/{len(signals)} required signals: "
                              f"{', '.join(hits)}",
                              evidence_ids=self._evidence_for(evidence_rows, hits))
                )
            else:
                missing.append(
                    self._row("required_signals", RUBRIC["required_signals"],
                              f"Evidence covers only {len(hits)}/{len(signals)} required signals",
                              evidence_ids=self._evidence_for(evidence_rows, hits))
                )

        # 6. Evidence quality ---------------------------------------------
        if verified:
            score += RUBRIC["evidence_quality"]
            matching.append(
                self._row("evidence_quality", RUBRIC["evidence_quality"],
                          f"{len(verified)} verified evidence item(s) with source URLs")
            )
        else:
            missing.append(
                self._row("evidence_quality", RUBRIC["evidence_quality"],
                          "No verified evidence — only inferred or unverified claims")
            )

        # 7. Exclusions ---------------------------------------------------
        exclusions = icp.get("exclusion_keywords") or []
        exclusion_haystack = _norm(
            f"{prospect.company_name} {prospect.job_title} {prospect.location} {evidence_text}"
        )
        exclusion_hits = _contains_any(exclusion_haystack, exclusions)
        if exclusion_hits:
            missing.append(
                self._row("no_exclusions", RUBRIC["no_exclusions"],
                          f"Exclusion keyword matched: {', '.join(exclusion_hits)}")
            )
        else:
            score += RUBRIC["no_exclusions"]
            matching.append(
                self._row("no_exclusions", RUBRIC["no_exclusions"],
                          "No ICP exclusion keyword matched")
            )

        threshold = int(icp.get("qualify_threshold", 70))
        is_qualified = (
            score >= threshold
            and bool(verified)
            and not exclusion_hits
        )

        explanation = self._explain(score, threshold, matching, missing, verified, exclusion_hits)

        return {
            "score": int(min(score, MAX_SCORE)),
            "max_score": MAX_SCORE,
            "is_qualified": bool(is_qualified),
            "threshold": threshold,
            "matching_criteria": matching,
            "missing_criteria": missing,
            "explanation": explanation,
        }

    @staticmethod
    def _row(criterion: str, points: int, detail: str, evidence_ids: list[str] | None = None) -> dict:
        return {
            "criterion": criterion,
            "points": int(points),
            "max_points": RUBRIC[criterion],
            "detail": detail,
            "evidence_ids": evidence_ids or [],
        }

    @staticmethod
    def _evidence_for(evidence_rows: list[dict], needles: list[str]) -> list[str]:
        """Evidence rows that share at least one significant token with the
        offer material they are supposed to justify."""
        tokens = {
            word
            for needle in needles or []
            for word in _norm(needle).replace(",", " ").split()
            if len(word) > 4
        }
        out: list[str] = []
        for row in evidence_rows:
            text = _norm(row.get("claim_text"))
            if any(token in text for token in tokens):
                out.append(row.get("id"))
        return [i for i in out if i]

    def _explain(
        self,
        score: int,
        threshold: int,
        matching: list[dict],
        missing: list[dict],
        verified: list[dict],
        exclusion_hits: list[str],
    ) -> str:
        parts = [
            f"Scored {score}/{MAX_SCORE} against ICP threshold {threshold}.",
        ]
        if matching:
            parts.append(
                "Matched: "
                + "; ".join(f"{m['criterion']} (+{m['points']})" for m in matching if m["points"])
                + "."
            )
        if missing:
            parts.append("Missing: " + "; ".join(m["criterion"] for m in missing) + ".")
        if exclusion_hits:
            parts.append("Exclusion keywords hit: " + ", ".join(exclusion_hits) + ".")
        if not verified:
            parts.append("No verified evidence is available, so this prospect cannot qualify.")
        parts.append(
            "Qualified." if score >= threshold and verified and not exclusion_hits
            else "Not qualified."
        )
        return " ".join(parts)

    # -- persisted entry points ------------------------------------------

    async def record(
        self,
        *,
        tenant_id: str,
        prospect: Prospect,
        icp: dict,
        evidence_rows: list[dict],
        actor: str = "operator",
    ) -> dict:
        from .config import ConfigService

        config = ConfigService(self.session)
        active_profile = await config.active_profile(tenant_id)
        offers = await config.list_offers(tenant_id)
        offer_rows = [await self.session.get(Offer, o["id"]) for o in offers]
        offer_rows = [o for o in offer_rows if o is not None]

        evaluation = self.evaluate(
            prospect=prospect, icp=icp, evidence_rows=evidence_rows, offers=offers
        )

        row = QualificationResult(
            id=new_id("qualification"),
            tenant_id=tenant_id,
            prospect_id=prospect.id,
            icp_id=icp["id"],
            icp_version=icp.get("version"),
            profile_version=active_profile.get("version") if active_profile else None,
            score=evaluation["score"],
            is_qualified=evaluation["is_qualified"],
            matching_criteria=evaluation["matching_criteria"],
            missing_criteria=evaluation["missing_criteria"],
            explanation=evaluation["explanation"],
            evaluated_by=actor,
        )
        self.session.add(row)
        await self.session.flush()

        result = qualification(row)
        result["threshold"] = evaluation["threshold"]
        result["max_score"] = evaluation["max_score"]

        # The offer match is part of the qualification handoff: which offer
        # fits, and which evidence justifies it.
        result["offer_match"] = await self.match_offer(
            tenant_id=tenant_id,
            prospect=prospect,
            evaluation=evaluation,
            evidence_rows=evidence_rows,
            offer_rows=offer_rows,
            actor=actor,
        )
        return result

    async def match_offer(
        self,
        *,
        tenant_id: str,
        prospect: Prospect,
        evaluation: dict,
        evidence_rows: list[dict],
        offer_rows: list[Offer],
        actor: str = "operator",
    ) -> dict | None:
        if not evaluation["is_qualified"] or not offer_rows:
            return None

        best: Offer | None = None
        best_score = 0
        rationale = ""
        for offer_row in offer_rows:
            score = self._offer_fit(prospect, offer_row, evidence_rows)
            if score > best_score:
                best, best_score = offer_row, score

        if best is None or best_score <= 0:
            return None

        evidence_ids = self._evidence_for(
            evidence_rows,
            list(best.pain_points_solved or [])
            + list(best.proof_points or [])
            + [best.target_persona or "", best.name or ""],
        )
        rationale = (
            f"Offer {best.name!r} targets {best.target_persona or 'the buyer'}; "
            f"{len(evidence_ids)} evidence item(s) corroborate the offer's "
            f"pain points and proof points."
        )

        from ..models import OfferMatch

        row = OfferMatch(
            id=new_id("offer_match"),
            tenant_id=tenant_id,
            prospect_id=prospect.id,
            offer_id=best.id,
            offer_version=best.version,
            rationale=rationale,
            evidence_ids=evidence_ids,
            score=int(min(100, best_score * 10)),
            is_selected=True,
            matched_by=actor,
        )
        self.session.add(row)
        await self.session.flush()

        from ..serialize import offer_match

        return {**offer_match(row), "offer": offer(best)}

    @staticmethod
    def _offer_fit(prospect: Prospect, offer_row: Offer, evidence_rows: list[dict]) -> int:
        """Explainable offer fit: persona match, corroborated pain points,
        and proof points that the evidence actually supports."""
        text = " ".join(
            _norm(x)
            for x in (
                prospect.job_title,
                prospect.company_name,
                " ".join(str(e.get("claim_text")) for e in evidence_rows),
            )
        )
        score = 0

        # Persona: any listed role the prospect's title satisfies.
        persona_tokens = [
            t for t in re.split(r"[,/]| and ", _norm(offer_row.target_persona)) if t.strip()
        ]
        if persona_tokens and any(
            token.strip() in text or token.strip().split()[-1] in text
            for token in persona_tokens
        ):
            score += 3

        for pain in offer_row.pain_points_solved or []:
            words = [w for w in _norm(pain).split() if len(w) > 4]
            hits = sum(1 for w in words if w in text)
            if words and hits >= max(1, len(words) // 2):
                score += 1
        for proof in offer_row.proof_points or []:
            if _norm(proof) in text:
                score += 1
        return score

    async def list_results(
        self, tenant_id: str, *, qualified_only: bool = False, limit: int = 50, offset: int = 0
    ) -> tuple[list[dict], int]:
        from sqlalchemy import func, select

        query = QualificationResult.__table__.select().where(
            QualificationResult.tenant_id == tenant_id
        )
        if qualified_only:
            query = query.where(QualificationResult.is_qualified.is_(True))
        query = query.order_by(QualificationResult.evaluated_at.desc()).limit(limit).offset(offset)
        rows = (await self.session.execute(query)).mappings().all()
        total = (
            await self.session.execute(
                select(func.count()).select_from(QualificationResult).where(
                    QualificationResult.tenant_id == tenant_id
                )
            )
        ).scalar_one()
        return [dict(r) for r in rows], total

    async def latest_for_prospect(self, tenant_id: str, prospect_id: str) -> dict | None:
        from sqlalchemy import func, select

        row = (
            await self.session.execute(
                select(QualificationResult)
                .where(
                    QualificationResult.tenant_id == tenant_id,
                    QualificationResult.prospect_id == prospect_id,
                )
                .order_by(QualificationResult.evaluated_at.desc())
            )
        ).scalars().first()
        if row is None:
            return None
        return qualification(row)


async def prerequisites_ok(session, tenant_id: str, prospect: Prospect) -> list[dict]:
    """Shared guard used by both the API and the stage runner."""
    from .research import ResearchService

    evidence_rows = await ResearchService(session).list_evidence(tenant_id, prospect.id)
    if not evidence_rows:
        raise PrerequisiteError(
            "Research has not produced any evidence for this prospect",
            code="stage_prerequisite",
            details={"stage": "research"},
            recovery_action="run_prerequisite_stage",
        )
    return evidence_rows


__all__ = ["MAX_SCORE", "RUBRIC", "QualificationService"]
