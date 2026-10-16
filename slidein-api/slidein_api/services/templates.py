"""Industry / workspace templates — versioned starting points, never forks.

Templates live as repo-pinned JSON (`slidein_api/templates/*.json`) in
phase 1. Applying a template is non-destructive by construction: it only
sets the tenant's `settings["template"]` pointer. Reads resolve
*effective* configuration as template-defaults-under-tenant-settings, so a
tenant customization can never be lost or silently overwritten, and
upgrading a template only moves the pointer.

Resolution rules:

* modules: tenant-explicit `settings["modules"]` wins whole; otherwise the
  template's modules; otherwise the full default set;
* terminology: per-key merge, tenant keys win;
* branding: never templated — brand identity belongs to the tenant alone.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..errors import NotFoundError, ValidationError
from ..ids import new_id
from ..models import ConfigVersion, Tenant, utcnow
from .activity import ActivityService
from .modules import DEFAULT_ENABLED, MODULE_IDS, enabled_modules, nav_order

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"

_REQUIRED_KEYS = (
    "id", "version", "label", "description", "modules", "terminology",
    "pipeline_stages", "task_types", "ai_use_cases", "required_integrations",
    "role_defaults",
)


def _load_template_file(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValidationError(
            f"Template file {path.name} is unreadable: {exc}",
            recovery_action="fix_request",
        )
    if not isinstance(raw, dict):
        raise ValidationError(
            f"Template file {path.name} must hold an object",
            recovery_action="fix_request",
        )
    missing = [key for key in _REQUIRED_KEYS if key not in raw]
    if missing:
        raise ValidationError(
            f"Template {path.name} is missing: {', '.join(missing)}",
            recovery_action="fix_request",
        )
    modules = raw["modules"]
    enabled = modules.get("enabled") if isinstance(modules, dict) else None
    if not isinstance(enabled, list) or not enabled:
        raise ValidationError(
            f"Template {path.name} must enable at least one module",
            recovery_action="fix_request",
        )
    bogus = [m for m in enabled if m not in MODULE_IDS]
    if bogus:
        raise ValidationError(
            f"Template {path.name} names unknown modules: {', '.join(sorted(set(bogus)))}",
            recovery_action="fix_request",
        )
    if "settings" not in enabled:
        raise ValidationError(
            f"Template {path.name} must keep the 'settings' module enabled",
            recovery_action="fix_request",
        )
    return raw


def load_templates() -> dict[str, dict[str, Any]]:
    """All pinned templates by id. Files are tiny; read fresh each call."""
    out: dict[str, dict[str, Any]] = {}
    if not TEMPLATE_DIR.is_dir():
        return out
    for path in sorted(TEMPLATE_DIR.glob("*.json")):
        doc = _load_template_file(path)
        if doc["id"] != path.stem:
            raise ValidationError(
                f"Template id {doc['id']!r} must match its file name {path.stem!r}",
                recovery_action="fix_request",
            )
        out[doc["id"]] = doc
    return out


def get_template_doc(template_id: str) -> dict[str, Any]:
    try:
        return copy.deepcopy(load_templates()[template_id])
    except KeyError:
        raise NotFoundError(f"Template {template_id!r} does not exist")


def _merge_terminology(template_doc: dict | None, tenant_terms: object) -> dict[str, Any]:
    base: dict[str, Any] = copy.deepcopy((template_doc or {}).get("terminology") or {})
    if isinstance(tenant_terms, dict):
        for section, value in tenant_terms.items():
            if isinstance(value, dict) and isinstance(base.get(section), dict):
                base[section] = {**base[section], **value}
            else:
                base[section] = copy.deepcopy(value)
    return base


class TemplateService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_templates(self) -> list[dict[str, Any]]:
        return [
            {
                "id": doc["id"],
                "version": doc["version"],
                "label": doc["label"],
                "description": doc["description"],
            }
            for doc in load_templates().values()
        ]

    async def get_template(self, template_id: str) -> dict[str, Any]:
        return get_template_doc(template_id)

    async def _settings(self, tenant_id: str) -> dict[str, Any]:
        row = await self.session.get(Tenant, tenant_id)
        if row is None:
            return {}
        return dict(row.settings or {})

    async def effective(self, tenant_id: str) -> dict[str, Any]:
        """Effective workspace configuration: template defaults under
        tenant settings. Unknown tenants get bare defaults."""
        settings = await self._settings(tenant_id)
        pointer = settings.get("template") if isinstance(settings.get("template"), dict) else None
        doc: dict[str, Any] | None = None
        if pointer and pointer.get("id"):
            try:
                doc = get_template_doc(str(pointer["id"]))
            except NotFoundError:
                doc = None  # pinned template removed: fall through to defaults
        explicit_modules = settings.get("modules")
        if isinstance(explicit_modules, dict) and explicit_modules.get("enabled"):
            enabled = enabled_modules(explicit_modules)
            order = nav_order(explicit_modules, enabled)
            source = "tenant"
        elif doc is not None:
            enabled = enabled_modules(doc["modules"])
            order = nav_order(doc["modules"], enabled)
            source = "template"
        else:
            enabled = list(DEFAULT_ENABLED)
            order = list(DEFAULT_ENABLED)
            source = "default"
        return {
            "template": (
                {
                    "id": pointer["id"],
                    "version": pointer.get("version"),
                    "applied_at": pointer.get("applied_at"),
                    "label": doc["label"] if doc else None,
                }
                if pointer and pointer.get("id")
                else None
            ),
            "modules": {"enabled": enabled, "nav_order": order, "source": source},
            "terminology": _merge_terminology(doc, settings.get("terminology")),
            "pipeline_stages": copy.deepcopy((doc or {}).get("pipeline_stages") or []),
            "task_types": list((doc or {}).get("task_types") or []),
            "ai_use_cases": list((doc or {}).get("ai_use_cases") or []),
            "required_integrations": list((doc or {}).get("required_integrations") or []),
        }

    @staticmethod
    def _check_terminology(value: object) -> dict[str, Any]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValidationError(
                "terminology must be an object of string maps",
                recovery_action="fix_request",
            )
        out: dict[str, Any] = {}
        for section, mapping in value.items():
            if not isinstance(mapping, dict) or not all(
                isinstance(k, str) and isinstance(v, str)
                for k, v in mapping.items()
            ):
                raise ValidationError(
                    f"terminology section {section!r} must map strings to strings",
                    recovery_action="fix_request",
                )
            out[str(section)] = {str(k): v.strip() for k, v in mapping.items()}
        return out

    async def apply_template(
        self, tenant_id: str, template_id: str, *, actor: str,
        terminology: object = None,
    ) -> dict[str, Any]:
        """Point the workspace at a template. Only the pointer (plus any
        explicit terminology overrides) is written; tenant settings, data,
        and history are untouched."""
        if not isinstance(template_id, str) or not template_id.strip():
            raise ValidationError(
                "template_id must be a non-empty string",
                recovery_action="fix_request",
            )
        doc = get_template_doc(template_id.strip())
        terms = self._check_terminology(terminology)
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
        applied_at = utcnow().isoformat()
        settings = dict(row.settings or {})
        settings["template"] = {
            "id": doc["id"],
            "version": doc["version"],
            "applied_at": applied_at,
        }
        if terms:
            merged_terms = _merge_terminology(None, settings.get("terminology"))
            merged_terms = _merge_terminology({"terminology": merged_terms}, terms)
            settings["terminology"] = merged_terms
        row.settings = settings
        await self.session.flush()
        self.session.add(
            ConfigVersion(
                id=new_id("config_version"),
                tenant_id=tenant_id,
                entity_type="workspace_template",
                entity_id=doc["id"],
                version=int(doc["version"]),
                snapshot={
                    "template_id": doc["id"],
                    "template_version": doc["version"],
                    "applied_at": applied_at,
                    "modules": doc["modules"],
                },
                actor=actor,
                reason=f"applied template {doc['id']} v{doc['version']}",
            )
        )
        await self.session.flush()
        activity = ActivityService(self.session)
        await activity.record(
            tenant_id=tenant_id,
            action="template.applied",
            actor=actor,
            actor_role=actor.split(":", 1)[-1] if ":" in actor else actor,
            summary=f"Workspace template {doc['id']} v{doc['version']} applied",
            entity_type="workspace_template",
            entity_id=doc["id"],
            details={"template_id": doc["id"], "template_version": doc["version"]},
        )
        return await self.effective(tenant_id)


__all__ = ["TemplateService", "get_template_doc", "load_templates"]
