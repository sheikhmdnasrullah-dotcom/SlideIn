"""Module registry — which product modules a workspace has enabled.

The registry is static code (phase 1): each module names the API surface it
fronts so the server can enforce access, not just hide navigation. Per-tenant
state is a validated `modules` section of `Tenant.settings`:

    {"enabled": ["overview", "discovery", ...], "nav_order": [...]}

`settings` can never be disabled: it hosts this configuration, and locking
it would lock the tenant out of re-enabling anything.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..errors import PermissionDenied, ValidationError
from ..models import Tenant
from .activity import ActivityService

MODULE_REGISTRY: tuple[dict[str, Any], ...] = (
    {"id": "overview", "label": "Overview", "min_role": "viewer",
     "description": "Pipeline attention queue and readiness."},
    {"id": "discovery", "label": "Discovery", "min_role": "viewer",
     "description": "Source-attributed prospect records."},
    {"id": "research", "label": "Research", "min_role": "viewer",
     "description": "Verified/inferred prospect evidence."},
    {"id": "qualification", "label": "Qualification", "min_role": "viewer",
     "description": "Rubric scores against the active ICP."},
    {"id": "personalization", "label": "Personalization", "min_role": "viewer",
     "description": "Evidence-backed message drafts."},
    {"id": "outreach", "label": "Outreach", "min_role": "operator",
     "description": "Approvals, sending policy, and dispatch."},
    {"id": "inbox", "label": "Inbox", "min_role": "viewer",
     "description": "Conversations and reply intents."},
    {"id": "activity", "label": "Activity", "min_role": "viewer",
     "description": "Workflow history and audit trail."},
    {"id": "settings", "label": "Settings", "min_role": "operator",
     "description": "Profile, offers, branding, and modules."},
)

MODULE_IDS = tuple(entry["id"] for entry in MODULE_REGISTRY)
DEFAULT_ENABLED: tuple[str, ...] = MODULE_IDS


def registry() -> list[dict[str, Any]]:
    return [dict(entry) for entry in MODULE_REGISTRY]


def enabled_modules(stored: object) -> list[str]:
    """Tenant's enabled modules; unknown tenants get the full default set."""
    if isinstance(stored, dict) and isinstance(stored.get("enabled"), list):
        ordered = [m for m in stored["enabled"] if m in MODULE_IDS]
        if ordered:
            # `settings` is load-bearing: a stored list without it is stale.
            return ordered if "settings" in ordered else [*ordered, "settings"]
    return list(DEFAULT_ENABLED)


def nav_order(stored: object, enabled: list[str]) -> list[str]:
    if isinstance(stored, dict) and isinstance(stored.get("nav_order"), list):
        requested = [m for m in stored["nav_order"] if m in enabled]
        return requested + [m for m in enabled if m not in requested]
    return list(enabled)


def check_module_enabled(stored: object, module_id: str) -> None:
    """Raise 403 unless the tenant has this module enabled.

    Call from routes alongside `require_role`: hidden navigation is not
    authorization.
    """
    if module_id not in MODULE_IDS:
        raise ValidationError(
            f"Unknown module {module_id!r}",
            details={"module": module_id},
            recovery_action="fix_request",
        )
    if module_id not in enabled_modules(stored):
        raise PermissionDenied(
            f"Module {module_id!r} is not enabled for this workspace",
            code="not_authorized",
            details={"module": module_id},
            recovery_action="request_authorization",
        )


def validate_modules_update(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValidationError(
            "Modules payload must be an object", recovery_action="fix_request"
        )
    unknown = [k for k in payload if k not in ("enabled", "nav_order")]
    if unknown:
        raise ValidationError(
            f"Unknown modules field(s): {', '.join(sorted(unknown))}",
            details={"unknown_fields": sorted(unknown)},
            recovery_action="fix_request",
        )
    out: dict[str, Any] = {}
    if "enabled" in payload:
        raw = payload["enabled"]
        if not isinstance(raw, list) or not all(isinstance(m, str) for m in raw):
            raise ValidationError(
                "'enabled' must be a list of module ids",
                recovery_action="fix_request",
            )
        bogus = [m for m in raw if m not in MODULE_IDS]
        if bogus:
            raise ValidationError(
                f"Unknown module id(s): {', '.join(sorted(set(bogus)))}",
                details={"unknown_modules": sorted(set(bogus))},
                recovery_action="fix_request",
            )
        if "settings" not in raw:
            raise ValidationError(
                "Module 'settings' cannot be disabled",
                details={"module": "settings"},
                recovery_action="fix_request",
            )
        # De-duplicate, preserving order.
        out["enabled"] = list(dict.fromkeys(raw))
    if "nav_order" in payload:
        raw = payload["nav_order"]
        if not isinstance(raw, list) or not all(isinstance(m, str) for m in raw):
            raise ValidationError(
                "'nav_order' must be a list of module ids",
                recovery_action="fix_request",
            )
        bogus = [m for m in raw if m not in MODULE_IDS]
        if bogus:
            raise ValidationError(
                f"Unknown module id(s): {', '.join(sorted(set(bogus)))}",
                details={"unknown_modules": sorted(set(bogus))},
                recovery_action="fix_request",
            )
        out["nav_order"] = list(dict.fromkeys(raw))
    return out


class ModulesService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _stored(self, tenant_id: str) -> object:
        row = await self.session.get(Tenant, tenant_id)
        if row is None:
            return None
        return (row.settings or {}).get("modules")

    async def get_modules(self, tenant_id: str) -> dict[str, Any]:
        stored = await self._stored(tenant_id)
        enabled = enabled_modules(stored)
        return {
            "enabled": enabled,
            "nav_order": nav_order(stored, enabled),
            "registry": registry(),
        }

    async def update_modules(
        self, tenant_id: str, payload: dict, *, actor: str
    ) -> dict[str, Any]:
        update = validate_modules_update(payload)
        row = await self.session.get(Tenant, tenant_id)
        if row is None:
            slug = tenant_id.replace("_", "-") or "workspace"
            row = Tenant(
                id=tenant_id,
                name=slug.replace("-", " ").title(),
                slug=slug,
            )
            self.session.add(row)
            await self.session.flush()
        stored = dict((row.settings or {}).get("modules") or {})
        stored.update(update)
        settings = dict(row.settings or {})
        settings["modules"] = stored
        row.settings = settings
        await self.session.flush()
        enabled = enabled_modules(stored)
        activity = ActivityService(self.session)
        await activity.record(
            tenant_id=tenant_id,
            action="modules.updated",
            actor=actor,
            actor_role=actor.split(":", 1)[-1] if ":" in actor else actor,
            summary="Workspace modules updated",
            entity_type="tenant",
            entity_id=tenant_id,
            details={"enabled": enabled},
        )
        return {
            "enabled": enabled,
            "nav_order": nav_order(stored, enabled),
            "registry": registry(),
        }
