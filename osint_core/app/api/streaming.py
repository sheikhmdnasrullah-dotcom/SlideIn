"""Real-time streaming endpoints — WebSocket and SSE.

Both transports carry the exact same EventEnvelope stream from Redis Pub/Sub;
choose per client capability. Frontend state is a faithful mirror of backend
state: every envelope the workers publish is forwarded verbatim.

  WS  /api/v1/ws/jobs/{job_id}
  WS  /api/v1/ws/leads/{email}          (URL-encode the @: %40)
  SSE /api/v1/stream/jobs/{job_id}
  SSE /api/v1/stream/leads/{email}
"""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from ..events.bus import EventStream

router = APIRouter(prefix="/api/v1")


async def _pump(ws: WebSocket, *, job_id: str | None = None, email: str | None = None):
    stop = asyncio.Event()
    try:
        async for env in EventStream.subscribe(job_id=job_id, email=email, stop=stop):
            await ws.send_json(env)
    except WebSocketDisconnect:
        pass
    finally:
        stop.set()


@router.websocket("/ws/jobs/{job_id}")
async def ws_job(ws: WebSocket, job_id: str):
    await ws.accept()
    await _pump(ws, job_id=job_id)


@router.websocket("/ws/leads/{email}")
async def ws_lead(ws: WebSocket, email: str):
    await ws.accept()
    await _pump(ws, email=email)


def _sse(job_id: str | None = None, email: str | None = None) -> StreamingResponse:
    async def gen():
        async for env in EventStream.subscribe(job_id=job_id, email=email):
            yield f"data: {json.dumps(env)}\n\n"

    return StreamingResponse(
        gen(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/stream/jobs/{job_id}")
async def sse_job(job_id: str):
    return _sse(job_id=job_id)


@router.get("/stream/leads/{email}")
async def sse_lead(email: str):
    return _sse(email=email)
