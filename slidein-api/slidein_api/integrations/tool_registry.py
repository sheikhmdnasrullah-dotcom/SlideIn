"""Canonical tool catalog and side-effect-free capability coverage planning.

A package is not a runnable research tool.  This registry contains tools and
providers with a product responsibility; frontend/build libraries remain in the
technology inventory.  ``build_coverage_plan`` considers every registered tool
for the requested stage and explains every skip.  It never executes a tool.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class ToolContext:
    domain: str = ""
    email: str = ""
    name: str = ""
    username: str = ""
    allow_active: bool = False

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> "ToolContext":
        return cls(
            domain=str(payload.get("domain") or "").strip(),
            email=str(payload.get("email") or "").strip(),
            name=str(payload.get("name") or "").strip(),
            username=str(payload.get("username") or "").strip(),
            allow_active=payload.get("allow_active") is True,
        )

    def has_target(self, target: str) -> bool:
        return bool(getattr(self, target))


@dataclass(frozen=True)
class ToolSpec:
    id: str
    name: str
    stage: str
    capabilities: tuple[str, ...]
    priority: int
    description: str
    runtime: str = "external_adapter"
    readiness: str = "unwired"
    required_env: tuple[str, ...] = ()
    command: str = ""
    command_env: str = ""
    package: str = ""
    targets: tuple[str, ...] = ()
    active: bool = False
    active_capabilities: tuple[str, ...] = ()
    wired: bool = False
    version: str = ""
    revision: str = ""

    def public(self, environ: Mapping[str, str] | None = None) -> dict:
        available, reason, missing = self.availability(environ)
        return {
            "id": self.id,
            "name": self.name,
            "stage": self.stage,
            "capabilities": list(self.capabilities),
            "priority": self.priority,
            "description": self.description,
            "runtime": self.runtime,
            "wired": self.wired,
            "availability": available,
            "reason": reason,
            "missing": missing,
            "required_env": list(self.required_env),
            "active": self.active,
            "active_capabilities": list(self.active_capabilities),
            "version": self.version,
            "revision": self.revision,
        }

    def availability(self, environ: Mapping[str, str] | None = None) -> tuple[str, str, list[str]]:
        env = os.environ if environ is None else environ
        if self.readiness == "candidate":
            return "unavailable", "candidate_not_installed", []
        if not self.wired:
            return "unavailable", "adapter_not_wired", []
        missing = [name for name in self.required_env if not env.get(name)]
        if missing:
            return "unavailable", "missing_configuration", missing
        if self.readiness == "command":
            command = env.get(self.command_env, "") if self.command_env else self.command
            command = command or self.command
            if not command or not shutil.which(command):
                return "unavailable", "missing_executable", [command or self.command_env]
        if self.readiness == "package" and importlib.util.find_spec(self.package) is None:
            return "unavailable", "missing_package", [self.package]
        if self.readiness == "path":
            path = Path(__file__).resolve().parents[2] / self.command
            if not path.exists():
                return "unavailable", "missing_installation", [self.command]
        return "ready", "", []


def _tool(id: str, name: str, stage: str, capabilities: tuple[str, ...], priority: int,
          description: str, **kwargs) -> ToolSpec:
    # Installed/configured is not equivalent to callable through the canonical API.
    kwargs.setdefault(
        "wired",
        id in {
            "website_connector", "website_lead_capture", "openosint", "ecc",
            "firecrawl", "maxmind_geoip2", "deterministic_personalization",
            "canonical_business_setup", "canonical_discovery",
            "canonical_inbound_webhook", "deterministic_conversation",
            "canonical_spam_preflight", "mx_preflight", "smtp_transport",
            "kumomta", "reacher",
        },
    )
    return ToolSpec(id, name, stage, capabilities, priority, description, **kwargs)


_TOOLS = (
    _tool("agent_reach", "Agent Reach", "research", ("web_search", "social_research"), 50,
          "Multi-backend research CLI; source content remains untrusted.", readiness="command", command="agent-reach", targets=("domain", "email", "name")),
    _tool("blackbird", "Blackbird", "research", ("username_enumeration",), 70,
          "Optional username OSINT command adapter.", readiness="command", command="blackbird", targets=("username",), active=True),
    _tool("botasaurus_website_scraper", "Botasaurus Website Scraper", "research", ("website_fetch", "contact_extraction"), 60,
          "Optional website/contact command adapter in osint_core.", readiness="command", command="website-email-contact-scraper", targets=("domain",)),
    _tool("brightdata", "Bright Data", "research", ("company_enrichment",), 80,
          "Key-gated company dataset provider.", readiness="env", required_env=("BRIGHTDATA_API_KEY",), targets=("domain", "name")),
    _tool("browser_use", "browser-use", "research", ("website_fetch", "browser_research"), 50,
          "Legacy browser agent fallback; canonical adapter not yet wired.", readiness="env", required_env=("OPENROUTER_API_KEY",), targets=("domain",)),
    _tool("crawl4ai", "Crawl4AI", "research", ("website_fetch", "browser_research"), 40,
          "Internal crawler service adapter.", readiness="env", required_env=("CRAWLER_SERVICE_URL",), targets=("domain",)),
    _tool("dig", "dig", "outreach", ("dns_email_authentication", "dns_blocklist"), 20,
          "DNS command used by the deliverability tooling.", readiness="command", command="dig", targets=("domain",)),
    _tool("dnspython", "dnspython", "outreach", ("dns_email_authentication", "dns_blocklist"), 10,
          "Python DNS resolver used by OSINT and deliverability checks.", readiness="package", package="dns", targets=("domain",)),
    _tool("ecc", "ECC", "engineering", ("engineering_research", "engineering_review"), 10,
          "Project-local agent engineering toolkit, not a prospect runtime tool.", runtime="project_local", readiness="path", command="external/ECC/README.md", version="2.2.3", revision="f3904009440af24f00617343910ee89714df8be3"),
    _tool("firecrawl", "Firecrawl / Fire Enrich", "research", ("website_fetch", "company_enrichment"), 30,
          "Firecrawl scrape/extract adapter with structured evidence output.", readiness="env", required_env=("FIRECRAWL_API_KEY",), targets=("domain",)),
    _tool("github_cli", "GitHub CLI", "research", ("code_footprint", "web_search"), 40,
          "GitHub repository/profile search through the gh CLI.", readiness="command", command="gh", targets=("name", "username")),
    _tool("gophish", "GoPhish", "outreach", ("campaign_execution",), 30,
          "Existing campaign service; live effects require separate authorization.", readiness="env", required_env=("GOPHISH_URL", "GOPHISH_API_KEY"), active=True),
    _tool("happydeliver", "happyDeliver", "outreach", ("deliverability_analysis", "dns_email_authentication"), 30,
          "Deliverability analyzer behind an adapter; license review remains explicit.", readiness="env", required_env=("HAPPYDELIVER_URL",), targets=("domain",)),
    _tool("holehe", "Holehe", "research", ("account_enumeration",), 70,
          "Active account-enumeration command; disabled without per-run authorization.", readiness="command", command="holehe", targets=("email",), active=True),
    _tool("imapflow", "ImapFlow", "outreach", ("inbound_email",), 30,
          "Legacy IMAP ingestion library; canonical connector remains separate.", readiness="env", required_env=("IMAP_HOST",), active=True),
    _tool("jina_reader", "Jina Reader", "research", ("website_fetch", "web_search"), 20,
          "Reader/search proxy used by the legacy Agent Reach adapter.", readiness="unwired", targets=("domain", "name")),
    _tool("kumomta", "KumoMTA", "outreach", ("mail_transport",), 10,
          "Canonical SMTP submission adapter plus existing MTA/Lua policy; live use requires authorization.", runtime="canonical", readiness="env", required_env=("KUMO_AUTH_PASS",), active=True),
    _tool("maigret", "Maigret", "research", ("username_enumeration",), 60,
          "Optional username registry/command adapter.", readiness="command", command="maigret", targets=("username",), active=True),
    _tool("nodemailer", "Nodemailer", "outreach", ("mail_transport",), 30,
          "Legacy Node mail transport library.", readiness="unwired", active=True),
    _tool("openosint", "OpenOSINT", "research", ("dns_research", "exposure_research", "code_footprint", "account_enumeration", "username_enumeration"), 10,
          "Canonical passive CLI bridge for DNS, exposure and GitHub; active lookups are gated.", readiness="command", command="openosint", command_env="OPENOSINT_CLI", targets=("domain", "email", "name", "username"), active_capabilities=("account_enumeration", "username_enumeration")),
    _tool("playwright", "Playwright", "research", ("website_fetch", "browser_research"), 60,
          "Local browser fallback through the legacy crawler service.", readiness="env", required_env=("CRAWLER_SERVICE_URL",), targets=("domain",)),
    _tool("reacher", "Reacher", "outreach", ("email_verification",), 10,
          "Email verification service; verification does not imply consent.", readiness="env", required_env=("REACHER_URL",), targets=("email",)),
    _tool("rspamd", "rspamd", "outreach", ("deliverability_analysis",), 20,
          "Spam/content analysis command used by deliverability checks.", readiness="command", command="rspamc"),
    _tool("spamassassin", "SpamAssassin", "outreach", ("deliverability_analysis",), 40,
          "Spam/content analysis command used by happyDeliver and local checks.", readiness="command", command="spamassassin"),
    _tool("spider", "Spider", "research", ("website_fetch", "web_search", "browser_research"), 70,
          "Official Spider package; canonical research adapter remains unwired.", readiness="package", package="spider_rs", targets=("domain", "name")),
    _tool("stagehand", "Stagehand / Browserbase", "research", ("website_fetch", "browser_research"), 50,
          "Legacy preferred browser agent; canonical adapter not yet wired.", readiness="env", required_env=("BROWSERBASE_API_KEY",), targets=("domain",)),
    _tool("steel", "Steel", "research", ("website_fetch", "browser_research"), 55,
          "Managed Chromium fallback through the legacy browser service.", readiness="env", required_env=("STEEL_API_KEY",), targets=("domain",)),
    _tool("subfinder", "Subfinder", "research", ("subdomain_discovery",), 20,
          "Passive subdomain command with crt.sh/BufferOver/HackerTarget fallbacks in osint_core.", readiness="command", command="subfinder", targets=("domain",)),
    _tool("tavily", "Tavily", "research", ("web_search",), 10,
          "Basic and advanced web search provider used by legacy lead research.", readiness="env", required_env=("TAVILY_API_KEY",), targets=("domain", "email", "name")),
    _tool("theharvester", "theHarvester", "research", ("contact_extraction", "subdomain_discovery"), 30,
          "Deployment assets exist; canonical service adapter is not yet wired.", readiness="command", command="theHarvester", targets=("domain",)),
    _tool("unspam", "Unspam.email", "outreach", ("deliverability_analysis",), 50,
          "Opt-in commercial spam/placement API; signals are not placement guarantees.", readiness="env", required_env=("UNSPAM_API_KEY",)),
    _tool("website_connector", "Canonical Website Connector", "research", ("website_fetch", "company_enrichment"), 10,
          "Built-in public company-page fetch and source-backed claim extraction.", runtime="canonical", readiness="builtin", targets=("domain",)),
    _tool("deepseek", "DeepSeek", "personalize", ("grounded_drafting",), 20,
          "OpenAI-compatible drafting provider in the legacy LLM gateway.", readiness="env", required_env=("DEEPSEEK_API_KEY",)),
    _tool("litellm", "LiteLLM", "personalize", ("grounded_drafting",), 40,
          "OpenAI-compatible model gateway fallback.", readiness="env", required_env=("LITELLM_BASE_URL", "LITELLM_API_KEY")),
    _tool("nvidia", "NVIDIA NIM", "personalize", ("grounded_drafting", "embeddings_reranking"), 30,
          "Model, embedding and reranking provider.", readiness="env", required_env=("NVIDIA_API_KEY",)),
    _tool("openai", "OpenAI", "personalize", ("grounded_drafting",), 60,
          "Model provider; failures must not become mock drafts.", readiness="env", required_env=("OPENAI_API_KEY",)),
    _tool("openrouter", "OpenRouter", "personalize", ("grounded_drafting",), 50,
          "OpenAI-compatible model router fallback.", readiness="env", required_env=("OPENROUTER_API_KEY",)),
    _tool("seekai", "SeekAI", "personalize", ("grounded_drafting",), 10,
          "Configured OpenAI-compatible gateway.", readiness="env", required_env=("SEEKAI_BASE_URL", "SEEKAI_API_KEY")),
    _tool("docker", "Docker / Docker Compose", "operations", ("deployment_observation",), 10,
          "Existing isolated service deployment tooling.", readiness="command", command="docker"),
    _tool("grafana", "Grafana", "operations", ("infrastructure_observation",), 20,
          "Existing infrastructure visualization, not a new customer dashboard.", readiness="unwired"),
    _tool("prometheus", "Prometheus", "operations", ("infrastructure_observation",), 10,
          "Existing metrics and alert source.", readiness="unwired"),
    _tool("refine", "Refine", "engineering", ("admin_interface_evaluation",), 20,
          "Vendored for engineering evaluation only; the accepted no-Refine runtime ADR remains.", runtime="project_local", readiness="path", command="external/refine/README.md", revision="2352eb5b6539e2f39ad9aef652279ad1dcf2c467"),
    _tool("maxmind_geoip2", "MaxMind GeoIP2", "analytics", ("network_context",), 10,
          "Local MMDB network context only; never a person or confirmed employer.", runtime="canonical", readiness="env", required_env=("GEOIP_MMDB_PATH",), version="5.3.0"),
    _tool("logsnag", "LogSnag", "analytics", ("operational_event_notification",), 30,
          "Official JS SDK and legacy HTTPS bridge for non-personal operational events.", readiness="env", required_env=("LOGSNAG_TOKEN", "LOGSNAG_PROJECT"), version="1.0.0"),
    _tool("rudderstack", "RudderStack", "analytics", ("first_party_event_collection", "event_routing"), 20,
          "Official consent-gated browser SDK; rudder-server is ELv2 and requires deployment review.", readiness="env", required_env=("RUDDERSTACK_WRITE_KEY", "RUDDERSTACK_DATA_PLANE_URL"), version="3.35.1"),
    _tool("snowplow", "Snowplow Analytics", "analytics", ("first_party_event_collection",), 10,
          "Official consent-gated browser SDK; collector/pipeline deployment is separate.", readiness="env", required_env=("SNOWPLOW_COLLECTOR_URL", "SNOWPLOW_APP_ID"), version="4.10.2"),
    _tool("website_lead_capture", "Consented Website Lead Capture", "analytics", ("consented_lead_capture", "session_stitching"), 5,
          "Canonical snippet and Prospect handoff; email comes only from explicit form identification.", runtime="canonical", readiness="builtin"),
    _tool("canonical_business_setup", "Canonical Business Setup", "configure", ("business_knowledge", "icp_configuration"), 5,
          "Versioned profile, offer, ICP and policy configuration.", runtime="canonical", readiness="builtin"),
    _tool("canonical_discovery", "Canonical Prospect Discovery", "discover", ("prospect_ingest", "source_attribution"), 5,
          "Deduplicated record and consented website intake with provenance.", runtime="canonical", readiness="builtin"),
    _tool("deterministic_personalization", "Evidence-backed Personalization", "personalize", ("grounded_drafting",), 5,
          "Canonical versioned drafting from approved offers and attributed evidence.", runtime="canonical", readiness="builtin"),
    _tool("anthropic", "Anthropic / Claude", "personalize", ("grounded_drafting",), 55,
          "Installed legacy model SDK; no canonical drafting adapter.", readiness="env", required_env=("ANTHROPIC_API_KEY",)),
    _tool("smtp_transport", "Canonical SMTP Transport", "outreach", ("mail_transport",), 20,
          "Canonical SMTP dispatch behind approval and deliverability gates.", runtime="canonical", readiness="env", required_env=("SLIDEIN_SMTP_HOST",), active=True),
    _tool("deliverability_daemon", "Deliverability Outreach Daemon", "outreach", ("sender_rotation", "human_pacing", "campaign_execution"), 40,
          "Legacy mailbox rotation and paced dispatch; not tenant-scoped canonical execution.", readiness="path", command="deliverability/background_outreach_daemon.py", active=True),
    _tool("deliverability_warmup", "Deliverability Warmup Tracker", "outreach", ("volume_ramp", "mailbox_warmup"), 10,
          "SQLite daily-volume and domain-ramp policy from the deliverability stack.", readiness="path", command="deliverability/core/warmup.py"),
    _tool("warmup_engine", "Mailbox Warmup Engine", "outreach", ("mailbox_warmup", "inbound_email"), 20,
          "Node BullMQ/Redis/Nodemailer/ImapFlow warmup workers; canonical adapter not wired.", readiness="path", command="warmup-engine/package.json", active=True, version="1.0.0"),
    _tool("optimization_warmup", "Optimization Warmup Engine", "outreach", ("mailbox_warmup", "volume_ramp"), 30,
          "Legacy staged warmup and placement feedback scheduler; not tenant-scoped.", readiness="path", command="optimization-engine/warmup_engine.py", active=True),
    _tool("warmbly", "Warmbly", "outreach", ("mailbox_warmup", "mailbox_management", "inbound_email"), 5,
          "Installed self-hosted warmup platform; canonical adapter wired (services/warmup.py + integrations/warmbly.py) and gates live sends with the 14-day warmup rule.", readiness="env", required_env=("WARMBLY_URL",), active=True),
    _tool("canonical_spam_preflight", "Canonical Spam Preflight", "outreach", ("deliverability_analysis",), 5,
          "Canonical copy audit; hard gate for live transport.", runtime="canonical", readiness="builtin"),
    _tool("mx_preflight", "Canonical MX Preflight", "outreach", ("mx_verification",), 10,
          "Canonical recipient MX check recorded as advisory evidence.", runtime="canonical", readiness="builtin", targets=("domain",)),
    _tool("canonical_inbound_webhook", "Canonical Inbound Webhook", "converse", ("inbound_email",), 5,
          "Tenant-scoped reply ingestion; production mailbox/provider feed remains separate.", runtime="canonical", readiness="builtin", targets=("email",)),
    _tool("deterministic_conversation", "Conversation Intent and Handoff", "converse", ("reply_classification", "owner_handoff"), 10,
          "Deterministic reply intent, suppression and owner/booking routing.", runtime="canonical", readiness="builtin", targets=("email",)),
)

TOOL_REGISTRY: tuple[ToolSpec, ...] = tuple(sorted(_TOOLS, key=lambda tool: tool.id))


def _candidate_row(tool: ToolSpec, context: ToolContext, capabilities: set[str],
                   environ: Mapping[str, str]) -> dict:
    relevant = set(tool.capabilities) & capabilities
    base = {
        "tool_id": tool.id,
        "capabilities": [cap for cap in tool.capabilities if cap in relevant],
        "priority": tool.priority,
        "status": "skipped",
        "reason": "",
        "missing": [],
        "fallbacks": [],
    }
    if not relevant:
        return {**base, "reason": "capability_not_requested"}
    if not context.allow_active:
        blocked = relevant & set(tool.active_capabilities)
        relevant -= blocked
        if tool.active or (blocked and not relevant):
            return {**base, "reason": "active_research_not_authorized"}
        base["capabilities"] = [cap for cap in tool.capabilities if cap in relevant]
    if tool.targets and not any(context.has_target(target) for target in tool.targets):
        return {**base, "reason": "missing_applicable_target"}
    availability, reason, missing = tool.availability(environ)
    if availability != "ready":
        return {**base, "reason": reason, "missing": missing}
    return {**base, "status": "ready", "reason": "eligible_not_executed"}


def fallback_chain(capability: str, *, context: ToolContext,
                   environ: Mapping[str, str] | None = None) -> list[str]:
    """Return eligible tools for one capability in deterministic priority order."""
    env = os.environ if environ is None else environ
    candidates = [tool for tool in TOOL_REGISTRY if capability in tool.capabilities]
    ready = []
    for tool in sorted(candidates, key=lambda item: (item.priority, item.id)):
        row = _candidate_row(tool, context, {capability}, env)
        if row["status"] == "ready":
            ready.append(tool.id)
    return ready


def build_coverage_plan(*, context: ToolContext, stage: str = "research",
                        capabilities: list[str] | None = None,
                        environ: Mapping[str, str] | None = None) -> dict:
    """Account for every tool in a stage without executing or fabricating success."""
    env = os.environ if environ is None else environ
    tools = [tool for tool in TOOL_REGISTRY if tool.stage == stage]
    available_capabilities = {cap for tool in tools for cap in tool.capabilities}
    requested = set(capabilities) if capabilities is not None else available_capabilities
    unknown = requested - available_capabilities
    if unknown:
        raise ValueError(f"Unknown capabilities for {stage}: {', '.join(sorted(unknown))}")

    ledger = []
    for tool in tools:
        row = _candidate_row(tool, context, requested, env)
        if row["status"] == "ready":
            fallbacks = (
                tool_id for capability in row["capabilities"]
                for tool_id in fallback_chain(capability, context=context, environ=env)
                if tool_id != tool.id
            )
            row["fallbacks"] = list(dict.fromkeys(fallbacks))
        ledger.append(row)

    return {
        "stage": stage,
        "requested_capabilities": sorted(requested),
        "ledger": ledger,
        "runnable_count": sum(row["status"] == "ready" for row in ledger),
        "skipped_count": sum(row["status"] == "skipped" for row in ledger),
        "complete_coverage": len(ledger) == len(tools),
        "executed": False,
        "mock_success": False,
    }


__all__ = [
    "TOOL_REGISTRY", "ToolContext", "ToolSpec", "build_coverage_plan", "fallback_chain",
]
