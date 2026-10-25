"""Background workers: per-lead enrichment + bulk fan-out with event streaming.

Storage contract (Redis):
  result:{email}       -> JSON EnrichmentResult (TTL 30d)
  dossier:{email}      -> JSON UnifiedDossier slice (TTL 30d)
  job:{job_id}         -> hash {status,total,done,failed,created_at}
  job:{job_id}:lead:{email} -> per-lead status

Streaming contract (Redis Pub/Sub, see app/events/):
  Every lifecycle transition publishes an EventEnvelope to
  osint:events, osint:events:job:{job_id}, osint:events:lead:{email}.
"""
from __future__ import annotations

import asyncio
import json
import time
import traceback
import uuid

import redis

from ..config import settings
from ..core.pipeline import EnrichmentPipeline
from ..events.bus import EventPublisher
from ..events.models import EventEnvelope, LifecycleStatus, ModuleName, ModuleStatus
from .celery_app import celery

DOSSIER_TTL = 30 * 86400

_redis: redis.Redis | None = None


def _store() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    return _redis


def _publish(task_id: str, email: str, *, job_id: str | None = None,
             module: ModuleName = ModuleName.SPIDERFOOT,
             status: ModuleStatus = ModuleStatus.QUEUED,
             progress: float = 0.0, live: dict | None = None,
             logs: list[str] | None = None) -> None:
    EventPublisher.publish(EventEnvelope(
        task_id=task_id, job_id=job_id, lead_email=email,
        active_framework=module,
        lifecycle_status=LifecycleStatus.from_module_status(status),
        progress_percentage=progress, extracted_delta=live or {},
        error_logs=" | ".join(logs) if logs else None,
    ))


def _run_pipeline(email: str, task_id: str, job_id: str | None) -> dict:
    return asyncio.run(
        EnrichmentPipeline().enrich(email, task_id=task_id, job_id=job_id)
    ).model_dump(mode="json")


@celery.task(bind=True, soft_time_limit=settings.lead_soft_time_limit,
             time_limit=settings.lead_hard_time_limit, max_retries=2)
def enrich_lead_task(self, email: str, job_id: str | None = None) -> dict:
    store = _store()
    task_id = self.request.id or "unknown"
    _publish(task_id, email, job_id=job_id, status=ModuleStatus.QUEUED, logs=["lead queued"])
    if job_id:
        store.hset(f"job:{job_id}", f"lead:{email}", "running")
    try:
        payload = _run_pipeline(email, task_id, job_id)
        pipe = store.pipeline()
        pipe.setex(f"result:{email}", DOSSIER_TTL, json.dumps(payload))
        pipe.setex(f"dossier:{email}", DOSSIER_TTL,
                   json.dumps(payload["dossier"]))
        if job_id:
            pipe.hset(f"job:{job_id}", f"lead:{email}", "done")
            pipe.hincrby(f"job:{job_id}", "done", 1)
        pipe.execute()
        # agentic workflow: park the draft in the approval queue
        try:
            from ..workflows import engine as wf
            draft = (payload.get("agents") or {}).get("copywriter") or {}
            wf.mark_pending_approval(email, job_id,
                                     (draft.get("subject_lines") or [None])[0])
        except Exception:
            pass  # approval queue must never break the enrichment return path
        return payload
    except Exception as exc:
        tb = traceback.format_exc(limit=8)
        _publish(task_id, email, job_id=job_id,
                 module=ModuleName.AI_AGENT_REASONING,
                 status=ModuleStatus.FAILED, logs=[f"task exception: {tb}"])
        if job_id:
            pipe = store.pipeline()
            pipe.hset(f"job:{job_id}", f"lead:{email}", f"failed: {exc}")
            pipe.hincrby(f"job:{job_id}", "failed", 1)
            pipe.execute()
        raise self.retry(exc=exc, countdown=30) from exc


@celery.task(bind=True)
def enrich_bulk_task(self, emails: list[str]) -> str:
    """Fan a list out to per-lead tasks and track them under one job id."""
    store = _store()
    job_id = str(uuid.uuid4())
    store.hset(f"job:{job_id}", mapping={
        "status": "running", "total": len(emails), "done": 0, "failed": 0,
        "created_at": str(time.time()),
    })
    store.expire(f"job:{job_id}", DOSSIER_TTL)
    for email in emails:
        enrich_lead_task.apply_async(args=[email, job_id], queue="osint")
    return job_id
