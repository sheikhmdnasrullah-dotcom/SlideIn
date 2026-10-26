"""Slidein API application factory."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from ..db import init_db
from .. import workspace_store as _workspace_store  # noqa: F401  (register tables on Base before create_all)
from ..errors import SlideinError
from .routes import auth, autopilot, config, factory, osint, outreach, overview, pipeline, setup, system, tools, workspace

logger = logging.getLogger("slidein.api")

PUBLIC_PREFIXES = ("/health", "/docs", "/redoc", "/openapi.json", "/v1/contracts")


async def _autopilot_loop(app: FastAPI) -> None:
    """Background agent loop: advances every workspace tick by tick.

    Started from the lifespan when `SLIDEIN_AUTOPILOT` is on (default).
    Individual ticks never raise; a crash only logs and retries next cycle.
    """
    from ..services.autopilot import AutopilotConfig, run_all_tenants

    cfg = AutopilotConfig.from_env()
    if not cfg.master_enabled:
        logger.info("autopilot loop disabled (SLIDEIN_AUTOPILOT=0)")
        return
    logger.info(
        "autopilot loop starting (interval=%ss batch=%s max_sends=%s ingest=%s)",
        cfg.interval_seconds, cfg.batch, cfg.max_sends, list(cfg.ingest_paths) or "none",
    )
    while True:
        try:
            results = await run_all_tenants(cfg)
            advanced = sum(1 for r in results.values() if r.get("status") == "ok")
            if results:
                logger.debug("autopilot tick: %s/%s workspaces advanced", advanced, len(results))
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — the loop outlives any single failure
            logger.exception("autopilot cycle failed")
        await asyncio.sleep(cfg.interval_seconds)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("slidein api starting")
    await init_db()
    autopilot_task: asyncio.Task | None = None
    try:
        from ..services.autopilot import AutopilotConfig

        if AutopilotConfig.from_env().master_enabled:
            autopilot_task = asyncio.create_task(_autopilot_loop(app))
    except Exception:  # noqa: BLE001 — never block API startup on the loop
        logger.exception("failed to start autopilot loop")
    try:
        yield
    finally:
        if autopilot_task is not None:
            autopilot_task.cancel()
            with suppress(asyncio.CancelledError):
                await autopilot_task
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
        status = 404 if exc.code in ("tenant_forbidden", "not_found", "prospect_not_found", "draft_not_found") else (
            403 if exc.code in ("not_authorized", "session_invalid") else 400
        )
        return JSONResponse(
            status_code=status,
            content=jsonable_encoder({"error": exc.to_dict()}),
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
            content=jsonable_encoder(content),
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
    @app.get("/healthz", tags=["system"], include_in_schema=False)
    async def root_health() -> dict:
        """Liveness probe, always public."""
        return {"status": "healthy", "service": "slidein-api", "version": "1.0.0"}

    prefix = "/v1"
    app.include_router(auth.router, prefix=prefix, tags=["auth"])
    app.include_router(system.router, prefix=prefix, tags=["system"])
    app.include_router(config.router, prefix=prefix, tags=["configuration"])
    app.include_router(pipeline.router, prefix=prefix, tags=["pipeline"])
    app.include_router(outreach.router, prefix=prefix, tags=["outreach"])
    app.include_router(osint.router, prefix=prefix, tags=["osint"])
    app.include_router(overview.router, prefix=prefix, tags=["overview"])
    app.include_router(factory.router, prefix=prefix, tags=["factory"])
    app.include_router(autopilot.router, prefix=prefix, tags=["autopilot"])
    app.include_router(workspace.router, prefix=prefix, tags=["workspace"])
    app.include_router(setup.router, prefix=prefix, tags=["setup"])
    app.include_router(tools.router, prefix=prefix, tags=["tools"])
    return app


app = create_app()

__all__ = ["PUBLIC_PREFIXES", "app", "create_app"]
