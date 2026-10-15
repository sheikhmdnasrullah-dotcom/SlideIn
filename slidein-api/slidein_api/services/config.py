"""Versioned business configuration — Business Profile, Offers, ICP.

This is the only place configuration is written. Saving always creates a
new version; the old version is kept and snapshotted in
`config_versions` so a prospect record can always be traced to the exact
configuration under which it advanced.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..errors import ConfigError, NotFoundError
from ..ids import new_id
from ..models import (
    BusinessProfile,
    ConfigVersion,
    IcpDefinition,
    Offer,
    Tenant,
)
from ..serialize import config_version, icp, offer, profile, tenant


def _snapshot_profile(rec: BusinessProfile) -> dict:
    return profile(rec)


def _snapshot(rec: Any) -> dict:
    for fn in (profile, offer, icp):
        try:
            return fn(rec)
        except AttributeError:  # pragma: no cover - dispatch guard
            continue
    return {"id": getattr(rec, "id", "")}


class ConfigService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # -- tenants ---------------------------------------------------------

    async def ensure_tenant(self, tenant_id: str, *, name: str | None = None) -> dict:
        row = await self.session.get(Tenant, tenant_id)
        if row is None:
            slug = tenant_id.replace("_", "-") or "workspace"
            row = Tenant(
                id=tenant_id,
                name=name or slug.replace("-", " ").title(),
                slug=slug,
            )
            self.session.add(row)
            await self.session.flush()
        return tenant(row)

    async def get_tenant(self, tenant_id: str) -> dict:
        row = await self.session.get(Tenant, tenant_id)
        if row is None:
            raise NotFoundError(f"Workspace {tenant_id!r} does not exist")
        return tenant(row)

    # -- profile ---------------------------------------------------------

    async def active_profile(self, tenant_id: str) -> dict | None:
        row = (
            await self.session.execute(
                select(BusinessProfile).where(
                    BusinessProfile.tenant_id == tenant_id,
                    BusinessProfile.is_active.is_(True),
                )
            )
        ).scalar_one_or_none()
        return profile(row) if row else None

    async def get_profile(self, tenant_id: str, profile_id: str) -> dict | None:
        row = await self.session.get(BusinessProfile, profile_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        return profile(row)

    async def save_profile(
        self, tenant_id: str, payload: dict, *, actor: str = "operator"
    ) -> dict:
        """Create or version the business profile. Always returns the new
        active version."""
        required = (
            "legal_name",
            "website_url",
            "industry",
            "company_description",
            "core_value_prop",
        )
        missing = [f for f in required if not str(payload.get(f, "")).strip()]
        if missing:
            raise ConfigError(
                "Business profile is incomplete",
                code="profile_incomplete",
                details={"missing_fields": missing},
                recovery_action="complete_business_profile",
            )

        previous = (
            await self.session.execute(
                select(BusinessProfile).where(
                    BusinessProfile.tenant_id == tenant_id,
                    BusinessProfile.is_active.is_(True),
                )
            )
        ).scalar_one_or_none()

        await self.ensure_tenant(tenant_id, name=str(payload["legal_name"]).strip())

        row = BusinessProfile(
            id=new_id("profile"),
            tenant_id=tenant_id,
            legal_name=str(payload["legal_name"]).strip(),
            website_url=str(payload["website_url"]).strip(),
            industry=str(payload["industry"]).strip(),
            company_description=str(payload["company_description"]).strip(),
            core_value_prop=str(payload["core_value_prop"]).strip(),
            markets_served=list(payload.get("markets_served") or []),
            target_roles=list(payload.get("target_roles") or []),
            brand_voice=str(payload.get("brand_voice", "")).strip(),
            version=1 if previous is None else int(previous.version) + 1,
            is_active=True,
            created_by=actor,
        )
        if previous is not None:
            previous.is_active = False
        self.session.add(row)
        await self.session.flush()

        await self._snapshot_version(
            tenant_id, "business_profile", row.id, row.version, row, actor,
            reason=payload.get("reason", "profile saved"),
        )
        return profile(row)

    # -- offers ----------------------------------------------------------

    async def list_offers(self, tenant_id: str, *, active_only: bool = True) -> list[dict]:
        query = select(Offer).where(Offer.tenant_id == tenant_id)
        if active_only:
            query = query.where(Offer.is_active.is_(True))
        rows = (await self.session.execute(query.order_by(Offer.created_at.desc()))).scalars().all()
        return [offer(r) for r in rows]

    async def save_offer(
        self, tenant_id: str, payload: dict, *, actor: str = "operator",
        profile_id: str | None = None,
    ) -> dict:
        active = await self.active_profile(tenant_id)
        if active is None:
            raise ConfigError(
                "Create a business profile before adding offers",
                code="profile_missing",
                recovery_action="create_business_profile",
            )
        target_profile = profile_id or active["id"]
        offer_id = str(payload.get("offer_id") or payload.get("id") or "")
        row = await self.session.get(Offer, offer_id) if offer_id else None
        if row is not None and row.tenant_id != tenant_id:
            raise NotFoundError("Offer not found")

        if row is None:
            if not str(payload.get("name", "")).strip():
                raise ConfigError(
                    "An offer needs a name", code="profile_incomplete",
                    recovery_action="complete_business_profile",
                )
            row = Offer(
                id=new_id("offer"),
                tenant_id=tenant_id,
                profile_id=target_profile,
                name=str(payload["name"]).strip(),
                version=1,
                created_by=actor,
            )
            self.session.add(row)
        else:
            row.is_active = bool(payload.get("is_active", True))

        for field in ("summary", "target_persona"):
            if field in payload:
                setattr(row, field, str(payload.get(field) or "").strip())
        for field in ("pain_points_solved", "proof_points"):
            if field in payload:
                setattr(row, field, list(payload.get(field) or []))
        await self.session.flush()
        await self._snapshot_version(
            tenant_id, "offer", row.id, row.version, row, actor,
            reason=payload.get("reason", "offer saved"),
        )
        return offer(row)

    async def deactivate_offer(self, tenant_id: str, offer_id: str) -> bool:
        row = await self.session.get(Offer, offer_id)
        if row is None or row.tenant_id != tenant_id:
            return False
        row.is_active = False
        await self.session.flush()
        return True

    # -- ICP -------------------------------------------------------------

    async def list_icps(self, tenant_id: str, *, active_only: bool = True) -> list[dict]:
        query = select(IcpDefinition).where(IcpDefinition.tenant_id == tenant_id)
        if active_only:
            query = query.where(IcpDefinition.is_active.is_(True))
        rows = (await self.session.execute(query.order_by(IcpDefinition.created_at.desc()))).scalars().all()
        return [icp(r) for r in rows]

    async def active_icp(self, tenant_id: str) -> dict | None:
        rows = await self.list_icps(tenant_id)
        return rows[0] if rows else None

    async def get_icp(self, tenant_id: str, icp_id: str) -> dict | None:
        row = await self.session.get(IcpDefinition, icp_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        return icp(row)

    async def save_icp(
        self, tenant_id: str, payload: dict, *, actor: str = "operator"
    ) -> dict:
        active = await self.active_profile(tenant_id)
        if active is None:
            raise ConfigError(
                "Create a business profile before defining an ICP",
                code="profile_missing",
                recovery_action="create_business_profile",
            )
        icp_id = str(payload.get("icp_id") or payload.get("id") or "")
        row = await self.session.get(IcpDefinition, icp_id) if icp_id else None
        if row is not None and row.tenant_id != tenant_id:
            raise NotFoundError("ICP not found")

        if row is None:
            name = str(payload.get("name", "")).strip()
            if not name:
                raise ConfigError(
                    "An ICP needs a name", code="profile_incomplete",
                    recovery_action="complete_business_profile",
                )
            profile_id = payload.get("profile_id") or active["id"]
            row = IcpDefinition(
                id=new_id("icp"),
                tenant_id=tenant_id,
                profile_id=str(profile_id),
                name=name,
                version=1,
                created_by=actor,
            )
            self.session.add(row)
        else:
            row.is_active = bool(payload.get("is_active", True))

        list_fields = ("industries", "geographies", "target_roles",
                       "required_signals", "exclusion_keywords")
        for field in list_fields:
            if field in payload:
                setattr(row, field, list(payload.get(field) or []))
        for field in ("company_size_min", "company_size_max", "qualify_threshold"):
            if field in payload and payload.get(field) is not None:
                setattr(row, field, int(payload[field]))
        await self.session.flush()
        await self._snapshot_version(
            tenant_id, "icp_definition", row.id, row.version, row, actor,
            reason=payload.get("reason", "icp saved"),
        )
        return icp(row)

    async def deactivate_icp(self, tenant_id: str, icp_id: str) -> bool:
        row = await self.session.get(IcpDefinition, icp_id)
        if row is None or row.tenant_id != tenant_id:
            return False
        row.is_active = False
        await self.session.flush()
        return True

    # -- configuration versions ------------------------------------------

    async def _snapshot_version(
        self, tenant_id: str, entity_type: str, entity_id: str, version: int,
        row: Any, actor: str, *, reason: str = "",
    ) -> dict:
        snapshot_row = ConfigVersion(
            id=new_id("config_version"),
            tenant_id=tenant_id,
            entity_type=entity_type,
            entity_id=entity_id,
            version=int(version),
            snapshot=_snapshot(row),
            actor=actor,
            reason=reason,
        )
        self.session.add(snapshot_row)
        await self.session.flush()
        return config_version(snapshot_row)

    async def list_config_versions(
        self, tenant_id: str, *, entity_type: str | None = None, limit: int = 50
    ) -> list[dict]:
        query = select(ConfigVersion).where(ConfigVersion.tenant_id == tenant_id)
        if entity_type:
            query = query.where(ConfigVersion.entity_type == entity_type)
        rows = (
            await self.session.execute(
                query.order_by(ConfigVersion.created_at.desc()).limit(limit)
            )
        ).scalars().all()
        return [config_version(r) for r in rows]

    async def get_config_version(
        self, tenant_id: str, entity_type: str, entity_id: str, version: int
    ) -> dict | None:
        row = (
            await self.session.execute(
                select(ConfigVersion).where(
                    ConfigVersion.tenant_id == tenant_id,
                    ConfigVersion.entity_type == entity_type,
                    ConfigVersion.entity_id == entity_id,
                    ConfigVersion.version == int(version),
                )
            )
        ).scalar_one_or_none()
        return config_version(row) if row else None

    async def profile_version(self, tenant_id: str, profile_id: str, version: int) -> dict | None:
        return await self.get_config_version(tenant_id, "business_profile", profile_id, version)

    async def readiness(self, tenant_id: str) -> dict:
        """Real readiness computed from persisted configuration and pipeline."""
        prof = await self.active_profile(tenant_id)
        offers = await self.list_offers(tenant_id)
        icps = await self.list_icps(tenant_id)

        checks: list[dict] = []

        def add(key: str, ok: bool, weight: int, message: str = "") -> None:
            checks.append(
                {
                    "key": key,
                    "status": "pass" if ok else "fail",
                    "weight": weight,
                    "message": message,
                }
            )

        add("business_profile", prof is not None, 20,
            "Business profile created and active" if prof else "No active business profile")
        add(
            "active_offers",
            len(offers) > 0,
            20,
            f"{len(offers)} active offer(s)" if offers else "No active offers",
        )
        add(
            "icp_rules",
            len(icps) > 0,
            20,
            f"{len(icps)} active ICP(s)" if icps else "No active ICP definitions",
        )
        if prof:
            add("brand_voice", bool(prof.get("brand_voice")), 5,
                "Brand voice set" if prof.get("brand_voice") else "Brand voice not set")
            add("target_roles",
                bool(prof.get("target_roles")),
                5,
                f"{len(prof.get('target_roles') or [])} target role(s)"
                if prof.get("target_roles") else "No target roles on the profile")
        else:
            add("brand_voice", False, 5, "Requires a business profile")
            add("target_roles", False, 5, "Requires a business profile")

        from .suppression import SuppressionService  # local import: avoids cycles

        suppression = SuppressionService(self.session)
        suppression_ok = await suppression.is_configured(tenant_id)
        add("suppression_list", suppression_ok, 10,
            "Suppression list loaded" if suppression_ok
            else "Suppression list not loaded yet")

        from .outreach import OutreachService

        outreach = OutreachService(self.session)
        policy = await outreach.policy(tenant_id)
        add(
            "approval_policy",
            bool(policy.get("require_approval")),
            10,
            "Human approval required before sending"
            if policy.get("require_approval") else "Approval is not required",
        )
        add(
            "rate_limits",
            bool(policy.get("daily_limit")),
            10,
            f"Daily limit {policy.get('daily_limit')}"
            if policy.get("daily_limit") else "No daily sending limit configured",
        )

        score = sum(c["weight"] for c in checks if c["status"] == "pass")
        return {
            "tenant_id": tenant_id,
            "overall_score": score,
            "is_ready_for_activation": all(
                c["status"] == "pass" for c in checks if c["weight"] >= 20
            ),
            "checklist": checks,
            "profile_version": prof.get("version") if prof else None,
        }
