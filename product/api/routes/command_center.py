"""
Acquisition OS — Command Center API Routes
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import random

from product.api.schemas import CommandCenterResponseSchema, CommandRequestSchema, CommandResponseSchema

router = APIRouter()


async def _get_services(request: Request, org_id: str):
    """Create services for an organization on each request."""
    from product.db.session import get_db_session
    from product.db.repositories import OrganizationRepository
    from product.services.service_impl import CommandCenterService
    from product.services.acquisition_engine import AcquisitionEngine
    from product.events import EventBus

    async with get_db_session() as session:
        org_repo = OrganizationRepository(session)
        org = await org_repo.get(org_id, org_id)
        if not org:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "ORG_NOT_FOUND", "message": "Organization not found"})

        org_config = org.get("settings", {}) or {}
        event_bus = EventBus.get()
        command_center_service = CommandCenterService(session, event_bus, org_config)

        return {"command_center_service": command_center_service}


@router.get("", response_model=CommandCenterResponseSchema, tags=["command-center"])
async def get_command_center(request: Request, org_id: str):
    """Get Command Center data."""
    services = await _get_services(request, org_id)
    command_center_service = services["command_center_service"]
    result = await command_center_service.get_command_center(org_id, "user_demo")
    return CommandCenterResponseSchema(**result)


@router.post("/command", response_model=CommandResponseSchema, tags=["command-center"])
async def execute_command(request: Request, org_id: str, payload: CommandRequestSchema):
    """Execute a natural language command."""
    services = await _get_services(request, org_id)
    command_center_service = services["command_center_service"]
    result = await command_center_service.execute_command(org_id, "user_demo", payload.command, payload.context)
    return CommandResponseSchema(**result)
