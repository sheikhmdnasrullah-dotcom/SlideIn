"""Suppression — checked before every send and applied on every opt-out."""

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..ids import new_id
from ..models import SuppressionRecord
from ..serialize import suppression

#: The default global suppressions loaded for a new workspace. These are
#: deliverability hygiene addresses, never customer data.
DEFAULT_GLOBAL_SUPPRESSIONS = (
    "abuse@",
    "postmaster@",
    "noreply@",
    "no-reply@",
    "donotreply@",
)


class SuppressionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def is_configured(self, tenant_id: str) -> bool:
        rows = (
            await self.session.execute(
                select(SuppressionRecord.id).where(
                    or_(
                        SuppressionRecord.tenant_id == tenant_id,
                        SuppressionRecord.tenant_id.is_(None),
                    )
                )
            )
        ).scalars().all()
        return len(rows) > 0

    async def seed_defaults(self, tenant_id: str) -> int:
        existing = set(
            (
                await self.session.execute(
                    select(SuppressionRecord.email).where(
                        or_(
                            SuppressionRecord.tenant_id == tenant_id,
                            SuppressionRecord.tenant_id.is_(None),
                        )
                    )
                )
            ).scalars().all()
        )
        added = 0
        for prefix in DEFAULT_GLOBAL_SUPPRESSIONS:
            row = SuppressionRecord(
                id=new_id("suppression"),
                tenant_id=None,
                email=f"{prefix}global",
                domain="",
                reason="manual_admin",
                note="Global role-address suppression (deliverability hygiene)",
                suppressed_by="system",
            )
            if row.email in existing:
                continue
            self.session.add(row)
            added += 1
        await self.session.flush()
        return added

    async def is_suppressed(self, tenant_id: str, email: str) -> dict | None:
        email = str(email or "").strip().lower()
        if not email:
            return None
        domain = email.split("@")[-1]
        rows = (
            await self.session.execute(
                select(SuppressionRecord).where(
                    or_(
                        SuppressionRecord.tenant_id == tenant_id,
                        SuppressionRecord.tenant_id.is_(None),
                    )
                )
            )
        ).scalars().all()
        for row in rows:
            target = row.email.lower()
            if target == email:
                return suppression(row)
            if target.endswith("@global") and email.startswith(target.split("@")[0]):
                return suppression(row)
            if target.startswith("@") and email.endswith(target):
                return suppression(row)
            if row.domain and row.domain.lower() == domain and row.reason == "hard_bounce":
                return suppression(row)
        return None

    async def list(
        self, tenant_id: str, *, limit: int = 100, offset: int = 0
    ) -> tuple[list[dict], int]:
        query = select(SuppressionRecord).where(
            or_(
                SuppressionRecord.tenant_id == tenant_id,
                SuppressionRecord.tenant_id.is_(None),
            )
        )
        total = len(
            (
                await self.session.execute(
                    query.with_only_columns(SuppressionRecord.id)
                )
            ).scalars().all()
        )
        rows = (
            await self.session.execute(
                query.order_by(SuppressionRecord.suppressed_at.desc()).limit(limit).offset(offset)
            )
        ).scalars().all()
        return [suppression(r) for r in rows], total

    async def add(
        self,
        *,
        tenant_id: str | None,
        email: str,
        reason: str,
        note: str = "",
        actor: str = "operator",
    ) -> dict:
        email = str(email or "").strip().lower()
        existing = await self.find_exact(tenant_id, email)
        if existing is not None:
            return existing
        row = SuppressionRecord(
            id=new_id("suppression"),
            tenant_id=tenant_id,
            email=email,
            domain=email.split("@")[-1] if "@" in email else "",
            reason=reason,
            note=note,
            suppressed_by=actor,
        )
        self.session.add(row)
        await self.session.flush()
        return suppression(row)

    async def find_exact(self, tenant_id: str | None, email: str) -> dict | None:
        email = str(email or "").strip().lower()
        row = (
            await self.session.execute(
                select(SuppressionRecord).where(
                    SuppressionRecord.email == email,
                    or_(
                        SuppressionRecord.tenant_id == tenant_id,
                        SuppressionRecord.tenant_id.is_(None),
                    ),
                )
            )
        ).scalars().first()
        return suppression(row) if row else None

    async def remove(self, tenant_id: str, suppression_id: str) -> bool:
        row = await self.session.get(SuppressionRecord, suppression_id)
        if row is None or (row.tenant_id is not None and row.tenant_id != tenant_id):
            return False
        await self.session.delete(row)
        await self.session.flush()
        return True
