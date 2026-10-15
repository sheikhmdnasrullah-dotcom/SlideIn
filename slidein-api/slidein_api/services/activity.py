"""Activity log — the single history trail behind the Activity section.

Both human actions and stage runs append here, so the Activity view is
the workflow history of the same records every other section shows.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..ids import new_id
from ..models import ActivityLog
from ..serialize import activity


class ActivityService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def record(
        self,
        *,
        tenant_id: str,
        action: str,
        actor: str = "system",
        actor_role: str = "system",
        summary: str = "",
        reason: str = "",
        entity_type: str = "",
        entity_id: str = "",
        prospect_id: str | None = None,
        stage: str = "",
        run_id: str | None = None,
        details: dict | None = None,
    ) -> dict:
        row = ActivityLog(
            id=new_id("activity"),
            tenant_id=tenant_id,
            actor=actor or "system",
            actor_role=actor_role or "system",
            action=action,
            summary=summary,
            reason=reason,
            entity_type=entity_type,
            entity_id=entity_id,
            prospect_id=prospect_id,
            stage=stage,
            run_id=run_id,
            details=details or {},
        )
        self.session.add(row)
        await self.session.flush()
        return activity(row)

    async def list(
        self,
        tenant_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
        stage: str | None = None,
        action: str | None = None,
        prospect_id: str | None = None,
    ) -> tuple[list[dict], int]:
        query = select(ActivityLog).where(ActivityLog.tenant_id == tenant_id)
        if stage:
            query = query.where(ActivityLog.stage == stage)
        if action:
            query = query.where(ActivityLog.action == action)
        if prospect_id:
            query = query.where(ActivityLog.prospect_id == prospect_id)
        count_query = (
            select(ActivityLog.id).where(ActivityLog.tenant_id == tenant_id)
        )
        if stage:
            count_query = count_query.where(ActivityLog.stage == stage)
        if action:
            count_query = count_query.where(ActivityLog.action == action)
        if prospect_id:
            count_query = count_query.where(ActivityLog.prospect_id == prospect_id)
        total = len((await self.session.execute(count_query)).scalars().all())
        rows = (
            await self.session.execute(
                query.order_by(ActivityLog.created_at.desc()).limit(limit).offset(offset)
            )
        ).scalars().all()
        return [activity(r) for r in rows], total

    async def for_prospect(self, tenant_id: str, prospect_id: str) -> list[dict]:
        rows = (
            await self.session.execute(
                select(ActivityLog)
                .where(
                    ActivityLog.tenant_id == tenant_id,
                    ActivityLog.prospect_id == prospect_id,
                )
                .order_by(ActivityLog.created_at.asc())
            )
        ).scalars().all()
        return [activity(r) for r in rows]

    async def count_by_stage(self, tenant_id: str) -> dict[str, int]:
        rows = (
            await self.session.execute(
                select(ActivityLog.stage).where(ActivityLog.tenant_id == tenant_id)
            )
        ).scalars().all()
        counts: dict[str, int] = {}
        for stage in rows:
            if not stage:
                continue
            counts[stage] = counts.get(stage, 0) + 1
        return counts

    async def stage_health(self, tenant_id: str) -> dict[str, Any]:
        """Success/failure/needs-review counts per stage, from stage runs."""
        from ..models import RunStatus, StageRun

        rows = (
            await self.session.execute(
                select(StageRun.stage, StageRun.status).where(
                    StageRun.tenant_id == tenant_id
                )
            )
        ).all()
        health: dict[str, dict[str, int]] = {}
        for stage, status in rows:
            bucket = health.setdefault(stage, {"succeeded": 0, "failed": 0, "needs_review": 0})
            if status == RunStatus.SUCCEEDED.value:
                bucket["succeeded"] += 1
            elif status == RunStatus.NEEDS_REVIEW.value:
                bucket["needs_review"] += 1
            else:
                bucket["failed"] += 1
        return health
