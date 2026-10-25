"""REST + WS surface.

  POST /api/v1/capture/track     — RudderStack-style ingestion (fast 202 ack,
                                   worker does the resolution)
  GET  /api/v1/tracker.js        — client embed, templated per site_key
  GET  /api/v1/crm/visitors      — resolved visitor ledger (dashboard feed)
  GET  /api/v1/crm/visitors/{id} — one record
  GET  /api/v1/crm/ledger        — internal event ledger (LogSnag-style)
  WS   /api/v1/ws/crm/live       — live CRM envelopes (optional ?site= filter)
"""
from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse

from .db import get_visitor, list_visitors
from .events import CRMStream
from .ledger import EventLedger
from .schemas import CRMEnvelope, CRMStatus, ResolutionTier, TrackPayload
from .workers.tasks import resolve_visitor_task

router = APIRouter(prefix="/api/v1")


@router.post("/capture/track")
async def capture_track(payload: TrackPayload, request: Request):
    """Ingestion is fire-and-forget: validate, ack 202, hand off to Celery."""
    body = payload.model_dump(mode="json")
    body["_visitor_id"] = str(uuid.uuid4())
    try:
        resolve_visitor_task.apply_async(
            args=[body], kwargs={"site_domain": _site_domain(payload)},
            queue="visitor",
        )
    except Exception:
        # broker down — degrade to inline resolution rather than dropping the hit
        from .pipeline import VisitorPipeline

        asyncio.get_running_loop().create_task(
            VisitorPipeline().resolve(
                payload, task_id="inline-capture",
                visitor_id=body["_visitor_id"],
                site_domain=_site_domain(payload),
            )
        )
    return JSONResponse({"status": "accepted", "visitor_id": body["_visitor_id"]},
                        status_code=202)


def _site_domain(payload: TrackPayload) -> str:
    url = (payload.context.page or {}).get("url", "")
    if "://" in url:
        return url.split("://", 1)[1].split("/", 1)[0].lower()
    return payload.site_key


@router.get("/tracker.js")
async def tracker_js(site_key: str, api_origin: str | None = None):
    from pathlib import Path

    template = (Path(__file__).resolve().parent.parent / "tracker" / "snippet.js").read_text()
    origin = (api_origin or "").rstrip("/")
    script = (template
              .replace("__API_ORIGIN__", origin)
              .replace("__SITE_KEY__", site_key))
    return HTMLResponse(script, media_type="application/javascript")


@router.get("/crm/visitors")
async def crm_visitors(site: str | None = None, limit: int = 100):
    return {"visitors": await list_visitors(site_domain=site, limit=limit)}


@router.get("/crm/visitors/{visitor_id}")
async def crm_visitor(visitor_id: str):
    record = await get_visitor(visitor_id)
    if not record:
        return JSONResponse({"error": "not found"}, status_code=404)
    return record


@router.get("/crm/ledger")
async def crm_ledger(limit: int = 200):
    return {"events": EventLedger().recent(limit)}


@router.websocket("/ws/crm/live")
async def ws_crm_live(ws: WebSocket, site: str | None = None):
    await ws.accept()
    stop = asyncio.Event()
    try:
        async for env in CRMStream.subscribe(site_domain=site, stop=stop):
            await ws.send_json(env)
    except WebSocketDisconnect:
        pass
    finally:
        stop.set()
