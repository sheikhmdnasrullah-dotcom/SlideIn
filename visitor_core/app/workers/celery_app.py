"""visitor_core Celery app.

`acks_late` + `prefetch_multiplier=1`: a worker death mid-resolution re-queues
the hit; hard time limit parks any wedged task. Pipeline itself is the final
safety net — it can never deadlock.
"""
from celery import Celery

from ..config import settings

celery = Celery(
    "visitor_core",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["visitor_core.app.workers.tasks"],
)

celery.conf.update(
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,
    task_default_queue="visitor",
    task_routes={"visitor_core.app.workers.tasks.*": {"queue": "visitor"}},
    result_expires=86400,
    broker_connection_retry_on_startup=True,
)
