"""Slidein API application factory."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from ..db import init_db
from ..errors import SlideinError
from .routes import config, outreach, overview, pipeline, system

logger = logging.getLogger("slidein.api")

PUBLIC_PREFIXES = ("/health", "/docs", "/redoc", "/openapi.json", "/v1/contracts")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("slidein api starting")
    await init_db()
    yield
    logger.info("slidein api stopped")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Slidein Workflow API",
        description=(
            "Backend contracts for the Slidein prospect-to-conversation "
            "workflow: configuration, discovery, research, qualification, "
            "personalization, outreach, conversations and activity."
        ),
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:3001",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(SlideinError)
    async def _slidein_error_handler(request: Request, exc: SlideinError):
        status = 404 if exc.code in ("tenant_forbidden", "not_found") else (
            403 if exc.code == "not_authorized" else 400
        )
        return JSONResponse(
            status_code=status,
            content={"error": exc.to_dict()},
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error_handler(request: Request, exc: StarletteHTTPException):
        """Every route raises `HTTPException(detail=<error dict>)`; this keeps
        the documented `{"error": {...}}` envelope for all of them."""
        detail = exc.detail
        if isinstance(detail, dict) and "code" in detail:
            content = {"error": detail}
        else:
            content = {
                "error": {
                    "code": "ERROR",
                    "message": str(detail),
                    "details": {},
                    "recovery_action": "retry_stage",
                    "retryable": False,
                }
            }
        return JSONResponse(
            status_code=exc.status_code,
            content=content,
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(Exception)
    async def _unhandled_handler(request: Request, exc: Exception):
        logger.exception("unhandled error on %s", request.url.path)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "unknown",
                    "message": f"{type(exc).__name__}: {exc}",
                    "details": {},
                    "recovery_action": "retry_stage",
                    "retryable": True,
                }
            },
        )

    @app.get("/health", tags=["system"], include_in_schema=False)
    async def root_health() -> dict:
        """Liveness probe, always public."""
        return {"status": "healthy", "service": "slidein-api", "version": "1.0.0"}

    prefix = "/v1"
    app.include_router(system.router, prefix=prefix, tags=["system"])
    app.include_router(config.router, prefix=prefix, tags=["configuration"])
    app.include_router(pipeline.router, prefix=prefix, tags=["pipeline"])
    app.include_router(outreach.router, prefix=prefix, tags=["outreach"])
    app.include_router(overview.router, prefix=prefix, tags=["overview"])
    return app


app = create_app()

__all__ = ["PUBLIC_PREFIXES", "app", "create_app"]
