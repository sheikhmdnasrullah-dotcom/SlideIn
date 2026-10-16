"""Team owners and deterministic booking resolution.

Resolution path: prospect -> assigned owner -> verified booking
destination. The AI never picks a link: anything unresolvable raises a
hold error with a recovery action, and drafts stay pending review.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..errors import ConfigError, NotFoundError, ValidationError
from ..ids import new_id
from ..models import Prospect, utcnow
from .models import ProspectOwnerAssignment, TeamOwner
from .schemas import OwnerInput


def _snapshot(row: TeamOwner) -> dict:
    return {
        "id": row.id,
        "display_name": row.display_name,
        "email": row.email,
        "crm_provider": row.crm_provider,
        "crm_owner_id": row.crm_owner_id,
        "booking_provider": row.booking_provider,
        "booking_url": row.booking_url,
        "booking_event_ref": row.booking_event_ref,
        "booking_verified": row.booking_verified,
        "is_active": row.is_active,
    }


def _valid_booking_url(url: str) -> bool:
    if not url:
        return False
    try:
        parts = urlparse(url)
    except ValueError:
        return False
    return parts.scheme in ("http", "https") and bool(parts.netloc)


class OwnerService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_owners(
        self, tenant_id: str, *, active_only: bool = False
    ) -> list[dict]:
        query = select(TeamOwner).where(TeamOwner.tenant_id == tenant_id)
        if active_only:
            query = query.where(TeamOwner.is_active.is_(True))
        rows = (await self.session.execute(query.order_by(TeamOwner.email))).scalars().all()
        return [_snapshot(r) for r in rows]

    async def get_owner(self, tenant_id: str, owner_id: str) -> dict | None:
        row = await self.session.get(TeamOwner, owner_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        return _snapshot(row)

    async def upsert_owner(
        self, tenant_id: str, payload: dict, *, actor: str = "operator"
    ) -> dict:
        try:
            data = OwnerInput(**payload)
        except PydanticValidationError as exc:
            clean_errs = []
            for err in exc.errors(include_url=False):
                e_copy = {k: v for k, v in err.items() if k != "ctx"}
                if "ctx" in err and isinstance(err["ctx"], dict):
                    e_copy["ctx"] = {k: str(v) for k, v in err["ctx"].items()}
                clean_errs.append(e_copy)
            raise ValidationError(
                "Invalid owner record",
                code="owner_invalid",
                details={"errors": clean_errs},
                recovery_action="fix_owner_record",
            ) from exc
        existing = (
            await self.session.execute(
                select(TeamOwner).where(
                    TeamOwner.tenant_id == tenant_id, TeamOwner.email == data.email
                )
            )
        ).scalars().first()
        if existing is None:
            row = TeamOwner(
                id=new_id("owner"), tenant_id=tenant_id,
                display_name=data.display_name, email=data.email,
                crm_provider=data.crm_provider, crm_owner_id=data.crm_owner_id,
                booking_provider=data.booking_provider,
                booking_url=data.booking_url,
                booking_event_ref=data.booking_event_ref,
                booking_verified=data.booking_verified,
                is_active=data.is_active,
            )
            self.session.add(row)
        else:
            # Re-verification is explicit: a changed URL unverifies itself.
            url_changed = data.booking_url != (existing.booking_url or "")
            existing.display_name = data.display_name
            existing.crm_provider = data.crm_provider
            existing.crm_owner_id = data.crm_owner_id
            existing.booking_provider = data.booking_provider
            existing.booking_url = data.booking_url
            existing.booking_event_ref = data.booking_event_ref
            existing.booking_verified = (
                data.booking_verified and not url_changed
                if url_changed else data.booking_verified
            )
            existing.is_active = data.is_active
            row = existing
        await self.session.flush()
        return _snapshot(row)

    async def import_owners(
        self, tenant_id: str, records: list[dict], *, actor: str = "operator"
    ) -> dict:
        """Bulk import (CSV-converted rows welcome). Per-row errors, no
        partial mystery: valid rows persist, bad rows are reported."""
        created = 0
        updated = 0
        errors: list[dict] = []
        before = {
            o["email"]
            for o in await self.list_owners(tenant_id)
        }
        for index, raw in enumerate(records):
            if not isinstance(raw, dict):
                errors.append({"index": index, "error": "row must be an object"})
                continue
            try:
                snap = await self.upsert_owner(tenant_id, raw, actor=actor)
            except ValidationError as exc:
                errors.append({"index": index, "error": exc.message,
                               "details": exc.details})
                continue
            if snap["email"] in before:
                updated += 1
            else:
                created += 1
                before.add(snap["email"])
        await self.session.flush()
        return {"created": created, "updated": updated, "errors": errors,
                "total": len(records)}

    async def set_owner_active(
        self, tenant_id: str, owner_id: str, active: bool
    ) -> dict:
        row = await self.session.get(TeamOwner, owner_id)
        if row is None or row.tenant_id != tenant_id:
            raise NotFoundError(f"Owner {owner_id!r} does not exist")
        row.is_active = active
        await self.session.flush()
        return _snapshot(row)

    async def assign_prospect(
        self, tenant_id: str, prospect_id: str, *, owner_id: str | None,
        source: str = "manual", actor: str = "operator",
    ) -> dict:
        prospect = await self.session.get(Prospect, prospect_id)
        if prospect is None or prospect.tenant_id != tenant_id:
            raise NotFoundError(f"Prospect {prospect_id!r} does not exist")
        if prospect.deleted_at is not None:
            raise ValidationError(
                "Prospect is deleted", code="prospect_deleted",
                recovery_action="restore_prospect",
            )
        owner = None
        if owner_id is not None:
            owner = await self.session.get(TeamOwner, owner_id)
            if owner is None or owner.tenant_id != tenant_id:
                raise NotFoundError(f"Owner {owner_id!r} does not exist")
            if not owner.is_active:
                raise ValidationError(
                    "Owner is inactive", code="owner_inactive",
                    recovery_action="activate_owner",
                )
        current = (
            await self.session.execute(
                select(ProspectOwnerAssignment).where(
                    ProspectOwnerAssignment.tenant_id == tenant_id,
                    ProspectOwnerAssignment.prospect_id == prospect_id,
                )
            )
        ).scalars().first()
        if current is None:
            current = ProspectOwnerAssignment(
                id=new_id("assignment"), tenant_id=tenant_id,
                prospect_id=prospect_id, history=[],
            )
            self.session.add(current)
        previous = current.owner_id
        current.owner_id = owner_id
        current.source = source
        current.assigned_by = actor
        current.history = [
            *current.history,
            {
                "previous_owner_id": previous, "owner_id": owner_id,
                "source": source, "actor": actor,
                "assigned_at": utcnow().isoformat(),
            },
        ]
        await self.session.flush()
        return {
            "prospect_id": prospect_id, "owner_id": owner_id,
            "previous_owner_id": previous, "source": source,
            "owner": _snapshot(owner) if owner else None,
        }

    async def assignment_for(
        self, tenant_id: str, prospect_id: str
    ) -> dict | None:
        row = (
            await self.session.execute(
                select(ProspectOwnerAssignment).where(
                    ProspectOwnerAssignment.tenant_id == tenant_id,
                    ProspectOwnerAssignment.prospect_id == prospect_id,
                )
            )
        ).scalars().first()
        if row is None:
            return None
        owner = None
        if row.owner_id:
            own = await self.session.get(TeamOwner, row.owner_id)
            if own is not None and own.tenant_id == tenant_id:
                owner = _snapshot(own)
        return {
            "prospect_id": prospect_id, "owner_id": row.owner_id,
            "source": row.source, "owner": owner, "history": row.history,
        }

    async def resolve_booking(
        self, tenant_id: str, prospect_id: str
    ) -> dict[str, Any]:
        """Deterministic prospect -> owner -> booking destination.

        Raises a hold error (never substitutes another owner's link) when
        anything on the path is missing or invalid.
        """
        prospect = await self.session.get(Prospect, prospect_id)
        if prospect is None or prospect.tenant_id != tenant_id:
            raise NotFoundError(f"Prospect {prospect_id!r} does not exist")
        assignment = await self.assignment_for(tenant_id, prospect_id)
        if assignment is None or not assignment["owner_id"]:
            raise ConfigError(
                "Prospect has no assigned owner; held for review",
                code="owner_unassigned",
                details={"prospect_id": prospect_id},
                recovery_action="assign_owner",
            )
        owner = assignment["owner"]
        if owner is None:
            raise ConfigError(
                "Assigned owner no longer exists; held for review",
                code="owner_removed",
                details={"prospect_id": prospect_id,
                         "owner_id": assignment["owner_id"]},
                recovery_action="assign_owner",
            )
        if not owner["is_active"]:
            raise ConfigError(
                "Assigned owner is inactive; held for review",
                code="owner_inactive",
                details={"prospect_id": prospect_id, "owner_id": owner["id"]},
                recovery_action="activate_owner",
            )
        url = owner["booking_url"] or ""
        if not url and not owner["booking_event_ref"]:
            raise ConfigError(
                "Owner has no booking destination; held for review",
                code="booking_missing",
                details={"prospect_id": prospect_id, "owner_id": owner["id"]},
                recovery_action="configure_booking",
            )
        if url and not _valid_booking_url(url):
            raise ConfigError(
                "Owner booking URL is invalid; held for review",
                code="booking_invalid",
                details={"prospect_id": prospect_id, "owner_id": owner["id"]},
                recovery_action="configure_booking",
            )
        if not owner["booking_verified"]:
            raise ConfigError(
                "Owner booking destination is unverified; held for review",
                code="booking_unverified",
                details={"prospect_id": prospect_id, "owner_id": owner["id"]},
                recovery_action="verify_booking",
            )
        return {
            "prospect_id": prospect_id,
            "owner_id": owner["id"],
            "owner_name": owner["display_name"],
            "owner_email": owner["email"],
            "booking_provider": owner["booking_provider"],
            "booking_url": url,
            "booking_event_ref": owner["booking_event_ref"],
            "assignment_source": assignment["source"],
        }

    async def owner_count(self, tenant_id: str) -> int:
        return (
            await self.session.execute(
                select(func.count(TeamOwner.id)).where(
                    TeamOwner.tenant_id == tenant_id,
                    TeamOwner.is_active.is_(True),
                )
            )
        ).scalar() or 0
