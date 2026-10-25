"""Unified Celery application — registers every task from both engines onto
one app so a single worker consumes the `osint` and `visitor` queues."""
from __future__ import annotations

from celery import Celery

from osint_core.app.config import settings as osint_settings
from osint_core.app.workers.celery_app import celery as _osint_celery
from visitor_core.app.workers.celery_app import celery as _visitor_celery

celery = Celery(
    "slidein-unified",
    broker=osint_settings.celery_broker_url,
    backend=osint_settings.celery_result_backend,
)

celery.conf.update(
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,
    result_expires=86400,
    broker_connection_retry_on_startup=True,
    task_routes={
        "osint_core.app.workers.tasks.enrich_lead_task": {"queue": "osint"},
        "osint_core.app.workers.tasks.enrich_bulk_task": {"queue": "osint"},
        "visitor_core.app.workers.tasks.resolve_visitor_task": {"queue": "visitor"},
    },
)

_registered = set()
for _src in (_osint_celery, _visitor_celery):
    for _name, _task in _src.tasks.items():
        if _name.startswith("celery.") or _name in _registered:
            continue
        celery.tasks.register(_task)
        _registered.add(_name)

assert {"osint_core.app.workers.tasks.enrich_lead_task",
        "visitor_core.app.workers.tasks.resolve_visitor_task"} <= _registered, _registered
