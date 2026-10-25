"""Strategic fallback layer — Retention.com commercial identity resolution.

Triggered only when: first-party context is unstitched AND the embedded
GeoIP lookup reports an anonymous/residential network. One proxy-routed
async HTTP call (JA3-spoofed curl_cffi + rotating residential SOCKS5) to the
Retention.com wrapper; returns normalized identity or None. All failures are
captured by the pipeline and surfaced as tier ANONYMOUS — never raised.
"""
from __future__ import annotations

import asyncio
import hashlib
import itertools
import json

from .config import settings


class RetentionFallback:
    def __init__(self):
        self._cycle = itertools.count()

    def _proxy(self) -> str | None:
        pool = settings.proxy_list
        if not pool:
            return None
        return pool[next(self._cycle) % len(pool)]

    async def resolve(self, *, ip: str, fingerprint_hash: str,
                      page_url: str, site_domain: str) -> dict | None:
        if not (settings.retention_api_url and settings.retention_api_key):
            return None
        payload = {
            "ip": ip, "fingerprint": fingerprint_hash,
            "page_url": page_url, "domain": site_domain,
            "request_id": hashlib.sha256(f"{ip}|{fingerprint_hash}".encode()).hexdigest()[:24],
        }
        proxy = self._proxy()
        try:
            from curl_cffi import AsyncSession
            async with AsyncSession(
                proxy=proxy, impersonate="chrome124",
                timeout=settings.fallback_timeout, verify=True,
            ) as session:
                resp = await session.post(
                    settings.retention_api_url,
                    headers={"Authorization": f"Bearer {settings.retention_api_key}",
                             "Content-Type": "application/json"},
                    data=json.dumps(payload),
                )
            if resp.status_code != 200:
                return None
            return self._normalize(resp.text)
        except Exception:
            return None

    @staticmethod
    def _normalize(body: str) -> dict | None:
        """Extract email / first / last / LinkedIn from the wrapper payload."""
        try:
            data = json.loads(body)
        except ValueError:
            return None
        prospect = data.get("prospect") or data.get("identity") or data
        email = prospect.get("email")
        if not email or "@" not in str(email):
            return None
        first = prospect.get("first_name") or prospect.get("firstName")
        last = prospect.get("last_name") or prospect.get("lastName")
        linkedin = prospect.get("linkedin_url") or prospect.get("linkedin") \
            or prospect.get("linkedinUrl")
        email = str(email).lower()
        return {
            "email": email,
            "first_name": first,
            "last_name": last,
            "linkedin_url": linkedin,
            "company_domain": email.split("@", 1)[1],
        }
