"""Lead enrichment orchestrator — 14-module recon matrix.

One email address in -> one EnrichmentResult out. Every module runs in strict
isolation (asyncio timeout inside `ProgressTracker.guard`); every chunk of
work broadcasts a live wire-schema event. After recon, the dossier is
assembled, the multi-hop entity graph is built, and the three-agent reasoning
cluster compiles the outreach draft.

Module order respects data dependencies:
  WebsiteScraper -> FireEnrich (needs site slots)
  Maigret -> Blackbird (handle candidates reuse the registry)
  Spiderfoot side-channel -> MailAccess -> Noimosiny (risk indexing chain)
  Holehe -> Bomkesh (footprint aggregation)
"""
from __future__ import annotations

import asyncio
import time

from ..agents.base import AgentContext
from ..agents.orchestrator import AgentOrchestrator
from ..core.email_parser import ParsedLead, parse_email
from ..core.http import HttpProbe
from ..core.progress import ProgressTracker
from ..core.transport import Ja3ProbeShim, Ja3Transport
from ..events.models import ModuleName, ModuleStatus
from ..integrations.brightdata import BrightDataAdapter
from ..integrations.fireenrich import FireEnrichAdapter, FireEnrichResult
from ..integrations.mailaccess import MailAccessResult, MailAccessRunner
from ..integrations.noimosiny import NoimosinyAdapter, NoimosinyResult
from ..integrations.website_scraper import ContactScrapeResult, WebsiteScraperAdapter
from ..modules.blackbird import BlackbirdResult, BlackbirdRunner
from ..modules.bomkesh import BomkeshResult, BomkeshRunner
from ..modules.dns_audit import DNSAuditor, tech_hints_from
from ..modules.holehe import HoleheRunner
from ..modules.osint_recon import OSINTRecon
from ..modules.openosint_tool import run_openosint
from ..modules.social import SocialEnumerator, gravatar_probe
from ..schemas import (
    CompanyIntelligence,
    EnrichmentResult,
    EntityGraph,
    GraphEdge,
    GraphNode,
    InfraRecon,
    ModuleResult,
    OSINTSideChannel,
    PersonalizationTokens,
    SocialFootprint,
    UnifiedDossier,
)

_MODULE_TIMEOUTS = {
    ModuleName.WEBSCRAPER: 90.0,
    ModuleName.FIREENRICH: 120.0,
    ModuleName.MAIGRET: 180.0,
    ModuleName.BLACKBIRD: 200.0,
    ModuleName.DNSRECON: 60.0,
    ModuleName.SUBFINDER: 150.0,
    ModuleName.SPIDERFOOT: 120.0,
    ModuleName.HOLEHE: 150.0,
    ModuleName.BOMKESH: 30.0,
    ModuleName.MAILACCESS: 200.0,
    ModuleName.NOIMOSINY: 60.0,
    ModuleName.BRIGHTDATA: 60.0,
}

_INTEREST_KEYWORDS = {
    "open source": "open-source", "kubernetes": "cloud-native", "devops": "DevOps",
    "machine learning": "ML/AI", "ai ": "ML/AI", "photography": "photography",
    "design": "design", "music": "music", "travel": "travel", "gaming": "gaming",
    "running": "running", "fitness": "fitness", "crypto": "crypto/web3",
    "bitcoin": "crypto/web3", "web3": "crypto/web3", "security": "security",
    "privacy": "privacy", "startup": "startups", "founder": "startups",
}


class EnrichmentPipeline:
    def __init__(self, probe: HttpProbe | None = None, ja3_transport: Ja3Transport | None = None):
        self._probe = probe or HttpProbe()
        self._ja3 = ja3_transport or Ja3Transport()
        shim = Ja3ProbeShim(self._ja3)
        self._social = SocialEnumerator(self._probe)
        self._dns = DNSAuditor()
        self._osint = OSINTRecon(shim)
        self._holehe = HoleheRunner()
        self._mailaccess = MailAccessRunner(self._ja3)
        self._brightdata = BrightDataAdapter(shim)
        self._webscraper = WebsiteScraperAdapter(shim)
        self._fireenrich = FireEnrichAdapter(shim)
        self._noimosiny = NoimosinyAdapter()
        self._blackbird = BlackbirdRunner(self._social)
        self._bomkesh = BomkeshRunner()

    async def enrich(self, email: str, *, task_id: str | None = None,
                     job_id: str | None = None) -> EnrichmentResult:
        t0 = time.monotonic()
        lead = parse_email(email)
        handle = lead.primary_handle
        tracker = self._tracker(task_id or "inline", job_id, email)

        n_sites = self._social.site_count
        n_candidates = min(len(lead.username_candidates), 4)
        plans: dict[ModuleName, int] = {
            ModuleName.WEBSCRAPER: 3,                 # /, /contact, /about
            ModuleName.FIREENRICH: FireEnrichAdapter.CHUNKS,
            ModuleName.MAIGRET: n_sites + 1,          # + gravatar
            ModuleName.BLACKBIRD: n_sites * n_candidates or 1,
            ModuleName.DNSRECON: 6 + self._dns.selector_count(),
            ModuleName.SUBFINDER: 4,                  # hosts added dynamically
            ModuleName.SPIDERFOOT: 4,                 # one chunk per adapter
            ModuleName.HOLEHE: HoleheRunner.total_units(),
            ModuleName.BOMKESH: 3,
            ModuleName.MAILACCESS: 4,
            ModuleName.NOIMOSINY: 1,
            ModuleName.BRIGHTDATA: 1,
            ModuleName.GRAPH: 1,
            ModuleName.AI_AGENT_REASONING: AgentOrchestrator.AGENT_UNITS,
        }
        tracker.set_plans(plans)

        module_meta: list[ModuleResult] = []
        store: dict[ModuleName, object] = {}

        async def _run(name: ModuleName, coro, empty, stats_fn=None):
            start = time.monotonic()
            result = await tracker.guard(
                name, coro, empty=empty,
                timeout_s=_MODULE_TIMEOUTS.get(name, 120.0),
            )
            module_meta.append(ModuleResult(
                name=name,
                status=tracker.status_of(name),
                duration_ms=int((time.monotonic() - start) * 1000),
                stats=stats_fn(result) if (stats_fn and result is not empty) else {},
            ))
            store[name] = result
            return result

        # ---------------------------------------------------- website slots
        async def _webscraper():
            async def _on_unit(hit: dict):
                await tracker.unit_done(ModuleName.WEBSCRAPER,
                                        live={"contact_scrape": hit})

            return await self._webscraper.scrape(lead.domain, on_unit=_on_unit)

        website: ContactScrapeResult = await _run(
            ModuleName.WEBSCRAPER, _webscraper, ContactScrapeResult(),
            stats_fn=lambda r: {"emails": len(r.emails), "pages": len(r.pages)},
        )

        # ---------------------------------------------------- fireenrich
        async def _fireenrich():
            async def _on_unit(chunk: str, data):
                await tracker.unit_done(ModuleName.FIREENRICH,
                                        live={f"fireenrich_{chunk}": data})

            return await self._fireenrich.enrich(
                lead.domain, website.to_dict(), on_unit=_on_unit
            )

        fireenrich: FireEnrichResult = await _run(
            ModuleName.FIREENRICH, _fireenrich, FireEnrichResult(),
            stats_fn=lambda r: {"tech_signals": len(r.tech_stack),
                                "funding_tracks": len(r.funding_tracks)},
        )

        # ---------------------------------------------------- maigret
        async def _maigret():
            async def _on_result(site_name: str, profile: dict):
                await tracker.unit_done(
                    ModuleName.MAIGRET,
                    live={"profile_check": {"site": site_name, **profile}},
                )

            footprint = await self._social.enumerate(handle, on_result=_on_result)
            gravatar = await gravatar_probe(self._probe, email)
            footprint.gravatar = gravatar
            if gravatar:
                for acct in gravatar.get("linked_accounts", []):
                    if acct.get("platform") and acct.get("url"):
                        footprint.profiles_found.append(_from_gravatar_account(acct))
            await tracker.unit_done(ModuleName.MAIGRET,
                                    live={"gravatar": bool(gravatar)})
            return footprint

        footprint: SocialFootprint = await _run(
            ModuleName.MAIGRET, _maigret, SocialFootprint(username_handle=handle),
            stats_fn=lambda r: {"platforms_checked": r.platforms_checked,
                                "profiles_found": len(r.profiles_found)},
        )

        # ---------------------------------------------------- blackbird
        async def _blackbird():
            async def _on_unit(hit: dict):
                await tracker.unit_done(ModuleName.BLACKBIRD,
                                        live={"blackbird_hit": hit})

            return await self._blackbird.run(lead.username_candidates, on_unit=_on_unit)

        blackbird: BlackbirdResult = await _run(
            ModuleName.BLACKBIRD, _blackbird, BlackbirdResult(),
            stats_fn=lambda r: {"hits": len(r.hits), "candidates": len(r.candidates)},
        )

        # ---------------------------------------------------- holehe
        async def _holehe():
            async def _on_unit(hit: dict):
                await tracker.unit_done(ModuleName.HOLEHE, live={"holehe_hit": hit})

            return await self._holehe.run(email, footprint, on_unit=_on_unit)

        holehe_hits: list[dict] = await _run(
            ModuleName.HOLEHE, _holehe, [],
            stats_fn=lambda r: {"registrations": len(r)},
        )

        # ---------------------------------------------------- dnsrecon
        async def _dnsrecon():
            async def _on_step(rtype: str, count: int):
                await tracker.unit_done(
                    ModuleName.DNSRECON,
                    live={"dns_record": {"type": rtype, "count": count}},
                )

            return await self._dns.audit(lead.domain, on_step=_on_step)

        dns_out = await _run(
            ModuleName.DNSRECON, _dnsrecon, ([], _empty_mail_auth(), []),
            stats_fn=lambda r: {"mx": len(r[0].mx), "dkim_selectors": len(r[1].dkim)},
        )
        dns_records, mail_auth, risks = dns_out

        # ---------------------------------------------------- subfinder
        async def _subfinder():
            def _extend_plan(hosts: list[str]):
                tracker.add_plan_units(ModuleName.SUBFINDER, len(hosts))

            async def _on_host(sub: dict):
                await tracker.unit_done(ModuleName.SUBFINDER, live={"subdomain": sub})

            return await _counted_subdomains(lead.domain, self._probe,
                                             _extend_plan, _on_host)

        subs_out = await _run(
            ModuleName.SUBFINDER, _subfinder, ([], []),
            stats_fn=lambda r: {"hosts": len(r[0]), "sources": r[1]},
        )
        subdomains, sources = subs_out

        tech_hints = sorted(set(
            tech_hints_from(dns_records.mx, dns_records.txt, dns_records.ns)
            + fireenrich.tech_stack
        ))
        infra = InfraRecon(
            domain=lead.domain,
            dns=dns_records,
            mail_auth=mail_auth,
            subdomains=subdomains,
            subdomain_sources=sources,
            deliverability_risks=risks,
            tech_hints=tech_hints,
            contact_emails=list(website.emails[:10]),
            social_links=list(website.socials[:10]),
        )

        # ---------------------------------------------------- spiderfoot
        async def _spiderfoot():
            async def _on_unit(adapter: str, contributed: bool):
                await tracker.unit_done(
                    ModuleName.SPIDERFOOT,
                    live={"adapter": adapter, "contributed": contributed},
                )

            return await self._osint.run(email=email, handle=handle,
                                         domain=lead.domain, on_unit=_on_unit)

        side: OSINTSideChannel = await _run(
            ModuleName.SPIDERFOOT, _spiderfoot, OSINTSideChannel(),
            stats_fn=lambda r: {"breaches": r.breach_exposure.breach_count,
                                "filings": len(r.filings),
                                "crypto": len(r.crypto_addresses)},
        )

        # ---------------------------------------------------- bomkesh
        async def _bomkesh():
            async def _on_unit(slot: dict):
                await tracker.unit_done(ModuleName.BOMKESH, live={"bomkesh": slot})

            return await self._bomkesh.run(
                email=email, handle=handle, holehe_hits=holehe_hits,
                footprint_profiles=[p.model_dump() for p in footprint.profiles_found],
                breach_names=side.breach_exposure.breaches, on_unit=_on_unit,
            )

        bomkesh: BomkeshResult = await _run(
            ModuleName.BOMKESH, _bomkesh, BomkeshResult(),
            stats_fn=lambda r: {"slots": len(r.email_registrations)
                                + len(r.handle_footprint)},
        )

        # ---------------------------------------------------- mailaccess
        async def _mailaccess():
            async def _on_unit(hit: dict):
                await tracker.unit_done(ModuleName.MAILACCESS,
                                        live={"mailaccess": hit})

            result = await self._mailaccess.run(
                email, side.breach_exposure, on_unit=_on_unit
            )
            tracker.add_plan_units(ModuleName.MAILACCESS,
                                   max(result.sampled - plans[ModuleName.MAILACCESS], 0))
            return result

        mailaccess: MailAccessResult = await _run(
            ModuleName.MAILACCESS, _mailaccess, MailAccessResult(),
            stats_fn=lambda r: {"risk_score": r.risk_score, "risk_level": r.risk_level},
        )

        # ---------------------------------------------------- noimosiny
        async def _noimosiny():
            async def _on_unit(hit: dict):
                await tracker.unit_done(ModuleName.NOIMOSINY, live=hit)

            return await self._noimosiny.run(
                email, handle, side.breach_exposure,
                mailaccess.to_dict(), on_unit=_on_unit,
            )

        noimosiny: NoimosinyResult = await _run(
            ModuleName.NOIMOSINY, _noimosiny, NoimosinyResult(),
            stats_fn=lambda r: {"risk_index": r.risk_index, "level": r.level},
        )

        # ---------------------------------------------------- brightdata
        async def _brightdata():
            async def _on_unit(hit: dict):
                await tracker.unit_done(ModuleName.BRIGHTDATA, live=hit)

            return await self._brightdata.enrich_company(lead.domain, on_unit=_on_unit)

        company: CompanyIntelligence = await _run(
            ModuleName.BRIGHTDATA, _brightdata,
            CompanyIntelligence(domain=lead.domain),
            stats_fn=lambda r: {"confidence": r.confidence},
        )

        # ---------------------------------------------------- dossier
        # Fold FireEnrich company vectors into CompanyIntelligence so the dossier
        # carries website-derived tech + funding, not just the BrightData slice.
        company.tech_stack = sorted(set(company.tech_stack + fireenrich.tech_stack))
        if not company.funding_stage and fireenrich.funding_tracks:
            company.funding_stage = fireenrich.funding_tracks[0].get("stage")
        if not company.total_funding and fireenrich.funding_tracks:
            company.total_funding = (
                fireenrich.funding_tracks[0].get("amount")
                or fireenrich.funding_tracks[0].get("total")
            )
        if not company.name and fireenrich.company_profile.get("name"):
            company.name = fireenrich.company_profile["name"]
        if not company.industry and fireenrich.company_profile.get("industry"):
            company.industry = fireenrich.company_profile["industry"]
        company.confidence = max(company.confidence, fireenrich.confidence)

        tokens = build_personalization_tokens(lead, footprint, infra, side)
        dossier = UnifiedDossier(
            lead_email=email,
            domain=lead.domain,
            username_handle=handle,
            enrichment_duration_ms=int((time.monotonic() - t0) * 1000),
            individual_social_footprint=footprint,
            corporate_infrastructure_recon=infra,
            personalization_tokens=tokens,
            osint_side_channel=side,
            errors=[],
        )

        # ---------------------------------------------------- entity graph
        await tracker.set_state(ModuleName.GRAPH, ModuleStatus.PIPELINING_GRAPH)
        graph = build_entity_graph(
            lead, footprint, infra, side, company, mailaccess, holehe_hits,
            website, fireenrich, blackbird,
        )
        await tracker.unit_done(
            ModuleName.GRAPH,
            live={"graph_nodes": len(graph.nodes), "graph_edges": len(graph.edges)},
        )
        module_meta.append(ModuleResult(
            name=ModuleName.GRAPH, status=ModuleStatus.COMPLETED,
            duration_ms=0,
            stats={"nodes": len(graph.nodes), "edges": len(graph.edges)},
        ))

        # ---------------------------------------------------- agent cluster
        # OpenOSINT CLI bridge (passive dns/exposure/github) — quiet by
        # design: no wire ModuleName, failures degrade to an empty payload
        # so the agent cluster always runs.
        try:
            openosint = await asyncio.wait_for(
                run_openosint(email=email, handle=handle, domain=lead.domain),
                timeout=180.0,
            )
        except Exception:
            openosint = {"available": False, "source": "openosint-cli", "lookups": []}

        extras = {
            "fireenrich": fireenrich.to_dict(),
            "website": {k: v for k, v in website.to_dict().items() if k != "raw_html"},
            "blackbird": blackbird.to_dict(),
            "noimosiny": noimosiny.to_dict(),
            "bomkesh": bomkesh.to_dict(),
            "openosint": openosint,
        }
        agent_ctx = AgentContext(
            lead_email=email, parsed=lead, footprint=footprint, infra=infra,
            side=side, dossier=dossier, company=company,
            mailaccess=mailaccess.to_dict(), extras=extras,
        )
        agents: dict = await tracker.guard(
            ModuleName.AI_AGENT_REASONING,
            lambda: AgentOrchestrator(tracker).run(agent_ctx),
            empty={}, timeout_s=240.0,
        )
        module_meta.append(ModuleResult(
            name=ModuleName.AI_AGENT_REASONING,
            status=tracker.status_of(ModuleName.AI_AGENT_REASONING),
            duration_ms=0,
            stats={"agents_completed": sum(1 for v in agents.values() if v)},
        ))

        result = EnrichmentResult(
            task_id=task_id or "inline",
            job_id=job_id,
            lead_email=email,
            duration_ms=int((time.monotonic() - t0) * 1000),
            dossier=dossier,
            modules=module_meta,
            company_intel=company,
            mailaccess=mailaccess.to_dict(),
            website=extras["website"],
            fireenrich=extras["fireenrich"],
            blackbird=extras["blackbird"],
            noimosiny=extras["noimosiny"],
            bomkesh=extras["bomkesh"],
            graph=graph,
            agents=agents,
        )
        await tracker.finalize(live={
            "lead": email,
            "modules_completed": sum(
                1 for m in module_meta if m.status is ModuleStatus.COMPLETED
            ),
        })
        return result

    # ------------------------------------------------------------------ #
    def _tracker(self, task_id: str, job_id: str | None, email: str) -> ProgressTracker:
        try:
            return ProgressTracker(task_id=task_id, job_id=job_id, lead_email=email)
        except Exception:
            return ProgressTracker.noop()


# --------------------------------------------------------------------------- #
# Subdomain helper that reports discovered host count before resolution
# --------------------------------------------------------------------------- #
async def _counted_subdomains(domain, probe, on_discovered, on_host):
    from ..modules import subdomains as sub_mod

    collected: set[str] = set()
    sources_used: list[str] = []
    tasks = {
        "crt.sh": sub_mod._from_crtsh(domain, probe),
        "bufferover": sub_mod._from_bufferover(domain, probe),
        "hackertarget": sub_mod._from_hackertarget(domain, probe),
        "subfinder": sub_mod._from_subfinder(domain),
    }
    results = await asyncio.gather(*tasks.values(), return_exceptions=True)
    for name, result in zip(tasks.keys(), results):
        if isinstance(result, set) and result:
            sources_used.append(name)
            collected |= result
    hosts = sub_mod._normalize(collected, domain)
    on_discovered(hosts)
    resolved = await sub_mod._resolve_all(hosts, on_host=on_host)
    return resolved, sources_used


# --------------------------------------------------------------------------- #
# Entity graph
# --------------------------------------------------------------------------- #
def build_entity_graph(lead: ParsedLead, footprint: SocialFootprint, infra: InfraRecon,
                       side: OSINTSideChannel, company: CompanyIntelligence,
                       mailaccess: MailAccessResult, holehe_hits: list[dict],
                       website: ContactScrapeResult | None = None,
                       fireenrich: FireEnrichResult | None = None,
                       blackbird: BlackbirdResult | None = None) -> EntityGraph:
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []

    def node(node_id: str, ntype: str, label: str, **attrs):
        nodes.append(GraphNode(id=node_id, type=ntype, label=label, attributes=attrs))

    def edge(src: str, dst: str, rel: str):
        edges.append(GraphEdge(source=src, target=dst, relation=rel))

    person_id = f"person:{lead.email}"
    node(person_id, "person", lead.email)
    node(f"handle:{lead.primary_handle}", "handle", lead.primary_handle)
    node(f"domain:{lead.domain}", "domain", lead.domain)
    edge(person_id, f"handle:{lead.primary_handle}", "uses")
    edge(person_id, f"domain:{lead.domain}", "resolves_to")

    company_id = f"company:{company.name or lead.domain}"
    node(company_id, "company", company.name or lead.domain,
         industry=company.industry, funding_stage=company.funding_stage)
    edge(company_id, f"domain:{lead.domain}", "owns")

    for p in footprint.profiles_found:
        if not p.exists:
            continue
        pid = f"profile:{p.platform}:{p.username or ''}"
        node(pid, "profile", f"{p.platform}/{p.username or ''}",
             url=p.url, confidence=p.confidence)
        edge(person_id, pid, "has_profile")

    for h in holehe_hits:
        if not h.get("registered"):
            continue
        hid = f"registration:{h.get('site')}"
        node(hid, "registration", str(h.get("site")))
        edge(person_id, hid, "registered_on")

    for mx in infra.dns.mx:
        mid = f"mx:{mx}"
        node(mid, "mx", mx)
        edge(f"domain:{lead.domain}", mid, "mails_via")

    for s in infra.subdomains:
        sid = f"sub:{s.host}"
        node(sid, "subdomain", s.host, env=s.environment_hint, a=s.a)
        edge(f"domain:{lead.domain}", sid, "hosts")

    for addr in side.crypto_addresses:
        aid = f"addr:{addr}"
        node(aid, "address", addr[:16] + "…", full=addr)
        edge(f"domain:{lead.domain}", aid, "exposed_in")

    if website is not None:
        for e in website.emails[:5]:
            cid = f"contact:{e}"
            node(cid, "contact", e)
            edge(f"domain:{lead.domain}", cid, "lists")
        for soc in website.socials[:5]:
            sid = f"social:{soc}"
            node(sid, "social", soc)
            edge(f"domain:{lead.domain}", sid, "links")

    if fireenrich is not None:
        for i, tr in enumerate(fireenrich.funding_tracks[:5]):
            fid = f"funding:{i}"
            node(fid, "funding", tr.get("stage", "round"),
                 amount=tr.get("amount"), date=tr.get("date"))
            edge(company_id, fid, "raised")

    return EntityGraph(nodes=nodes, edges=edges)


# --------------------------------------------------------------------------- #
# Personalization tokens
# --------------------------------------------------------------------------- #
def build_personalization_tokens(lead: ParsedLead, footprint: SocialFootprint,
                                 infra: InfraRecon, side: OSINTSideChannel) -> PersonalizationTokens:
    full_name = None
    gravatar = footprint.gravatar or {}
    if gravatar.get("display_name"):
        full_name = gravatar["display_name"]
    if not full_name:
        for p in sorted(footprint.profiles_found, key=lambda x: -x.confidence):
            if p.full_name:
                full_name = p.full_name
                break

    tokens = PersonalizationTokens(
        full_name=full_name,
        first_name=None,
        last_name=None,
        username_handle=lead.primary_handle,
        name_confidence=0.9 if full_name else (0.5 if lead.name_tokens else 0.0),
    )
    if full_name:
        parts = full_name.split()
        tokens.first_name, tokens.last_name = parts[0], parts[-1]
    elif lead.name_tokens:
        tokens.first_name = lead.name_tokens[0].capitalize()
        if len(lead.name_tokens) > 1:
            tokens.last_name = lead.name_tokens[-1].capitalize()

    for p in sorted(footprint.profiles_found, key=lambda x: -x.confidence):
        tokens.avatar_url = tokens.avatar_url or p.avatar_url
        tokens.bio_excerpt = tokens.bio_excerpt or (p.bio[:280] if p.bio else None)
        tokens.location = tokens.location or p.location
    if gravatar:
        tokens.avatar_url = tokens.avatar_url or gravatar.get("avatar_url")
        tokens.bio_excerpt = tokens.bio_excerpt or ((gravatar.get("about_me") or "")[:280] or None)
        tokens.location = tokens.location or (gravatar.get("location") or None) or None

    blob = " ".join(filter(None, [tokens.bio_excerpt, tokens.full_name or ""])).lower()
    tokens.interests = sorted({label for needle, label in _INTEREST_KEYWORDS.items() if needle in blob})

    tokens.icebreakers = _build_icebreakers(tokens, footprint, infra, side)
    tokens.security_posture = _security_posture(infra)
    tokens.likely_stack = infra.tech_hints[:8]
    return tokens


def _security_posture(infra: InfraRecon) -> str:
    score = 0
    if infra.mail_auth.spf.present:
        score += 1
    if infra.mail_auth.spf.all_qualifier == "-":
        score += 1
    if infra.mail_auth.dkim:
        score += 1
    if infra.mail_auth.dmarc.present and infra.mail_auth.dmarc.policy in ("quarantine", "reject"):
        score += 2
    return {0: "weak", 1: "weak", 2: "standard", 3: "standard", 4: "strong", 5: "strong"}[score]


def _build_icebreakers(tokens, footprint, infra, side) -> list[str]:
    out: list[str] = []
    name = tokens.first_name or "there"
    if tokens.interests:
        out.append(f"Noticed your interest in {tokens.interests[0]} — quick question, {name}.")
    github = next((p for p in footprint.profiles_found if p.platform == "GitHub"), None)
    if github:
        out.append(f"Found your GitHub — love what you're building, {name}.")
    staging = [s for s in infra.subdomains if s.environment_hint in ("staging", "development")]
    if staging:
        out.append("Noticed your staging environment is publicly resolvable — happy to share how we lock that down.")
    if infra.mail_auth.dmarc.present and infra.mail_auth.dmarc.policy == "none":
        out.append("Quick win: your DMARC is monitor-only; enforcing it takes 10 minutes.")
    if tokens.location:
        out.append(f"How's the weather in {tokens.location}? Reaching out from the Slidein team.")
    return out[:5]


def _from_gravatar_account(acct: dict):
    from ..schemas import SocialProfile

    return SocialProfile(
        platform=f"gravatar:{acct['platform']}",
        url=acct["url"],
        exists=True,
        confidence=0.9,
        username=acct.get("username"),
    )


def _empty_mail_auth():
    from ..schemas import MailAuth

    return MailAuth()
