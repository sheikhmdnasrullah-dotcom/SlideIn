"""
Acquisition OS — Main Application
Complete FastAPI application with all routes and services.
"""

from fastapi import FastAPI, Depends, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
import uuid
import random
import logging
import os

from product.db.session import init_db, get_db_session
from product.db.models import Organization, User
from product.db.repositories import (
    OrganizationRepository, OpportunityRepository, ConversationRepository,
    MessageRepository, SystemActivityRepository, AutomationRepository,
    MissionRepository,
)
from product.services.service_impl import (
    OpportunityService, CommandCenterService, AutomationEngine,
    OnboardingService, DemoDataService,
)
from product.services.acquisition_engine import AcquisitionEngine, OpportunityState
from product.agents.orchestrator import AIOrchestrator
from product.agents.llm import llm_provider
from product.events import EventBus, EventTypes, register_default_handlers
from product.api.security import authenticate, require_org_access

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Acquisition OS API starting up")
    # Initialize database
    await init_db()
    # Register event handlers
    event_bus = EventBus.get()
    register_default_handlers(event_bus)
    logger.info("Acquisition OS API ready")
    yield
    logger.info("Acquisition OS API shutting down")


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    app = FastAPI(
        title="Acquisition OS API",
        description="Product API for the Acquisition Operating System",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
        # Global credential check (API_SPEC.md §1): every request must carry
        # a valid org-scoped API key unless the path is explicitly public.
        dependencies=[Depends(authenticate)],
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://localhost:3001",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:3001",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Health check
    @app.get("/health", tags=["system"])
    async def health():
        return {"status": "healthy", "service": "acquisition-os-api", "version": "0.1.0", "llm_provider": llm_provider.provider}

    # Register routers. Org-scoped routers carry the tenant-binding
    # dependency (API_SPEC.md §1): the key's organization must match the
    # organization in the path, otherwise 404 (no cross-tenant oracle).
    from product.api.routes import opportunities, command_center, health as health_router
    org_deps = [Depends(require_org_access)]
    app.include_router(
        opportunities.router,
        prefix="/v1/organizations/{org_id}/opportunities",
        tags=["opportunities"],
        dependencies=org_deps,
    )
    app.include_router(
        command_center.router,
        prefix="/v1/organizations/{org_id}/command-center",
        tags=["command-center"],
        dependencies=org_deps,
    )
    app.include_router(
        health_router.router,
        prefix="/v1/organizations/{org_id}",
        tags=["health"],
        dependencies=org_deps,
    )
    app.include_router(health_router.router, tags=["health"])

    # Documented error envelope (API_SPEC.md §1). Registered inside the
    # factory so every app instance — including test apps — behaves the same.
    # StarletteHTTPException covers both fastapi.HTTPException (raised by
    # route code) and the router's own 404/405 exceptions (MRO lookup).
    from starlette.exceptions import HTTPException as StarletteHTTPException
    from fastapi.exceptions import RequestValidationError
    from fastapi.encoders import jsonable_encoder

    status_codes = {
        401: "UNAUTHENTICATED",
        404: "NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
    }

    async def _error_envelope(request, exc):
        if isinstance(exc, RequestValidationError):
            return JSONResponse(
                status_code=422,
                content={"error": {"code": "VALIDATION_ERROR", "message": "Request validation failed", "details": jsonable_encoder(exc.errors())}},
            )
        detail = exc.detail
        if isinstance(detail, dict):
            code = detail.get("code") or status_codes.get(exc.status_code, "ERROR")
            message = detail.get("message", str(detail))
            details = detail.get("details", [])
        else:
            code = status_codes.get(exc.status_code, "ERROR")
            message = str(detail)
            details = []
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": code, "message": message, "details": details}},
            headers=getattr(exc, "headers", None),
        )

    app.add_exception_handler(StarletteHTTPException, _error_envelope)
    app.add_exception_handler(RequestValidationError, _error_envelope)

    return app


app = create_app()


# ---------------------------------------------------------------------------
# Dependency: get services for a request
# ---------------------------------------------------------------------------

async def get_services(org_id: str):
    """Get service instances for an organization."""
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
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "product.api.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        reload=True,
    )
