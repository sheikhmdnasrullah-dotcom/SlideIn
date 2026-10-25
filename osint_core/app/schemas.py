"""Unified, database-ready dossier schema.

Every enrichment run produces exactly one UnifiedDossier with three top-level
sections (mirroring the product spec):

  individual_social_footprint      -> what we learned about the PERSON
  corporate_infrastructure_recon   -> what we learned about the COMPANY/domain
  personalization_tokens           -> derived, LLM-ready copywriting inputs
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

from .events.models import ModuleName, ModuleStatus


# --------------------------------------------------------------------------- #
# Social footprint
# --------------------------------------------------------------------------- #
class SocialProfile(BaseModel):
    platform: str
    url: str
    exists: bool = True
    confidence: float = 0.5            # 0..1 heuristic
    username: str | None = None
    user_id: str | None = None         # internal numeric/UUID account id
    full_name: str | None = None
    avatar_url: str | None = None
    bio: str | None = None
    location: str | None = None
    raw: dict = Field(default_factory=dict)


class SocialFootprint(BaseModel):
    username_handle: str
    platforms_checked: int = 0
    profiles_found: list[SocialProfile] = Field(default_factory=list)
    name_tokens: list[str] = Field(default_factory=list)
    gravatar: dict | None = None       # email-keyed gravatar profile (if any)


# --------------------------------------------------------------------------- #
# Corporate infrastructure recon
# --------------------------------------------------------------------------- #
class DNSRecords(BaseModel):
    a: list[str] = Field(default_factory=list)
    aaaa: list[str] = Field(default_factory=list)
    mx: list[str] = Field(default_factory=list)
    txt: list[str] = Field(default_factory=list)
    ns: list[str] = Field(default_factory=list)
    soa: str | None = None


class SPFRecord(BaseModel):
    present: bool = False
    record: str | None = None
    all_qualifier: str | None = None   # '-', '~', '?', '+'
    includes: list[str] = Field(default_factory=list)
    mechanisms: list[str] = Field(default_factory=list)


class DKIMRecord(BaseModel):
    selector: str
    record: str
    key_type: str | None = None        # rsa / ed25519
    service_type: str | None = None    # t= tag, e.g. * vs email


class DMARCRecord(BaseModel):
    present: bool = False
    record: str | None = None
    policy: str | None = None          # p=
    subdomain_policy: str | None = None  # sp=
    alignment_dkim: str | None = None  # adkim=
    alignment_spf: str | None = None   # aspf=
    aggregate_uris: list[str] = Field(default_factory=list)   # rua
    forensic_uris: list[str] = Field(default_factory=list)    # ruf


class MailAuth(BaseModel):
    spf: SPFRecord = Field(default_factory=SPFRecord)
    dkim: list[DKIMRecord] = Field(default_factory=list)
    dmarc: DMARCRecord = Field(default_factory=DMARCRecord)


class Subdomain(BaseModel):
    host: str
    a: list[str] = Field(default_factory=list)
    aaaa: list[str] = Field(default_factory=list)
    environment_hint: str | None = None   # staging/dev/admin/api...


class InfraRecon(BaseModel):
    domain: str
    dns: DNSRecords = Field(default_factory=DNSRecords)
    mail_auth: MailAuth = Field(default_factory=MailAuth)
    subdomains: list[Subdomain] = Field(default_factory=list)
    subdomain_sources: list[str] = Field(default_factory=list)
    deliverability_risks: list[str] = Field(default_factory=list)
    tech_hints: list[str] = Field(default_factory=list)   # CDNs, SaaS fingerprints from MX/CNAME/TXT
    contact_emails: list[str] = Field(default_factory=list)  # from website contact scraping
    social_links: list[str] = Field(default_factory=list)     # corporate social URLs


# --------------------------------------------------------------------------- #
# OSINT recon side-channel
# --------------------------------------------------------------------------- #
class BreachExposure(BaseModel):
    breach_count: int = 0
    breaches: list[str] = Field(default_factory=list)   # breach names
    data_classes: list[str] = Field(default_factory=list)
    source: str = "hibp"


class FilingHit(BaseModel):
    accession: str
    form_type: str | None = None
    filing_date: str | None = None
    snippet: str | None = None
    url: str | None = None


class OSINTSideChannel(BaseModel):
    breach_exposure: BreachExposure = Field(default_factory=BreachExposure)
    crypto_addresses: list[str] = Field(default_factory=list)
    filings: list[FilingHit] = Field(default_factory=list)
    darkweb_mentions: list[dict] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Personalization tokens (LLM-ready)
# --------------------------------------------------------------------------- #
class PersonalizationTokens(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    full_name: str | None = None
    username_handle: str | None = None
    avatar_url: str | None = None
    bio_excerpt: str | None = None
    location: str | None = None
    interests: list[str] = Field(default_factory=list)
    icebreakers: list[str] = Field(default_factory=list)   # pre-built openers
    security_posture: str | None = None                    # weak/standard/strong
    likely_stack: list[str] = Field(default_factory=list)  # from infra fingerprints
    name_confidence: float = 0.0


# --------------------------------------------------------------------------- #
# Unified dossier
# --------------------------------------------------------------------------- #
class UnifiedDossier(BaseModel):
    lead_email: str
    domain: str
    username_handle: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    enrichment_duration_ms: int = 0
    individual_social_footprint: SocialFootprint
    corporate_infrastructure_recon: InfraRecon
    personalization_tokens: PersonalizationTokens
    osint_side_channel: OSINTSideChannel = Field(default_factory=OSINTSideChannel)
    errors: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Expansion layer: company intelligence, agents, graph, module results
# --------------------------------------------------------------------------- #
class CompanyIntelligence(BaseModel):
    name: str | None = None
    domain: str
    industry: str | None = None
    size_band: str | int | None = None
    funding_stage: str | None = None
    total_funding: str | None = None
    leadership: list[dict] = Field(default_factory=list)
    tech_stack: list[str] = Field(default_factory=list)
    confidence: float = 0.0


class EmailDraft(BaseModel):
    subject_lines: list[str] = Field(default_factory=list)
    body: str = ""
    personalization_hooks: list[str] = Field(default_factory=list)
    verified_signals_used: list[str] = Field(default_factory=list)
    compliance: dict = Field(default_factory=dict)
    llm_generated: bool = False


class ModuleResult(BaseModel):
    name: ModuleName
    status: ModuleStatus
    duration_ms: int = 0
    stats: dict = Field(default_factory=dict)
    error: str | None = None


class GraphNode(BaseModel):
    id: str
    type: str                     # person | handle | email | domain | company |
                                  # mx | profile | subdomain | filing | address
    label: str
    attributes: dict = Field(default_factory=dict)


class GraphEdge(BaseModel):
    source: str
    target: str
    relation: str                 # uses | has_profile | resolves_to | hosts |
                                  # mails_via | filed | exposed_in | registered_on


class EntityGraph(BaseModel):
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)


class EnrichmentResult(BaseModel):
    """Final database-ready payload: everything the OSINT layer, the expansion
    integrations, the entity graph, and the agent cluster produced."""
    task_id: str
    job_id: str | None = None
    lead_email: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    duration_ms: int = 0
    dossier: UnifiedDossier
    modules: list[ModuleResult] = Field(default_factory=list)
    company_intel: CompanyIntelligence
    mailaccess: dict = Field(default_factory=dict)
    website: dict = Field(default_factory=dict)      # WebsiteScraper slots
    fireenrich: dict = Field(default_factory=dict)   # company/funding/tech vectors
    blackbird: dict = Field(default_factory=dict)
    noimosiny: dict = Field(default_factory=dict)
    bomkesh: dict = Field(default_factory=dict)
    graph: EntityGraph = Field(default_factory=EntityGraph)
    agents: dict = Field(default_factory=dict)   # investigator/researcher/copywriter
