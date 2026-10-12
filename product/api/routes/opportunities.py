"""
Acquisition OS — Opportunities API Routes
Real implementations using services.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status, Request
from fastapi.responses import JSONResponse
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from pydantic import BaseModel

from product.api.schemas import (
    OpportunityCreateSchema,
    OpportunityResponseSchema,
    OpportunityDetailSchema,
    ResearchRequestSchema,
    ResearchResponseSchema,
    QualificationResponseSchema,
    PersonalizationRequestSchema,
    PersonalizationResponseSchema,
    MessageRequestSchema,
    MessageResponseSchema,
    SendRequestSchema,
    SendResponseSchema,
    BookRequestSchema,
    BookResponseSchema,
    PipelineResponseSchema,
    PaginatedResponse,
)
from product.services.acquisition_engine import OpportunityState

router = APIRouter()


# ---------------------------------------------------------------------------
# Service factory
# ---------------------------------------------------------------------------

async def _get_org_services(request: Request, org_id: str):
    """Create services for an organization on each request."""
    from product.db.session import get_db_session
    from product.db.repositories import (
        OrganizationRepository, OpportunityRepository, ConversationRepository,
        MessageRepository, SystemActivityRepository, AutomationRepository,
        MissionRepository,
    )
    from product.services.service_impl import (
        OpportunityService, CommandCenterService, AutomationEngine,
    )
    from product.services.acquisition_engine import AcquisitionEngine
    from product.events import EventBus

    async with get_db_session() as session:
        # Verify org exists
        org_repo = OrganizationRepository(session)
        org = await org_repo.get(org_id, org_id)
        if not org:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "ORG_NOT_FOUND", "message": "Organization not found"})

        # Get org config
        org_config = org.get("settings", {})
        if not org_config:
            org_config = {"icp": {}, "brand_voice": {}, "business_policy": {}}

        # Initialize services
        event_bus = EventBus.get()
        opportunity_service = OpportunityService(session, event_bus, org_config)
        command_center_service = CommandCenterService(session, event_bus, org_config)
        automation_engine = AutomationEngine(session, event_bus, org_config)

        return {
            "session": session,
            "org": org,
            "org_config": org_config,
            "opportunity_service": opportunity_service,
            "command_center_service": command_center_service,
            "automation_engine": automation_engine,
        }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("", response_model=PaginatedResponse, tags=["opportunities"])
async def list_opportunities(
    request: Request,
    org_id: str,
    state: Optional[str] = Query(None),
    min_score: Optional[int] = Query(None, ge=0, le=100),
    max_score: Optional[int] = Query(None, ge=0, le=100),
    search: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List opportunities with filters."""
    services = await _get_org_services(request, org_id)
    opportunity_service = services["opportunity_service"]

    filters = {}
    if state:
        filters["state"] = state
    if search:
        filters["search"] = search

    try:
        opportunities, total = await opportunity_service.opp_repo.list(
            org_id, filters, {"limit": limit, "offset": offset}, order_by="updated_at", order_dir="desc"
        )
    except Exception as e:
        opportunities = []
        total = 0

    return {
        "data": [_opportunity_to_response(o) for o in opportunities],
        "pagination": {"total": total, "limit": limit, "offset": offset},
    }


@router.post("", response_model=OpportunityResponseSchema, status_code=status.HTTP_201_CREATED, tags=["opportunities"])
async def create_opportunity(request: Request, org_id: str, payload: OpportunityCreateSchema):
    """Create a new opportunity."""
    services = await _get_org_services(request, org_id)
    opportunity_service = services["opportunity_service"]

    opportunity = await opportunity_service.create_opportunity(org_id, payload.dict())
    return _opportunity_to_response(opportunity)


# Static paths must be registered before /{opportunity_id} or they are
# shadowed by the dynamic segment (e.g. GET .../opportunities/pipeline).
@router.get("/pipeline", response_model=PipelineResponseSchema, tags=["opportunities"])
async def get_pipeline(request: Request, org_id: str):
    """Get pipeline view."""
    services = await _get_org_services(request, org_id)
    opportunity_service = services["opportunity_service"]
    result = await opportunity_service.get_pipeline(org_id)
    return PipelineResponseSchema(**result)


@router.get("/{opportunity_id}", response_model=OpportunityDetailSchema, tags=["opportunities"])
async def get_opportunity(request: Request, org_id: str, opportunity_id: str):
    """Get opportunity details."""
    services = await _get_org_services(request, org_id)
    opportunity_service = services["opportunity_service"]
    opportunity = await opportunity_service.opp_repo.get(opportunity_id, org_id)

    if not opportunity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "NOT_FOUND", "message": "Opportunity not found"})

    return _opportunity_to_detail(opportunity)


@router.post("/{opportunity_id}/research", response_model=ResearchResponseSchema, tags=["opportunities"])
async def research_opportunity(request: Request, org_id: str, opportunity_id: str, payload: ResearchRequestSchema):
    """Trigger research agent."""
    services = await _get_org_services(request, org_id)
    opportunity_service = services["opportunity_service"]
    try:
        result = await opportunity_service.research_opportunity(org_id, opportunity_id, payload.depth)
        return ResearchResponseSchema(
            opportunity_id=opportunity_id,
            dossier=result.get("research_dossier", {}),
            evidence=result.get("research_dossier", {}).get("evidence", []),
            confidence=result.get("research_dossier", {}).get("confidence", "medium"),
            opportunity_score=result.get("opportunity_score", 45),
            updated_at=datetime.utcnow(),
        )
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "NOT_FOUND", "message": "Opportunity not found"})


@router.post("/{opportunity_id}/qualify", response_model=QualificationResponseSchema, tags=["opportunities"])
async def qualify_opportunity(request: Request, org_id: str, opportunity_id: str):
    """Trigger qualification agent."""
    services = await _get_org_services(request, org_id)
    opportunity_service = services["opportunity_service"]
    try:
        result = await opportunity_service.qualify_opportunity(org_id, opportunity_id)
        return QualificationResponseSchema(
            opportunity_id=opportunity_id,
            fit_score=result.get("fit", {}),
            opportunity_score=result.get("opportunity_score", 70),
            qualification_stage=result.get("qualification", {}).get("stage", "qualified"),
            reasoning=result.get("next_best_action_reason", ""),
            recommended_angle=result.get("qualification", {}).get("recommended_angle", ""),
            updated_at=datetime.utcnow(),
        )
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "NOT_FOUND", "message": "Opportunity not found"})


@router.post("/{opportunity_id}/personalize", response_model=PersonalizationResponseSchema, tags=["opportunities"])
async def personalize_opportunity(request: Request, org_id: str, opportunity_id: str, payload: PersonalizationRequestSchema):
    """Trigger personalization agent."""
    services = await _get_org_services(request, org_id)
    opportunity_service = services["opportunity_service"]
    result = await opportunity_service.ai.personalize_opportunity(org_id, opportunity_id, payload.dict())
    return PersonalizationResponseSchema(
        opportunity_id=opportunity_id,
        personalization=result.get("personalization", {}),
        provenance=result.get("provenance", []),
        generated_at=datetime.utcnow(),
    )


@router.post("/{opportunity_id}/message", response_model=MessageResponseSchema, tags=["opportunities"])
async def generate_message(request: Request, org_id: str, opportunity_id: str, payload: MessageRequestSchema):
    """Generate a message."""
    services = await _get_org_services(request, org_id)
    opportunity_service = services["opportunity_service"]
    result = await opportunity_service.ai.generate_message(org_id, opportunity_id, payload.dict())
    return MessageResponseSchema(
        opportunity_id=opportunity_id,
        message=result.get("message", {}),
        generated_at=datetime.utcnow(),
    )


@router.post("/{opportunity_id}/send", response_model=SendResponseSchema, tags=["opportunities"])
async def send_message(request: Request, org_id: str, opportunity_id: str, payload: SendRequestSchema):
    """Send a message to an opportunity."""
    services = await _get_org_services(request, org_id)
    opportunity_service = services["opportunity_service"]
    try:
        result = await opportunity_service.send_message(org_id, opportunity_id, payload.dict())
        return SendResponseSchema(
            opportunity_id=opportunity_id,
            message_id=result.get("message_id", ""),
            status=result.get("status", "sent"),
            sent_at=result.get("sent_at"),
        )
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "NOT_FOUND", "message": "Opportunity not found"})


@router.post("/{opportunity_id}/book", response_model=BookResponseSchema, tags=["opportunities"])
async def book_opportunity(request: Request, org_id: str, opportunity_id: str, payload: BookRequestSchema):
    """Trigger booking agent."""
    services = await _get_org_services(request, org_id)
    opportunity_service = services["opportunity_service"]
    result = await opportunity_service.ai.recommend_booking(org_id, opportunity_id, {
        "opportunity_state": {},
        "advisor": {"id": payload.advisor_id, "name": "Advisor", "calendar_id": payload.calendar_id},
    })
    return BookResponseSchema(
        opportunity_id=opportunity_id,
        recommendation=result.get("recommendation", {}),
        generated_at=datetime.utcnow(),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _opportunity_to_response(opp: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": opp.get("id", ""),
        "org_id": opp.get("org_id", ""),
        "person": opp.get("person", {}),
        "opportunity_score": opp.get("opportunity_score", 0),
        "fit": opp.get("fit", {}),
        "intent": opp.get("intent", {}),
        "state": opp.get("state", "discovered"),
        "qualification": opp.get("qualification", {}),
        "next_best_action": opp.get("next_best_action"),
        "next_best_action_reason": opp.get("next_best_action_reason"),
        "next_action_at": opp.get("next_action_at"),
        "tags": opp.get("tags", []),
        "created_at": opp.get("created_at", datetime.utcnow().isoformat()),
        "updated_at": opp.get("updated_at", datetime.utcnow().isoformat()),
        "version": opp.get("version", 1),
    }


def _opportunity_to_detail(opp: Dict[str, Any]) -> Dict[str, Any]:
    base = _opportunity_to_response(opp)
    base.update({
        "behavior": opp.get("behavior", []),
        "conversation": opp.get("conversation", []),
        "appointment": opp.get("appointment"),
        "provenance": opp.get("provenance", {}),
        "lifecycle": opp.get("lifecycle", {}),
        "research_dossier": opp.get("research_dossier"),
    })
    return base
