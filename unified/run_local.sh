#!/bin/bash
# Run the full unified stack locally: Redis + one Celery worker (both queues)
# + one FastAPI server (both engines + dashboard at http://localhost:8400).
set -e
cd "$(dirname "$0")/.."

if [ -x .venv/bin/python ]; then PY=.venv/bin/python; else PY=python3; fi

if ! (echo PING | (exec 3<>/dev/tcp/127.0.0.1/6379 && echo -e "PING\r" >&3 && head -c 5 <&3) 2>/dev/null | grep -q PONG); then
  if command -v docker >/dev/null 2>&1; then
    docker start osint-redis >/dev/null 2>&1 || \
      docker run -d --name osint-redis -p 6379:6379 redis:7-alpine >/dev/null
    echo "redis: docker container 'osint-redis' up"
  else
    echo "WARNING: no local redis on :6379 and docker unavailable" >&2
  fi
fi

$PY -m celery -A unified.worker.celery worker -Q osint,visitor \
    --pool=threads --concurrency=8 --loglevel=info &
WORKER_PID=$!
trap 'kill $WORKER_PID 2>/dev/null' EXIT
echo "worker: celery pid $WORKER_PID (queues: osint, visitor)"

exec $PY -m uvicorn unified.server:app --host 0.0.0.0 --port "${PORT:-8400}"
