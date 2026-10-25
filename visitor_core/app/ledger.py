"""Module B — LogSnag-style internal event ledger.

Mirrors LogSnag's event design (channel / event / icon / notify / tags) into:
  * an internal Redis-backed ledger (`visitor:ledger`, capped stream-like list)
    — the durable audit trail the dashboard can page through;
  * an optional live push to the real LogSnag API when LOGSNAG_TOKEN is set.

Pipeline steps emit: "Visitor Intercepted", "Session Stitched",
"Corporate Domain Isolated", "Fallback Triggered", "Identity Resolved".
"""
from __future__ import annotations

import json
import time

import httpx
import redis

from .config import settings

LEDGER_KEY = "visitor:ledger"
LEDGER_MAX = 5000


class EventLedger:
    def __init__(self):
        self._client: redis.Redis | None = None

    def _conn(self) -> redis.Redis:
        if self._client is None:
            self._client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        return self._client

    def log(self, channel: str, event: str, *, description: str = "",
            tags: dict | None = None, icon: str = "👁", notify: bool = False) -> None:
        record = {
            "channel": channel, "event": event, "description": description,
            "icon": icon, "tags": tags or {}, "ts": time.time(),
        }
        try:
            r = self._conn()
            pipe = r.pipeline()
            pipe.lpush(LEDGER_KEY, json.dumps(record))
            pipe.ltrim(LEDGER_KEY, 0, LEDGER_MAX - 1)
            pipe.execute()
        except redis.RedisError:
            pass  # ledger must never break the pipeline
        if settings.logsnag_token:
            self._push_logsnag(record)

    def recent(self, limit: int = 200) -> list[dict]:
        try:
            raw = self._conn().lrange(LEDGER_KEY, 0, limit - 1)
            return [json.loads(item) for item in raw]
        except (redis.RedisError, ValueError):
            return []

    def _push_logsnag(self, record: dict) -> None:
        """Best-effort mirror; exceptions swallowed (offline-safe)."""
        try:
            with httpx.Client(timeout=5) as client:
                client.post(
                    "https://api.logsnag.com/v1/log",
                    headers={
                        "Authorization": f"Bearer {settings.logsnag_token}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "project": settings.logsnag_project,
                        "channel": record["channel"],
                        "event": record["event"],
                        "description": record["description"],
                        "icon": record["icon"],
                        "tags": record["tags"],
                        "notify": record["event"] in ("Identity Resolved", "Fallback Triggered"),
                    },
                )
        except httpx.HTTPError:
            pass
