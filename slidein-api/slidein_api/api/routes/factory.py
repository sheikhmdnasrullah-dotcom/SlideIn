"""Factory routes: provision, owners, maps, connections, configs,
validation, activation, safe test. Operator control plane over HTTP."""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException
from starlette import status as http_status

from ...db import session_scope
from ...errors import SlideinError
from ...factory.activation import ActivationService
from ...factory.configs import DeploymentConfigService
from ...factory.connections import ConnectionService
from ...factory.models import CrmFieldMap
from ...factory.owners import OwnerService
from ...factory.schemas import CrmMapInput
from ...factory.testrun import TestRunService
from ...factory.validation import ValidationService
from ...security import AuthContext, require_auth, require_role, resolve_workspace
from ...services.config import ConfigService

router = APIRouter()

_STATUS_BY_CODE = {
    "not_found": http_status.HTTP_404_NOT_FOUND,
    "tenant_forbidden": http_status.HTTP_404_NOT_FOUND,
    "prospect_not_found": http_status.HTTP_404_NOT_FOUND,
    "not_authorized": http_status.HTTP_403_FORBIDDEN,
    "owner_unassigned": http_status.HTTP_409_CONFLICT,
    "owner_inactive": http_status.HTTP_409_CONFLICT,
    "owner_removed": http_status.HTTP_409_CONFLICT,
    "booking_missing": http_status.HTTP_409_CONFLICT,
    "booking_invalid": http_status.HTTP_409_CONFLICT,
    "booking_unverified": http_status.HTTP_409_CONFLICT,
    "activation_blocked": http_status.HTTP_409_CONFLICT,
}


def _error(exc: SlideinError) -> HTTPException:
    status = _STATUS_BY_CODE.get(exc.code, http_status.HTTP_400_BAD_REQUEST)
    return HTTPException(status_code=status, detail=exc.to_dict())


# -- provisioning ---------------------------------------------------------------

@router.post("/factory/tenants", tags=["factory"])
async def provision_tenant(
    payload: dict = Body(...),
    auth: AuthContext = Depends(require_auth),
) -> dict:
    """Create a client workspace row. Admin only. The workspace API key is
    still added to the server secret store by hand (documented manual step)."""
    require_role(auth, "admin")
    tenant_id = str(payload.get("tenant_id") or "").strip()
    if not tenant_id:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail={"code": "tenant_id_required",
                    "message": "tenant_id is required",
                    "details": {}, "recovery_action": "provide_tenant_id",
                    "retryable": False},
        )
    async with session_scope() as session:
        row = await ConfigService(session).ensure_tenant(
            tenant_id, name=str(payload.get("name") or tenant_id),
        )
        return {
            "tenant": row,
            "next_steps": [
                "Add an API key for this tenant to SLIDEIN_API_KEYS.",
                "Save a deployment config for the tenant.",
                "Complete intake, then run factory validation.",
            ],
        }


# -- owners ---------------------------------------------------------------------

@router.get("/tenants/{tenant_id}/factory/owners", tags=["factory"])
async def list_owners(
    tenant_id: str, auth: AuthContext = Depends(resolve_workspace)
) -> dict:
    async with session_scope() as session:
        rows = await OwnerService(session).list_owners(auth.tenant_id)
    return {"data": rows, "total": len(rows)}


@router.post("/tenants/{tenant_id}/factory/owners", tags=["factory"])
async def upsert_owner(
    tenant_id: str, payload: dict = Body(...),
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    require_role(auth, "operator")
    async with session_scope() as session:
        try:
            row = await OwnerService(session).upsert_owner(
                auth.tenant_id, payload, actor=f"user:{auth.role}")
        except SlideinError as exc:
            raise _error(exc)
    return {"owner": row}


@router.post("/tenants/{tenant_id}/factory/owners/import", tags=["factory"])
async def import_owners(
    tenant_id: str, payload: dict = Body(...),
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    require_role(auth, "operator")
    records = payload.get("records")
    if not isinstance(records, list):
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail={"code": "records_required",
                    "message": "records must be a list of owner objects",
                    "details": {}, "recovery_action": "fix_import_payload",
                    "retryable": False},
        )
    async with session_scope() as session:
        result = await OwnerService(session).import_owners(
            auth.tenant_id, records, actor=f"user:{auth.role}")
    return result


@router.patch("/tenants/{tenant_id}/factory/owners/{owner_id}", tags=["factory"])
async def patch_owner(
    tenant_id: str, owner_id: str, payload: dict = Body(...),
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    require_role(auth, "operator")
    async with session_scope() as session:
        service = OwnerService(session)
        current = await service.get_owner(auth.tenant_id, owner_id)
        if current is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail={"code": "not_found", "message": "Owner not found",
                        "details": {}, "recovery_action": "list_owners",
                        "retryable": False},
            )
        if "is_active" in payload and len(payload) == 1:
            row = await service.set_owner_active(
                auth.tenant_id, owner_id, bool(payload["is_active"]))
            return {"owner": row}
        merged = {**current, **payload}
        try:
            row = await service.upsert_owner(
                auth.tenant_id, merged, actor=f"user:{auth.role}")
        except SlideinError as exc:
            raise _error(exc)
    return {"owner": row}


@router.post(
    "/tenants/{tenant_id}/factory/prospects/{prospect_id}/assign",
    tags=["factory"],
)
async def assign_prospect(
    tenant_id: str, prospect_id: str, payload: dict = Body(...),
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    require_role(auth, "operator")
    async with session_scope() as session:
        try:
            result = await OwnerService(session).assign_prospect(
                auth.tenant_id, prospect_id,
                owner_id=payload.get("owner_id"),
                source=str(payload.get("source") or "manual"),
                actor=f"user:{auth.role}",
            )
        except SlideinError as exc:
            raise _error(exc)
    return result


@router.get(
    "/tenants/{tenant_id}/factory/prospects/{prospect_id}/booking",
    tags=["factory"],
)
async def resolve_booking(
    tenant_id: str, prospect_id: str,
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    async with session_scope() as session:
        try:
            resolved = await OwnerService(session).resolve_booking(
                auth.tenant_id, prospect_id)
        except SlideinError as exc:
            raise _error(exc)
    return resolved


# -- CRM maps -------------------------------------------------------------------

@router.get("/tenants/{tenant_id}/factory/crm-maps", tags=["factory"])
async def list_crm_maps(
    tenant_id: str, auth: AuthContext = Depends(resolve_workspace)
) -> dict:
    from sqlalchemy import select

    async with session_scope() as session:
        rows = (
            await session.execute(
                select(CrmFieldMap).where(
                    CrmFieldMap.tenant_id == auth.tenant_id)
            )
        ).scalars().all()
        data = [{
            "id": r.id, "provider": r.provider,
            "slidein_field": r.slidein_field,
            "external_field": r.external_field,
            "direction": r.direction, "is_active": r.is_active,
        } for r in rows]
    return {"data": data, "total": len(data)}


@router.post("/tenants/{tenant_id}/factory/crm-maps", tags=["factory"])
async def save_crm_map(
    tenant_id: str, payload: dict = Body(...),
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    require_role(auth, "operator")
    from sqlalchemy import select

    from ...ids import new_id
    from pydantic import ValidationError as PydanticValidationError

    try:
        data = CrmMapInput(**payload)
    except PydanticValidationError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail={"code": "crm_map_invalid", "message": "Invalid field map",
                    "details": {"errors": exc.errors(include_url=False)},
                    "recovery_action": "fix_crm_map", "retryable": False},
        )
    async with session_scope() as session:
        existing = (
            await session.execute(
                select(CrmFieldMap).where(
                    CrmFieldMap.tenant_id == auth.tenant_id,
                    CrmFieldMap.provider == data.provider,
                    CrmFieldMap.slidein_field == data.slidein_field,
                )
            )
        ).scalars().first()
        if existing is None:
            row = CrmFieldMap(
                id=new_id("crm_map"), tenant_id=auth.tenant_id,
                provider=data.provider, slidein_field=data.slidein_field,
                external_field=data.external_field, direction=data.direction,
            )
            session.add(row)
        else:
            existing.external_field = data.external_field
            existing.direction = data.direction
            existing.is_active = True
            row = existing
        await session.flush()
        saved = {"id": row.id, "provider": row.provider,
                 "slidein_field": row.slidein_field,
                 "external_field": row.external_field,
                 "direction": row.direction, "is_active": row.is_active}
    return {"map": saved}


@router.delete("/tenants/{tenant_id}/factory/crm-maps/{map_id}", tags=["factory"])
async def delete_crm_map(
    tenant_id: str, map_id: str,
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    require_role(auth, "operator")
    async with session_scope() as session:
        row = await session.get(CrmFieldMap, map_id)
        if row is None or row.tenant_id != auth.tenant_id:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail={"code": "not_found", "message": "Map not found",
                        "details": {}, "recovery_action": "list_crm_maps",
                        "retryable": False},
            )
        await session.delete(row)
        await session.flush()
    return {"deleted": True}


# -- connections ------------------------------------------------------------------

@router.get("/tenants/{tenant_id}/factory/connections", tags=["factory"])
async def list_connections(
    tenant_id: str, auth: AuthContext = Depends(resolve_workspace)
) -> dict:
    async with session_scope() as session:
        rows = await ConnectionService(session).list_connections(auth.tenant_id)
    return {"data": rows, "total": len(rows)}


@router.post("/tenants/{tenant_id}/factory/connections", tags=["factory"])
async def register_connection(
    tenant_id: str, payload: dict = Body(...),
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    require_role(auth, "operator")
    async with session_scope() as session:
        try:
            row = await ConnectionService(session).register(
                auth.tenant_id, payload, actor=f"user:{auth.role}")
        except SlideinError as exc:
            raise _error(exc)
    return {"connection": row}


@router.post(
    "/tenants/{tenant_id}/factory/connections/{connection_id}/probe",
    tags=["factory"],
)
async def probe_connection(
    tenant_id: str, connection_id: str,
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    require_role(auth, "operator")
    async with session_scope() as session:
        try:
            row = await ConnectionService(session).probe(
                auth.tenant_id, connection_id)
        except SlideinError as exc:
            raise _error(exc)
    return {"connection": row}


@router.delete(
    "/tenants/{tenant_id}/factory/connections/{connection_id}",
    tags=["factory"],
)
async def revoke_connection(
    tenant_id: str, connection_id: str,
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    require_role(auth, "operator")
    async with session_scope() as session:
        ok = await ConnectionService(session).revoke(
            auth.tenant_id, connection_id)
    if not ok:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "Connection not found",
                    "details": {}, "recovery_action": "list_connections",
                    "retryable": False},
        )
    return {"revoked": True,
            "note": "Rotate or delete the secret itself in the secret store."}


# -- configs ----------------------------------------------------------------------

@router.get("/tenants/{tenant_id}/factory/blueprints", tags=["factory"])
async def available_blueprints(
    tenant_id: str, auth: AuthContext = Depends(resolve_workspace)
) -> dict:
    async with session_scope() as session:
        items = DeploymentConfigService(session).available_blueprints()
    return {"data": items}


@router.get("/tenants/{tenant_id}/factory/configs", tags=["factory"])
async def list_configs(
    tenant_id: str, auth: AuthContext = Depends(resolve_workspace)
) -> dict:
    async with session_scope() as session:
        rows = await DeploymentConfigService(session).list_versions(auth.tenant_id)
    return {"data": rows, "total": len(rows)}


@router.get("/tenants/{tenant_id}/factory/configs/active", tags=["factory"])
async def active_config(
    tenant_id: str, auth: AuthContext = Depends(resolve_workspace)
) -> dict:
    async with session_scope() as session:
        row = await DeploymentConfigService(session).get_active(auth.tenant_id)
    return {"config": row}


@router.post("/tenants/{tenant_id}/factory/configs", tags=["factory"])
async def save_config(
    tenant_id: str, payload: dict = Body(...),
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    require_role(auth, "operator")
    async with session_scope() as session:
        try:
            row = await DeploymentConfigService(session).save_config(
                auth.tenant_id, payload, actor=f"user:{auth.role}",
                note=str(payload.get("note") or ""))
        except SlideinError as exc:
            raise _error(exc)
    return {"config": row}


@router.post("/tenants/{tenant_id}/factory/configs/rollback", tags=["factory"])
async def rollback_config(
    tenant_id: str, payload: dict = Body(...),
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    require_role(auth, "operator")
    try:
        to_version = int(payload.get("to_version"))
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail={"code": "version_required",
                    "message": "to_version must be an integer",
                    "details": {}, "recovery_action": "list_configs",
                    "retryable": False},
        )
    async with session_scope() as session:
        try:
            row = await DeploymentConfigService(session).rollback(
                auth.tenant_id, to_version, actor=f"user:{auth.role}",
                note=str(payload.get("note") or ""))
        except SlideinError as exc:
            raise _error(exc)
    return {"config": row}


# -- validation / activation / test -------------------------------------------------

@router.get("/tenants/{tenant_id}/factory/validation", tags=["factory"])
async def validation_report(
    tenant_id: str, auth: AuthContext = Depends(resolve_workspace)
) -> dict:
    async with session_scope() as session:
        report = await ValidationService(session).report(auth.tenant_id)
    return report


@router.get("/tenants/{tenant_id}/factory/activation", tags=["factory"])
async def activation_status(
    tenant_id: str, auth: AuthContext = Depends(resolve_workspace)
) -> dict:
    async with session_scope() as session:
        return await ActivationService(session).status(auth.tenant_id)


@router.post("/tenants/{tenant_id}/factory/activation/activate", tags=["factory"])
async def activate(
    tenant_id: str, auth: AuthContext = Depends(resolve_workspace)
) -> dict:
    require_role(auth, "admin")
    async with session_scope() as session:
        try:
            result = await ActivationService(session).activate(
                auth.tenant_id, actor=f"user:{auth.role}")
        except SlideinError as exc:
            raise _error(exc)
    return result


@router.post("/tenants/{tenant_id}/factory/activation/deactivate", tags=["factory"])
async def deactivate(
    tenant_id: str, payload: dict = Body(...),
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    require_role(auth, "admin")
    async with session_scope() as session:
        try:
            result = await ActivationService(session).deactivate(
                auth.tenant_id, actor=f"user:{auth.role}",
                reason=str(payload.get("reason") or ""))
        except SlideinError as exc:
            raise _error(exc)
    return result


@router.post("/tenants/{tenant_id}/factory/test", tags=["factory"])
async def safe_test(
    tenant_id: str, payload: dict = Body(...),
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    require_role(auth, "operator")
    async with session_scope() as session:
        try:
            report = await TestRunService(session).run(
                auth.tenant_id, mode=str(payload.get("mode") or "sample"),
                prospect_id=payload.get("prospect_id"),
                actor=f"user:{auth.role}",
            )
        except SlideinError as exc:
            raise _error(exc)
    return report
