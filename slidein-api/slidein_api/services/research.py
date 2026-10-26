"""Research — collects source-backed evidence for one prospect.

Research never invents facts. Evidence comes from one of three connectors:

  * `WebsiteConnector` — fetches the prospect's public pages with a real
    HTTP request and extracts only what those pages actually contain.
  * `SuppliedClaimsConnector` — accepts claims already collected by an
    external connector (search API, internal enrichment feed) as long as
    each one carries its own source URL.
  * `openosint` — runs the OpenOSINT CLI's passive lookups (DNS, exposure,
    GitHub) through :class:`slidein_api.integrations.openosint.
    OpenOSINTAdapter` and files each tool's output as a claim; see
    `services/osint.py` for the target and claim mapping.

Every evidence row records the URL it came from, whether the claim was
read directly from that page (`verified`) or derived from it (`inferred`),
and the collector that produced it. If no connector can produce a claim,
the stage fails with `source_unavailable` (retryable) rather than
returning empty evidence.
"""

from __future__ import annotations

import gzip
import json
import re
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any, Iterable

from ..errors import ProviderError, SlideinError
from ..ids import new_id
from ..integrations.firecrawl import FirecrawlAdapter
from ..integrations.openosint import DEFAULT_LOOKUPS, OpenOSINTAdapter
from ..models import EvidenceItem, Prospect, VerificationStatus
from ..serialize import evidence
from .osint import claims_from_results, targets_for

USER_AGENT = "SlideinResearch/1.0 (+https://slidein.example/bot)"
REQUEST_TIMEOUT = 10.0


@dataclass
class Claim:
    """A candidate evidence row before it is persisted."""

    evidence_type: str
    claim_text: str
    source_url: str
    source_name: str = ""
    confidence: float = 1.0
    verification_status: str = VerificationStatus.VERIFIED.value
    collector: str = "website_connector"

    def to_dict(self) -> dict:
        return {
            "evidence_type": self.evidence_type,
            "claim_text": self.claim_text,
            "source_url": self.source_url,
            "source_name": self.source_name,
            "confidence": self.confidence,
            "verification_status": self.verification_status,
            "collector": self.collector,
        }


_TECH_SIGNATURES: tuple[tuple[str, str], ...] = (
    ("wp-content", "WordPress"),
    ("wp-includes", "WordPress"),
    ("cdn.shopify.com", "Shopify"),
    ("static.parastorage.com", "Wix"),
    ("assets.squarespace.com", "Squarespace"),
    ("webflow", "Webflow"),
    ("react", "React"),
    ("next-static", "Next.js"),
    ("nuxt", "Nuxt"),
    ("gatsby", "Gatsby"),
    ("js.hs-scripts.com", "HubSpot"),
    ("js.hsforms.net", "HubSpot"),
    ("static.hubspot.com", "HubSpot"),
    ("intercom", "Intercom"),
    ("segment.com/analytics.js", "Segment"),
    ("googletagmanager.com", "Google Tag Manager"),
    ("google-analytics.com", "Google Analytics"),
    ("plausible.io", "Plausible"),
    ("hotjar", "Hotjar"),
    ("stripe.com", "Stripe"),
    ("js.stripe.com", "Stripe"),
    ("recaptcha", "Google reCAPTCHA"),
    ("cloudflareinsights", "Cloudflare"),
    ("fbevents.js", "Meta Pixel"),
    ("t.co/i/adsct", "Twitter Ads"),
    ("linkedin.com/px", "LinkedIn Insight"),
)


class _PageParser(HTMLParser):
    """Extracts only what a page states about itself."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.meta_description = ""
        self.meta_generator = ""
        self.headings: list[str] = []
        self.paragraphs: list[str] = []
        self.asset_urls: list[str] = []
        self.job_links: list[str] = []
        self._capture: str | None = None
        self._depth_skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {k.lower(): (v or "") for k, v in attrs}
        if tag in ("script", "style"):
            self._capture = "skip"
            src = attributes.get("src", "")
            if src:
                self.asset_urls.append(src)
            return
        if tag in ("link", "img"):
            for key in ("href", "src"):
                if attributes.get(key):
                    self.asset_urls.append(attributes[key])
        if tag == "meta":
            name = attributes.get("name", "").lower()
            prop = attributes.get("property", "").lower()
            content = attributes.get("content", "")
            if name == "description" and content and not self.meta_description:
                self.meta_description = content.strip()
            if name == "generator" and content:
                self.meta_generator = content.strip()
        if tag in ("h1", "h2", "h3"):
            self._capture = "heading"
        if tag == "p":
            self._capture = "paragraph"
        if tag == "a":
            href = attributes.get("href", "")
            if re.search(r"/(jobs?|careers?|hiring|positions?)\b", href, re.I):
                self.job_links.append(href)

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style") and self._capture == "skip":
            self._capture = None
        elif tag in ("h1", "h2", "h3") and self._capture == "heading":
            self._capture = None
        elif tag == "p" and self._capture == "paragraph":
            self._capture = None

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if not text or self._capture is None:
            return
        if self._capture == "heading":
            self.headings.append(text[:300])
        elif self._capture == "paragraph":
            self.paragraphs.append(text[:600])


def _fetch(url: str) -> tuple[str, int]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
            "Accept-Encoding": "gzip",
        },
        method="GET",
    )
    context = ssl.create_default_context()
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT, context=context) as response:
        raw = response.read()
        if (response.headers.get("Content-Encoding") or "").lower() == "gzip":
            raw = gzip.decompress(raw)
        charset = response.headers.get_content_charset() or "utf-8"
        return raw.decode(charset, "replace"), response.status


class WebsiteConnector:
    """Fetches public pages and turns their content into claims."""

    name = "website_connector"

    def __init__(self, *, timeout: float = REQUEST_TIMEOUT, offline: bool = False) -> None:
        self.timeout = timeout
        self.offline = offline
        self.fetched_urls: list[str] = []

    def collect(self, prospect: Prospect, *, depth: str = "standard") -> list[Claim]:
        if self.offline:
            raise ProviderError(
                "Website connector is running in offline mode",
                code="source_unavailable",
                recovery_action="retry_stage",
            )
        domain = (prospect.company_domain or prospect.email.split("@")[-1]).strip().strip(".")
        if not domain:
            raise SlideinError(
                "Prospect has no company domain to research",
                code="prospect_invalid",
                recovery_action="fix_prospect_record",
            )

        paths = ["/"]
        if depth in ("standard", "deep"):
            paths += ["/about", "/about-us"]
        if depth == "deep":
            paths += ["/careers", "/jobs", "/pricing", "/services"]

        claims: list[Claim] = []
        for path in paths:
            url = f"https://{domain}{path}"
            try:
                html, status = _fetch(url)
            except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError) as exc:
                # One failing page is not a failing stage as long as the
                # homepage produced something.
                if path == "/":
                    continue
                continue
            if status >= 400:
                continue
            self.fetched_urls.append(url)
            claims.extend(self._claims_from(url, html, path))

        if not claims:
            raise ProviderError(
                f"No public page could be read for {domain!r}",
                code="source_unavailable",
                details={"domain": domain, "attempted": self.fetched_urls or [f"https://{domain}/"]},
                recovery_action="retry_stage",
            )
        return claims

    def _claims_from(self, url: str, html: str, path: str) -> list[Claim]:
        parser = _PageParser()
        try:
            parser.feed(html)
        except Exception:  # pragma: no cover - malformed html must not crash
            pass

        claims: list[Claim] = []
        if parser.title_parts and parser.title_parts[0]:
            claims.append(
                Claim(
                    evidence_type="website_claim",
                    claim_text=f"Page title: {parser.title_parts[0].strip()}",
                    source_url=url,
                    source_name=url.split("/")[2],
                )
            )
        if parser.meta_description:
            claims.append(
                Claim(
                    evidence_type="website_claim",
                    claim_text=f"Stated positioning: {parser.meta_description}",
                    source_url=url,
                    source_name=url.split("/")[2],
                )
            )
        if parser.meta_generator:
            claims.append(
                Claim(
                    evidence_type="tech_stack",
                    claim_text=f"Site built with {parser.meta_generator} (page-declared generator).",
                    source_url=url,
                    source_name=url.split("/")[2],
                    confidence=0.7,
                    verification_status=VerificationStatus.INFERRED.value,
                )
            )
        for heading in parser.headings[:6]:
            claims.append(
                Claim(
                    evidence_type="website_claim",
                    claim_text=f"Section heading on {path or '/'}: {heading}",
                    source_url=url,
                    source_name=url.split("/")[2],
                )
            )

        stack = self._detect_stack(parser.asset_urls, html)
        if stack:
            claims.append(
                Claim(
                    evidence_type="tech_stack",
                    claim_text="Detected technologies referenced by the page: "
                    + ", ".join(stack),
                    source_url=url,
                    source_name=url.split("/")[2],
                    confidence=0.65,
                    verification_status=VerificationStatus.INFERRED.value,
                )
            )

        if parser.job_links:
            unique = sorted(set(parser.job_links))[:8]
            claims.append(
                Claim(
                    evidence_type="hiring_signal",
                    claim_text=(
                        f"The site links to {len(unique)} hiring-related page(s) "
                        f"({', '.join(unique[:3])})."
                    ),
                    source_url=url,
                    source_name=url.split("/")[2],
                    confidence=0.8,
                    verification_status=VerificationStatus.INFERRED.value,
                )
            )
        return claims

    def _detect_stack(self, asset_urls: Iterable[str], html: str) -> list[str]:
        haystack = " ".join(asset_urls) + " " + html
        haystack = haystack.lower()
        found: list[str] = []
        for signature, label in _TECH_SIGNATURES:
            if signature in haystack and label not in found:
                found.append(label)
        return found[:8]


class SuppliedClaimsConnector:
    """Accepts claims already collected elsewhere.

    Used by the search/CSV connectors and by tests. A supplied claim is
    `verified` only if it declares a source URL; otherwise it is stored as
    `unverified` so downstream stages treat it as inference.
    """

    name = "supplied_claims"

    def collect(self, prospect: Prospect, *, claims: list[dict] | None = None, **_: Any) -> list[Claim]:
        result: list[Claim] = []
        for raw in claims or []:
            source_url = str(raw.get("source_url") or "").strip()
            claim_text = str(raw.get("claim_text") or "").strip()
            if not claim_text:
                continue
            verification = str(
                raw.get("verification_status") or VerificationStatus.VERIFIED.value
            )
            if not source_url and verification == VerificationStatus.VERIFIED.value:
                verification = VerificationStatus.UNVERIFIED.value
            result.append(
                Claim(
                    evidence_type=str(raw.get("evidence_type") or "website_claim"),
                    claim_text=claim_text,
                    source_url=source_url,
                    source_name=str(raw.get("source_name") or ""),
                    confidence=float(raw.get("confidence") or (1.0 if verification == "verified" else 0.5)),
                    verification_status=verification,
                    collector=str(raw.get("collector") or self.name),
                )
            )
        return result


CONNECTORS = {
    "website": WebsiteConnector,
    "supplied": SuppliedClaimsConnector,
}


class ResearchService:
    def __init__(self, session) -> None:
        self.session = session

    async def collect_evidence(
        self,
        *,
        tenant_id: str,
        prospect: Prospect,
        depth: str = "standard",
        supplied_claims: list[dict] | None = None,
        connector: str = "website",
        offline_connector: bool = False,
        actor: str = "operator",
    ) -> dict:
        """Persist evidence rows. Returns the contract's outputs."""
        claims: list[Claim] = []

        if supplied_claims:
            claims.extend(SuppliedClaimsConnector().collect(prospect, claims=supplied_claims))

        if connector == "openosint":
            results = await OpenOSINTAdapter().run_lookups(
                targets_for(prospect, list(DEFAULT_LOOKUPS)), list(DEFAULT_LOOKUPS)
            )
            for raw in claims_from_results(results, prospect):
                claims.append(Claim(**raw))
            if not claims:
                raise ProviderError(
                    "OpenOSINT produced no evidence for this prospect",
                    code="source_unavailable",
                    details={"lookups": [r.summary() for r in results]},
                    recovery_action="retry_stage",
                )
        elif connector in {"website", "firecrawl", "supplied"} or not supplied_claims:
            domain = (prospect.company_domain or prospect.email.split("@")[-1]).strip().strip(".")
            if connector == "firecrawl":
                try:
                    for raw in await FirecrawlAdapter().scrape(domain):
                        claims.append(Claim(**raw))
                except ProviderError:
                    if not claims:
                        website = WebsiteConnector(offline=offline_connector)
                        claims.extend(website.collect(prospect, depth=depth))
            elif connector in {"website", "supplied"}:
                try:
                    website = WebsiteConnector(offline=offline_connector)
                    claims.extend(website.collect(prospect, depth=depth))
                except ProviderError:
                    # Configured Firecrawl is the deterministic website fallback.
                    # With no key, preserve the original source_unavailable error.
                    if not claims and FirecrawlAdapter().api_key:
                        for raw in await FirecrawlAdapter().scrape(domain):
                            claims.append(Claim(**raw))
                    elif not claims:
                        raise
            else:
                raise SlideinError(
                    f"Unknown research connector {connector!r}",
                    code="source_unavailable",
                    recovery_action="retry_stage",
                )

        if not claims:
            raise ProviderError(
                "No research connector produced a claim",
                code="source_unavailable",
                recovery_action="retry_stage",
            )

        rows: list[EvidenceItem] = []
        for claim in claims:
            row = EvidenceItem(
                id=new_id("evidence"),
                tenant_id=tenant_id,
                prospect_id=prospect.id,
                evidence_type=claim.evidence_type,
                claim_text=claim.claim_text,
                source_url=claim.source_url,
                source_name=claim.source_name,
                confidence=round(claim.confidence, 2),
                verification_status=claim.verification_status,
                collector=claim.collector,
                retrieved_by=actor,
            )
            self.session.add(row)
            rows.append(row)
        await self.session.flush()

        verified = sum(
            1 for r in rows if r.verification_status == VerificationStatus.VERIFIED.value
        )
        return {
            "evidence_ids": [r.id for r in rows],
            "evidence_count": len(rows),
            "verified_count": verified,
            "collector": connector,
            "research_summary": {
                "evidence_types": sorted({r.evidence_type for r in rows}),
                "sources": sorted({r.source_name for r in rows if r.source_name}),
                "verified": verified,
                "total": len(rows),
            },
        }

    async def list_evidence(self, tenant_id: str, prospect_id: str) -> list[dict]:
        from sqlalchemy import select as _select

        rows = (
            await self.session.execute(
                _select(EvidenceItem)
                .where(
                    EvidenceItem.tenant_id == tenant_id,
                    EvidenceItem.prospect_id == prospect_id,
                )
                .order_by(EvidenceItem.retrieved_at.asc())
            )
        ).scalars().all()
        return [evidence(r) for r in rows]


def extract_json_ld(html: str) -> list[dict]:
    """Best-effort JSON-LD reader — used by connectors that need structured
    organization data."""
    blocks = re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html,
        re.S | re.I,
    )
    parsed: list[dict] = []
    for block in blocks:
        try:
            parsed.append(json.loads(block.strip()))
        except (ValueError, TypeError):
            continue
    return parsed
