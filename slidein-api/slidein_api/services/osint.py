"""OSINT — enriches one prospect with OpenOSINT lookups.

The adapter (:mod:`slidein_api.integrations.openosint`) owns everything
about *running* the CLI; this service owns everything about *what a
prospect means* to it:

* :func:`targets_for` — picks the value each lookup runs against from the
  prospect record (company domain for dns/exposure, company or full name
  for github, the address itself for email, LinkedIn handle or email local
  part for username).
* :func:`claims_from_results` — turns successful lookups into claim dicts
  using the research stage's evidence conventions (verified claims carry a
  source URL; probes with no single source page are stored unverified).
* :class:`OSINTService` — persists those claims as `EvidenceItem` rows with
  collector ``openosint:<tool>``, so the research stage can mix them with
  website claims and still attribute every row to its collector.

Evidence policy: a failed lookup is reported, never invented. The stage
only fails when *every* requested lookup failed (`source_unavailable`,
retryable) — the same contract the research connectors follow.
"""

from __future__ import annotations

import re
from typing import Sequence
from urllib.parse import quote

from sqlalchemy import select

from ..errors import ProviderError, ValidationError
from ..ids import new_id
from ..integrations.openosint import (
    DEFAULT_LOOKUPS,
    LOOKUP_SPECS,
    MAX_CLAIM_CHARS,
    LookupResult,
    OpenOSINTAdapter,
)
from ..models import EvidenceItem, Prospect, VerificationStatus
from ..serialize import evidence as serialize_evidence
from .discovery import normalize_domain

_LINKEDIN_HANDLE_RE = re.compile(
    r"(?:linkedin\.com/in/|linkedin\.com/pub/)([A-Za-z0-9\-_%]+)", re.I
)

#: Collector prefix — every row this service writes starts with it.
COLLECTOR_PREFIX = "openosint"


def _domain_for(prospect: Prospect) -> str:
    domain = normalize_domain(prospect.company_domain or "")
    if domain:
        return domain
    if "@" in (prospect.email or ""):
        return normalize_domain(prospect.email.split("@")[-1])
    return ""


def _identity_for(prospect: Prospect) -> str:
    """What a GitHub search should run: the person, then the company.

    The CLI resolves an exact login first, then fuzzy-searches users —
    both are person-oriented, so a full name beats an org string.
    """
    first = (prospect.first_name or "").strip()
    last = (prospect.last_name or "").strip()
    full = f"{first} {last}".strip()
    if full:
        return full
    return (prospect.company_name or "").strip()


def _username_for(prospect: Prospect) -> str:
    """A handle sherlock can actually search: LinkedIn slug, else email local part."""
    link = (prospect.linkedin_url or "").strip()
    match = _LINKEDIN_HANDLE_RE.search(link)
    if match:
        return match.group(1)
    if "@" in (prospect.email or ""):
        return prospect.email.split("@")[0]
    return ""


def targets_for(prospect: Prospect, lookups: Sequence[str] | None = None) -> dict[str, str]:
    """Map each requested lookup to the target value for this prospect.

    Lookups with no usable field on the record are simply absent — the
    adapter reports them as "no target" so the response stays explicit.
    """
    selected = list(lookups) if lookups else list(DEFAULT_LOOKUPS)
    domain = _domain_for(prospect)
    identity = _identity_for(prospect)
    targets: dict[str, str] = {}
    for name in selected:
        if name not in LOOKUP_SPECS:
            continue
        if name in ("dns", "exposure"):
            if domain:
                targets[name] = domain
        elif name == "github":
            if identity:
                targets[name] = identity
        elif name == "email":
            if prospect.email:
                targets[name] = prospect.email
        elif name == "username":
            handle = _username_for(prospect)
            if handle:
                targets[name] = handle
    return targets


def _source_for(lookup: str, target: str, domain: str) -> tuple[str, str, str]:
    """(source_url, source_name, verification_status) for one lookup result.

    Direct reads of a single page are `verified` with that page as source.
    Cross-site probes (email/username) have no single source page, so they
    follow the SuppliedClaimsConnector convention: no URL → `unverified`.
    """
    if lookup in ("dns", "exposure") and domain:
        return f"https://{domain}", domain, VerificationStatus.VERIFIED.value
    if lookup == "github":
        if re.fullmatch(r"[A-Za-z0-9\-_.]+", target) and " " not in target:
            return f"https://github.com/{target}", "github.com", VerificationStatus.VERIFIED.value
        return (
            f"https://github.com/search?q={quote(target)}",
            "github.com",
            VerificationStatus.VERIFIED.value,
        )
    if lookup == "email" and domain:
        # The probe ran against many sites; the domain only anchors the claim.
        return "", f"openosint:email ({domain})", VerificationStatus.UNVERIFIED.value
    return "", f"openosint:{lookup}", VerificationStatus.UNVERIFIED.value


def claims_from_results(
    results: Sequence[LookupResult], prospect: Prospect
) -> list[dict]:
    """Successful lookups → claim dicts (research evidence conventions)."""
    domain = _domain_for(prospect)
    claims: list[dict] = []
    for result in results:
        if not result.ok:
            continue
        spec = LOOKUP_SPECS[result.lookup]
        source_url, source_name, verification = _source_for(
            result.lookup, result.target, domain
        )
        head = f"[openosint {result.tool}] {result.target}"
        body = "\n".join(result.lines)
        claim_text = f"{head}\n{body}"[:MAX_CLAIM_CHARS]
        claims.append(
            {
                "evidence_type": spec.evidence_type,
                "claim_text": claim_text,
                "source_url": source_url,
                "source_name": source_name,
                "confidence": spec.confidence,
                "verification_status": verification,
                "collector": f"{COLLECTOR_PREFIX}:{result.tool}",
            }
        )
    return claims


class OSINTService:
    """Runs OpenOSINT lookups for a prospect and files the evidence."""

    def __init__(self, session) -> None:
        self.session = session

    def adapter(self, *, allow_active: bool | None = None) -> OpenOSINTAdapter:
        return OpenOSINTAdapter(allow_active=allow_active)

    async def enrich_prospect(
        self,
        *,
        tenant_id: str,
        prospect: Prospect,
        lookups: Sequence[str] | None = None,
        allow_active: bool | None = None,
        actor: str = "operator",
    ) -> dict:
        """Run the requested lookups and persist their evidence rows.

        Returns the contract's outputs: the per-lookup run summaries plus
        the created evidence ids. Raises only when nothing usable came back.
        """
        selected = list(lookups) if lookups else list(DEFAULT_LOOKUPS)
        unknown = [name for name in selected if name not in LOOKUP_SPECS]
        if unknown:
            raise ValidationError(
                f"Unknown OpenOSINT lookup(s): {', '.join(sorted(unknown))}",
                code="prospect_invalid",
                details={"allowed": sorted(LOOKUP_SPECS)},
                recovery_action="fix_prospect_record",
            )

        targets = targets_for(prospect, selected)
        untargeted = [name for name in selected if name not in targets]
        if untargeted:
            raise ValidationError(
                "Prospect record is missing the fields these lookups need: "
                + ", ".join(sorted(untargeted)),
                code="prospect_invalid",
                details={"missing_lookups": sorted(untargeted)},
                recovery_action="fix_prospect_record",
            )

        results = await self.adapter(allow_active=allow_active).run_lookups(
            targets, selected, allow_active=allow_active
        )
        claims = claims_from_results(results, prospect)
        if not claims:
            raise ProviderError(
                "OpenOSINT produced no usable evidence for this prospect",
                code="source_unavailable",
                details={"lookups": [r.summary() for r in results]},
                recovery_action="retry_stage",
            )

        rows: list[EvidenceItem] = []
        for claim in claims:
            row = EvidenceItem(
                id=new_id("evidence"),
                tenant_id=tenant_id,
                prospect_id=prospect.id,
                evidence_type=claim["evidence_type"],
                claim_text=claim["claim_text"],
                source_url=claim["source_url"],
                source_name=claim["source_name"],
                confidence=claim["confidence"],
                verification_status=claim["verification_status"],
                collector=claim["collector"],
                retrieved_by=actor,
            )
            self.session.add(row)
            rows.append(row)
        await self.session.flush()

        verified = sum(
            1 for r in rows if r.verification_status == VerificationStatus.VERIFIED.value
        )
        return {
            "prospect_id": prospect.id,
            "collector": COLLECTOR_PREFIX,
            "lookups": [r.summary() for r in results],
            "evidence_ids": [r.id for r in rows],
            "evidence_count": len(rows),
            "verified_count": verified,
            "research_summary": {
                "evidence_types": sorted({r.evidence_type for r in rows}),
                "sources": sorted({r.source_name for r in rows if r.source_name}),
                "verified": verified,
                "total": len(rows),
            },
        }

    async def list_evidence(self, tenant_id: str, prospect_id: str) -> list[dict]:
        """Evidence rows this service created for the prospect."""
        rows = (
            await self.session.execute(
                select(EvidenceItem)
                .where(
                    EvidenceItem.tenant_id == tenant_id,
                    EvidenceItem.prospect_id == prospect_id,
                    EvidenceItem.collector.like(f"{COLLECTOR_PREFIX}%"),
                )
                .order_by(EvidenceItem.retrieved_at.asc())
            )
        ).scalars().all()
        return [serialize_evidence(row) for row in rows]


# ---------------------------------------------------------------------------
# Ad-hoc research — no prospect record, just a query string
# ---------------------------------------------------------------------------

#: Google dork templates (label, template), ported from OpenOSINT's
#: ``generate_dorks`` so the dashboard can offer clickable per-platform
#: searches without a SERP API key.
DORK_TEMPLATES: tuple[tuple[str, str], ...] = (
    ("Exact match", '"{target}"'),
    ("LinkedIn", '"{target}" site:linkedin.com'),
    ("X / Twitter", '"{target}" (site:x.com OR site:twitter.com)'),
    ("Facebook", '"{target}" site:facebook.com'),
    ("Instagram", '"{target}" site:instagram.com'),
    ("GitHub", '"{target}" site:github.com'),
    ("PDF files", '"{target}" filetype:pdf'),
    ("Profile pages", '"{target}" inurl:profile'),
    ("Resume / CV", '"{target}" resume OR cv'),
    ("Breach mentions", '"{target}" leaked OR breach OR dump'),
    ("Page titles", 'intitle:"{target}"'),
    ("Elsewhere", '"{target}" -site:linkedin.com -site:facebook.com'),
)

_GOOGLE_BASE = "https://www.google.com/search?q="

_EMAIL_QUERY_RE = re.compile(r"[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
_DOMAIN_QUERY_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9.-]*\.[A-Za-z]{2,}$")


def detect_target_type(query: str) -> str:
    """Classify a free-form query: ``email`` | ``domain`` | ``handle`` | ``name``."""
    q = (query or "").strip()
    if not q:
        return "name"
    if " " not in q and _EMAIL_QUERY_RE.fullmatch(q):
        return "email"
    if " " not in q and _DOMAIN_QUERY_RE.fullmatch(q):
        return "domain"
    if " " not in q:
        return "handle"
    return "name"


def default_lookups_for(target_type: str) -> tuple[str, ...]:
    """Passive-first lookup set for an ad-hoc query of this type."""
    if target_type == "email":
        return ("email", "username")  # both active — gated per call
    if target_type == "domain":
        return ("dns", "exposure")
    if target_type == "handle":
        return ("github", "username")
    return ("github",)  # name


def query_targets(query: str, target_type: str) -> dict[str, str]:
    """Map every lookup that applies to this query to its target value."""
    q = (query or "").strip()
    if target_type == "email":
        local, _, domain = q.partition("@")
        targets: dict[str, str] = {"email": q}
        if local:
            targets["username"] = local
        if domain:
            targets["dns"] = domain
            targets["exposure"] = domain
        return targets
    if target_type == "domain":
        return {"dns": q, "exposure": q}
    if target_type == "handle":
        return {"github": q, "username": q}
    return {"github": q}


def dorks_for(query: str) -> list[dict]:
    """Clickable Google search URLs for a query, one per platform template."""
    q = (query or "").strip()
    return [
        {
            "label": label,
            "url": f"{_GOOGLE_BASE}{quote(template.format(target=q), safe='')}",
        }
        for label, template in DORK_TEMPLATES
    ]


__all__ = [
    "COLLECTOR_PREFIX",
    "DORK_TEMPLATES",
    "OSINTService",
    "claims_from_results",
    "default_lookups_for",
    "detect_target_type",
    "dorks_for",
    "query_targets",
    "targets_for",
]
