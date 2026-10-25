"""Rotating SOCKS5 residential proxy pipeline.

One proxy = one identity. Every outbound probe acquires a fresh proxy from the
pool so per-IP rate limits, perimeter WAFs, and throttles never correlate
requests back to our infrastructure. Failed proxies are cooled down with
exponential backoff; the pool degrades to direct egress if empty (lab mode).

Usage:
    pool = ProxyPool.from_settings(settings)
    proxy_url = pool.acquire()          # -> "socks5://user:pass@host:port" or None
    ...perform request...
    pool.report(proxy_url, success=True/False)
"""
from __future__ import annotations

import asyncio
import itertools
import time
from dataclasses import dataclass

from ..config import settings as _settings


@dataclass
class _ProxyState:
    url: str
    failures: int = 0
    cooldown_until: float = 0.0


class ProxyPool:
    def __init__(self, urls: tuple[str, ...], cooldown_base: float = 30.0):
        self._states = [_ProxyState(url=u) for u in urls]
        self._cooldown_base = cooldown_base
        self._cycle = itertools.count()
        self._lock = asyncio.Lock()

    @classmethod
    def from_settings(cls, settings=None) -> "ProxyPool":
        s = settings or _settings
        return cls(tuple(s.proxy_list) if s.proxy_enabled else (), s.proxy_cooldown_base)

    @property
    def size(self) -> int:
        return len(self._states)

    def acquire(self) -> str | None:
        """Round-robin the pool, skipping proxies that are in cooldown."""
        if not self._states:
            return None
        n = len(self._states)
        now = time.monotonic()
        for _ in range(n):
            state = self._states[next(self._cycle) % n]
            if state.cooldown_until <= now:
                return state.url
        # All cooling down: return the least-punished one anyway (better than stalling).
        return min(self._states, key=lambda s: s.cooldown_until).url

    def report(self, url: str, success: bool) -> None:
        for state in self._states:
            if state.url == url:
                if success:
                    state.failures = 0
                    state.cooldown_until = 0.0
                else:
                    state.failures += 1
                    state.cooldown_until = time.monotonic() + self._cooldown_base * (
                        2 ** min(state.failures - 1, 5)
                    )
                return


# Process-wide singleton so every module shares one rotation cycle.
pool = ProxyPool.from_settings()
