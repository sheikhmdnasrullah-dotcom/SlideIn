"""FastAPI application factory.

Run:
    uvicorn app.main:create_app --factory --port 8400
"""
from __future__ import annotations

from fastapi import FastAPI

from .api.routes import router


def create_app() -> FastAPI:
    app = FastAPI(
        title="osint_core",
        version="0.1.0",
        description="Passive OSINT enrichment engine — email address to unified dossier.",
    )
    app.include_router(router)
    from .api import streaming

    app.include_router(streaming.router)
    return app


app = create_app()
