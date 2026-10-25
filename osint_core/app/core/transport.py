"""curl_cffi transport with JA3/TLS fingerprint impersonation.

Why this exists next to the plain httpx probe (`core/http.py`):
httpx runs on a Python TLS stack whose JA3 signature is instantly flagged by
Cloudflare/DataDome-style WAFs and platform bot defenses. curl_cffi ships a
compiled libcurl-impersonate binding that presents a genuine Chrome TLS
fingerprint. Combined with per-request SOCKS5 residential rotation, platform
nodes see an ordinary residential Chrome session.

Same contract as HttpProbe: `get()` raises ProbeError only after all retries
are exhausted; expected "not found" statuses are returned, not retried.
"""
from __future__ import annotations

import asyncio
import random

from curl_cffi import AsyncSession
from curl_cffi.requests.errors import RequestsError

from ..config import settings
from .proxy import pool as _pool


class Ja3ProbeError(Exception):
    def __init__(self, url: str, last: Exception | None = None, status: int | None = None):
        self.url, self.last, self.status = url, last, status
        super().__init__(f"ja3 probe failed {url} status={status} err={last}")


class Ja3Transport:
    def __init__(self, proxy_pool=_pool, impersonate: str | None = None):
        self._pool = proxy_pool
        self._impersonate = impersonate or settings.curl_impersonate

    async def get(
        self,
        url: str,
        *,
        headers: dict | None = None,
        accept_statuses: set[int] | None = None,
        retries: int | None = None,
        timeout: float | None = None,
    ):
        """Returns (status, text). Raises Ja3ProbeError when retries exhaust."""
        accept = accept_statuses or set(range(200, 300))
        attempts = retries if retries is not None else settings.max_retries
        last_exc: Exception | None = None
        last_status: int | None = None

        for attempt in range(1, attempts + 1):
            proxy_url = self._pool.acquire()
            try:
                async with AsyncSession(
                    proxy=proxy_url,
                    impersonate=self._impersonate,
                    timeout=timeout or settings.request_timeout,
                    verify=True,
                ) as s:
                    resp = await s.get(url, headers=headers)
                if resp.status_code in accept:
                    self._pool.report(proxy_url, True)
                    return resp.status_code, resp.text
                last_status = resp.status_code
                if resp.status_code != 429 and 400 <= resp.status_code < 500:
                    break
                self._pool.report(proxy_url, False)
            except (RequestsError, asyncio.TimeoutError) as exc:
                last_exc = exc
                self._pool.report(proxy_url, False)
            await asyncio.sleep(
                settings.backoff_base * (2 ** (attempt - 1)) + random.random()
            )

        raise Ja3ProbeError(url, last=last_exc, status=last_status)


ja3 = Ja3Transport()


class Ja3ProbeShim:
    """Presents Ja3Transport through the HttpProbe interface so existing
    adapters (OSINT recon, BrightData) can ride the JA3 transport unchanged."""

    def __init__(self, transport: Ja3Transport | None = None):
        self._t = transport or ja3

    async def get(self, url: str, *, headers: dict | None = None,
                accept_statuses: set[int] | None = None, retries: int | None = None,
                timeout: float | None = None):
        from types import SimpleNamespace

        status, text = await self._t.get(
            url, headers=headers, accept_statuses=accept_statuses,
            retries=retries, timeout=timeout,
        )
        return SimpleNamespace(status_code=status, text=text)
