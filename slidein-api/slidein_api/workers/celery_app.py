"""Celery configuration; PostgreSQL remains the workflow system of record."""

from __future__ import annotations

import os

from celery import Celery

from ..services.jobs import broker_url

celery_app = Celery(
    "slidein",
    broker=broker_url(),
    backend=os.getenv("SLIDEIN_CELERY_RESULT_BACKEND") or None,
    include=["slidein_api.workers.tasks"],
)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_default_queue="workflow",
    task_routes={
        "slidein.workers.execute_job": {"queue": "workflow"},
        "slidein.workers.scheduler_tick": {"queue": "control"},
    },
    beat_schedule={
        "slidein-durable-scheduler": {
            "task": "slidein.workers.scheduler_tick",
            "schedule": float(os.getenv("SLIDEIN_SCHEDULER_INTERVAL_SECONDS", "30")),
            "options": {"queue": "control"},
        }
    },
    broker_connection_retry_on_startup=True,
)

__all__ = ["celery_app"]
