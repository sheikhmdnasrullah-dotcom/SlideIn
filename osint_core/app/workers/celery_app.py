"""Celery application.

Worker settings chosen for long, unreliable, network-bound tasks:
  acks_late            — a worker crash re-queues the lead instead of losing it
  prefetch_multiplier=1— fair distribution across workers; no hoarding
  task_time_limit      — hard kill so a wedged lead can never park a slot
"""
from __future__ import annotations

from celery import Celery

from ..config import settings

# Resolve the task module path the same way this module was imported, so the
# worker works whether the package is mounted as `osint_core.app...` or `app...`.
_TASKS_MODULE = __name__.rsplit(".", 1)[0] + ".tasks"

celery = Celery(
    "osint_core",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[_TASKS_MODULE],
)

celery.conf.update(
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,
    task_default_queue="osint",
    task_routes={f"{_TASKS_MODULE}.*": {"queue": "osint"}},
    result_expires=86400,
    broker_connection_retry_on_startup=True,
)
