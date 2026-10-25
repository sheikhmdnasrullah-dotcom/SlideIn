"""FastAPI application factory.

Run:
    uvicorn app.main:create_app --factory --port 8500
(from the visitor_core directory, or visitor_core.app.main with cwd=saas)
"""
from __future__ import annotations

from fastapi import FastAPI

from .api import router


def create_app() -> FastAPI:
    app = FastAPI(
        title="visitor_core",
        version="0.1.0",
        description="Website visitor identity capture & CRM ingestion engine.",
    )

    @app.on_event("startup")
    async def _startup() -> None:
        from .db import init_db

        await init_db()

    app.include_router(router)
    return app


app = create_app()
