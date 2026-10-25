"""unified — single-process integration of osint_core + visitor_core.

One FastAPI server (all REST + WS/SSE routes from both engines + dashboard),
one Celery worker (both queues). Run via run_local.sh or:

    .venv/bin/celery -A unified.worker.celery worker -Q osint,visitor \
        --pool=threads --concurrency=8
    .venv/bin/uvicorn unified.server:app --host 0.0.0.0 --port 8400
"""
