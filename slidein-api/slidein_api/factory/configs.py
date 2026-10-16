"""Versioned deployment configuration with rollback.

Only registered blueprint versions can be pinned, so a deployment can
never point at an unknown or untested workflow.
"""

from __future__ import annotations

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..blueprints import get_blueprint, list_blueprints
from ..errors import ConfigError, NotFoundError, ValidationError
from ..ids import new_id
from .models import DeploymentConfig
from .schemas import DeploymentConfigInput


def _snapshot(row: DeploymentConfig) -> dict:
    return {
        "id": row.id,
        "blueprint_name": row.blueprint_name,
        "blueprint_version": row.blueprint_version,
        "version_no": row.version_no,
        "payload": row.payload,
        "actor": row.actor,
        "note": row.note,
        "is_active": row.is_active,
        "created_at": row.created_at.isoformat(),
    }


class DeploymentConfigService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def available_blueprints(self) -> list[dict]:
        return [
            {"name": b.name, "version": b.version, "title": b.title,
             "stages": list(b.stages)}
            for b in list_blueprints()
        ]

    async def save_config(
        self, tenant_id: str, payload: dict, *, actor: str = "operator",
        note: str = "",
    ) -> dict:
        try:
            data = DeploymentConfigInput(**payload)
        except PydanticValidationError as exc:
            raise ValidationError(
                "Invalid deployment configuration",
                code="deployment_config_invalid",
                details={"errors": exc.errors(include_url=False)},
                recovery_action="fix_deployment_config",
            ) from exc
        try:
            get_blueprint(data.blueprint_name, data.blueprint_version)
        except KeyError:
            raise ConfigError(
                f"Unknown blueprint {data.blueprint_name}@{data.blueprint_version}",
                code="unknown_blueprint",
                recovery_action="select_registered_blueprint",
            ) from None
        latest = (
            await self.session.execute(
                select(func.max(DeploymentConfig.version_no)).where(
                    DeploymentConfig.tenant_id == tenant_id
                )
            )
        ).scalar() or 0
        prior = (
            await self.session.execute(
                select(DeploymentConfig).where(
                    DeploymentConfig.tenant_id == tenant_id,
                    DeploymentConfig.is_active.is_(True),
                )
            )
        ).scalars().all()
        for row in prior:
            row.is_active = False
        row = DeploymentConfig(
            id=new_id("deploy_config"), tenant_id=tenant_id,
            blueprint_name=data.blueprint_name,
            blueprint_version=data.blueprint_version,
            version_no=latest + 1,
            payload=data.model_dump(mode="json"),
            actor=actor, note=note, is_active=True,
        )
        self.session.add(row)
        await self.session.flush()
        return _snapshot(row)

    async def list_versions(self, tenant_id: str) -> list[dict]:
        rows = (
            await self.session.execute(
                select(DeploymentConfig)
                .where(DeploymentConfig.tenant_id == tenant_id)
                .order_by(DeploymentConfig.version_no.desc())
            )
        ).scalars().all()
        return [_snapshot(r) for r in rows]

    async def get_active(self, tenant_id: str) -> dict | None:
        row = (
            await self.session.execute(
                select(DeploymentConfig).where(
                    DeploymentConfig.tenant_id == tenant_id,
                    DeploymentConfig.is_active.is_(True),
                )
            )
        ).scalars().first()
        return _snapshot(row) if row else None

    async def rollback(
        self, tenant_id: str, to_version: int, *, actor: str = "operator",
        note: str = "",
    ) -> dict:
        """Rollback appends a new version copying the old payload — history
        is never rewritten, so a bad rollback can itself be rolled back."""
        target = (
            await self.session.execute(
                select(DeploymentConfig).where(
                    DeploymentConfig.tenant_id == tenant_id,
                    DeploymentConfig.version_no == to_version,
                )
            )
        ).scalars().first()
        if target is None:
            raise NotFoundError(
                f"Deployment config version {to_version} does not exist"
            )
        return await self.save_config(
            tenant_id, target.payload, actor=actor,
            note=note or f"rollback to version {to_version}",
        )
