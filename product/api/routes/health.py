"""
Acquisition OS — Health API Routes
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from datetime import datetime, timedelta
from typing import List
import random

from product.api.schemas import HealthMetricSchema, AcquisitionHealthResponseSchema

router = APIRouter()


async def _get_services(request: Request, org_id: str):
    """Create services for an organization on each request."""
    from product.db.session import get_db_session
    from product.db.repositories import OrganizationRepository
    from product.services.health import HealthService
    from product.events import EventBus

    async with get_db_session() as session:
        org_repo = OrganizationRepository(session)
        org = await org_repo.get(org_id, org_id)
        if not org:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "ORG_NOT_FOUND", "message": "Organization not found"})

        org_config = org.get("settings", {}) or {}
        event_bus = EventBus.get()
        health_service = HealthService(session, None, org_config)

        return {"health_service": health_service}


@router.get("/health", response_model=AcquisitionHealthResponseSchema, tags=["health"])
async def get_health(request: Request, org_id: str):
    """Spec §10: GET /v1/organizations/{org_id}/health."""
    services = await _get_services(request, org_id)
    result = await services["health_service"].get_acquisition_health(org_id)
    return AcquisitionHealthResponseSchema(**result)


@router.get("/acquisition-health", response_model=AcquisitionHealthResponseSchema, tags=["health"])
async def get_acquisition_health(request: Request, org_id: str):
    """Get acquisition health metrics."""
    services = await _get_services(request, org_id)
    health_service = services["health_service"]
    result = await health_service.get_acquisition_health(org_id)
    return AcquisitionHealthResponseSchema(**result)
