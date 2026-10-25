"""Redis Pub/Sub plumbing.

  * Workers (sync Celery context OR inside the asyncio pipeline): EventPublisher.
  * API (asyncio): EventStream.subscribe() async generator feeding WebSocket/SSE.

Channels:
  osint:events                      — global firehose (ops dashboards)
  osint:events:job:{job_id}         — one bulk batch
  osint:events:lead:{email}         — one lead, cross-job
"""
from __future__ import annotations

import json

import redis
import redis.asyncio as aioredis

from ..config import settings
from .models import EventEnvelope

GLOBAL_CHANNEL = "osint:events"


def job_channel(job_id: str) -> str:
    return f"osint:events:job:{job_id}"


def lead_channel(email: str) -> str:
    return f"osint:events:lead:{email.strip().lower()}"


class EventPublisher:
    """Sync client — safe to call from Celery workers and (briefly) inside the
    asyncio loop (a single RPUBLISH is microseconds; negligible vs probe I/O)."""

    _client: redis.Redis | None = None

    @classmethod
    def _conn(cls) -> redis.Redis:
        if cls._client is None:
            cls._client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        return cls._client

    @classmethod
    def publish(cls, env: EventEnvelope) -> None:
        payload = env.model_dump_json()
        try:
            r = cls._conn()
            channels = [GLOBAL_CHANNEL, lead_channel(env.lead_email)]
            if env.job_id:
                channels.append(job_channel(env.job_id))
            for ch in channels:
                r.publish(ch, payload)
        except redis.RedisError:
            pass  # event streaming is best-effort; never break the pipeline

    @classmethod
    def close(cls) -> None:
        if cls._client is not None:
            cls._client.close()
            cls._client = None


class EventStream:
    """Async subscriber used by the FastAPI streaming endpoints."""

    @staticmethod
    async def subscribe(
        *,
        job_id: str | None = None,
        email: str | None = None,
        stop=None,
    ):
        """Yields parsed EventEnvelope dicts until client disconnect (stop set).

        Subscribes to the SINGLE most specific channel (lead > job > global):
        the publisher writes every envelope to each applicable scope channel,
        so one subscription is complete — and never duplicated.
        """
        client = aioredis.from_url(settings.redis_url, decode_responses=True)
        if email:
            channels = [lead_channel(email)]
        elif job_id:
            channels = [job_channel(job_id)]
        else:
            channels = [GLOBAL_CHANNEL]
        try:
            pubsub = client.pubsub(ignore_subscribe_messages=True)
            await pubsub.subscribe(*channels)
            async for message in pubsub.listen():
                if stop is not None and stop.is_set():
                    break
                try:
                    yield json.loads(message["data"])
                except (ValueError, KeyError, TypeError):
                    continue  # malformed frame: never leak into the frontend
        finally:
            await client.aclose()
