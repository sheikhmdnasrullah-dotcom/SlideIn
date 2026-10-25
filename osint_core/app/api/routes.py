"""REST API surface.

  POST /api/v1/enrich          {email}           -> enqueue (or run sync in dev)
  POST /api/v1/enrich/bulk     {emails:[...]}    -> enqueue batch, returns job_id
  GET  /api/v1/jobs/{job_id}                     -> batch progress
  GET  /api/v1/dossier/{email}                   -> cached UnifiedDossier
  GET  /healthz
"""
from __future__ import annotations

import asyncio
import json

import redis
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr

from ..config import settings
from ..core.pipeline import EnrichmentPipeline
from ..schemas import EnrichmentResult, UnifiedDossier
from ..workers.tasks import enrich_bulk_task, enrich_lead_task

router = APIRouter(prefix="/api/v1")

_store: redis.Redis | None = None


def _redis() -> redis.Redis:
    global _store
    if _store is None:
        _store = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    return _store


class EnrichRequest(BaseModel):
    email: EmailStr
    sync: bool = False  # dev convenience: run inline instead of enqueueing


class BulkRequest(BaseModel):
    emails: list[EmailStr]
    chunk_size: int = 500
    name: str | None = None           # campaign label (agentic workflow)


class EnqueueResponse(BaseModel):
    job_id: str | None = None
    task_id: str | None = None
    status: str


class DecideRequest(BaseModel):
    action: str                       # approve | reject
    note: str = ""


@router.post("/enrich", response_model=EnqueueResponse)
async def enrich(req: EnrichRequest):
    if req.sync:
        result = await EnrichmentPipeline().enrich(str(req.email), task_id="inline-sync")
        _store_result(str(req.email), result.model_dump(mode="json"))
        return EnqueueResponse(status="succeeded-inline")

    if not _celery_reachable():
        raise HTTPException(503, "worker broker unreachable; use sync=true or start celery")
    task = enrich_lead_task.apply_async(args=[str(req.email)], queue="osint")
    return EnqueueResponse(task_id=task.id, status="queued")


@router.post("/enrich/bulk", response_model=EnqueueResponse)
async def enrich_bulk(req: BulkRequest):
    emails = [str(e) for e in req.emails]
    if not _celery_reachable():
        raise HTTPException(503, "worker broker unreachable")
    job_id = enrich_bulk_task.apply_async(args=[emails], queue="osint").get(timeout=10)
    if req.name:
        try:
            from ..workflows import engine as wf
            wf.create_campaign(req.name, job_id, len(emails))
            for e in emails:
                wf.init_lead(job_id, e)
        except redis.RedisError:
            pass  # campaign metadata is best-effort; enrichment is unaffected
    return EnqueueResponse(job_id=job_id, status="queued")


# --------------------------------------------------------------------------- #
# Agentic workflow: campaigns + approval queue (client-facing dashboard feeds)
# --------------------------------------------------------------------------- #
@router.get("/campaigns/{job_id}")
async def campaign_status(job_id: str):
    from ..workflows import engine as wf

    try:
        return wf.campaign_status(job_id)
    except redis.RedisError:
        raise HTTPException(503, "workflow store unreachable")


@router.get("/approval/queue")
async def approval_queue(limit: int = 100):
    from ..workflows import engine as wf

    try:
        return {"pending": wf.pending_queue(limit)}
    except redis.RedisError:
        raise HTTPException(503, "workflow store unreachable")


@router.post("/approval/{email}")
async def approval_decide(email: str, req: DecideRequest):
    from ..workflows import engine as wf

    try:
        return wf.decide(email, req.action, req.note)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except KeyError:
        raise HTTPException(404, "no approval record for this email")
    except redis.RedisError:
        raise HTTPException(503, "workflow store unreachable")


@router.get("/jobs/{job_id}")
async def job_status(job_id: str):
    data = _redis().hgetall(f"job:{job_id}")
    if not data:
        raise HTTPException(404, "job not found")
    total = int(data.get("total", 0))
    done = int(data.get("done", 0))
    failed = int(data.get("failed", 0))
    data["pending"] = total - done - failed
    if total and done + failed >= total:
        data["status"] = "completed" if failed == 0 else "completed_with_failures"
    return data


@router.get("/dossier/{email}", response_model=UnifiedDossier)
async def get_dossier(email: str):
    raw = _redis().get(f"dossier:{email}")
    if not raw:
        raise HTTPException(404, "no dossier for this email (enrich first)")
    return UnifiedDossier(**json.loads(raw))


@router.get("/result/{email}", response_model=EnrichmentResult)
async def get_result(email: str):
    """Full payload: dossier + module results + entity graph + agent outputs."""
    raw = _redis().get(f"result:{email}")
    if not raw:
        raise HTTPException(404, "no enrichment result for this email (enrich first)")
    return EnrichmentResult(**json.loads(raw))


@router.get("/healthz")
async def healthz():
    try:
        _redis().ping()
        redis_ok = True
    except redis.RedisError:
        redis_ok = False
    return {"status": "ok", "redis": redis_ok, "proxy_pool": len(settings.proxy_list)}


def _store_result(email: str, payload: dict) -> None:
    store = _redis()
    pipe = store.pipeline()
    pipe.setex(f"result:{email}", 30 * 86400, json.dumps(payload))
    pipe.setex(f"dossier:{email}", 30 * 86400, json.dumps(payload["dossier"]))
    pipe.execute()


def _celery_reachable() -> bool:
    try:
        from ..workers.celery_app import celery

        with celery.connection_for_write() as conn:
            conn.ensure_connection(max_retries=1)
        return True
    except Exception:
        return False
