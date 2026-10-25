"""Redis Pub/Sub for the CRM live stream.

  osint:... channels belong to osint_core; visitor_core owns:
    visitor:crm:live           — global CRM firehose
    visitor:crm:site:{domain}  — per client-site stream
"""
from __future__ import annotations

import json

import redis
import redis.asyncio as aioredis

from .config import settings
from .schemas import CRMEnvelope

GLOBAL_CHANNEL = "visitor:crm:live"


def site_channel(site_domain: str) -> str:
    return f"visitor:crm:site:{site_domain.lower()}"


class CRMPublisher:
    _client: redis.Redis | None = None

    @classmethod
    def _conn(cls) -> redis.Redis:
        if cls._client is None:
            cls._client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        return cls._client

    @classmethod
    def publish(cls, env: CRMEnvelope) -> None:
        try:
            r = cls._conn()
            channels = [GLOBAL_CHANNEL]
            if env.site_domain:
                channels.append(site_channel(env.site_domain))
            payload = env.model_dump_json()
            for ch in channels:
                r.publish(ch, payload)
        except redis.RedisError:
            pass  # streaming is best-effort; the ledger is the source of truth


class CRMStream:
    @staticmethod
    async def subscribe(*, site_domain: str | None = None, stop=None):
        client = aioredis.from_url(settings.redis_url, decode_responses=True)
        channels = [site_channel(site_domain)] if site_domain else [GLOBAL_CHANNEL]
        try:
            pubsub = client.pubsub(ignore_subscribe_messages=True)
            await pubsub.subscribe(*channels)
            async for message in pubsub.listen():
                if stop is not None and stop.is_set():
                    break
                try:
                    yield json.loads(message["data"])
                except (ValueError, KeyError, TypeError):
                    continue
        finally:
            await client.aclose()
