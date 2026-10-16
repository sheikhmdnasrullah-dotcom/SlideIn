"""Configuration routes: business profile, offers, ICPs, readiness."""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from starlette import status as http_status

from ...db import session_scope
from ...errors import SlideinError
from ...security import AuthContext, require_role, resolve_workspace
from ...services.branding import BrandingService
from ...services.config import ConfigService
from ...services.modules import ModulesService
from ...services.templates import TemplateService
from ..deps import module_gate

router = APIRouter()


def _error(exc: SlideinError) -> HTTPException:
    code = exc.code
    status = (
        http_status.HTTP_404_NOT_FOUND
        if code in ("not_found", "tenant_forbidden", "prospect_not_found", "draft_not_found")
        else http_status.HTTP_403_FORBIDDEN
        if code == "not_authorized"
        else http_status.HTTP_400_BAD_REQUEST
    )
    return HTTPException(status_code=status, detail=exc.to_dict())


@router.get("/tenants/{tenant_id}/profile", tags=["configuration"])
async def get_profile(tenant_id: str, auth: AuthContext = Depends(resolve_workspace)) -> dict:
    async with session_scope() as session:
        service = ConfigService(session)
        profile = await service.active_profile(auth.tenant_id)
        offers = await service.list_offers(auth.tenant_id)
        icps = await service.list_icps(auth.tenant_id)
        versions = await service.list_config_versions(auth.tenant_id, limit=25)
        return {
            "profile": profile,
            "offers": offers,
            "icps": icps,
            "config_versions": versions,
            "readiness": await service.readiness(auth.tenant_id),
        }


@router.post("/tenants/{tenant_id}/profile", tags=["configuration"])
async def save_profile(
    tenant_id: str,
    payload: dict = Body(...),
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    require_role(auth, "operator")
    async with session_scope() as session:
        service = ConfigService(session)
        try:
            profile = await service.save_profile(
                auth.tenant_id, payload, actor=f"user:{auth.role}"
            )
            readiness = await service.readiness(auth.tenant_id)
        except SlideinError as exc:
            raise _error(exc)
    return {"profile": profile, "readiness": readiness}


@router.post("/tenants/{tenant_id}/offers", tags=["configuration"])
async def save_offer(
    tenant_id: str,
    payload: dict = Body(...),
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    require_role(auth, "operator")
    async with session_scope() as session:
        service = ConfigService(session)
        try:
            offer = await service.save_offer(
                auth.tenant_id, payload, actor=f"user:{auth.role}"
            )
            readiness = await service.readiness(auth.tenant_id)
        except SlideinError as exc:
            raise _error(exc)
    return {"offer": offer, "readiness": readiness}


@router.delete("/tenants/{tenant_id}/offers/{offer_id}", tags=["configuration"])
async def deactivate_offer(
    tenant_id: str, offer_id: str, auth: AuthContext = Depends(resolve_workspace)
) -> dict:
    require_role(auth, "operator")
    async with session_scope() as session:
        removed = await ConfigService(session).deactivate_offer(auth.tenant_id, offer_id)
        if not removed:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail={"code": "not_found", "message": "Offer not found"},
            )
        readiness = await ConfigService(session).readiness(auth.tenant_id)
    return {"deactivated": True, "readiness": readiness}


@router.post("/tenants/{tenant_id}/icps", tags=["configuration"])
async def save_icp(
    tenant_id: str,
    payload: dict = Body(...),
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    require_role(auth, "operator")
    async with session_scope() as session:
        service = ConfigService(session)
        try:
            icp = await service.save_icp(auth.tenant_id, payload, actor=f"user:{auth.role}")
            readiness = await service.readiness(auth.tenant_id)
        except SlideinError as exc:
            raise _error(exc)
    return {"icp": icp, "readiness": readiness}


@router.delete("/tenants/{tenant_id}/icps/{icp_id}", tags=["configuration"])
async def deactivate_icp(
    tenant_id: str, icp_id: str, auth: AuthContext = Depends(resolve_workspace)
) -> dict:
    require_role(auth, "operator")
    async with session_scope() as session:
        removed = await ConfigService(session).deactivate_icp(auth.tenant_id, icp_id)
        if not removed:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail={"code": "not_found", "message": "ICP not found"},
            )
        readiness = await ConfigService(session).readiness(auth.tenant_id)
    return {"deactivated": True, "readiness": readiness}


@router.get("/tenants/{tenant_id}/readiness", tags=["configuration"])
async def readiness(tenant_id: str, auth: AuthContext = Depends(resolve_workspace)) -> dict:
    async with session_scope() as session:
        return await ConfigService(session).readiness(auth.tenant_id)


@router.get("/tenants/{tenant_id}/config-versions", tags=["configuration"])
async def config_versions(
    tenant_id: str,
    entity_type: str | None = Query(None),
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    async with session_scope() as session:
        rows = await ConfigService(session).list_config_versions(
            auth.tenant_id, entity_type=entity_type, limit=100
        )
        return {"config_versions": rows}


@router.get("/tenants/{tenant_id}/branding", tags=["configuration"])
async def get_branding(
    tenant_id: str, auth: AuthContext = Depends(resolve_workspace)
) -> dict:
    async with session_scope() as session:
        await module_gate(session, auth.tenant_id, "settings")
        return {"branding": await BrandingService(session).get_branding(auth.tenant_id)}


@router.put("/tenants/{tenant_id}/branding", tags=["configuration"])
async def update_branding(
    tenant_id: str,
    payload: dict = Body(...),
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    require_role(auth, "operator")
    async with session_scope() as session:
        await module_gate(session, auth.tenant_id, "settings")
        try:
            branding = await BrandingService(session).update_branding(
                auth.tenant_id, payload, actor=f"user:{auth.role}"
            )
        except SlideinError as exc:
            raise _error(exc)
    return {"branding": branding}


@router.get("/tenants/{tenant_id}/modules", tags=["configuration"])
async def get_modules(
    tenant_id: str, auth: AuthContext = Depends(resolve_workspace)
) -> dict:
    async with session_scope() as session:
        await module_gate(session, auth.tenant_id, "settings")
        result = await ModulesService(session).get_modules(auth.tenant_id)
        effective = await TemplateService(session).effective(auth.tenant_id)
        # Effective modules: tenant settings win, template fills the rest.
        result["enabled"] = effective["modules"]["enabled"]
        result["nav_order"] = effective["modules"]["nav_order"]
        result["source"] = effective["modules"]["source"]
        result["template"] = effective["template"]
        return result


@router.put("/tenants/{tenant_id}/modules", tags=["configuration"])
async def update_modules(
    tenant_id: str,
    payload: dict = Body(...),
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    require_role(auth, "operator")
    async with session_scope() as session:
        await module_gate(session, auth.tenant_id, "settings")
        try:
            result = await ModulesService(session).update_modules(
                auth.tenant_id, payload, actor=f"user:{auth.role}"
            )
        except SlideinError as exc:
            raise _error(exc)
        effective = await TemplateService(session).effective(auth.tenant_id)
        result["source"] = effective["modules"]["source"]
        result["template"] = effective["template"]
    return result


@router.get("/tenants/{tenant_id}/template", tags=["configuration"])
async def get_template(
    tenant_id: str, auth: AuthContext = Depends(resolve_workspace)
) -> dict:
    async with session_scope() as session:
        await module_gate(session, auth.tenant_id, "settings")
        return await TemplateService(session).effective(auth.tenant_id)


@router.post("/tenants/{tenant_id}/template", tags=["configuration"])
async def apply_template(
    tenant_id: str,
    payload: dict = Body(...),
    auth: AuthContext = Depends(resolve_workspace),
) -> dict:
    require_role(auth, "operator")
    async with session_scope() as session:
        await module_gate(session, auth.tenant_id, "settings")
        try:
            result = await TemplateService(session).apply_template(
                auth.tenant_id,
                payload.get("template_id"),
                actor=f"user:{auth.role}",
                terminology=payload.get("terminology"),
            )
        except SlideinError as exc:
            raise _error(exc)
    return result
