"""Passive OSINT side-channel — Spiderfoot-core methodology.

Adapter classes, each isolated behind a small interface so a dead upstream or a
missing API key degrades that channel to empty instead of failing the run:

  BreachAdapter     data-leak registries (HaveIBeenPwned v3 API; key required,
                    graceful stub without one)
  CryptoAdapter     public cryptographic address mentions associated with the
                    domain/handle (BTC/ETH/LTC regex sweep over public search
                    results; Spiderfoot sfp_bitcoin/sfp_ethereum pattern)
  FilingsAdapter    historical corporate filings (SEC EDGAR full-text search —
                    free, no key)
  DarkWebAdapter    interface for darkweb mention engines (Ahmia/onion search).
                    Default NullAdapter returns [] — wire your engine here;
                    the pipeline contract stays stable.

OpenOSINT/MCP angle: each adapter exposes a typed `run(**params) -> dict`
contract — these are exactly the tools an MCP server would expose to an agent.
"""
from __future__ import annotations

import re
from typing import Protocol

from ..config import settings
from ..core.http import HttpProbe, ProbeError
from ..schemas import BreachExposure, FilingHit, OSINTSideChannel

BTC_RE = re.compile(r"\b(bc1[a-z0-9]{25,60}|[13][a-km-zA-HJ-NP-Z1-9]{25,34})\b")
ETH_RE = re.compile(r"\b0x[a-fA-F0-9]{40}\b")
LTC_RE = re.compile(r"\b(L[a-km-zA-HJ-NP-Z1-9]{26,33}|ltc1[a-z0-9]{25,60})\b")


class Adapter(Protocol):
    async def run(self, *, email: str, handle: str, domain: str) -> dict: ...


# --------------------------------------------------------------------------- #
class BreachAdapter:
    """HaveIBeenPwned v3 'breachedaccount'. Requires HIBP_API_KEY."""

    URL = "https://haveibeenpwned.com/api/v3/breachedaccount/{email}"

    def __init__(self, probe: HttpProbe):
        self._probe = probe

    async def run(self, *, email: str, handle: str, domain: str) -> dict:
        if not settings.hibp_api_key:
            return {"breach_count": 0, "breaches": [], "data_classes": [], "source": "hibp-stub"}
        try:
            resp = await self._probe.get(
                self.URL.format(email=email),
                headers={"hibp-api-key": settings.hibp_api_key},
                accept_statuses={200, 404},
            )
        except ProbeError:
            return {"breach_count": 0, "breaches": [], "data_classes": [], "source": "hibp-error"}
        if resp.status_code == 404:
            return {"breach_count": 0, "breaches": [], "data_classes": [], "source": "hibp"}
        import json

        rows = json.loads(resp.text)
        classes: set[str] = set()
        for row in rows:
            classes.update(row.get("DataClasses") or [])
        return {
            "breach_count": len(rows),
            "breaches": [r.get("Name") for r in rows],
            "data_classes": sorted(classes),
            "source": "hibp",
        }


# --------------------------------------------------------------------------- #
class CryptoAdapter:
    """Spiderfoot-style crypto address harvesting.

    Pulls public search-result snippets for `{domain} crypto wallet` and
    `{handle} bitcoin`, then sweeps them for address regexes. Passive: we only
    read what search engines already index.
    """

    def __init__(self, probe: HttpProbe):
        self._probe = probe

    async def run(self, *, email: str, handle: str, domain: str) -> dict:
        queries = [f'"{domain}" (bitcoin OR ethereum OR "crypto wallet")',
                   f'"{handle}" (btc OR eth OR wallet)']
        addresses: set[str] = set()
        for q in queries:
            for match in BTC_RE.findall(await self._ddg(q)):
                addresses.add(match if isinstance(match, str) else match[0])
            addresses.update(ETH_RE.findall(await self._ddg(q)))
            for match in LTC_RE.findall(await self._ddg(q)):
                addresses.add(match if isinstance(match, str) else match[0])
        return {"crypto_addresses": sorted(addresses)}

    async def _ddg(self, query: str) -> str:
        try:
            resp = await self._probe.get(
                "https://html.duckduckgo.com/html/?q=" + query.replace(" ", "+"),
                accept_statuses={200},
            )
            return resp.text
        except ProbeError:
            return ""


# --------------------------------------------------------------------------- #
class FilingsAdapter:
    """SEC EDGAR full-text search over historical corporate filings."""

    URL = "https://efts.sec.gov/LATEST/search-index?q={q}"
    HEADERS = {"User-Agent": "SlideinVenture-osint-core admin@slidein.example"}

    def __init__(self, probe: HttpProbe):
        self._probe = probe

    async def run(self, *, email: str, handle: str, domain: str) -> dict:
        company = domain.split(".")[0]
        try:
            resp = await self._probe.get(
                self.URL.format(q=f'"{company}"'),
                headers=self.HEADERS,
                accept_statuses={200},
            )
            import json

            data = json.loads(resp.text)
        except (ProbeError, ValueError):
            return {"filings": []}
        hits = []
        for h in (data.get("hits", {}).get("hits") or [])[:10]:
            src = h.get("_source", {})
            hits.append(FilingHit(
                accession=h.get("_id"),
                form_type=src.get("form"),
                filing_date=src.get("file_date"),
                snippet=src.get("display_names", [None])[0] if src.get("display_names") else None,
                url=f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany"
                    f"&CIK={src.get('cik')}" if src.get("cik") else None,
            ).model_dump())
        return {"filings": hits}


# --------------------------------------------------------------------------- #
class DarkWebAdapter:
    """Mention engine interface. Default = null object (no dark-web crawling in
    this repo). Swap in an Ahmia/OnionSearch-backed implementation by
    subclassing and overriding `run` — pipeline code does not change."""

    async def run(self, *, email: str, handle: str, domain: str) -> dict:
        return {"darkweb_mentions": []}


# --------------------------------------------------------------------------- #
class OSINTRecon:
    def __init__(self, probe: HttpProbe, adapters: list[Adapter] | None = None):
        self._adapters = adapters or [
            BreachAdapter(probe),
            CryptoAdapter(probe),
            FilingsAdapter(probe),
            DarkWebAdapter(),
        ]

    async def run(self, *, email: str, handle: str, domain: str, on_unit=None) -> OSINTSideChannel:
        import asyncio

        async def _safe(adapter: Adapter) -> dict:
            try:
                result = await adapter.run(email=email, handle=handle, domain=domain)
            except Exception:
                return {}  # adapters are strictly best-effort
            if on_unit is not None:
                await on_unit(type(adapter).__name__, bool(result))
            return result

        merged: dict = {}
        for result in await asyncio.gather(*[_safe(a) for a in self._adapters]):
            merged.update(result)

        return OSINTSideChannel(
            breach_exposure=BreachExposure(
                breach_count=merged.get("breach_count", 0),
                breaches=merged.get("breaches", []),
                data_classes=merged.get("data_classes", []),
                source=merged.get("source", "none"),
            ),
            crypto_addresses=merged.get("crypto_addresses", []),
            filings=[FilingHit(**f) for f in merged.get("filings", [])],
            darkweb_mentions=merged.get("darkweb_mentions", []),
        )
