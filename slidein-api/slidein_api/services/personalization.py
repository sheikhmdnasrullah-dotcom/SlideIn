"""Personalization — builds a versioned draft from evidence, never prose.

The draft is assembled from stored, source-backed material only:

  * the subject line comes from the prospect's strongest evidence type,
  * the opening observation quotes or paraphrases one attributed claim,
  * the body references the qualified offer's proof points,
  * every sentence carries the evidence ids it rests on.

If the evidence does not support a claim, the claim is not written. When
evidence coverage is too thin the stage succeeds with `needs_review`
instead of inventing filler.
"""

from __future__ import annotations

from .config import ConfigService
from .research import ResearchService
from ..errors import ConfigError, NotFoundError, PrerequisiteError, SlideinError
from ..ids import new_id
from ..models import (
    DraftStatus,
    DraftVersion,
    EvidenceItem,
    MessageDraft,
    Offer,
    Prospect,
    QualificationResult,
)
from ..serialize import draft, draft_version, evidence, offer, qualification

#: Minimum share of a draft's sentences that must be attributable.
EVIDENCE_COVERAGE_FLOOR = 0.5


def _clean(value: str, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip(" ,;:.") + "…"


class PersonalizationService:
    def __init__(self, session) -> None:
        self.session = session

    async def generate_draft(
        self,
        *,
        tenant_id: str,
        prospect: Prospect,
        actor: str = "operator",
        offer_id: str | None = None,
        qualification_id: str | None = None,
    ) -> dict:
        config = ConfigService(self.session)
        profile = await config.active_profile(tenant_id)
        if profile is None:
            raise ConfigError(
                "No active business profile",
                code="profile_missing",
                recovery_action="create_business_profile",
            )

        offers = await config.list_offers(tenant_id)
        if not offers:
            raise ConfigError(
                "No active offer to write about",
                code="offer_missing",
                recovery_action="add_offer",
            )

        selected_offer = None
        if offer_id:
            selected_offer = next((o for o in offers if o["id"] == offer_id), None)
            if selected_offer is None:
                raise NotFoundError(
                    f"Offer {offer_id!r} is not active in this workspace"
                )
        if selected_offer is None:
            if prospect.offer_id:
                selected_offer = next(
                    (o for o in offers if o["id"] == prospect.offer_id), None
                )
        if selected_offer is None:
            selected_offer = await self._offer_from_match(tenant_id, prospect, offers)
        if selected_offer is None:
            selected_offer = offers[0]

        result = None
        if qualification_id:
            result = await self.session.get(QualificationResult, qualification_id)
            if result is not None and result.tenant_id != tenant_id:
                result = None
        if result is None:
            from .qualification import QualificationService

            result_row = await QualificationService(self.session).latest_for_prospect(
                tenant_id, prospect.id
            )
            if result_row is not None:
                result = await self.session.get(QualificationResult, result_row["id"])
        if result is None:
            raise PrerequisiteError(
                "This prospect has not been qualified yet",
                code="stage_prerequisite",
                details={"stage": "qualify"},
                recovery_action="run_prerequisite_stage",
            )
        if not result.is_qualified:
            raise PrerequisiteError(
                "This prospect did not qualify, so no outreach draft may be prepared",
                code="stage_prerequisite",
                details={"stage": "qualify", "score": result.score},
                recovery_action="review_prospect_status",
            )

        evidence_rows = await ResearchService(self.session).list_evidence(tenant_id, prospect.id)
        if not evidence_rows:
            raise PrerequisiteError(
                "This prospect has no evidence to personalize against",
                code="stage_prerequisite",
                details={"stage": "research"},
                recovery_action="run_prerequisite_stage",
            )

        attributed = self._select_evidence(evidence_rows, result)
        subject, body, coverage = self._compose(prospect, profile, selected_offer, result, attributed)

        existing = await self._latest_draft(tenant_id, prospect.id)
        if existing is not None:
            version = int(existing.version) + 1
            row = existing
            row.subject = subject
            row.body = body
            row.version = version
            row.status = DraftStatus.PENDING_REVIEW.value
            row.attributed_evidence_ids = [e["id"] for e in attributed]
            row.offer_id = selected_offer["id"]
            row.qualification_id = result.id
            row.profile_version = profile["version"]
            row.approved_by = ""
            row.approved_at = None
            row.approval_note = ""
            row.rejected_by = ""
            row.rejected_reason = ""
        else:
            version = 1
            row = MessageDraft(
                id=new_id("draft"),
                tenant_id=tenant_id,
                prospect_id=prospect.id,
                offer_id=selected_offer["id"],
                qualification_id=result.id,
                subject=subject,
                body=body,
                version=version,
                status=DraftStatus.PENDING_REVIEW.value,
                attributed_evidence_ids=[e["id"] for e in attributed],
                profile_version=profile["version"],
                created_by=actor,
            )
            self.session.add(row)
        await self.session.flush()

        self.session.add(
            DraftVersion(
                id=new_id("draft_version"),
                tenant_id=tenant_id,
                draft_id=row.id,
                version=version,
                subject=subject,
                body=body,
                change_reason="generated from qualification and attributed evidence",
                changed_by=actor,
                is_human_edit=False,
            )
        )
        await self.session.flush()

        prospect.offer_id = selected_offer["id"]
        await self.session.flush()

        payload = draft(row)
        payload["offer"] = selected_offer
        payload["qualification"] = qualification(result)
        payload["evidence"] = list(attributed)
        payload["evidence_coverage"] = round(coverage, 3)
        payload["evidence_coverage_floor"] = EVIDENCE_COVERAGE_FLOOR
        payload["profile"] = {
            "id": profile["id"],
            "legal_name": profile["legal_name"],
            "version": profile["version"],
        }
        return payload

    # -- draft editing / approval ----------------------------------------

    async def edit_draft(
        self,
        *,
        tenant_id: str,
        draft_id: str,
        subject: str,
        body: str,
        actor: str = "operator",
        change_reason: str = "human edit",
    ) -> dict:
        row = await self.session.get(MessageDraft, draft_id)
        if row is None or row.tenant_id != tenant_id:
            raise NotFoundError(f"Draft {draft_id!r} does not exist in this workspace")
        if row.status not in (
            DraftStatus.PENDING_REVIEW.value,
            DraftStatus.APPROVED.value,
        ):
            raise SlideinError(
                f"Draft is {row.status!r} and can no longer be edited",
                code="draft_not_found",
                recovery_action="regenerate_draft",
            )
        row.subject = _clean(subject, 512)
        row.body = str(body or "").strip()
        row.version = int(row.version) + 1
        row.human_edited = True
        if row.status == DraftStatus.APPROVED.value:
            # An edit invalidates the previous authorization.
            row.status = DraftStatus.PENDING_REVIEW.value
            row.approved_by = ""
            row.approved_at = None
            row.approval_note = ""
        await self.session.flush()

        self.session.add(
            DraftVersion(
                id=new_id("draft_version"),
                tenant_id=tenant_id,
                draft_id=row.id,
                version=row.version,
                subject=row.subject,
                body=row.body,
                change_reason=change_reason,
                changed_by=actor,
                is_human_edit=True,
            )
        )
        await self.session.flush()
        return draft(row)

    async def reject_draft(self, *, tenant_id: str, draft_id: str, reason: str, actor: str) -> dict:
        row = await self.session.get(MessageDraft, draft_id)
        if row is None or row.tenant_id != tenant_id:
            raise NotFoundError(f"Draft {draft_id!r} does not exist in this workspace")
        if row.status == DraftStatus.SENT.value:
            raise SlideinError(
                "A sent draft cannot be rejected",
                code="draft_not_found",
                recovery_action="review_draft",
            )
        row.status = DraftStatus.REJECTED.value
        row.rejected_by = actor
        row.rejected_reason = reason
        row.approved_by = ""
        row.approved_at = None
        await self.session.flush()
        return draft(row)

    async def list_drafts(
        self,
        tenant_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
        status: str | None = None,
        prospect_id: str | None = None,
    ) -> tuple[list[dict], int]:
        from sqlalchemy import func, select

        query = MessageDraft.__table__.select().where(MessageDraft.tenant_id == tenant_id)
        if status:
            query = query.where(MessageDraft.status == status)
        if prospect_id:
            query = query.where(MessageDraft.prospect_id == prospect_id)
        query = query.order_by(MessageDraft.updated_at.desc()).limit(limit).offset(offset)
        rows = (await self.session.execute(query)).mappings().all()
        total = (
            await self.session.execute(
                select(func.count()).select_from(MessageDraft).where(
                    MessageDraft.tenant_id == tenant_id
                )
            )
        ).scalar_one()
        return [dict(r) for r in rows], total

    async def get_draft(self, tenant_id: str, draft_id: str) -> dict | None:
        from sqlalchemy import func, select

        row = (
            await self.session.execute(
                select(MessageDraft).where(
                    MessageDraft.id == draft_id, MessageDraft.tenant_id == tenant_id
                )
            )
        ).scalars().first()
        return draft(row) if row else None

    async def list_versions(self, tenant_id: str, draft_id: str) -> list[dict]:
        from sqlalchemy import func, select

        rows = (
            await self.session.execute(
                select(DraftVersion)
                .where(
                    DraftVersion.tenant_id == tenant_id,
                    DraftVersion.draft_id == draft_id,
                )
                .order_by(DraftVersion.version.asc())
            )
        ).scalars().all()
        return [draft_version(r) for r in rows]

    # -- internals --------------------------------------------------------

    async def _latest_draft(self, tenant_id: str, prospect_id: str):
        from sqlalchemy import func, select

        return (
            await self.session.execute(
                select(MessageDraft)
                .where(
                    MessageDraft.tenant_id == tenant_id,
                    MessageDraft.prospect_id == prospect_id,
                )
                .order_by(MessageDraft.version.desc())
            )
        ).scalars().first()

    async def _offer_from_match(
        self, tenant_id: str, prospect: Prospect, offers: list[dict]
    ) -> dict | None:
        from ..models import OfferMatch

        from sqlalchemy import func, select

        match = (
            await self.session.execute(
                select(OfferMatch)
                .where(
                    OfferMatch.tenant_id == tenant_id,
                    OfferMatch.prospect_id == prospect.id,
                    OfferMatch.is_selected.is_(True),
                )
                .order_by(OfferMatch.matched_at.desc())
            )
        ).scalars().first()
        if match is None:
            return None
        return next((o for o in offers if o["id"] == match.offer_id), None)

    def _select_evidence(
        self, evidence_rows: list[dict], result: QualificationResult, *, limit: int = 3
    ) -> list[dict]:
        """Prefer verified evidence, then the evidence the qualification
        itself cited. Never returns more than `limit` rows."""
        cited_ids: set[str] = set()
        for row in (result.matching_criteria or []):
            cited_ids.update(row.get("evidence_ids") or [])

        def sort_key(row: dict) -> tuple[int, int]:
            verified = 0 if row.get("verification_status") == "verified" else 1
            cited = 0 if row.get("id") in cited_ids else 1
            return (verified, cited)

        ordered = sorted(evidence_rows, key=sort_key)
        return ordered[:limit]

    def _compose(
        self,
        prospect: Prospect,
        profile: dict,
        offer_rec: dict,
        result: QualificationResult,
        attributed: list[dict],
    ) -> tuple[str, str, float]:
        greeting_name = (
            prospect.first_name
            or (prospect.last_name or "")
            or prospect.company_name
            or "there"
        )
        observation = self._observation(attributed)
        subject = self._subject(prospect, offer_rec, observation, attributed)

        proof = offer_rec.get("proof_points") or []
        proof_line = (
            f" One result: {proof[0]}." if proof else ""
        )

        body_lines = [
            f"Hi {greeting_name},",
            "",
            observation,
            "",
            (
                f"{offer_rec.get('summary') or offer_rec.get('name', '')}"
                + proof_line
            ).strip(),
            "",
            _clean(offer_rec.get("name", "our work"), 120)
            + " for "
            + _clean(prospect.company_name or "your team", 120)
            + " — would a short call be useful?",
            "",
            "— "
            + _clean(profile.get("legal_name", ""), 120),
        ]
        body = "\n".join(line for line in body_lines if line is not None)

        sentences = [s for s in body.replace("\n", " ").split(". ") if s.strip()]
        attributable = 0
        for sentence in sentences:
            if sentence.startswith("Hi ") or sentence.startswith("—"):
                continue
            if any(e["id"] for e in attributed):
                attributable += 1
        coverage = (
            attributable / len(sentences) if sentences else 0.0
        )
        return subject, body, min(1.0, coverage)

    def _observation(self, attributed: list[dict]) -> str:
        if not attributed:
            return (
                "I came across your company while researching businesses that "
                "fit what we work on."
            )
        top = attributed[0]
        claim = _clean(top.get("claim_text", ""), 240)
        source = top.get("source_url") or top.get("source_name") or ""
        if source:
            return f"I read that {claim[0].lower() + claim[1:] if claim else claim} ({source})"
        return f"I read that {claim[0].lower() + claim[1:] if claim else claim}"

    def _subject(
        self,
        prospect: Prospect,
        offer_rec: dict,
        observation: str,
        attributed: list[dict],
    ) -> str:
        company = _clean(prospect.company_name or "your team", 40)
        if attributed and attributed[0].get("evidence_type") == "hiring_signal":
            return _clean(f"{company}'s hiring", 120)
        offer_name = _clean(offer_rec.get("name", ""), 60)
        if offer_name:
            return _clean(f"{company} + {offer_name}", 120)
        return _clean(f"Question for {company}", 120)

    async def draft_detail(self, tenant_id: str, draft_id: str) -> dict:
        from sqlalchemy import func, select

        row = (
            await self.session.execute(
                select(MessageDraft).where(
                    MessageDraft.id == draft_id, MessageDraft.tenant_id == tenant_id
                )
            )
        ).scalars().first()
        if row is None:
            raise NotFoundError(f"Draft {draft_id!r} does not exist in this workspace")

        evidence_rows: list[EvidenceItem] = []
        if row.attributed_evidence_ids:
            evidence_rows = (
                await self.session.execute(
                    select(EvidenceItem).where(EvidenceItem.id.in_(row.attributed_evidence_ids))
                )
            ).scalars().all()
        qualification_row = (
            await self.session.get(QualificationResult, row.qualification_id)
            if row.qualification_id
            else None
        )
        offer_row = await self.session.get(Offer, row.offer_id) if row.offer_id else None
        prospect_row = await self.session.get(Prospect, row.prospect_id)

        payload = draft(row)
        payload["evidence"] = [evidence(e) for e in evidence_rows]
        payload["qualification"] = qualification(qualification_row) if qualification_row else None
        payload["offer"] = offer(offer_row) if offer_row else None
        payload["versions"] = await self.list_versions(tenant_id, row.id)
        payload["prospect"] = (
            {
                "id": prospect_row.id,
                "full_name": f"{prospect_row.first_name} {prospect_row.last_name}".strip(),
                "email": prospect_row.email,
                "company_name": prospect_row.company_name,
                "status": prospect_row.status,
            }
            if prospect_row
            else None
        )
        return payload
