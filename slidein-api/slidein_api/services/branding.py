"""Tenant branding — the white-label identity of one workspace.

Branding lives in a validated `branding` section of `Tenant.settings`, so no
schema change is needed and one tenant's brand can never leak into another:
every read/write is scoped by `AuthContext.tenant_id` at the route layer.

Security notes:

* `logo_url` / `favicon_url` must be plain https URLs (no credentials, no
  javascript:, capped length) so a brand asset can never become an XSS or
  SSRF vector when rendered.
* `colors` must be `#rgb` / `#rrggbb` hex so theme tokens cannot inject CSS.
* `custom_domain` is stored with `domain_verified: False` always. Domain
  ownership verification is a separate flow; this module never marks a
  domain verified and ignores any such claim in the payload.
"""

from __future__ import annotations

import copy
import re
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.ext.asyncio import AsyncSession

from ..errors import ValidationError
from ..models import Tenant
from .activity import ActivityService

DEFAULT_BRANDING: dict[str, Any] = {
    "business_name": "",
    "logo_url": "",
    "favicon_url": "",
    "colors": {
        "primary": "#1a56db",
        "surface": "#ffffff",
        "ink": "#111827",
    },
    "email_from_name": "",
    "custom_domain": "",
    "domain_verified": False,
}

_KNOWN_KEYS = frozenset(DEFAULT_BRANDING)
_KNOWN_COLORS = frozenset(DEFAULT_BRANDING["colors"])
_HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
_HOST_RE = re.compile(
    r"^(?=.{1,253}$)(?!-)[A-Za-z0-9-]{1,63}(?<!-)"
    r"(?:\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))*\.[A-Za-z]{2,}$"
)
_MAX_URL_LEN = 2048
_MAX_NAME_LEN = 120


def _fail(field: str, reason: str) -> ValidationError:
    return ValidationError(
        f"Invalid branding field {field!r}: {reason}",
        details={"field": field, "reason": reason},
        recovery_action="fix_request",
    )


def _check_url(field: str, value: object) -> str:
    if not isinstance(value, str):
        raise _fail(field, "must be a string")
    text = value.strip()
    if text == "":
        return ""
    if len(text) > _MAX_URL_LEN:
        raise _fail(field, f"must be under {_MAX_URL_LEN} characters")
    try:
        parsed = urlparse(text)
    except ValueError:
        raise _fail(field, "is not a valid URL")
    if parsed.scheme != "https" or not parsed.hostname:
        raise _fail(field, "must be an absolute https URL")
    if parsed.username or parsed.password:
        raise _fail(field, "must not embed credentials")
    return text


def _check_name(field: str, value: object) -> str:
    if not isinstance(value, str):
        raise _fail(field, "must be a string")
    text = value.strip()
    if len(text) > _MAX_NAME_LEN:
        raise _fail(field, f"must be under {_MAX_NAME_LEN} characters")
    return text


def _check_domain(value: object) -> str:
    if not isinstance(value, str):
        raise _fail("custom_domain", "must be a string")
    text = value.strip().lower().rstrip(".")
    if text == "":
        return ""
    if len(text) > 253 or not _HOST_RE.match(text):
        raise _fail("custom_domain", "must be a valid hostname")
    return text


def validate_branding_update(payload: object) -> dict[str, Any]:
    """Validate a branding PATCH body. Returns normalised fields to merge."""
    if not isinstance(payload, dict):
        raise ValidationError(
            "Branding payload must be an object",
            recovery_action="fix_request",
        )
    unknown = [key for key in payload if key not in _KNOWN_KEYS]
    if unknown:
        raise ValidationError(
            f"Unknown branding field(s): {', '.join(sorted(unknown))}",
            details={"unknown_fields": sorted(unknown)},
            recovery_action="fix_request",
        )
    out: dict[str, Any] = {}
    if "business_name" in payload:
        out["business_name"] = _check_name("business_name", payload["business_name"])
    if "email_from_name" in payload:
        out["email_from_name"] = _check_name(
            "email_from_name", payload["email_from_name"]
        )
    if "logo_url" in payload:
        out["logo_url"] = _check_url("logo_url", payload["logo_url"])
    if "favicon_url" in payload:
        out["favicon_url"] = _check_url("favicon_url", payload["favicon_url"])
    if "custom_domain" in payload:
        out["custom_domain"] = _check_domain(payload["custom_domain"])
        # Changing the domain always drops verification; a separate flow
        # re-verifies ownership. The payload can never set this itself.
        out["domain_verified"] = False
    if "domain_verified" in payload:
        raise _fail("domain_verified", "is managed by domain verification only")
    if "colors" in payload:
        raw_colors = payload["colors"]
        if not isinstance(raw_colors, dict):
            raise _fail("colors", "must be an object")
        unknown_colors = [k for k in raw_colors if k not in _KNOWN_COLORS]
        if unknown_colors:
            raise _fail(
                "colors", f"unknown token(s): {', '.join(sorted(unknown_colors))}"
            )
        colors: dict[str, str] = {}
        for token, raw in raw_colors.items():
            if not isinstance(raw, str) or not _HEX_RE.match(raw.strip()):
                raise _fail(f"colors.{token}", "must be #rgb or #rrggbb hex")
            colors[token] = raw.strip().lower()
        out["colors"] = colors
    return out


def merge_branding(stored: object) -> dict[str, Any]:
    """Defaults with the tenant's stored overrides applied (never mutates)."""
    merged: dict[str, Any] = copy.deepcopy(DEFAULT_BRANDING)
    if isinstance(stored, dict):
        for key in _KNOWN_KEYS:
            if key == "colors" and isinstance(stored.get("colors"), dict):
                for token in _KNOWN_COLORS:
                    raw = stored["colors"].get(token)
                    if isinstance(raw, str) and _HEX_RE.match(raw.strip()):
                        merged["colors"][token] = raw.strip().lower()
            elif key in stored and key != "colors":
                merged[key] = stored[key]
    return merged


class BrandingService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_branding(self, tenant_id: str) -> dict[str, Any]:
        row = await self.session.get(Tenant, tenant_id)
        stored = row.settings.get("branding") if row is not None else None
        return merge_branding(stored)

    async def update_branding(
        self, tenant_id: str, payload: dict, *, actor: str
    ) -> dict[str, Any]:
        update = validate_branding_update(payload)
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
        current = merge_branding((row.settings or {}).get("branding"))
        for key, value in update.items():
            if key == "colors":
                current["colors"].update(value)
            else:
                current[key] = value
        # JSONMap has no mutation tracking: reassign a fresh settings dict.
        settings = dict(row.settings or {})
        settings["branding"] = current
        row.settings = settings
        await self.session.flush()
        activity = ActivityService(self.session)
        await activity.record(
            tenant_id=tenant_id,
            action="branding.updated",
            actor=actor,
            actor_role=actor.split(":", 1)[-1] if ":" in actor else actor,
            summary="Workspace branding updated",
            entity_type="tenant",
            entity_id=tenant_id,
            details={"fields": sorted(update)},
        )
        return current
