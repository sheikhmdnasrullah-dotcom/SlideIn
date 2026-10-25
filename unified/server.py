"""Unified FastAPI server: mounts both engines' routers, serves the dashboard,
and exposes a merged firehose SSE stream (osint events + CRM events)."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse

from osint_core.app.api.routes import router as osint_router
from osint_core.app.api.streaming import router as osint_stream_router
from osint_core.app.events.bus import EventStream
from visitor_core.app.api import router as visitor_router
from visitor_core.app.events import CRMStream


def create_app() -> FastAPI:
    app = FastAPI(
        title="Slidein — Unified Enrichment + Visitor Engine",
        version="1.0.0",
        description="Lead enrichment matrix, visitor identity capture, agentic "
                    "drafts, approval workflow — one process.",
    )

    @app.on_event("startup")
    async def _startup() -> None:
        from visitor_core.app.db import init_db

        await init_db()

    app.include_router(osint_router)          # /api/v1/enrich, /result, /jobs, /approval…
    app.include_router(osint_stream_router)   # /api/v1/ws/*, /api/v1/stream/*
    app.include_router(visitor_router)        # /api/v1/capture/track, /crm/*, tracker.js…

    @app.get("/", response_class=HTMLResponse)
    async def dashboard() -> str:
        return (Path(__file__).parent / "dashboard.html").read_text(encoding="utf-8")

    @app.get("/stream/all")
    async def stream_all() -> StreamingResponse:
        """Merged firehose: every envelope from both engines, one SSE feed —
        the dashboard's single source of live truth."""

        async def gen():
            queue: asyncio.Queue = asyncio.Queue()

            async def pump(agen):
                try:
                    async for item in agen:
                        await queue.put(item)
                except Exception:
                    pass

            t1 = asyncio.create_task(pump(EventStream.subscribe()))
            t2 = asyncio.create_task(pump(CRMStream.subscribe()))
            try:
                while True:
                    yield f"data: {json.dumps(await queue.get())}\n\n"
            finally:
                t1.cancel()
                t2.cancel()

        return StreamingResponse(
            gen(), media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app


app = create_app()
