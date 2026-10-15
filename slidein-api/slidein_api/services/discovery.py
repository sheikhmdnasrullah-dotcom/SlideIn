"""Discovery — the only place prospect records are created.

Each record is created with its source attribution and the exact
configuration version it was produced under, so Discovery's output can be
traced back to the ICP that asked for it.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..errors import ConfigError, SlideinError, ValidationError
from ..ids import new_id
from ..models import Prospect, utcnow
from ..serialize import prospect

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_email(value: str) -> str:
    return str(value or "").strip().lower()


def normalize_domain(value: str) -> str:
    domain = str(value or "").strip().lower()
    domain = re.sub(r"^https?://", "", domain)
    domain = domain.split("/")[0]
    return domain.lstrip(".").strip()


class DiscoveryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_prospect(self, tenant_id: str, prospect_id: str) -> Prospect | None:
        row = await self.session.get(Prospect, prospect_id)
        if row is None or row.tenant_id != tenant_id or row.deleted_at is not None:
            return None
        return row

    async def list_prospects(
        self,
        tenant_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
        status: str | None = None,
        search: str | None = None,
        min_score: int | None = None,
        source: str | None = None,
    ) -> tuple[list[dict], int]:
        query = select(Prospect).where(
            Prospect.tenant_id == tenant_id, Prospect.deleted_at.is_(None)
        )
        if status:
            query = query.where(Prospect.status == status)
        if source:
            query = query.where(Prospect.source == source)
        if min_score is not None:
            query = query.where(Prospect.qualification_score >= int(min_score))
        if search:
            term = f"%{search.strip()}%"
            query = query.where(
                Prospect.email.ilike(term)
                | Prospect.company_name.ilike(term)
                | Prospect.first_name.ilike(term)
                | Prospect.last_name.ilike(term)
                | Prospect.job_title.ilike(term)
            )
        total = len(
            (await self.session.execute(query.with_only_columns(Prospect.id))).scalars().all()
        )
        rows = (
            await self.session.execute(
                query.order_by(Prospect.discovered_at.desc()).limit(limit).offset(offset)
            )
        ).scalars().all()
        return [prospect(r) for r in rows], total

    async def create_records(
        self,
        tenant_id: str,
        *,
        icp_id: str,
        records: list[dict],
        source: str = "manual",
        source_ref: str = "",
        profile_id: str | None = None,
        profile_version: int | None = None,
        created_by: str = "operator",
    ) -> dict:
        """Idempotent batch ingest. Duplicates are reported, not merged.

        Returns the ids created plus the counts the contract promises.
        """
        from .config import ConfigService

        config = ConfigService(self.session)
        icp_rec = await config.get_icp(tenant_id, icp_id)
        if icp_rec is None:
            raise ConfigError(
                "No active ICP to discover against",
                code="icp_missing",
                recovery_action="define_icp",
            )
        profile = await config.active_profile(tenant_id)
        if profile is None:
            raise ConfigError(
                "No active business profile",
                code="profile_missing",
                recovery_action="create_business_profile",
            )

        existing_emails = {
            normalize_email(e)
            for e in (
                await self.session.execute(
                    select(Prospect.email).where(Prospect.tenant_id == tenant_id)
                )
            ).scalars().all()
        }

        created: list[str] = []
        duplicates: list[str] = []
        skipped: list[dict] = []
        seen_in_batch: set[str] = set()

        for index, raw in enumerate(records):
            email = normalize_email(raw.get("email"))
            if not _EMAIL_RE.match(email):
                skipped.append({"index": index, "reason": "invalid_email", "email": raw.get("email", "")})
                continue
            company = str(raw.get("company_name") or "").strip()
            if not company:
                skipped.append({"index": index, "reason": "missing_company", "email": email})
                continue
            if email in existing_emails or email in seen_in_batch:
                duplicates.append(email)
                continue
            seen_in_batch.add(email)

            domain = normalize_domain(raw.get("company_domain") or email.split("@")[-1])
            row = Prospect(
                id=new_id("prospect"),
                tenant_id=tenant_id,
                first_name=str(raw.get("first_name") or "").strip(),
                last_name=str(raw.get("last_name") or "").strip(),
                email=email,
                phone=str(raw.get("phone") or "").strip(),
                company_name=company,
                company_domain=domain,
                job_title=str(raw.get("job_title") or "").strip(),
                linkedin_url=str(raw.get("linkedin_url") or "").strip(),
                company_size=(
                    int(raw["company_size"])
                    if str(raw.get("company_size") or "").isdigit()
                    else None
                ),
                location=str(raw.get("location") or "").strip(),
                source=str(raw.get("source") or source),
                source_ref=str(raw.get("source_ref") or source_ref),
                source_detail=dict(raw.get("source_detail") or {}),
                status="discovered",
                profile_id=profile["id"],
                profile_version=profile_version or profile["version"],
                icp_id=icp_rec["id"],
                icp_version=icp_rec["version"],
                discovered_by=created_by,
                state_history=[
                    {
                        "state": "discovered",
                        "entered_at": utcnow().isoformat(),
                        "exited_at": None,
                        "reason": f"ingested from {str(raw.get('source') or source)}",
                        "actor": created_by,
                        "stage": "discover",
                        "run_id": "",
                    }
                ],
            )
            self.session.add(row)
            created.append(row.id)

        await self.session.flush()

        return {
            "prospect_ids": created,
            "created": len(created),
            "duplicates": len(duplicates),
            "duplicate_emails": duplicates,
            "skipped": len(skipped),
            "skipped_records": skipped,
            "profile_version": profile_version or profile["version"],
            "icp_id": icp_rec["id"],
            "icp_version": icp_rec["version"],
        }

    async def counts_by_status(self, tenant_id: str) -> dict[str, int]:
        rows = (
            await self.session.execute(
                select(Prospect.status).where(
                    Prospect.tenant_id == tenant_id, Prospect.deleted_at.is_(None)
                )
            )
        ).scalars().all()
        counts: dict[str, int] = {}
        for status in rows:
            counts[status] = counts.get(status, 0) + 1
        return counts

    async def source_breakdown(self, tenant_id: str) -> list[dict]:
        rows = (
            await self.session.execute(
                select(Prospect.source).where(
                    Prospect.tenant_id == tenant_id, Prospect.deleted_at.is_(None)
                )
            )
        ).scalars().all()
        counts: dict[str, int] = {}
        for src in rows:
            counts[src] = counts.get(src, 0) + 1
        return [{"source": k, "count": v} for k, v in sorted(counts.items(), key=lambda i: -i[1])]

    async def set_status(
        self, prospect: Prospect, *, to_status: str, reason: str = ""
    ) -> None:
        prospect.status = to_status
        prospect.status_reason = reason

    async def apply_transition(
        self,
        prospect: Prospect,
        *,
        to_status: str,
        reason: str = "",
        actor: str = "system",
        stage: str = "",
        run_id: str | None = None,
    ) -> bool:
        """Enforce the lifecycle and append the history entry.

        Returns False (and changes nothing) when the transition is a no-op.
        Anything outside the declared table raises `invalid_transition`,
        which the stage runner records as a failed run.
        """
        from ..contracts import StageName
        from ..errors import TransitionError
        from ..lifecycle import (
            PROSPECT_TRANSITIONS,
            ProspectHistory,
            can_transition,
        )

        current = prospect.status
        if current == to_status:
            return False

        if not can_transition(PROSPECT_TRANSITIONS, current, to_status):
            raise TransitionError(
                f"Cannot move prospect from {current!r} to {to_status!r}. "
                f"Allowed: {list(PROSPECT_TRANSITIONS.get(current, ()))}",
                details={
                    "from_status": current,
                    "to_status": to_status,
                    "prospect_id": prospect.id,
                },
                recovery_action="review_prospect_status",
            )

        history = ProspectHistory(entries=list(prospect.state_history or []))
        history.append(
            to_status,
            reason=reason,
            actor=actor,
            stage=stage or (StageName.DISCOVER.value if to_status == "discovered" else ""),
            run_id=run_id or "",
        )
        prospect.status = to_status
        prospect.status_reason = reason
        prospect.state_history = history.to_list()
        await self.session.flush()
        return True
async def icp_matches_soft(icp: dict, record: dict) -> list[str]:
    """Soft signals an ICP would like. Used to flag, never to reject."""
    flags: list[str] = []
    keywords = [k.lower() for k in icp.get("exclusion_keywords", []) if k]
    if keywords:
        haystack = " ".join(
            str(record.get(k, "")) for k in ("company_name", "job_title", "location")
        ).lower()
        for keyword in keywords:
            if keyword and keyword in haystack:
                flags.append(f"exclusion keyword matched: {keyword}")
    size = record.get("company_size")
    if isinstance(size, int) and size:
        if size < int(icp.get("company_size_min", 1)):
            flags.append("company size below ICP minimum")
        if size > int(icp.get("company_size_max", 5000)):
            flags.append("company size above ICP maximum")
    return flags


def coerce_records(payload: Any) -> list[dict]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    raise ValidationError("records must be a list of objects")
