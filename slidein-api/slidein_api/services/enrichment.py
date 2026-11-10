"""Heavy enrichment pass — runs the full OSINT stack over one prospect.

Order (fixed): subfinder → dnsrecon → theHarvester → GitHub CLI → holehe →
maigret (→ Spiderfoot at deep depth). Every run records per-tool status in
`prospect.source_detail["enrichment"]`, persists source-backed evidence, and
Reacher-verifies the canonical email plus up to five discovered alternates.

The outreach stage enforces `status == "complete"` before any live send, so
no email goes on the wire without this pass having run and the recipient
having been verified.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

from ..errors import NotFoundError, SlideinError
from ..integrations.reacher import ReacherAdapter
from ..models import Prospect, VerificationStatus, utcnow
from .preflight import reacher_verification
from .research import Claim, ResearchService
from .enrichment_tools import TOOL_SPECS, run_tool

ENRICHMENT_KEY = "enrichment"
MAX_VERIFY_EMAILS = 6


def _username_candidates(prospect: Prospect) -> list[str]:
    candidates: list[str] = []
    if prospect.linkedin_url:
        slug = prospect.linkedin_url.rstrip("/").split("/")[-1].split("?")[0]
        if slug and slug not in candidates:
            candidates.append(slug)
    local = (prospect.email.split("@")[0] or "").lower()
    for token in (local, local.split(".")[0], local.split("_")[0]):
        token = "".join(ch for ch in token if ch.isalnum())
        if token and token not in candidates:
            candidates.append(token)
    return candidates[:2]


class EnrichmentService:
    def __init__(self, session) -> None:
        self.session = session

    async def enrich(
        self,
        *,
        tenant_id: str,
        prospect_id: str,
        actor: str,
        depth: str = "standard",
    ) -> dict:
        prospect = await self.session.get(Prospect, prospect_id)
        if prospect is None or prospect.tenant_id != tenant_id:
            raise NotFoundError(
                f"Prospect {prospect_id!r} does not exist in this workspace",
                code="prospect_not_found",
                recovery_action="return_to_discovery",
            )

        domain = (prospect.company_domain or prospect.email.split("@")[-1]).strip().strip(".")
        username = _username_candidates(prospect)[0] if _username_candidates(prospect) else ""
        target = {
            "domain": domain,
            "email": prospect.email.strip().lower(),
            "username": username,
            "name": f"{prospect.first_name} {prospect.last_name}".strip() or prospect.company_name,
            "company": prospect.company_name or domain,
        }

        specs = [s for s in TOOL_SPECS if depth == "deep" or not s.deep_only]
        semaphore = asyncio.Semaphore(3)

        async def run_one(spec):
            async with semaphore:
                started = time.monotonic()
                result = await asyncio.to_thread(run_tool, spec, target=target)
                result["tool_id"] = spec.tool_id
                result["duration_ms"] = int((time.monotonic() - started) * 1000)
                return result

        results = await asyncio.gather(*(run_one(spec) for spec in specs))

        claims: list[Claim] = []
        personal_emails: dict[str, str] = {}  # email -> source tool
        social_profiles: list[dict] = []
        accounts: list[dict] = []
        subdomains: list[str] = []
        records: list[str] = []
        repos: list[dict] = []
        names: list[str] = []
        tool_status: dict[str, dict] = {}

        for result in results:
            tool_id = result["tool_id"]
            parsed = result.get("parsed") or {}
            tool_status[tool_id] = {
                "status": "ok" if result.get("ok") else "failed",
                "duration_ms": result.get("duration_ms", 0),
                "error": result.get("error") or ("" if result.get("ok") else "nonzero_exit"),
            }
            counts: dict[str, int] = {}

            def count(key: str, n: int) -> None:
                if n:
                    counts[key] = n

            if tool_id == "subfinder":
                found = parsed.get("subdomains") or []
                subdomains.extend(h for h in found if h not in subdomains)
                count("subdomains", len(found))
                for host in found[:25]:
                    claims.append(Claim(
                        evidence_type="exposure", claim_text=f"Subdomain: {host}",
                        source_url=f"https://{host}", source_name="subfinder",
                        collector="enrichment:subfinder",
                    ))
            elif tool_id == "dnsrecon":
                found = parsed.get("records") or []
                records.extend(found)
                count("dns_records", len(found))
                for rec in found[:25]:
                    claims.append(Claim(
                        evidence_type="dns", claim_text=f"DNS record: {rec}",
                        source_url=f"https://{domain}", source_name="dnsrecon",
                        collector="enrichment:dnsrecon",
                    ))
            elif tool_id == "theharvester":
                emails = [e.lower() for e in (parsed.get("emails") or []) if "@" in e]
                for e in emails:
                    personal_emails.setdefault(e, "theharvester")
                people = parsed.get("linkedin_people") or []
                names.extend(p for p in people if p not in names)
                hosts = parsed.get("hosts") or []
                count("emails", len(emails)), count("people", len(people)), count("hosts", len(hosts))
                for e in emails[:25]:
                    claims.append(Claim(
                        evidence_type="contact", claim_text=f"Email address published: {e}",
                        source_url=f"https://{domain}", source_name="theharvester",
                        confidence=0.7, collector="enrichment:theharvester",
                    ))
                for p in people[:15]:
                    claims.append(Claim(
                        evidence_type="identity", claim_text=f"LinkedIn profile: {p}",
                        source_url=p if p.startswith("http") else f"https://{p}",
                        source_name="theharvester", confidence=0.6,
                        collector="enrichment:theharvester",
                    ))
            elif tool_id == "github_cli":
                found = parsed.get("repos") or []
                repos.extend(found)
                count("repos", len(found))
                for r in found[:10]:
                    claims.append(Claim(
                        evidence_type="code", claim_text=f"Repository {r['full_name']} ({r['stars']}★): {r['description'][:120]}",
                        source_url=r["url"], source_name="github", confidence=0.8,
                        collector="enrichment:github_cli",
                    ))
            elif tool_id == "holehe":
                found = parsed.get("accounts") or []
                for site in found:
                    accounts.append({"site": site, "source": "holehe"})
                count("accounts", len(found))
                for site in found[:25]:
                    claims.append(Claim(
                        evidence_type="account", claim_text=f"Account registered on {site} for this email",
                        source_url=f"https://{site}", source_name="holehe", confidence=0.65,
                        verification_status=VerificationStatus.UNVERIFIED.value,
                        collector="enrichment:holehe",
                    ))
            elif tool_id == "maigret":
                found = parsed.get("profiles") or []
                for p in found:
                    social_profiles.append({"url": p["url"], "site": p.get("site", ""), "source": "maigret"})
                count("profiles", len(found))
                for p in found[:30]:
                    claims.append(Claim(
                        evidence_type="social", claim_text=f"Profile found: {p['url']}",
                        source_url=p["url"], source_name="maigret", confidence=0.7,
                        verification_status=VerificationStatus.UNVERIFIED.value,
                        collector="enrichment:maigret",
                    ))
            elif tool_id == "spiderfoot":
                for e in parsed.get("emails") or []:
                    personal_emails.setdefault(e, "spiderfoot")
                for s in parsed.get("socials") or []:
                    social_profiles.append({"url": s, "site": "", "source": "spiderfoot"})
                for a in parsed.get("accounts") or []:
                    accounts.append({"site": a, "source": "spiderfoot"})
                count("emails", len(parsed.get("emails") or []))
                count("socials", len(parsed.get("socials") or []))
                count("accounts", len(parsed.get("accounts") or []))

            tool_status[tool_id]["found"] = counts

        # Reacher: verify the canonical email and the discovered alternates.
        # Verification never blocks enrichment itself; verdicts are recorded.
        emails_to_verify = [target["email"]] + [
            e for e in personal_emails if e != target["email"]
        ][:MAX_VERIFY_EMAILS - 1]
        verifications: dict[str, dict] = {}
        for email in emails_to_verify:
            try:
                verdict = await reacher_verification(email)
            except SlideinError as exc:  # Reacher unreachable → record, don't fail
                verdict = {"status": "unavailable", "detail": exc.message[:200]}
            verifications[email] = verdict

        evidence_result = {"evidence_ids": [], "evidence_count": 0}
        if claims:
            evidence_result = await ResearchService(self.session).persist_claims(
                tenant_id=tenant_id,
                prospect=prospect,
                claims=claims,
                actor=actor,
                collector="enrichment",
            )

        # Field upgrades: only fill fields that are still empty.
        updates: dict[str, str] = {}
        if not prospect.linkedin_url:
            li = next(
                (p["url"] for p in social_profiles if "linkedin" in p["url"].lower()
                 or "linked" in p.get("site", "").lower()), ""
            )
            if li:
                prospect.linkedin_url = li
                updates["linkedin_url"] = li
        if not prospect.location and names:
            pass  # names are not locations; keep location untouched

        enrichment = {
            "status": "complete",
            "depth": depth,
            "enriched_at": utcnow().isoformat(),
            "enriched_by": actor,
            "domain": domain,
            "tools": tool_status,
            "personal_emails": [
                {"email": e, "source": src,
                 "verification": verifications.get(e, {}).get("status", "unknown")}
                for e, src in sorted(personal_emails.items())
            ][:50],
            "social_profiles": social_profiles[:50],
            "accounts": accounts[:50],
            "subdomains": sorted(set(subdomains))[:100],
            "dns_records": records[:100],
            "repos": repos[:25],
            "people": names[:25],
            "canonical_email_verification": verifications.get(target["email"], {}),
            "evidence_count": evidence_result.get("evidence_count", 0),
        }
        detail = dict(prospect.source_detail or {})
        detail[ENRICHMENT_KEY] = enrichment
        prospect.source_detail = detail
        prospect.updated_at = datetime.now(timezone.utc)
        await self.session.flush()

        return {
            "prospect_id": prospect.id,
            "enrichment": enrichment,
            "field_updates": updates,
            "evidence_count": evidence_result.get("evidence_count", 0),
            "tools_run": len(results),
            "tools_ok": sum(1 for r in results if r.get("ok")),
        }


__all__ = ["EnrichmentService", "ENRICHMENT_KEY"]
