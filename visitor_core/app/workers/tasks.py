"""Worker task: resolve one tracked hit end-to-end."""
from __future__ import annotations

import asyncio

from ..pipeline import VisitorPipeline
from ..schemas import CRMEnvelope, CRMStatus, ResolutionTier, TrackPayload
from .celery_app import celery
from ..events import CRMPublisher


def _run(payload: TrackPayload, task_id: str, visitor_id: str | None,
         site_domain: str):
    return asyncio.run(
        VisitorPipeline().resolve(payload, task_id=task_id,
                                  visitor_id=visitor_id, site_domain=site_domain)
    )


@celery.task(bind=True, soft_time_limit=150, time_limit=180, max_retries=1)
def resolve_visitor_task(self, payload_dict: dict, *, site_domain: str = "") -> dict:
    task_id = self.request.id or "unknown"
    payload = TrackPayload(**payload_dict)
    try:
        record = _run(payload, task_id, payload_dict.get("_visitor_id"),
                      site_domain)
        return record.model_dump(mode="json")
    except Exception as exc:
        import traceback

        CRMPublisher.publish(CRMEnvelope(
            task_id=task_id, site_domain=site_domain,
            resolution_tier=ResolutionTier.ANONYMOUS,
            status=CRMStatus.COMPLETED,
            error_logs=traceback.format_exc(limit=8),
        ))
        raise self.retry(exc=exc, countdown=20) from exc
