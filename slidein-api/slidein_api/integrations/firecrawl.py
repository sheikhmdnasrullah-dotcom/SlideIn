"""Narrow Firecrawl scrape adapter for source-backed company research.

The adapter never turns provider failure into empty/mock success. Callers may
fall back to another connector, but must preserve the returned source URL.
Only public HTTPS company domains are accepted; arbitrary provider base URLs,
IPs, local hosts, credentials and non-HTTP schemes are rejected.
"""

from __future__ import annotations

import ipaddress
import os
import re
from urllib.parse import urlparse

import httpx

from ..errors import ProviderError, SlideinError

_DOMAIN = re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")


def public_company_url(domain: str) -> str:
    """Validate a company domain without performing DNS or network traffic."""
    value = domain.strip().lower().rstrip(".")
    if not _DOMAIN.fullmatch(value):
        raise SlideinError(
            "Research requires a valid public company domain",
            code="prospect_invalid",
            recovery_action="fix_prospect_record",
        )
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise SlideinError(
            "Private or local research targets are not allowed",
            code="prospect_invalid",
            recovery_action="fix_prospect_record",
        )
    if value == "localhost" or value.endswith((".localhost", ".local", ".internal")):
        raise SlideinError(
            "Private or local research targets are not allowed",
            code="prospect_invalid",
            recovery_action="fix_prospect_record",
        )
    return f"https://{value}/"


class FirecrawlAdapter:
    name = "firecrawl"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str = "https://api.firecrawl.dev",
        timeout: float = 30.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.getenv("FIRECRAWL_API_KEY", "").strip()
        self.base_url = base_url.rstrip("/")
        parsed = urlparse(self.base_url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Firecrawl base URL must be credentialed-free HTTPS")
        self.timeout = timeout
        self.client = client

    async def scrape(self, domain: str) -> list[dict]:
        if not self.api_key:
            raise ProviderError(
                "Firecrawl is not configured",
                code="source_unavailable",
                details={"missing": ["FIRECRAWL_API_KEY"]},
                recovery_action="configure_provider",
            )
        url = public_company_url(domain)
        owns_client = self.client is None
        client = self.client or httpx.AsyncClient(timeout=self.timeout)
        try:
            response = await client.post(
                f"{self.base_url}/v1/scrape",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"url": url, "formats": ["markdown"], "onlyMainContent": True},
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderError(
                "Firecrawl could not retrieve the company page",
                code="source_unavailable",
                details={"provider": self.name, "error_type": type(exc).__name__},
                recovery_action="retry_stage",
            ) from exc
        finally:
            if owns_client:
                await client.aclose()

        if not isinstance(payload, dict) or payload.get("success") is False:
            raise ProviderError(
                "Firecrawl returned an unsuccessful response",
                code="source_unavailable",
                details={"provider": self.name},
                recovery_action="retry_stage",
            )
        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        markdown = str(data.get("markdown") or "").strip()
        if not markdown:
            raise ProviderError(
                "Firecrawl returned no readable company content",
                code="source_unavailable",
                details={"provider": self.name, "source_url": url},
                recovery_action="retry_stage",
            )
        metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
        source_url = str(metadata.get("sourceURL") or url)
        if urlparse(source_url).scheme != "https":
            source_url = url
        return [{
            "evidence_type": "website_claim",
            "claim_text": f"Retrieved public page content:\n{markdown[:12000]}",
            "source_url": source_url,
            "source_name": urlparse(source_url).hostname or domain,
            "confidence": 1.0,
            "verification_status": "verified",
            "collector": self.name,
        }]


__all__ = ["FirecrawlAdapter", "public_company_url"]
