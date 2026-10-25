"""Fault-tolerant async HTTP probe.

Design rules:
  * One request -> one fresh proxy identity (per-request rotation).
  * Hard per-attempt timeout; exponential backoff with jitter on transport errors.
  * A 404 (or any expected "not found" status) is a VALID outcome, not a retry.
  * Per-request errors never escape to the caller as exceptions unless every
    retry is exhausted — a single broken platform node must not stall a batch.

Every module (social, subdomains, OSINT adapters) funnels through `HttpProbe.get`.
"""
from __future__ import annotations

import asyncio
import random

import httpx

from ..config import settings
from .proxy import pool as _pool


class ProbeError(Exception):
    """All retry attempts exhausted."""

    def __init__(self, url: str, last: Exception | None = None, status: int | None = None):
        self.url, self.last, self.status = url, last, status
        super().__init__(f"probe failed {url} status={status} err={last}")


class HttpProbe:
    def __init__(self, proxy_pool=_pool):
        self._pool = proxy_pool

    def _client(self, proxy_url: str | None) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            proxy=proxy_url,
            timeout=httpx.Timeout(
                settings.request_timeout, connect=settings.connect_timeout
            ),
            headers={
                "User-Agent": random.choice(settings.user_agents),
                "Accept-Language": "en-US,en;q=0.9",
            },
            follow_redirects=True,
            verify=True,
        )

    async def get(
        self,
        url: str,
        *,
        headers: dict | None = None,
        accept_statuses: set[int] | None = None,
        retries: int | None = None,
    ) -> httpx.Response:
        """GET with retry. Raises ProbeError only when all attempts fail."""
        accept = accept_statuses or set(range(200, 300))
        attempts = retries if retries is not None else settings.max_retries
        last_exc: Exception | None = None
        last_status: int | None = None

        for attempt in range(1, attempts + 1):
            proxy_url = self._pool.acquire()
            try:
                async with self._client(proxy_url) as client:
                    resp = await client.get(url, headers=headers)
                if resp.status_code in accept:
                    self._pool.report(proxy_url, True)
                    return resp
                last_status = resp.status_code
                # Retryable statuses only; other 4xx fail fast (don't punish proxy).
                if resp.status_code != 429 and 400 <= resp.status_code < 500:
                    break
                self._pool.report(proxy_url, False)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_exc = exc
                self._pool.report(proxy_url, False)
            await asyncio.sleep(
                settings.backoff_base * (2 ** (attempt - 1)) + random.random()
            )

        raise ProbeError(url, last=last_exc, status=last_status)


probe = HttpProbe()
