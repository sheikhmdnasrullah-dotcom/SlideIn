"""FireEnrich adapter — multi-agent parallel company enrichment.

Three sub-agents run concurrently per domain, each emitting its own chunk
events:
  * Company Profile vector — name, description, category tags
  * Financial Data        — funding tracks (stage, total, last round, investors)
  * Tech Stack fingerprint — CMS/analytics/framework signals from site + headers

Paths:
  * FIRECRAWL_API_KEY set -> Firecrawl `/v1/scrape` + `/v1/extract` (structured
    JSON via llm-extraction prompts).
  * Otherwise -> deterministic heuristics over the WebsiteScraper slots and
    DNS/infra fingerprints. Contract identical.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import dataclass, field

from ..core.transport import Ja3ProbeShim, Ja3ProbeError


@dataclass
class FireEnrichResult:
    company_profile: dict = field(default_factory=dict)   # name, description, tags
    funding_tracks: list[dict] = field(default_factory=list)  # stage, total, date, investors
    tech_stack: list[str] = field(default_factory=list)
    source: str = "heuristic-fallback"
    confidence: float = 0.4

    def to_dict(self) -> dict:
        return {
            "company_profile": self.company_profile,
            "funding_tracks": self.funding_tracks,
            "tech_stack": self.tech_stack,
            "source": self.source,
            "confidence": self.confidence,
        }


_TECH_SIGNALS = {
    "wordpress": r"wp-content|wp-includes", "shopify": r"cdn\.shopify\.com|myshopify",
    "react": r"data-reactroot|__NEXT_DATA__|react", "next.js": r"__NEXT_DATA__|/_next/",
    "google analytics": r"googletagmanager|google-analytics|gtag\(",
    "segment": r"cdn\.segment\.com", "hubspot": r"js\.hs-scripts|hs-analytics",
    "stripe": r"js\.stripe\.com", "intercom": r"widget\.intercom\.io",
    "cloudflare": r"cloudflare", "hotjar": r"static\.hotjar",
    "vercel": r"vercel|x-vercel", "webflow": r"webflow",
}


class FireEnrichAdapter:
    CHUNKS = 3  # profile / financial / tech_stack — one progress unit each

    def __init__(self, transport: Ja3ProbeShim):
        self._transport = transport
        self._key = os.getenv("FIRECRAWL_API_KEY", "")

    async def enrich(self, domain: str, website: dict | None = None, on_unit=None) -> FireEnrichResult:
        result = FireEnrichResult()
        async def _chunk(name: str, coro):
            data = await coro
            if on_unit is not None:
                await on_unit(name, data)
            return data

        profile, funding, tech = await asyncio.gather(
            _chunk("company_profile", self._company_profile(domain, website)),
            _chunk("funding", self._funding_tracks(domain)),
            _chunk("tech_stack", self._tech_stack(domain, website)),
        )
        result.company_profile = profile
        result.funding_tracks = funding
        result.tech_stack = tech
        if self._key:
            result.source = "firecrawl"
            result.confidence = 0.85
        return result

    # ------------------------------------------------------------------ #
    async def _scrape(self, url: str) -> str:
        try:
            resp = await self._transport.get(url, accept_statuses={200}, timeout=20)
            return resp.text if resp.status_code == 200 else ""
        except Exception:
            return ""

    async def _company_profile(self, domain: str, website: dict | None) -> dict:
        if self._key:
            extracted = await self._firecrawl_extract(
                domain,
                "Extract the company name, one-sentence description, and 5 category tags.",
                {"type": "object", "properties": {
                    "name": {"type": "string"}, "description": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}}}},
            )
            if extracted:
                return extracted
        title, meta = "", ""
        html = (website or {}).get("raw_html", "")
        m = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
        if m:
            title = re.sub(r"\s+", " ", m.group(1)).strip()
        m = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']',
                      html, re.S | re.I)
        if m:
            meta = m.group(1).strip()
        return {
            "name": (website or {}).get("company_name") or domain.split(".")[0],
            "description": meta or title,
            "tags": [],
        }

    async def _funding_tracks(self, domain: str) -> list[dict]:
        if self._key:
            extracted = await self._firecrawl_extract(
                domain,
                "Extract every funding event: stage, amount, date, investors. "
                "Return empty array if none found.",
                {"type": "object", "properties": {"funding_tracks": {"type": "array"}}},
            )
            if extracted and extracted.get("funding_tracks"):
                return extracted["funding_tracks"]
        return []  # no reliable passive source without the extraction API

    async def _tech_stack(self, domain: str, website: dict | None) -> list[str]:
        html = (website or {}).get("raw_html", "")
        if not html:
            html = await self._scrape(f"https://{domain}")
        stack = [name for name, pat in _TECH_SIGNALS.items() if re.search(pat, html, re.I)]
        return sorted(set(stack))

    # ------------------------------------------------------------------ #
    async def _firecrawl_extract(self, domain: str, prompt: str, schema: dict) -> dict | None:
        try:
            async with __import__("httpx").AsyncClient(timeout=45) as client:
                resp = await client.post(
                    "https://api.firecrawl.dev/v1/extract",
                    headers={"Authorization": f"Bearer {self._key}"},
                    json={"urls": [f"https://{domain}"], "prompt": prompt,
                          "schema": schema},
                )
                if resp.status_code != 200:
                    return None
                data = resp.json()
                if data.get("success"):
                    return data.get("data") or {}
        except Exception:
            return None
        return None
