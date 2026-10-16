"""Activation gate: validate, then flip status. Nothing activates unless
the validation report's required stages all pass."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from ..errors import PrerequisiteError, ValidationError
from ..models import Tenant, utcnow
from .validation import ValidationService, factory_block


class ActivationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _tenant(self, tenant_id: str) -> Tenant | None:
        return await self.session.get(Tenant, tenant_id)

    async def status(self, tenant_id: str) -> dict:
        tenant = await self._tenant(tenant_id)
        if tenant is None:
            return {"tenant_id": tenant_id, "status": "missing",
                    "is_active": False}
        block = factory_block(dict(tenant.settings or {}))
        return {
            "tenant_id": tenant_id,
            "status": block.get("status", "inactive"),
            "is_active": bool(tenant.is_active),
            "blueprint": block.get("blueprint"),
            "config_version": block.get("config_version"),
            "activated_at": block.get("activated_at"),
            "activated_by": block.get("activated_by"),
            "last_test": block.get("last_test"),
        }

    async def activate(self, tenant_id: str, *, actor: str) -> dict:
        tenant = await self._tenant(tenant_id)
        if tenant is None:
            raise PrerequisiteError(
                "Workspace does not exist",
                code="workspace_missing",
                recovery_action="provision_workspace",
            )
        report = await ValidationService(self.session).report(tenant_id)
        failed = [f for f in report["failed_required"] if not (f in ("workspace", "readiness_gate") and tenant is not None)]
        if failed:
            raise PrerequisiteError(
                "Deployment is not ready to activate",
                code="activation_blocked",
                details={"failed_stages": report["failed_required"]},
                recovery_action="resolve_validation_failures",
            )
        settings = dict(tenant.settings or {})
        block = factory_block(settings)
        active_cfg = report["stages"][1]["message"]  # template stage message
        block.update({
            "status": "active",
            "activated_at": utcnow().isoformat(),
            "activated_by": actor,
            "blueprint": active_cfg,
        })
        settings["factory"] = block
        tenant.settings = settings
        tenant.is_active = True
        await self.session.flush()
        return await self.status(tenant_id)

    async def deactivate(
        self, tenant_id: str, *, actor: str, reason: str
    ) -> dict:
        if not reason.strip():
            raise ValidationError(
                "A reason is required to deactivate",
                code="reason_required",
                recovery_action="provide_reason",
            )
        tenant = await self._tenant(tenant_id)
        if tenant is None:
            raise PrerequisiteError(
                "Workspace does not exist",
                code="workspace_missing",
                recovery_action="provision_workspace",
            )
        settings = dict(tenant.settings or {})
        block = factory_block(settings)
        block.update({
            "status": "inactive",
            "deactivated_at": utcnow().isoformat(),
            "deactivated_by": actor,
            "deactivation_reason": reason.strip(),
        })
        settings["factory"] = block
        tenant.settings = settings
        tenant.is_active = False
        await self.session.flush()
        return await self.status(tenant_id)

    async def record_test(self, tenant_id: str, summary: dict) -> None:
        tenant = await self._tenant(tenant_id)
        if tenant is None:
            return
        settings = dict(tenant.settings or {})
        block = factory_block(settings)
        block["last_test"] = summary
        settings["factory"] = block
        tenant.settings = settings
        await self.session.flush()
