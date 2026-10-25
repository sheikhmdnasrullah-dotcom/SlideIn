"""Website Contact Scraper adapter (omkarcloud/website-email-contact-scraper).

Harvests company metadata slots from the corporate site: alternative contact
emails, support lines, and corporate social patterns.

Paths:
  * WEBSITE_SCRAPER_CMD set -> headless engine invocation (botasaurus-based
    scraper), JSON output parsed into slots.
  * Fallback -> JA3 fetch of `/`, `/contact`, `/about` with strict per-page
    timeouts; mailto:/tel: extraction and social-link pattern harvesting.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
from dataclasses import dataclass, field

from ..core.transport import Ja3ProbeShim, Ja3ProbeError

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
TEL_RE = re.compile(r"tel:(\+?[0-9][0-9 .()\-]{6,})")
SOCIAL_RE = re.compile(
    r"https?://(?:www\.)?(linkedin\.com/company/[\w\-]+|twitter\.com/[\w\-]+|"
    r"x\.com/[\w\-]+|facebook\.com/[\w\-]+|instagram\.com/[\w\-]+|github\.com/[\w\-]+)"
)


@dataclass
class ContactScrapeResult:
    emails: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)
    socials: list[str] = field(default_factory=list)
    pages: list[str] = field(default_factory=list)
    raw_html: str = ""
    company_name: str | None = None
    engine: str = "builtin-fetcher"

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


class WebsiteScraperAdapter:
    def __init__(self, transport: Ja3ProbeShim):
        self._transport = transport

    async def scrape(self, domain: str, on_unit=None) -> ContactScrapeResult:
        cmd = os.getenv("WEBSITE_SCRAPER_CMD", "")
        if cmd and shutil.which(cmd.split()[0]):
            result = await self._run_engine(cmd, domain)
            if result is not None:
                if on_unit:
                    await on_unit({"page": "engine", "emails": len(result.emails)})
                return result
        return await self._run_builtin(domain, on_unit)

    async def _run_engine(self, cmd: str, domain: str) -> ContactScrapeResult | None:
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd.split(), f"https://{domain}", "--json",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            )
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
            data = json.loads(out.decode())
        except (asyncio.TimeoutError, OSError, ValueError):
            return None
        return ContactScrapeResult(
            emails=list({e.lower() for e in data.get("emails", [])}),
            phones=data.get("phones", []),
            socials=data.get("socials", []),
            pages=data.get("pages", []),
            engine="website-scraper-engine",
        )

    async def _run_builtin(self, domain: str, on_unit) -> ContactScrapeResult:
        result = ContactScrapeResult()
        paths = ["/", "/contact", "/about"]
        for path in paths:
            url = f"https://{domain}{path}"
            try:
                resp = await self._transport.get(
                    url, accept_statuses={200}, timeout=15, retries=1
                )
                html = resp.text if resp.status_code == 200 else ""
            except Exception:
                html = ""
            if not html:
                continue
            if path == "/":
                result.raw_html = html[:200_000]
            result.pages.append(url)
            result.emails = sorted({*result.emails,
                                    *{e.lower() for e in EMAIL_RE.findall(html)
                                      if not e.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp"))}})
            result.phones = sorted({*result.phones, *{p.strip() for p in TEL_RE.findall(html)}})
            result.socials = sorted({*result.socials, *SOCIAL_RE.findall(html)})
            if on_unit:
                await on_unit({"page": path, "emails": len(result.emails),
                               "phones": len(result.phones)})
        return result
